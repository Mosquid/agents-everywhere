# Call context API

The Python/FastAPI service for people, one shared system prompt, and person-linked
telephone call history in the [phone agent stack](../README.md). Profiles contain
background text; audio and transcripts are stored separately and retrieved by
call ID. The agent does not automatically update profiles or load previous call
transcripts into new conversations.

## Access and authentication

Compose exposes the API on the server at `http://127.0.0.1:8090`.
For local access, keep an SSH tunnel open:

```sh
ssh -N -L 8090:127.0.0.1:8090 <user>@192.168.1.195
```

Open the [interactive API docs](http://127.0.0.1:8090/docs) and authorize with the
token for the operation. Tokens are configured in the stack's `.env`; retain
the existing values when connecting to an existing installation. All three
must be distinct and at least 32 characters.

| Token | Allowed operations |
| --- | --- |
| `CONTEXT_READ_TOKEN` | `POST /context` |
| `CONTEXT_ADMIN_TOKEN` | `POST /context`, manage people/profiles and the shared prompt, retrieve calls and recordings |
| `CALL_WRITE_TOKEN` | `POST /calls` only; the admin token does not grant this operation |

All data endpoints require `Authorization: Bearer <token>`. `GET /health` is
unauthenticated and checks database access. The examples below assume the tunnel
is active and the relevant existing tokens are exported in your shell. Keep
tokens out of Git and chat.

## People and shared prompt

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/people` | List people, phone numbers, external keys, and profile text |
| PUT | `/people/{person_id}` | Create or replace a person and profile using a UUID |
| GET | `/prompt` | Read the shared `system_prompt` |
| PUT | `/prompt` | Replace it with `{"system_prompt":"Your shared instructions"}` |
| POST | `/context` | Resolve the shared prompt and background for a `person_id` |

Create a fictional profile with a client-generated UUID. This example uses a
fictional phone number and does not place a call:

```sh
curl --fail-with-body -X PUT \
  http://127.0.0.1:8090/people/52ade6bc-2a91-4a60-a8b1-45a532fb9a2f \
  -H "Authorization: Bearer $CONTEXT_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"phone":"+12025550123","external_key":"example:alex","initial_data":"Name: Alex. Preferred language: English. Likes gardening."}'
```

`external_key` is required, unique, and 1–256 characters. `phone` is nullable;
non-null values must use international E.164 format with `+` and no spaces.
`initial_data` is text up to 16,000 characters; Markdown or serialized JSON is
fine. `PUT` replaces the whole profile: omitting `phone` resets it to null,
and omitting `initial_data` clears it. Reusing another person's external key
returns `409`. Invalid payloads return `422`.

There are no per-person system prompts. Profile payloads reject `system_prompt`
and other extra fields. Use `PUT /prompt` for the single shared prompt
(1–16,000 characters). It is seeded from [`default-prompt.txt`](default-prompt.txt)
only on first initialization; editing that file does not change an existing DB.

Fetch the exact person's context:

```sh
curl --fail-with-body http://127.0.0.1:8090/context \
  -H "Authorization: Bearer $CONTEXT_READ_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"person_id":"52ade6bc-2a91-4a60-a8b1-45a532fb9a2f"}'
```

The response contains `matched`, `system_prompt`, and `initial_data`. A person
profile takes precedence over legacy phone-indexed context. An existing empty
profile still returns `matched: true`; it does not fall back. A person without
either profile gets the shared prompt, empty initial data, and `matched: false`.
An unknown person ID returns `404`. If both lookup fields are supplied,
`person_id` takes precedence and the body's `phone` is ignored.

## Call registration and person selection

Before starting GPT-Live, the agent waits for its participant, creates a call
record with `POST /calls`, then fetches `/context` using the returned `person_id`.
API failure prevents GPT-Live initialization. Context is a startup snapshot;
updates apply to the next call. Background text is passed to the model as data
alongside the shared instructions.

`POST /calls` registers a call record; it does not dial or start audio recording.
It requires the call writer token. Example for the person created above:

```sh
curl --fail-with-body http://127.0.0.1:8090/calls \
  -H "Authorization: Bearer $CALL_WRITE_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"person_id":"52ade6bc-2a91-4a60-a8b1-45a532fb9a2f","phone":"+12025550123","external_key":"example:alex","room":"example-room","job_id":"example-job-1"}'
```

The response contains `id` (call UUID), `person_id`, `room`, `job_id`, and
`started_at` (Unix seconds). `external_key`, `room`, and `job_id` are required;
their maximum lengths are 256, 256, and 128 characters. Repeating a `job_id`
returns its original call, even if other request fields changed.

| Selection | Behavior |
| --- | --- |
| Explicit `person_id` | Person must exist (`404` otherwise); request phone must equal the stored phone, including null (`409` on mismatch) |
| Phone without `person_id` | Reuse the sole matching person, or create an unverified person if unknown; multiple matches return `409` |
| No phone or `person_id` | Match `external_key`, or create an unverified person for that key |

SIP participants supply `sip.phoneNumber`. Outbound calls select a person with
`participant_attributes={"app.person_id": "<person UUID>"}` in the
[phone guide's call command](../README.md#profiles-and-calls). Incoming calls
from shared numbers also need a selection flow; that flow is not implemented.
Anonymous SIP callers without a usable phone number use `anonymous:<job ID>`,
creating a separate person per call.

Non-SIP clients can also load saved profiles through `rtc:<participant identity>`.
The optional browser tester uses the selected profile's RTC identity; its
default option uses `rtc:chat-tester`. Phone numbers and RTC identities are lookup keys, not verified
identities.

## Call history and recordings

All retrieval endpoints below require the admin token:

| Method | Endpoint | Result |
| --- | --- | --- |
| GET | `/people/{person_id}/calls` | Calls newest first, with recording status; an unknown person returns an empty list |
| GET | `/calls/{call_id}` | Call/person link, status, and `audio_available` / `transcript_available` |
| GET | `/calls/{call_id}/audio` | Stereo Ogg/Opus download |
| GET | `/calls/{call_id}/transcript` | Final transcript, or complete saved journal segments while incomplete |

Unknown call IDs or missing requested artifacts return `404`. Availability
flags indicate that a file exists, not that recording has finished. Transcript
segments contain `id`, `speaker` (`person` or `agent`), `text`, `timestamp` (Unix
seconds), and `interrupted`. Model-generated transcripts can contain errors;
a finalized silent conversation may have an empty transcript.

Recording starts with the agent audio session, after context lookup. It does
not capture carrier ringing or earlier audio. Stereo channel 0 is the person
and channel 1 the agent. Segments are flushed to `transcript.jsonl` during the
call. Shutdown closes audio and writes `transcript.json` and `completion.json`.

A live call or unfinished shutdown is `incomplete`. Finalization marks it
`completed` when nonempty audio is present and no known session error occurred,
otherwise `failed`. Completion metadata adds `ended_at` and `transcript_segments`.
Abrupt process/host failure can leave partial artifacts marked `incomplete`;
allow time after hangup for finalization. Registration alone does not guarantee
that the agent reached recording startup.

## Storage and privacy limits

| Docker volume | Contents |
| --- | --- |
| `hola_context-data` | SQLite database at `/data/context.sqlite3` |
| `hola_call-recordings` | `/recordings/<call-id>/audio.ogg`, transcript files, and completion metadata |

These names apply to the `hola` Compose project. The existing `.195` deployment
still uses the `gpt-live_` prefix. Container recreation preserves these volumes. The agent writes recordings;
the API mounts them read-only. The agent has context-read and call-write tokens,
not the admin retrieval token. This configuration does not upload recordings
to LiveKit Cloud. Audio and supplied context still go to OpenAI for inference.

Recordings are private; no automatic sharing, personal-fact extraction, or
wellbeing escalation is implemented. Recording permission management, automatic
retention, encryption at rest, and backups are not implemented by this service.
API request access logging is disabled, but SIP logs can contain phone numbers.

## Legacy phone profiles

These admin endpoints remain for older phone-indexed background records:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| PUT | `/recipients/{phone}` | Replace background with `{"initial_data":"Profile text"}` |
| GET | `/recipients/{phone}` | Read a legacy record, or `404` if absent |
| DELETE | `/recipients/{phone}` | Delete that legacy record; returns `204` |

`POST /context` with only `{"phone":"+12025550123"}` looks in this legacy
table, not the person profiles table. Use `person_id` for current profiles.
The legacy `PUT` also clears background when `initial_data` is omitted.
Deleting a legacy recipient does not delete a person, call history, audio,
transcripts, logs, or backups. There is no complete person-erasure endpoint.

## Synthetic demo profiles

[`demo-people.json`](../demo-people.json) contains five fictional profiles with
stable UUIDs. [`seed-people.py`](../seed-people.py) creates or replaces them via
the admin API. Set `CONTEXT_ADMIN_TOKEN`, `DEMO_PHONE`, and
`DEMO_ALTERNATE_PHONE` privately, then run from the repository root:

```sh
.venv-livekit/bin/python livekit/seed-people.py
```

The script defaults to `http://127.0.0.1:8090`; `CONTEXT_API_URL` can override it.
Inês uses the alternate number; the other four share the main number. The
fixture contains no real routing numbers and the script makes no phone calls.
Fictional family-circle entries grant no sharing permissions or past call history.

## Local checks

From the repository root with Python 3.12, install both the API and agent
dependencies because the tests cover their integration:

```sh
python3.12 -m venv .venv-livekit
.venv-livekit/bin/pip install -r livekit/requirements.txt -r livekit/context-api/requirements.txt
.venv-livekit/bin/python -m unittest discover -s livekit/context-api -p 'test_*.py' -v
```

The tests use temporary data and test tokens, with agent network/model calls
mocked; they do not contact the deployed stack or place calls.
