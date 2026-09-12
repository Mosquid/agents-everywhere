import os
import secrets
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

DB_PATH = os.environ.get('DB_PATH', '/data/context.sqlite3')
READ_TOKEN = os.environ['CONTEXT_READ_TOKEN']
ADMIN_TOKEN = os.environ['CONTEXT_ADMIN_TOKEN']
if len(READ_TOKEN) < 32 or len(ADMIN_TOKEN) < 32 or READ_TOKEN == ADMIN_TOKEN:
    raise RuntimeError('Configure distinct tokens of at least 32 characters')
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
        db.execute('CREATE TABLE IF NOT EXISTS recipients (phone TEXT PRIMARY KEY, initial_data TEXT NOT NULL, system_prompt TEXT)')
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

class Lookup(BaseModel):
    phone: Phone | None = None

class Recipient(BaseModel):
    initial_data: str = Field(default='', max_length=16000)
    system_prompt: Prompt | None = None

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
        row = db.execute('SELECT initial_data, system_prompt FROM recipients WHERE phone=?', (body.phone,)).fetchone()
        prompt = db.execute('SELECT system_prompt FROM settings WHERE id=1').fetchone()[0]
    return {'matched': row is not None, 'system_prompt': (row['system_prompt'] or prompt) if row else prompt,
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
        db.execute('INSERT INTO recipients VALUES (?, ?, ?) ON CONFLICT(phone) DO UPDATE SET initial_data=excluded.initial_data, system_prompt=excluded.system_prompt',
                   (phone, body.initial_data, body.system_prompt))
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
