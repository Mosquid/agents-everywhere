"""Persist LiveKit's local audio and speaker-labelled conversation history."""
import asyncio
import json
import os
from pathlib import Path

from livekit.agents import llm


def message_row(item):
    if not isinstance(item, llm.ChatMessage) or item.role not in ('user', 'assistant'):
        return None
    if not item.text_content:
        return None
    return {'id': item.id, 'speaker': 'person' if item.role == 'user' else 'agent',
            'text': item.text_content, 'timestamp': item.created_at,
            'interrupted': item.interrupted}


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as file:
        json.dump(value, file, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


class CallRecording:
    def __init__(self, ctx, session, call_id):
        self.session = session
        self.path = Path(os.environ['RECORDINGS_DIR']) / call_id
        self.path.mkdir(mode=0o700, parents=True, exist_ok=False)
        # LiveKit writes to its documented per-job directory. The symlink keeps
        # the output on our persistent volume throughout the call, not just at exit.
        (ctx.session_directory / 'audio.ogg').symlink_to(self.path / 'audio.ogg')
        self.journal = (self.path / 'transcript.jsonl').open('a', buffering=1)
        self.lock = asyncio.Lock()
        self.finished = False
        self.failed = False
        session.on('conversation_item_added', self.on_message)
        session.on('close', self.on_close)
        ctx.add_shutdown_callback(self.finish)

    def on_message(self, event):
        row = message_row(event.item)
        if row and not self.journal.closed:
            self.journal.write(json.dumps(row, ensure_ascii=False)+'\n')
            self.journal.flush()
            os.fsync(self.journal.fileno())

    def on_close(self, event):
        self.failed = event.error is not None or event.reason == 'error'

    async def finish(self, *args):
        async with self.lock:
            if self.finished:
                return
            await self.session.aclose()
            rows = [row for item in self.session.history.items if (row := message_row(item))]
            write_json(self.path / 'transcript.json', rows)
            self.journal.close()
            audio = self.path / 'audio.ogg'
            import time
            write_json(self.path / 'completion.json', {
                'status': 'completed' if not self.failed and audio.exists() and audio.stat().st_size > 0 else 'failed',
                'ended_at': time.time(), 'transcript_segments': len(rows)})
            self.finished = True
