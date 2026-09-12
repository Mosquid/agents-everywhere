import os
import secrets
import sqlite3
import json
import time
import uuid
import asyncio
import contextlib

import follow_up
import health_sms
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

DB_PATH = os.environ.get('DB_PATH', '/data/context.sqlite3')
READ_TOKEN = os.environ['CONTEXT_READ_TOKEN']
ADMIN_TOKEN = os.environ['CONTEXT_ADMIN_TOKEN']
CALL_TOKEN = os.environ['CALL_WRITE_TOKEN']
RECORDINGS_DIR = Path(os.environ.get('RECORDINGS_DIR', '/recordings'))
if len(READ_TOKEN) < 32 or len(ADMIN_TOKEN) < 32 or READ_TOKEN == ADMIN_TOKEN:
    raise RuntimeError('Configure distinct tokens of at least 32 characters')
if len(CALL_TOKEN) < 32 or CALL_TOKEN in (READ_TOKEN, ADMIN_TOKEN):
    raise RuntimeError('Configure a distinct call writer token of at least 32 characters')
Phone = Annotated[str, Field(pattern=r'^\+[1-9][0-9]{6,14}$')]
Prompt = Annotated[str, Field(min_length=1, max_length=16000)]

@contextmanager
def database():
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA secure_delete=ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()

