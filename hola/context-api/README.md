# Call context API

The Python/FastAPI service for people, one shared system prompt, and person-linked
telephone call history, summaries, and callback scheduling in the
[phone agent stack](../README.md). Profiles contain background text; recordings,
summaries, and bookings are linked by call and person IDs. The agent does not
automatically update profiles or load previous calls or summaries into new conversations.

## Access and authentication

Compose exposes the API on the server at `http://127.0.0.1:8090`.
For a local Compose installation, access it directly. For a remote installation,
replace `user@server` with the remote SSH login and keep a tunnel open:

```sh
ssh -N -L 8090:127.0.0.1:8090 user@server
```

Open the [interactive API docs](http://127.0.0.1:8090/docs) and authorize with the
token for the operation. Tokens are configured in the repository root `.env`; retain
the existing values when connecting to an existing installation. All three
must be distinct and at least 32 characters.

| Token | Allowed operations |
| --- | --- |
| `CONTEXT_READ_TOKEN` | `POST /context`, `GET /settings` |
| `CONTEXT_ADMIN_TOKEN` | Read context/settings, manage people, prompt, settings and calling permission, retrieve calls, recordings, summaries, and bookings; retry failed summaries |
| `CALL_WRITE_TOKEN` | Register calls and read/book/cancel their follow-ups; the admin token does not grant these operations |

All data endpoints require `Authorization: Bearer <token>`. `GET /health` is
unauthenticated and checks database access. The curl examples below assume
the API is reachable locally (directly or through the tunnel) and the relevant
token has been exported in your shell. Compose reads `.env` for containers; it
does not export those values into your terminal. Keep
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
on first initialization. The scheduling migration also replaces the exact old
bundled conversation-test prompt; custom prompts are preserved. Later edits to
the file do not replace an existing prompt. The bundled prompt introduces hola
and offers follow-up calls. Profile changes and `PUT /prompt` apply when the next
agent session starts. Tool usage instructions are appended by the agent; global
timing restrictions are enforced by the API regardless of prompt text.
At each call's start, the agent adds its current UTC date and time in ISO 8601
format to both the live and backend prompts. The stored shared prompt stays a
template; `GET /prompt` does not contain a stale hard-coded date. The callback
options tool provides a fresh current time during the conversation.
The agent also has a current-weather tool. It calls Open-Meteo directly and
does not send the profile or transcript to that provider; see the [agent guide](../README.md#profiles-and-calls).

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
The included web chat interface uses the selected profile's RTC identity; its
default option uses `rtc:chat-tester`. Phone numbers and RTC identities are
lookup keys, not verified identities. To make a person appear in the browser
selector, give them an `rtc:` external key and nonempty `initial_data`. JSON
with `name` and `language` fields supplies the displayed labels.

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

## Follow-up calls and summaries

### Global timing settings

`GET /settings` accepts a read or admin token. `PUT /settings` requires admin:

```sh
curl --fail-with-body -X PUT http://127.0.0.1:8090/settings \
  -H "Authorization: Bearer $CONTEXT_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"next_call_min_hours":48,"next_call_max_hours":168}'
```

These are persistent global settings, measured from the source call's
`started_at`. Values are whole hours from 1 to 8760, with maximum at least
minimum; defaults are 48 and 168. Sending only one field resets the other to
its default. The API rejects bookings outside this window or in the past.
Changing the window marks existing out-of-range bookings `needs_reschedule`;
it does not silently move them or reinstate previously invalidated bookings.

### Conversation tools and bookings

| Method | Endpoint | Token / purpose |
| --- | --- | --- |
| GET | `/calls/{call_id}/follow-up` | Call writer: current time, allowed UTC window, phone availability, permission, pending booking |
| POST | `/calls/{call_id}/follow-up` | Call writer: book or reschedule the next call |
| POST | `/calls/{call_id}/cancel-follow-up` | Call writer: cancel, optionally disable future bookings |
| GET | `/people/{person_id}/scheduled-calls` | Admin: booking history, source call, agreement, status and errors |
| PUT | `/people/{person_id}/calling-permission` | Admin: `{"allowed":false}` cancels pending bookings; `true` permits new bookings |

The agent tools bind the call ID internally, so the model cannot select another
person. It reads the options, proposes a follow-up based on the conversation,
and asks for agreement to an exact local time. Booking requires a saved phone
number plus these fields:

```json
{
  "scheduled_at": "2026-09-15T15:00:00+02:00",
  "timezone": "Europe/Madrid",
  "reason": "Hear how the newly planted tomatoes are growing",
  "agreement": "Yes, call me on September 15 at 3 pm Madrid time."
}
```

This date is illustrative; use a future time inside the window returned for
the actual call. The timestamp's UTC offset must match the IANA timezone on
that date, including daylight saving time. The API stores UTC Unix seconds
and the timezone; the booking response also includes `scheduled_local`.
Agreement is an agent-supplied quote, not independently verified consent.
The agent confirms booking only after a successful API result.

Each person has at most one pending callback; another booking request updates
it. Starting a newer conversation marks an earlier pending booking `superseded`.
Old conversations cannot book or cancel the newer conversation's follow-up.
Cancelling uses `{"reason":"Please cancel","stop_future_calls":false}`.
For an opt-out, set `stop_future_calls` to `true`; only an administrator can
re-enable bookings. Cancellation does not stop a dial already in progress;
the response reports `dial_already_in_progress`.

The API's scheduler polls every five seconds and uses the existing
`orange-local-proxy` trunk. It waits for source-call finalization, rechecks
permission, phone number, and global limits, and commits `dialing` before
contacting LiveKit. The normal states are `scheduled` → `dialing` → `answered`.
Other states are `cancelled`, `superseded`, `needs_reschedule`, `missed`, and
`unknown`. A changed number requires rescheduling. Calls more than 15 minutes
late, or beyond the global maximum, are missed; allow margin before the latest
boundary. `answered` records successful SIP answer, not a completed conversation.
Failures and interrupted dial attempts become `unknown` and are never
automatically retried, because the carrier may already have received the call.

### Stored summaries

`GET /calls/{call_id}/summary` requires admin and returns `call_id`, `person_id`,
`status`, `data`, `model`, `prompt_version`, `generated_at`, `attempts`, and error
metadata. Ready `data` contains `summary`, `topics`, `new_facts`, and
`follow_up_topics`. Facts remain attributed claims from the transcript and do
not update the permanent profile. Bookings remain separate authoritative records.

New calls receive a durable summary job. The API waits for final transcript
and completion metadata, then uses `gpt-5.6-luna` with structured output and
`store=false`. The final transcript is sent to OpenAI for this request. Jobs
move from `pending` to `processing` and `ready`; failures retry after 60 seconds
up to three attempts, then become `failed`. Empty person transcripts are
`skipped`. An interrupted processing job can be recovered after five minutes.
`POST /calls/{call_id}/summary/retry` lets admin retry a failed job. Calls created
before this feature have no summary job and return `404`; there is no automatic
backfill. A call without finalized artifacts remains pending.

Both workers run inside the existing API container and use its persistent
SQLite volume. Tests set `FOLLOW_UP_WORKERS_ENABLED=0` to disable background
work; normal Compose startup enables it. Summaries and tools require OpenAI
model access; scheduled dialing requires working LiveKit and Orange services.

## Storage and privacy limits

| Docker volume | Contents |
| --- | --- |
| `hola_context-data` | SQLite profiles, prompt, calls, summaries, scheduling settings, and bookings at `/data/context.sqlite3` |
| `hola_call-recordings` | `/recordings/<call-id>/audio.ogg`, transcript files, and completion metadata |

These names apply to the `hola` Compose project. Container recreation preserves
these volumes. The agent writes recordings;
the API mounts them read-only. The agent has context-read and call-write tokens,
not the admin retrieval token. This configuration does not upload recordings
to LiveKit Cloud. Audio and supplied context still go to OpenAI for inference.

Recordings and summaries are private. Summary facts are not automatically
merged into profiles or shared. No wellbeing escalation is implemented.
Callback opt-out does not implement recording permission management. Automatic
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
stable UUIDs and English, Russian, or Ukrainian language preferences. Startup
does not seed them automatically. From the repository root, with Compose running:

```sh
docker compose exec -T -e CONTEXT_ADMIN_TOKEN='<value from .env>' agent python seed-people.py
```

The agent normally has no admin token, so pass it explicitly for this command.
It already has the internal `CONTEXT_API_URL`. The script creates or replaces
profiles, and prints their IDs. Refresh the browser to see them in the selector.

Without phone overrides, all five profiles get null phone numbers and work in
web chat. To attach telephone routes, pass both numbers explicitly:

```sh
docker compose exec -T \
  -e CONTEXT_ADMIN_TOKEN='<value from .env>' \
  -e DEMO_PHONE='<main-number-in-E.164-format>' \
  -e DEMO_ALTERNATE_PHONE='<alternate-number-in-E.164-format>' \
  agent python seed-people.py
```

Inês uses the alternate number; the other four share the main number. These
values must be passed to the process; adding them to the root `.env` alone does
not inject them into the agent. Rerunning the seeder replaces demo backgrounds
and phone numbers, including resetting an omitted number to null. Existing
person IDs and call records are retained. No call is placed by seeding.

For direct execution outside Docker, [`seed-people.py`](../seed-people.py) uses
the standard Python library and defaults to `http://127.0.0.1:8090`. Export
`CONTEXT_ADMIN_TOKEN` and any phone overrides first; `CONTEXT_API_URL` can change
the destination. It does not read `.env` itself.

The fixture contains no real routing numbers. Its family-circle entries grant
no sharing permissions or past call history.

## Local checks

See the [stack verification instructions](../README.md#troubleshooting-and-verification)
for the configuration, API/agent, and web chat test commands. The API tests cover
profile lookup, token permissions, person/call linkage, recording metadata,
shared phone numbers, migrations, global timing limits, timezone validation,
tool/API round trips, opt-out, summary retries, and preventing duplicate dialing
after worker interruption. Dialing and summary generation are mocked in these tests.
