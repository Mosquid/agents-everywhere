import importlib.util
import os
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

temporary = tempfile.TemporaryDirectory()
os.environ.update(DB_PATH=temporary.name+'/test.sqlite3', CONTEXT_READ_TOKEN='r'*40,
                  CONTEXT_ADMIN_TOKEN='a'*40, CALL_WRITE_TOKEN='w'*40,
                  RECORDINGS_DIR=temporary.name+'/recordings', CONTEXT_API_URL='http://context-api')
import app
READ = {'Authorization': 'Bearer '+'r'*40}
ADMIN = {'Authorization': 'Bearer '+'a'*40}
PHONE = '+12025550123'

class APITest(unittest.TestCase):
    def test_context_lifecycle_and_permissions(self):
        with TestClient(app.app) as client:
            self.assertEqual(client.post('/context', json={}).status_code, 401)
            self.assertEqual(client.put('/prompt', headers=READ, json={'system_prompt':'bad'}).status_code, 403)
            self.assertEqual(client.post('/context', headers={'Authorization':'Bearer wrong'}, json={}).status_code, 401)
            original = client.get('/prompt', headers=ADMIN).json()['system_prompt']
            self.assertEqual(client.post('/context', headers=READ, json={}).json(),
                             {'matched':False,'system_prompt':original,'initial_data':''})
            self.assertEqual(client.put('/recipients/not-a-phone', headers=ADMIN, json={}).status_code, 422)
            self.assertEqual(client.put('/prompt', headers=ADMIN, json={'system_prompt':''}).status_code, 422)
            self.assertEqual(client.put('/recipients/'+PHONE, headers=ADMIN, json={'initial_data':'Likes tea'}).status_code, 200)
            client.put('/prompt', headers=ADMIN, json={'system_prompt':'Global prompt'})
            response = client.post('/context', headers=READ, json={'phone':PHONE})
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertEqual(response.json(), {'matched':True,'system_prompt':'Global prompt','initial_data':'Likes tea'})
            client.put('/recipients/'+PHONE, headers=ADMIN, json={'initial_data':'Likes tea','system_prompt':'Personal prompt'})
            self.assertEqual(client.post('/context', headers=READ, json={'phone':'+12025550124'}).json()['initial_data'],'')
        with TestClient(app.app) as client:
            self.assertEqual(client.post('/context', headers=READ, json={'phone':PHONE}).json()['system_prompt'],'Personal prompt')
            self.assertEqual(client.delete('/recipients/'+PHONE, headers=READ).status_code,403)
            self.assertEqual(client.delete('/recipients/'+PHONE, headers=ADMIN).status_code,204)
            self.assertEqual(client.get('/recipients/'+PHONE, headers=ADMIN).status_code,404)
            self.assertFalse(client.post('/context', headers=READ, json={'phone':PHONE}).json()['matched'])

sys.path.insert(0, str(Path(__file__).parents[1]))
spec = importlib.util.spec_from_file_location('voice_agent', Path(__file__).parents[1]/'agent.py')
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)

class AgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_context_loaded_before_session(self):
        participant=MagicMock(kind=agent.rtc.ParticipantKind.PARTICIPANT_KIND_SIP,
                              attributes={'sip.phoneNumber':PHONE},identity='callee')
        ctx=MagicMock(wait_for_participant=AsyncMock(return_value=participant))
        response=MagicMock()
        response.json.return_value={'id':'test-call','system_prompt':'Personal prompt','initial_data':'Likes tea'}
        client=AsyncMock()
        client.post.return_value=response
        session=MagicMock(start=AsyncMock())
        ctx.job.id='job-test'
        ctx.room.name='room-test'
        with patch.object(agent.httpx,'AsyncClient') as factory, patch.object(agent,'GPTLiveModel'), patch.object(agent,'AgentSession',return_value=session), patch.object(agent,'CallRecording') as recorder:
            factory.return_value.__aenter__.return_value=client
            await agent.entrypoint(ctx)
            self.assertEqual(client.post.call_args.kwargs['json'],{'phone':PHONE})
            instructions=session.start.call_args.kwargs['agent'].instructions
            self.assertTrue(instructions.startswith('Personal prompt'))
            self.assertIn('Likes tea',instructions)
            self.assertEqual(session.start.call_args.kwargs['room_options'].participant_identity,'callee')
            recorder.assert_called_once_with(ctx,session,'test-call')
            self.assertTrue(session.start.call_args.kwargs['record']['audio'])

    async def test_api_failure_does_not_start_model(self):
        ctx=MagicMock(wait_for_participant=AsyncMock(return_value=MagicMock(attributes={},kind=0)))
        with patch.object(agent.httpx,'AsyncClient') as factory, patch.object(agent,'GPTLiveModel') as model:
            factory.return_value.__aenter__.return_value.post.side_effect=agent.httpx.ConnectError('unavailable')
            with self.assertRaises(agent.httpx.ConnectError):
                await agent.entrypoint(ctx)
            model.assert_not_called()

