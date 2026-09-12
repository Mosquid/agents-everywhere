import asyncio
import json
import os
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault('CONTEXT_READ_TOKEN', 'r' * 40)
os.environ.setdefault('CONTEXT_ADMIN_TOKEN', 'a' * 40)
os.environ.setdefault('CALL_WRITE_TOKEN', 'w' * 40)
os.environ['FOLLOW_UP_WORKERS_ENABLED'] = '0'
from fastapi.testclient import TestClient
import app
import workers

ADMIN = {'Authorization': 'Bearer ' + app.ADMIN_TOKEN}
WRITER = {'Authorization': 'Bearer ' + app.CALL_TOKEN}
READ = {'Authorization': 'Bearer ' + app.READ_TOKEN}


class FollowUpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.recordings = Path(self.tmp.name) / 'recordings'
        self.patches = [patch.object(app, 'DB_PATH', self.tmp.name + '/db.sqlite3'),
                        patch.object(app, 'RECORDINGS_DIR', self.recordings)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.client = TestClient(app.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.call = self.client.post('/calls', headers=WRITER, json={
            'phone': '+12025550123', 'external_key': 'test', 'room': 'test-room',
            'job_id': str(uuid.uuid4())}).json()
        self.path = '/calls/' + self.call['id']

    def booking(self, hours=72):
        stamp = self.call['started_at'] + hours * 3600
        return {'scheduled_at': datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
                'timezone': 'UTC', 'reason': 'Follow up after family visit',
                'agreement': 'Yes, please call me at that time.'}

    def create(self, hours=72):
        r = self.client.post(self.path + '/follow-up', headers=WRITER, json=self.booking(hours))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def complete(self, transcript=None):
        directory = self.recordings / self.call['id']
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'completion.json').write_text('{"status":"completed"}')
        (directory / 'transcript.json').write_text(json.dumps(transcript if transcript is not None else [
            {'speaker': 'person', 'text': 'My daughter will visit on Sunday.'},
            {'speaker': 'agent', 'text': 'That sounds nice.'}]))

    def state(self, booking_id):
        with app.database() as db:
            return dict(db.execute('SELECT * FROM scheduled_calls WHERE id=?', (booking_id,)).fetchone())

    def tick(self, now, dial):
        with patch.object(workers.time, 'time', return_value=now), patch.object(workers, 'dial', dial):
            asyncio.run(workers.scheduler_once(app.database, self.recordings))

    def test_global_policy_boundaries_auth_and_persistence(self):
        self.assertEqual(self.client.get('/settings', headers=READ).json(), {'next_call_min_hours': 48, 'next_call_max_hours': 168})
        self.assertEqual(self.client.put('/settings', headers=READ, json={}).status_code, 403)
        for body in ({'next_call_min_hours': 0}, {'next_call_min_hours': 170, 'next_call_max_hours': 168}, {'next_call_min_hours': '48'}):
            self.assertEqual(self.client.put('/settings', headers=ADMIN, json=body).status_code, 422)
        for hours in (24, 47.999, 168.001):
            self.assertEqual(self.client.post(self.path + '/follow-up', headers=WRITER, json=self.booking(hours)).status_code, 422)
        for hours in (48, 168):
            self.create(hours)
        self.assertEqual(self.client.post(self.path + '/follow-up', headers=READ, json=self.booking()).status_code, 403)
        self.client.put('/settings', headers=ADMIN, json={'next_call_min_hours': 72, 'next_call_max_hours': 120})
        with app.database() as db:
            self.assertEqual(db.execute('SELECT next_call_min_hours FROM settings').fetchone()[0], 72)
            self.assertEqual(db.execute('SELECT status FROM scheduled_calls').fetchone()[0], 'needs_reschedule')
        with TestClient(app.app) as restarted:
            self.assertEqual(restarted.get('/settings', headers=READ).json()['next_call_max_hours'], 120)

    def test_timezone_offsets_and_single_pending_booking(self):
        for body in ({**self.booking(), 'scheduled_at': '2026-09-15T10:00:00'},
                     {**self.booking(), 'timezone': 'Invalid/Zone'},
                     {**self.booking(), 'timezone': 'Europe/Madrid'}):
            self.assertEqual(self.client.post(self.path + '/follow-up', headers=WRITER, json=body).status_code, 422)
        first = self.create()
        second = self.create(80)
        self.assertEqual(first['id'], second['id'])
        third = self.create(80)
        self.assertEqual(second['id'], third['id'])
        self.assertAlmostEqual(self.state(first['id'])['scheduled_at'], self.call['started_at'] + 80 * 3600, places=5)

    def test_opt_out_cancels_and_prevents_rebooking(self):
        booking = self.create()
        r = self.client.post(self.path + '/cancel-follow-up', headers=WRITER, json={'reason': 'Do not call again', 'stop_future_calls': True})
        self.assertFalse(r.json()['calling_allowed'])
        self.assertEqual(self.state(booking['id'])['status'], 'cancelled')
        self.assertEqual(self.client.post(self.path + '/follow-up', headers=WRITER, json=self.booking()).status_code, 409)
        route = '/people/' + self.call['person_id'] + '/calling-permission'
        self.assertEqual(self.client.put(route, headers=WRITER, json={'allowed': True}).status_code, 403)
        self.assertEqual(self.client.put(route, headers=ADMIN, json={'allowed': True}).status_code, 200)
        self.create()

    def test_no_phone_and_newer_conversation(self):
        booking = self.create()
        newer = self.client.post('/calls', headers=WRITER, json={
            'phone': '+12025550123', 'external_key': 'test', 'room': 'new', 'job_id': 'new-job'}).json()
        self.assertEqual(newer['person_id'], self.call['person_id'])
        self.assertEqual(self.state(booking['id'])['status'], 'superseded')
        self.assertEqual(self.client.post(self.path + '/follow-up', headers=WRITER, json=self.booking()).status_code, 409)
        rtc = self.client.post('/calls', headers=WRITER, json={'external_key': 'rtc:browser', 'room': 'browser', 'job_id': 'browser'}).json()
        self.assertEqual(self.client.post('/calls/' + rtc['id'] + '/follow-up', headers=WRITER, json=self.booking()).status_code, 409)

    def test_due_call_runs_once_after_completion(self):
        booking = self.create()
        dial = AsyncMock()
        self.tick(booking['scheduled_at'] - 1, dial)
        dial.assert_not_awaited()
        self.tick(booking['scheduled_at'], dial)
        dial.assert_not_awaited()
        self.complete()
        self.tick(booking['scheduled_at'], dial)
        self.tick(booking['scheduled_at'] + 1, dial)
        dial.assert_awaited_once()
        self.assertEqual(dial.call_args.args[0]['person_id'], self.call['person_id'])
        self.assertEqual(self.state(booking['id'])['status'], 'answered')

    def test_uncertain_dial_is_never_automatically_retried(self):
        self.complete()
        booking = self.create()
        dial = AsyncMock(side_effect=TimeoutError())
        self.tick(booking['scheduled_at'], dial)
        self.tick(booking['scheduled_at'] + 1, dial)
        dial.assert_awaited_once()
        self.assertEqual(self.state(booking['id'])['status'], 'unknown')

    def test_missed_time_and_phone_change_do_not_dial(self):
        self.complete()
        booking = self.create()
        dial = AsyncMock()
        self.tick(booking['scheduled_at'] + 901, dial)
        self.assertEqual(self.state(booking['id'])['status'], 'missed')
        booking = self.create(80)
        with app.database() as db:
            db.execute('UPDATE people SET phone=? WHERE id=?', ('+12025550124', self.call['person_id']))
        self.tick(booking['scheduled_at'], dial)
        self.assertEqual(self.state(booking['id'])['status'], 'needs_reschedule')
        dial.assert_not_awaited()

    def test_crashed_dial_is_not_replayed(self):
        booking = self.create()
        with app.database() as db:
            db.execute("UPDATE scheduled_calls SET status='dialing',updated_at=0 WHERE id=?", (booking['id'],))
        dial = AsyncMock()
        self.tick(booking['scheduled_at'], dial)
        self.assertEqual(self.state(booking['id'])['status'], 'unknown')
        dial.assert_not_awaited()

    def test_unfinished_source_does_not_block_other_people(self):
        waiting = self.create()
        self.call = self.client.post('/calls', headers=WRITER, json={
            'phone': '+12025550124', 'external_key': 'second', 'room': 'second', 'job_id': 'second'}).json()
        self.path = '/calls/' + self.call['id']
        ready = self.create()
        self.complete()
        dial = AsyncMock()
        self.tick(ready['scheduled_at'], dial)
        dial.assert_awaited_once()
        self.assertEqual(self.state(ready['id'])['status'], 'answered')
        self.assertEqual(self.state(waiting['id'])['status'], 'scheduled')

    def test_summary_waits_for_final_transcript_and_is_persisted(self):
        result = {'summary': 'The person discussed a planned family visit.', 'topics': ['family'],
                  'new_facts': ['The person said their daughter plans to visit Sunday.'], 'follow_up_topics': ['Ask about the visit.']}
        with patch.object(workers, 'summarize', AsyncMock(return_value=result)) as model:
            asyncio.run(workers.summary_once(app.database, self.recordings))
            model.assert_not_awaited()
            self.complete()
            asyncio.run(workers.summary_once(app.database, self.recordings))
            asyncio.run(workers.summary_once(app.database, self.recordings))
            model.assert_awaited_once()
        r = self.client.get(self.path + '/summary', headers=ADMIN)
        self.assertEqual(r.json()['data'], result)
        self.assertEqual(r.json()['status'], 'ready')
        self.assertEqual(r.json()['person_id'], self.call['person_id'])
        self.assertEqual(r.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.client.get(self.path + '/summary', headers=READ).status_code, 403)
        with TestClient(app.app) as restarted:
            self.assertEqual(restarted.get(self.path + '/summary', headers=ADMIN).json()['data'], result)

    def test_summary_retry_empty_transcript_and_lease_recovery(self):
        self.complete()
        with patch.object(workers, 'summarize', AsyncMock(side_effect=RuntimeError())) as model:
            for _ in range(3):
                with app.database() as db:
                    db.execute('UPDATE call_summaries SET next_attempt_at=0')
                asyncio.run(workers.summary_once(app.database, self.recordings))
            asyncio.run(workers.summary_once(app.database, self.recordings))
            self.assertEqual(model.await_count, 3)
        self.assertEqual(self.client.get(self.path + '/summary', headers=ADMIN).json()['status'], 'failed')
        self.assertEqual(self.client.post(self.path + '/summary/retry', headers=ADMIN).status_code, 200)
        with app.database() as db:
            db.execute("UPDATE call_summaries SET status='processing',lease_until=0,attempts=1")
        self.complete([])
        with patch.object(workers, 'summarize', AsyncMock()) as model:
            asyncio.run(workers.summary_once(app.database, self.recordings))
            model.assert_not_awaited()
        self.assertEqual(self.client.get(self.path + '/summary', headers=ADMIN).json()['status'], 'skipped')

    def test_agent_tools_are_scoped_and_report_api_rejection(self):
        import sys
        sys.path.insert(0, str(Path(__file__).parents[1]))
        import httpx
        import agent_tools
        assistant = agent_tools.HolaAgent('Shared prompt', self.call['id'])
        transport = httpx.ASGITransport(app=app.app)
        original_client = httpx.AsyncClient

        async def exercise():
            def client_factory(**kwargs):
                return original_client(transport=transport, **kwargs)
            with patch.object(agent_tools.httpx, 'AsyncClient', side_effect=client_factory), \
                 patch.dict(os.environ, {'CONTEXT_API_URL': 'http://test', 'CALL_WRITE_TOKEN': app.CALL_TOKEN}):
                options = await assistant.get_next_call_options()
                self.assertTrue(options['ok'])
                self.assertEqual(options['result']['next_call_min_hours'], 48)
                bad = await assistant.schedule_next_call(**self.booking(24))
                self.assertFalse(bad['ok'])
                good = await assistant.schedule_next_call(**self.booking(72))
                self.assertTrue(good['ok'])
                self.assertEqual(good['result']['source_call_id'], self.call['id'])
                self.assertIn('scheduled_local', good['result'])
                cancelled = await assistant.cancel_next_call(reason='Please stop calling', stop_future_calls=True)
                self.assertFalse(cancelled['result']['calling_allowed'])
        asyncio.run(exercise())
