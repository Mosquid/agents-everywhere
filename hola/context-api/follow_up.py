"""Durable callback policy and bookings; times are UTC Unix seconds in SQLite."""
import time
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class SchedulingSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    next_call_min_hours: int = Field(default=48, ge=1, le=8760, strict=True)
    next_call_max_hours: int = Field(default=168, ge=1, le=8760, strict=True)

    @model_validator(mode='after')
    def ordered(self):
        if self.next_call_max_hours < self.next_call_min_hours:
            raise ValueError('Maximum hours must be at least the minimum')
        return self


class Booking(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scheduled_at: AwareDatetime
    timezone: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)
    agreement: str = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def valid_local_time(self):
        try:
            local = self.scheduled_at.astimezone(ZoneInfo(self.timezone))
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Use an IANA timezone such as Europe/Madrid')
        if local.utcoffset() != self.scheduled_at.utcoffset():
            raise ValueError('Timestamp offset must match the timezone on that date')
        return self


class Cancellation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    stop_future_calls: bool = False
    reason: str = Field(min_length=1, max_length=1000)


class CallingPermission(BaseModel):
    model_config = ConfigDict(extra='forbid')
    allowed: bool


def migrate(db):
    columns = {r['name'] for r in db.execute('PRAGMA table_info(settings)')}
    for name, default in (('next_call_min_hours', 48), ('next_call_max_hours', 168)):
        if name not in columns:
            db.execute(f'ALTER TABLE settings ADD COLUMN {name} INTEGER NOT NULL DEFAULT {default}')
    db.execute('''CREATE TABLE IF NOT EXISTS calling_permissions (
        person_id TEXT PRIMARY KEY, allowed INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS scheduled_calls (
        id TEXT PRIMARY KEY, person_id TEXT NOT NULL, source_call_id TEXT NOT NULL,
        phone TEXT NOT NULL, scheduled_at REAL NOT NULL, timezone TEXT NOT NULL,
        reason TEXT NOT NULL, agreement TEXT NOT NULL, status TEXT NOT NULL,
        updated_at REAL NOT NULL, error TEXT)''')
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_pending_call ON scheduled_calls(person_id) WHERE status IN ('scheduled','dialing')")
    db.execute('''CREATE TABLE IF NOT EXISTS call_summaries (
        call_id TEXT PRIMARY KEY, status TEXT NOT NULL, data TEXT, model TEXT,
        prompt_version TEXT, generated_at REAL, attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt_at REAL NOT NULL DEFAULT 0, lease_until REAL, error TEXT)''')


def settings(db):
    return dict(db.execute('SELECT next_call_min_hours,next_call_max_hours FROM settings WHERE id=1').fetchone())


def allowed(db, person_id):
    row = db.execute('SELECT allowed FROM calling_permissions WHERE person_id=?', (person_id,)).fetchone()
    return row is None or bool(row['allowed'])


def window(db, call):
    policy = settings(db)
    return (round(call['started_at'] + policy['next_call_min_hours'] * 3600, 6),
            round(call['started_at'] + policy['next_call_max_hours'] * 3600, 6))


def info(db, call):
    earliest, latest = window(db, call)
    person = db.execute('SELECT phone FROM people WHERE id=?', (call['person_id'],)).fetchone()
    pending = db.execute("SELECT * FROM scheduled_calls WHERE person_id=? AND status IN ('scheduled','dialing')", (call['person_id'],)).fetchone()
    return {**settings(db), 'now': datetime.now(timezone.utc).isoformat(),
            'earliest': datetime.fromtimestamp(earliest, timezone.utc).isoformat(),
            'latest': datetime.fromtimestamp(latest, timezone.utc).isoformat(),
            'has_phone': bool(person and person['phone']), 'calling_allowed': allowed(db, call['person_id']),
            'pending': dict(pending) if pending else None}


def latest_call(db, call):
    latest = db.execute('SELECT id FROM calls WHERE person_id=? ORDER BY started_at DESC,rowid DESC LIMIT 1', (call['person_id'],)).fetchone()
    if latest['id'] != call['id']:
        raise HTTPException(409, 'A newer conversation exists; schedule from that call')


def book(db, call, body):
    latest_call(db, call)
    if not allowed(db, call['person_id']):
        raise HTTPException(409, 'Future calls are disabled for this person')
    phone = db.execute('SELECT phone FROM people WHERE id=?', (call['person_id'],)).fetchone()['phone']
    if not phone:
        raise HTTPException(409, 'No telephone number is saved for this person')
    now = time.time()
    stamp = body.scheduled_at.timestamp()
    earliest, latest = window(db, call)
    if stamp <= now or not earliest <= stamp <= latest:
        raise HTTPException(422, {'message': 'Choose a future time inside the global window', **info(db, call)})
    pending = db.execute("SELECT * FROM scheduled_calls WHERE person_id=? AND status IN ('scheduled','dialing')", (call['person_id'],)).fetchone()
    if pending and pending['status'] == 'dialing':
        raise HTTPException(409, 'A callback is already being dialed')
    booking_id = pending['id'] if pending else str(uuid.uuid4())
    db.execute('''INSERT INTO scheduled_calls VALUES (?,?,?,?,?,?,?,?,?,?,NULL)
        ON CONFLICT(id) DO UPDATE SET source_call_id=excluded.source_call_id,
        phone=excluded.phone,scheduled_at=excluded.scheduled_at,timezone=excluded.timezone,
        reason=excluded.reason,agreement=excluded.agreement,updated_at=excluded.updated_at,error=NULL''',
        (booking_id, call['person_id'], call['id'], phone, stamp, body.timezone,
         body.reason, body.agreement, 'scheduled', now))
    result = dict(db.execute('SELECT * FROM scheduled_calls WHERE id=?', (booking_id,)).fetchone())
    result['scheduled_local'] = body.scheduled_at.astimezone(ZoneInfo(body.timezone)).isoformat()
    return result


def cancel(db, call, body):
    latest_call(db, call)
    if body.stop_future_calls:
        db.execute('INSERT INTO calling_permissions VALUES (?,0) ON CONFLICT(person_id) DO UPDATE SET allowed=0', (call['person_id'],))
    dialing = db.execute("SELECT 1 FROM scheduled_calls WHERE person_id=? AND status='dialing'", (call['person_id'],)).fetchone()
    db.execute("UPDATE scheduled_calls SET status='cancelled',error=?,updated_at=? WHERE person_id=? AND status='scheduled'",
               (body.reason, time.time(), call['person_id']))
    return {'cancelled': True, 'calling_allowed': allowed(db, call['person_id']),
            'dial_already_in_progress': bool(dialing)}