if __name__ == '__main__':
    unittest.main()

class CallAPITest(unittest.TestCase):
    def test_person_linkage_recordings_and_authorization(self):
        writer={'Authorization':'Bearer '+'w'*40}
        request={'phone':PHONE,'external_key':'ignored','room':'test-room','job_id':'job-1'}
        with TestClient(app.app) as client:
            self.assertEqual(client.post('/calls',headers=READ,json=request).status_code,403)
            first=client.post('/calls',headers=writer,json=request).json()
            self.assertEqual(client.post('/calls',headers=writer,json=request).json()['id'],first['id'])
            second=client.post('/calls',headers=writer,json={**request,'job_id':'job-2'}).json()
            self.assertEqual(first['person_id'],second['person_id'])
            self.assertNotEqual(first['id'],second['id'])
            third=client.post('/calls',headers=writer,json={**request,'phone':'+12025550124','job_id':'job-3'}).json()
            self.assertNotEqual(first['person_id'],third['person_id'])
            directory=app.RECORDINGS_DIR / first['id']
            directory.mkdir(parents=True)
            (directory/'audio.ogg').write_bytes(b'fake-audio')
            transcript=[{'speaker':'person','text':'Hello','timestamp':1},{'speaker':'agent','text':'Hi','timestamp':2}]
            (directory/'transcript.json').write_text(json.dumps(transcript))
            (directory/'completion.json').write_text(json.dumps({'status':'completed','ended_at':3}))
            self.assertEqual(client.get('/calls/'+first['id']+'/audio',headers=READ).status_code,403)
            self.assertEqual(client.get('/calls/'+first['id']+'/audio',headers=ADMIN).content,b'fake-audio')
            self.assertEqual(client.get('/calls/'+first['id']+'/transcript',headers=ADMIN).json(),transcript)
            calls=client.get('/people/'+first['person_id']+'/calls',headers=ADMIN).json()
            self.assertEqual(len(calls),2)
            self.assertEqual({c['status'] for c in calls},{'incomplete','completed'})
        with TestClient(app.app) as client:
            self.assertEqual(len(client.get('/people/'+first['person_id']+'/calls',headers=ADMIN).json()),2)

class RecordingTest(unittest.IsolatedAsyncioTestCase):
    async def test_incremental_and_final_transcript(self):
        from call_recording import CallRecording
        from livekit.agents import llm
        with tempfile.TemporaryDirectory() as tmp:
            ctx=MagicMock(session_directory=Path(tmp))
            session=MagicMock(aclose=AsyncMock())
            session.history.items=[llm.ChatMessage(role='user',content=['Hello']),llm.ChatMessage(role='assistant',content=['Hi'])]
            recording=CallRecording(ctx,session,'unit-recording')
            self.assertTrue((Path(tmp)/'audio.ogg').is_symlink())
            for item in session.history.items:
                recording.on_message(MagicMock(item=item))
            self.assertEqual(len((recording.path/'transcript.jsonl').read_text().splitlines()),2)
            (recording.path/'audio.ogg').write_bytes(b'fake audio')
            recording.on_close(MagicMock(error=RuntimeError('test error'),reason='error'))
            await recording.finish()
            await recording.finish()
            session.aclose.assert_awaited_once()
            self.assertEqual(json.loads((recording.path/'completion.json').read_text())['status'],'failed')
            self.assertEqual([r['speaker'] for r in json.loads((recording.path/'transcript.json').read_text())],['person','agent'])
