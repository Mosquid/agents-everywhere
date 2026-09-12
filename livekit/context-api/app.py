import os
import secrets
import sqlite3
import json
import time
import uuid
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
        db.execute('INSERT OR IGNORE INTO settings VALUES (1, ?)', (Path(__file__).with_name('default-prompt.txt').read_text().strip(),))
    yield

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
