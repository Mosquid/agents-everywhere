# Call context API

SQLite-backed service in the `gpt-live` Compose stack. The server exposes it only
at `127.0.0.1:8090`. Database: `/data/context.sqlite3` in volume
`gpt-live_context-data`. Recreating the container preserves data.

All data endpoints require `Authorization: Bearer <token>`. Tokens are in the
server's `/home/inlanger/stacks/gpt-live/.env`:
- `CONTEXT_READ_TOKEN`: agent context lookup only.
- `CONTEXT_ADMIN_TOKEN`: profile/prompt management and recording retrieval.
- `CALL_WRITE_TOKEN`: create person-linked call records; no recording retrieval or profile edits.

| Method | Endpoint | Body / purpose |
| --- | --- | --- |
| POST | `/context` | `{"phone":"+12025550123"}`; returns resolved prompt, initial data, and `matched` |
| PUT | `/recipients/{phone}` | Replace recipient data and optional prompt override |
| GET | `/recipients/{phone}` | Read recipient record |
| DELETE | `/recipients/{phone}` | Remove recipient record |
| GET | `/prompt` | Read global system prompt |
| PUT | `/prompt` | `{"system_prompt":"Your instructions"}` |
| GET | `/health` | Unauthenticated database health check |

Recipient body example (fictional):
```json
{
  "initial_data": "Name: Alex. Preferred language: English. Prefers concise answers.",
  "system_prompt": null
}
```
`initial_data` is text (Markdown is fine). A null prompt inherits the global
prompt. PUT replaces the entire record; omitting initial_data clears it, and
omitting system_prompt removes its override. Phone numbers must be international
E.164 format, with `+` and no spaces. No real recipient records are prepopulated.

To access locally:
```sh
ssh -N -L 8090:127.0.0.1:8090 192.168.1.195
```
Open `http://127.0.0.1:8090/docs`, authorize with the admin token from the remote
.env, and create/update records. Do not paste tokens into chat or commit them.

Before each session, the agent waits for its participant, reads `sip.phoneNumber`
for SIP participants, and POSTs to `/context`. Non-SIP clients use the default
prompt without personal data. Unknown numbers also get the default. API failure
prevents GPT-Live initialization. The fetched prompt and background are a snapshot;
changes apply to the next session. Every new agent call is recorded locally
and its transcript is saved; no automatic personal-fact updates are implemented. The system prompt is seeded from default-prompt.txt only once;
use the API to change it thereafter.

Phone lookup is not identity verification. Do not use caller ID alone to disclose
sensitive information. Context sent to GPT-Live is processed by OpenAI. API request
access logging is disabled, but existing SIP logs still contain phone numbers.
SQLite storage is not encrypted by this service; retention scheduling and backup
policies are not implemented. DELETE /recipients removes only initial profile
context; it does not erase person records, calls, recordings, provider retention,
existing sessions, SIP logs, or external backups.

Local checks:
```sh
.venv-livekit/bin/python -m unittest discover -s livekit/context-api -p 'test_*.py' -v
```

## Person-linked call recordings

This project is a phone-based social network for older adults (DOCS/PROJECT.md).
Call artifacts are private. Recording a conversation does not authorize sharing
it or any extracted update with a relative or friend. No automatic sharing or
wellbeing escalation is implemented.

Every new agent session first creates a call through POST /calls. Phone numbers
map to stable person IDs; unknown phone numbers get an unverified person record.
Browser test participants use their RTC identity. Anonymous SIP callers get
separate unverified records per call. Phone/RTC identity linkage is not identity
verification. Existing recipient profiles remain indexed by the person's phone.

Audio and transcripts are written under /recordings/<call-id>/ in the persistent
`gpt-live_call-recordings` volume. LiveKit records stereo Ogg/Opus: channel 0 is
the person, channel 1 is the agent. Recording begins when the agent audio session
starts; it does not capture earlier carrier ringing or audio before agent startup.
Transcript segments contain speaker, text, timestamp, and interruption status.
They are model-generated transcripts and can contain recognition errors.

Segments are flushed during the call to transcript.jsonl. At shutdown the agent
closes the audio file and writes final transcript.json and completion.json.
Call status stays `incomplete` until finalization (including during a live call);
normal completion becomes `completed`, and known session errors become `failed`.
Abrupt process/host failure can leave partial artifacts, which remain marked
incomplete. Finalization can occur about 20 seconds after hangup. A successfully
finalized silent call may have an empty transcript. Recording is not retroactive.

Admin API endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | /people | List stable person IDs and phone/RTC lookup keys |
| GET | /people/{person_id}/calls | List that person's calls and recording status |
| GET | /calls/{call_id} | Metadata, person link, completion status |
| GET | /calls/{call_id}/audio | Download stereo Ogg audio |
| GET | /calls/{call_id}/transcript | Final transcript, or saved segments while incomplete |

The agent has a call-creation token and filesystem write access, not the admin
retrieval token. The API mounts recordings read-only. No recordings are sent to
LiveKit Cloud by this configuration. Audio still goes to OpenAI for inference.
Recording notice/permission management, automatic retention, encryption at rest,
and backups are separate work; this implementation does not establish GDPR
compliance.