@asynccontextmanager
async def lifespan(app):
    os.umask(0o077)
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with database() as db:
        db.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK (id=1), system_prompt TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS recipients (phone TEXT PRIMARY KEY, initial_data TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS people (id TEXT PRIMARY KEY, phone TEXT, external_key TEXT UNIQUE)')
        # A shared test/household number is a contact route, not a unique person ID.
        phone_unique = any(index['unique'] and [column['name'] for column in db.execute('SELECT * FROM pragma_index_info(?)', (index['name'],))] == ['phone']
                           for index in db.execute('PRAGMA index_list(people)').fetchall())
        if phone_unique:
            db.execute('CREATE TABLE people_migrated (id TEXT PRIMARY KEY, phone TEXT, external_key TEXT UNIQUE)')
            db.execute('INSERT INTO people_migrated SELECT id, phone, external_key FROM people')
            db.execute('DROP TABLE people')
            db.execute('ALTER TABLE people_migrated RENAME TO people')
        db.execute('CREATE TABLE IF NOT EXISTS person_profiles (person_id TEXT PRIMARY KEY REFERENCES people(id), initial_data TEXT NOT NULL)')
        for table in ('recipients', 'person_profiles'):
            if 'system_prompt' in [row['name'] for row in db.execute('SELECT * FROM pragma_table_info(?)', (table,))]:
                db.execute(f'ALTER TABLE {table} DROP COLUMN system_prompt')
        db.execute('CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, person_id TEXT NOT NULL REFERENCES people(id), room TEXT NOT NULL, job_id TEXT UNIQUE NOT NULL, started_at REAL NOT NULL)')
        db.execute('INSERT OR IGNORE INTO settings (id,system_prompt) VALUES (1, ?)', (Path(__file__).with_name('default-prompt.txt').read_text().strip(),))
        follow_up.migrate(db)
        health_sms.migrate(db)
        db.execute('UPDATE settings SET system_prompt=? WHERE id=1 AND system_prompt=?',
                   (Path(__file__).with_name('default-prompt.txt').read_text().strip(), "You are a concise, friendly voice assistant for a conversation test. Reply in the user's language. Answer directly and keep replies short. No backend or tools are connected. Do not delegate or claim to take external actions. If asked for an action or information you cannot provide, briefly explain that limitation."))
    tasks = []
    if os.environ.get('FOLLOW_UP_WORKERS_ENABLED', '1') == '1':
        from workers import run_summaries, run_scheduler
        tasks = [asyncio.create_task(run_summaries(database, RECORDINGS_DIR)),
                 asyncio.create_task(run_scheduler(database, RECORDINGS_DIR))]
    if health_sms.enabled():
        tasks.append(asyncio.create_task(health_sms.run(database, RECORDINGS_DIR)))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

app = FastAPI(title='Call context API', lifespan=lifespan)
bearer = HTTPBearer()

def reader(auth: HTTPAuthorizationCredentials = Depends(bearer)):
    if not any(secrets.compare_digest(auth.credentials, token) for token in (READ_TOKEN, ADMIN_TOKEN)):
        raise HTTPException(401, 'Invalid token')

def admin(auth: HTTPAuthorizationCredentials = Depends(bearer)):
    if not secrets.compare_digest(auth.credentials, ADMIN_TOKEN):
        raise HTTPException(403, 'Admin token required')

def call_writer(auth: HTTPAuthorizationCredentials = Depends(bearer)):
    if not secrets.compare_digest(auth.credentials, CALL_TOKEN):
        raise HTTPException(403, 'Call writer token required')

class Lookup(BaseModel):
    phone: Phone | None = None
    person_id: UUID | None = None

class Recipient(BaseModel):
    model_config = ConfigDict(extra='forbid')
    initial_data: str = Field(default='', max_length=16000)

class PromptUpdate(BaseModel):
    system_prompt: Prompt

@app.get('/health')
def health():
    with database() as db:
        db.execute('SELECT system_prompt FROM settings WHERE id=1').fetchone()
    return {'status': 'ok'}

@app.post('/context', dependencies=[Depends(reader)])
def context(body: Lookup, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    with database() as db:
        row = None
        phone = body.phone
        if body.person_id:
            person = db.execute('SELECT phone FROM people WHERE id=?', (str(body.person_id),)).fetchone()
            if person is None:
                raise HTTPException(404, 'Person not found')
            phone = person['phone']
            row = db.execute('SELECT initial_data FROM person_profiles WHERE person_id=?', (str(body.person_id),)).fetchone()
        if row is None:
            row = db.execute('SELECT initial_data FROM recipients WHERE phone=?', (phone,)).fetchone()
        prompt = db.execute('SELECT system_prompt FROM settings WHERE id=1').fetchone()[0]
    return {'matched': row is not None, 'system_prompt': prompt,
            'initial_data': row['initial_data'] if row else ''}

@app.get('/prompt', dependencies=[Depends(admin)])
def get_prompt():
    with database() as db:
        return dict(db.execute('SELECT system_prompt FROM settings WHERE id=1').fetchone())

@app.put('/prompt', dependencies=[Depends(admin)])
def put_prompt(body: PromptUpdate):
    with database() as db:
        db.execute('UPDATE settings SET system_prompt=? WHERE id=1', (body.system_prompt,))
    return body

@app.put('/recipients/{phone}', dependencies=[Depends(admin)])
def put_recipient(phone: Phone, body: Recipient):
    with database() as db:
        db.execute('INSERT INTO recipients VALUES (?, ?) ON CONFLICT(phone) DO UPDATE SET initial_data=excluded.initial_data',
                   (phone, body.initial_data))
    return {'phone': phone, **body.model_dump()}

@app.get('/recipients/{phone}', dependencies=[Depends(admin)])
def get_recipient(phone: Phone, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    with database() as db:
        row = db.execute('SELECT * FROM recipients WHERE phone=?', (phone,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Recipient not found')
    return dict(row)

@app.delete('/recipients/{phone}', dependencies=[Depends(admin)], status_code=204)
def delete_recipient(phone: Phone):
    with database() as db:
        db.execute('DELETE FROM recipients WHERE phone=?', (phone,))
    return Response(status_code=204)

class CallStart(BaseModel):
    phone: Phone | None = None
    person_id: UUID | None = None
    external_key: str = Field(min_length=1, max_length=256)
    room: str = Field(min_length=1, max_length=256)
    job_id: str = Field(min_length=1, max_length=128)

@app.post('/calls', dependencies=[Depends(call_writer)])
def start_call(body: CallStart):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT * FROM calls WHERE job_id=?', (body.job_id,)).fetchone()
        if existing:
            return dict(existing)
        if body.person_id:
            person = db.execute('SELECT id, phone FROM people WHERE id=?', (str(body.person_id),)).fetchone()
            if person is None:
                raise HTTPException(404, 'Person not found')
            if body.phone != person['phone']:
                raise HTTPException(409, 'Selected person does not match call phone')
        else:
            matches = db.execute('SELECT id FROM people WHERE phone=?' if body.phone else 'SELECT id FROM people WHERE external_key=?',
                                 (body.phone or body.external_key,)).fetchall()
            if len(matches) > 1:
                raise HTTPException(409, 'Shared phone number: select person_id explicitly')
            person = matches[0] if matches else None
        person_id = person['id'] if person else str(uuid.uuid4())
        if not person:
            db.execute('INSERT INTO people VALUES (?, ?, ?)',
                       (person_id, body.phone, None if body.phone else body.external_key))
        call = {'id': str(uuid.uuid4()), 'person_id': person_id, 'room': body.room,
                'job_id': body.job_id, 'started_at': time.time()}
        db.execute('INSERT INTO calls VALUES (:id, :person_id, :room, :job_id, :started_at)', call)
        db.execute("INSERT INTO call_summaries (call_id,status) VALUES (?,'pending')", (call['id'],))
        health_sms.enroll(db, call)
        db.execute("UPDATE scheduled_calls SET status='superseded',updated_at=? WHERE person_id=? AND status='scheduled'",
                   (time.time(), person_id))
    return call


def call_details(row):
    result = dict(row)
    directory = RECORDINGS_DIR / result['id']
    result['status'] = 'incomplete'
    completion = directory / 'completion.json'
    if completion.exists():
        result.update(json.loads(completion.read_text()))
    result['audio_available'] = (directory / 'audio.ogg').exists()
    result['transcript_available'] = (directory / 'transcript.json').exists() or (directory / 'transcript.jsonl').exists()
    return result


def find_call(call_id):
    with database() as db:
        row = db.execute('SELECT * FROM calls WHERE id=?', (str(call_id),)).fetchone()
    if row is None:
        raise HTTPException(404, 'Call not found')
    return row


@app.get('/people/{person_id}/health-contact', dependencies=[Depends(admin)])
def get_health_contact(person_id: UUID, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    with database() as db:
        return health_sms.contact(db, str(person_id))


@app.put('/people/{person_id}/health-contact', dependencies=[Depends(admin)])
def put_health_contact(person_id: UUID, body: health_sms.HealthContact, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        return health_sms.save_contact(db, str(person_id), body)


@app.post('/calls/{call_id}/health-notification', dependencies=[Depends(call_writer)])
def request_health_notification(call_id: UUID, body: health_sms.NotificationRequest, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    call = find_call(call_id)
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        result = health_sms.enqueue(db, call, body.timing, 'agent_tool')
    return {'id': result['id'], 'status': result['status'], 'timing': result['timing'],
            'message': 'Queued is not sent. Submitted means accepted by Twilio, not delivered to the contact.'}


@app.post('/calls/{call_id}/health-notification/opt-out', dependencies=[Depends(call_writer)])
def opt_out_health_notification(call_id: UUID):
    call = find_call(call_id)
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        health_sms.revoke(db, call['person_id'])
    return {'enabled': False, 'message': 'Pending notifications cancelled. An SMS already submitted or in flight cannot be recalled.'}


@app.get('/calls/{call_id}/health-notification', dependencies=[Depends(admin)])
def get_health_notification(call_id: UUID, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    find_call(call_id)
    with database() as db:
        review = db.execute('SELECT * FROM health_reviews WHERE call_id=?', (str(call_id),)).fetchone()
        return {'notification': health_sms.notification(db, str(call_id)),
                'review': dict(review) if review else None}

@app.get('/people', dependencies=[Depends(admin)])
def list_people(response: Response):
    response.headers['Cache-Control'] = 'no-store'
    with database() as db:
        return [dict(row) for row in db.execute('SELECT people.*, person_profiles.initial_data FROM people LEFT JOIN person_profiles ON person_profiles.person_id=people.id ORDER BY people.id')]

class PersonProfile(Recipient):
    phone: Phone | None = None
    external_key: str = Field(min_length=1, max_length=256)

@app.put('/people/{person_id}', dependencies=[Depends(admin)])
def put_person(person_id: UUID, body: PersonProfile):
    try:
        with database() as db:
            db.execute('INSERT INTO people (id, phone, external_key) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET phone=excluded.phone, external_key=excluded.external_key',
                       (str(person_id), body.phone, body.external_key))
            db.execute('INSERT INTO person_profiles VALUES (?, ?) ON CONFLICT(person_id) DO UPDATE SET initial_data=excluded.initial_data',
                       (str(person_id), body.initial_data))
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'External key already belongs to another person')
    return {'id': str(person_id), **body.model_dump()}

@app.get('/people/{person_id}/calls', dependencies=[Depends(admin)])
def person_calls(person_id: UUID, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    with database() as db:
        rows = db.execute('SELECT * FROM calls WHERE person_id=? ORDER BY started_at DESC', (str(person_id),)).fetchall()
    return [call_details(row) for row in rows]

@app.get('/calls/{call_id}', dependencies=[Depends(admin)])
def get_call(call_id: UUID, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return call_details(find_call(call_id))

@app.get('/calls/{call_id}/audio', dependencies=[Depends(admin)])
def get_audio(call_id: UUID):
    find_call(call_id)
    path = RECORDINGS_DIR / str(call_id) / 'audio.ogg'
    if not path.exists():
        raise HTTPException(404, 'Audio not available')
    return FileResponse(path, media_type='audio/ogg', filename=f'{call_id}.ogg', headers={'Cache-Control':'no-store'})

@app.get('/calls/{call_id}/transcript', dependencies=[Depends(admin)])
def get_transcript(call_id: UUID, response: Response):
    find_call(call_id)
    response.headers['Cache-Control'] = 'no-store'
    directory = RECORDINGS_DIR / str(call_id)
    if (directory / 'transcript.json').exists():
        return json.loads((directory / 'transcript.json').read_text())
    journal = directory / 'transcript.jsonl'
    if not journal.exists():
        raise HTTPException(404, 'Transcript not available')
    rows = []
    for line in journal.read_text().splitlines(keepends=True):
        if line.endswith('\n'):
            rows.append(json.loads(line))
    return rows


@app.get('/settings', dependencies=[Depends(reader)])
def get_settings(response: Response):
    response.headers['Cache-Control'] = 'no-store'
    with database() as db:
        return follow_up.settings(db)

@app.put('/settings', dependencies=[Depends(admin)])
def put_settings(body: follow_up.SchedulingSettings):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE settings SET next_call_min_hours=?,next_call_max_hours=? WHERE id=1',
                   (body.next_call_min_hours, body.next_call_max_hours))
        db.execute("""UPDATE scheduled_calls SET status='needs_reschedule',error='Global window changed',updated_at=?
            WHERE status='scheduled' AND NOT scheduled_at BETWEEN
            ROUND((SELECT started_at FROM calls WHERE id=source_call_id)+?*3600,6) AND
            ROUND((SELECT started_at FROM calls WHERE id=source_call_id)+?*3600,6)""",
            (time.time(), body.next_call_min_hours, body.next_call_max_hours))
    return body

@app.get('/calls/{call_id}/follow-up', dependencies=[Depends(call_writer)])
def get_follow_up(call_id: UUID, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    call = find_call(call_id)
    with database() as db:
        return follow_up.info(db, call)

@app.post('/calls/{call_id}/follow-up', dependencies=[Depends(call_writer)])
def schedule_follow_up(call_id: UUID, body: follow_up.Booking):
    call = find_call(call_id)
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        return follow_up.book(db, call, body)

@app.post('/calls/{call_id}/cancel-follow-up', dependencies=[Depends(call_writer)])
def cancel_follow_up(call_id: UUID, body: follow_up.Cancellation):
    call = find_call(call_id)
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        return follow_up.cancel(db, call, body)

@app.get('/people/{person_id}/scheduled-calls', dependencies=[Depends(admin)])
def scheduled_calls(person_id: UUID, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    with database() as db:
        return [dict(r) for r in db.execute('SELECT * FROM scheduled_calls WHERE person_id=? ORDER BY scheduled_at DESC', (str(person_id),))]

@app.put('/people/{person_id}/calling-permission', dependencies=[Depends(admin)])
def set_calling_permission(person_id: UUID, body: follow_up.CallingPermission):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM people WHERE id=?', (str(person_id),)).fetchone():
            raise HTTPException(404, 'Person not found')
        db.execute('INSERT INTO calling_permissions VALUES (?,?) ON CONFLICT(person_id) DO UPDATE SET allowed=excluded.allowed',
                   (str(person_id), int(body.allowed)))
        if not body.allowed:
            db.execute("UPDATE scheduled_calls SET status='cancelled',updated_at=?,error='Calls disabled' WHERE person_id=? AND status='scheduled'",
                       (time.time(), str(person_id)))
    return body

@app.get('/calls/{call_id}/summary', dependencies=[Depends(admin)])
def get_summary(call_id: UUID, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    call = find_call(call_id)
    with database() as db:
        row = db.execute('SELECT * FROM call_summaries WHERE call_id=?', (str(call_id),)).fetchone()
    if not row:
        raise HTTPException(404, 'No summary job exists for this older call')
    result = dict(row)
    result['person_id'] = call['person_id']
    result['data'] = json.loads(result['data']) if result['data'] else None
    return result

@app.post('/calls/{call_id}/summary/retry', dependencies=[Depends(admin)])
def retry_summary(call_id: UUID):
    find_call(call_id)
    with database() as db:
        changed = db.execute("UPDATE call_summaries SET status='pending',attempts=0,next_attempt_at=0,error=NULL WHERE call_id=? AND status='failed'", (str(call_id),)).rowcount
    if not changed:
        raise HTTPException(409, 'Only failed summary jobs can be retried')
    return {'status': 'pending'}
