# hola phone agent stack

The phone-call infrastructure for [hola](../docs/PROJECT.md), a
social network for older adults. A Python agent talks with callers using
OpenAI GPT-Live, loads their profile and instructions from a local API, and
saves person-linked call audio, transcripts, and summaries, and schedules callbacks.

## Services

All eight services are defined in the root [compose.yaml](../compose.yaml).
Seven stay running; one performs setup and exits.

| Compose service | Purpose | Expected state after startup |
| --- | --- | --- |
| `livekit` | Rooms and real-time audio transport | Running |
| `sip` | Bridges telephone audio to LiveKit rooms | Running |
| `orange-sip-proxy` | Registers with Orange and forwards signaling to `sip` | Running; check logs for registration success |
| `redis` | LiveKit coordination and stored SIP trunks/routing | Running, healthy |
| `context-api` | SQLite people, prompt, calls, summaries, scheduling policy, and automatic callback dialing | Running, healthy |
| `agent` | Loads context, talks to GPT-Live, records conversations, agrees and books callbacks | Running; logs show registered worker |
| `web-chat` | Browser interface and room-token server | Running; open localhost:8092 |
| `sip-setup` | Creates trunks and incoming-call routing | Exited (0) after success |

`Exited (0)` for `sip-setup` is normal. It retries on failure. It uses the agent
image to run a different command; it does not handle live calls. Both `sip` and
`orange-sip-proxy` are needed: the former bridges media, while the latter performs
the Orange account registration used by this integration. Port mappings for
both appear under `sip` because they share a network namespace.

GPT-Live runs at OpenAI, outside these containers. Browser and telephone
sessions both use the same Python agent, context API, and recording storage.

**No LiveKit Cloud account or cloud API key is required.** `LIVEKIT_API_KEY`
and `LIVEKIT_API_SECRET` are credentials we generate and configure on our own
LiveKit server. The agent and SIP service use them to authenticate locally.
`OPENAI_API_KEY` is the separate credential issued by OpenAI.

## Configuration and startup

Follow the [root quick start](../README.md#run-hola). All commands run from the
repository root, with one `compose.yaml` and one private `.env`. The configuration
command generates distinct LiveKit credentials and context API tokens, and asks
for the machine's LAN IPv4 address plus OpenAI and Orange credentials.

| Setting | Purpose |
| --- | --- |
| `HOLA_HOST_IP` | This machine's LAN IPv4 address advertised for WebRTC and SIP media |
| `OPENAI_API_KEY` | OpenAI key with access to GPT-Live and `gpt-5.6-luna` for tools and summaries |
| `ORANGE_AUTH_USERNAME`, `ORANGE_PASSWORD`, `ORANGE_FROM_NUMBER` | Orange SIP account credentials and E.164 phone number |
| `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | Generated credentials for this installation's LiveKit server |
| `CONTEXT_READ_TOKEN`, `CONTEXT_ADMIN_TOKEN`, `CALL_WRITE_TOKEN` | Generated, distinct tokens for context lookup, administration, and call creation/scheduling |

Orange Spain defaults are `ORANGE_DOMAIN=sip.orange.es`,
`ORANGE_PROXY_HOST=proxy2.sip.orange.es`, and `ORANGE_PROXY_PORT=5060`.
If your working account uses different values, add them to `.env`. Compose
forwards these three overrides to the proxy. Other proxy options in its source
are not automatically passed through from the root `.env`.

Compose uses a bridge network, published media ports, and Docker service names.
The Orange proxy shares the SIP container's network namespace; their private
signaling stays on loopback. Redis is internal. The context API and web chat
are published only on the host's loopback address.

```sh
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
docker compose logs --tail=50 agent sip orange-sip-proxy sip-setup
```

`sip-setup` automatically creates the inbound/outbound trunks and dispatch rule,
then exits successfully. It reuses entries with the same names; it does not
change existing trunk settings. For a new Orange account or number on an existing
installation, update its trunks through the LiveKit API before calling.

Confirm successful Orange registration in the proxy logs, then test an actual
call to verify carrier audio. Provider access and router/firewall routing are
still required on each machine's network. A successful trunk setup is separate
from successful Orange registration and a working telephone call.

## Profiles and calls

The context API is available only on the server's loopback address at
`http://127.0.0.1:8090`. For a local installation, open the API documentation directly on the same
computer. An SSH tunnel is only needed when administering a remote installation.

Open `http://127.0.0.1:8090/docs` and authorize with `CONTEXT_ADMIN_TOKEN`.
See the [context API guide](context-api/README.md) for profile creation,
prompt updates, demo profiles, and all endpoints.

Incoming calls create a room and automatically dispatch the agent. Before
starting GPT-Live, the agent creates a call record and fetches the selected
person's context. GPT-Live uses [Responses delegation](https://developers.openai.com/api/docs/guides/live-delegation)
with `gpt-5.6-luna` to execute conversation tools: read callback options,
book/reschedule the next call, cancel/opt out, and look up current weather.
Callback tools are bound to the current call and person. Speech still uses
`gpt-live-1`. Both prompts receive the current UTC date and time at call start.

The `get_weather(location)` tool uses Open-Meteo's geocoding and weather APIs,
following [LiveKit's function-tool guidance](https://docs.livekit.io/agents/logic/tools/definition/).
It returns the resolved place, local data time, timezone, temperature, feels-like
temperature, cloud cover, precipitation, wind, and units. The agent asks for a
city and country/region when unclear, and attributes answers to Open-Meteo.
This provides current conditions; future forecasts are not included. It reuses
LiveKit's HTTP session with five-second timeouts per request and reports service
failures without inventing weather. Only the requested location goes to the
weather provider. The prototype uses its public API without an additional key;
see [Open-Meteo's service terms](https://open-meteo.com/en/terms) before commercial use.

For an outbound call, select a person and use the outbound trunk ID printed
in the `sip-setup` logs. Replace all three placeholders below. **This command
places a telephone call.**

```sh
docker compose exec -T \
  -e CALL_TO='<recipient-number-in-E.164-format>' \
  -e PERSON_ID='<person-uuid>' \
  -e SIP_TRUNK_ID='<outbound-trunk-id>' agent python - <<'PY'
import asyncio
import os
import uuid
from livekit import api

async def main():
    async with api.LiveKitAPI() as client:
        call = await client.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=os.environ['SIP_TRUNK_ID'],
                sip_call_to=os.environ['CALL_TO'],
                room_name='outbound-' + str(uuid.uuid4()),
                participant_identity='phone-user',
                participant_attributes={'app.person_id': os.environ['PERSON_ID']},
                wait_until_answered=True,
            ),
            timeout=60,
        )
        print('Answered:', call.room_name)

asyncio.run(main())
PY
```

The person's stored number must match the dialled number. When multiple
people share a number, explicit person selection is required; the agent does
not guess. Incoming calls from a shared number need a selection flow that is
not implemented yet. Phone-number matching is not identity verification.

## Follow-up calls and summaries

The agent proposes a callback based on the conversation and saves it after the
person agrees an exact date, time, and timezone. The API enforces a global
48–168 hour window measured from the current call's start. Change the two hour
settings through `PUT /settings`; they persist in SQLite. A saved phone number
is required, including when arranging a callback from web chat.

The API container runs both background workers: it summarizes finalized
transcripts with `gpt-5.6-luna`, and dials due callbacks through the existing
Orange outbound trunk. There are no additional services to start. Each person
can have one pending callback; starting another conversation supersedes the
previous pending booking. Calls require the source conversation to be finalized.
The scheduler allows up to 15 minutes of lateness, within the global maximum;
otherwise it marks the booking missed. Interrupted or uncertain dial attempts
are recorded for review and are never automatically repeated.

The agent can cancel a pending call or disable future bookings at the person's
request. An administrator can re-enable bookings. Changes to the global window
invalidate bookings outside it instead of silently moving them. For endpoints,
statuses, and summary retries, see the [API guide](context-api/README.md#follow-up-calls-and-summaries).

## Audio, transcripts, and storage

Each agent audio session saves stereo Ogg audio (person and agent on separate
channels) and a speaker-labelled transcript. Use the admin API to retrieve them:

| Endpoint | Result |
| --- | --- |
| `GET /people/{person_id}/calls` | Call history and recording status |
| `GET /calls/{call_id}` | Call metadata and person link |
| `GET /calls/{call_id}/audio` | Audio download |
| `GET /calls/{call_id}/transcript` | Transcript segments |
| `GET /calls/{call_id}/summary` | Summary status, structured content, and generation metadata |

A call remains `incomplete` while recording or awaiting finalization. Normal
finalization marks it `completed`; known session failures are marked `failed`.
Abrupt shutdown can leave partial recordings. Transcripts are model-generated
and may contain recognition errors. Recording starts with the agent audio
session, not with carrier ringing.

| Docker volume | Contents |
| --- | --- |
| `hola_redis-data` | LiveKit/SIP state |
| `hola_context-data` | SQLite profiles, prompt, calls, summaries, scheduling settings, and bookings |
| `hola_call-recordings` | Audio, transcripts, and completion metadata |

Container recreation preserves these volumes. `docker compose down -v`
deletes them. Recordings are private and require admin API access; they are
not automatically shared with relatives or friends. Audio is still sent to
OpenAI for inference; the final transcript also goes to OpenAI for summarization.
Summaries do not update profiles or become automatic conversation memory.
Recording notice/permission management, automatic
retention, encryption at rest, and backups are not implemented by this stack.

## Older installations

The earlier `.195` deployment used `/home/inlanger/stacks/gpt-live`, Compose
project `gpt-live`, and volumes prefixed `gpt-live_`. Those are historical
installation details, not prerequisites or defaults for teammates.
The current Compose file does not migrate those volumes or rewrite old trunks.
Preserve that installation's credentials and data before moving it to this layout;
starting `hola` creates separate volumes. Its Orange proxy was stopped on
2026-09-12 at the user's request; repository updates do not restart it.

## Network ports

| Service | Port / scope |
| --- | --- |
| LiveKit signaling | TCP 7880, LAN and loopback |
| LiveKit WebRTC | TCP 7881, UDP 7882 |
| LiveKit SIP | TCP/UDP 5060; RTP UDP 10000–10100 |
| Orange proxy | UDP 5064 and 5070 by default |
| Context API | TCP 8090, loopback only |
| Agent health | TCP 8089, agent container loopback only; not published to host |
| Redis | TCP 6379, Docker network only |
| Web chat | TCP 8092, host loopback only |

This configuration targets a LAN deployment. It does not provide public NAT
routing or TLS termination. A browser frontend needs HTTPS or localhost for
microphone access.

## Troubleshooting and verification

| Symptom | Check |
| --- | --- |
| Compose rejects a missing setting | Run `python3 hola/configure.py`; correct existing blank values in the root `.env` |
| A published port is already in use | Stop the earlier process or stack using that port before starting hola |
| `sip-setup` keeps restarting | Read `docker compose logs --tail=50 sip-setup livekit`; successful setup exits with code 0 |
| Orange is running but not registered | Check account values, provider address, and network access in `orange-sip-proxy` logs |
| Browser stays waiting for an agent | Check `agent` logs for registration, context API errors, or OpenAI access errors |
| Browser connects but audio does not flow | Verify `HOLA_HOST_IP` is this machine's current LAN IPv4 address and media ports are reachable |
| Profile selector is empty | Seed profiles and refresh; only populated profiles with `rtc:` external keys appear |
| A recording is `incomplete` | Allow finalization after disconnect; inspect agent logs if it remains incomplete |

Verified locally on macOS with OrbStack on 2026-09-12: building and starting the
Compose services, trunk provisioning, browser profile selection and replies,
prerecorded speech through LiveKit, and person-linked audio/transcript retrieval.
Live browser conversations also verified current weather lookup, saving an agreed
callback, cancellation and opt-out, and a stored post-call summary. Scheduled
dialing was checked with a mocked carrier; no real telephone call was placed.
A real Orange carrier call was not verified with this bridge-network layout.
Windows and Linux were not exercised in that local test.

For code changes, run the following from the repository root with Python 3.12.
These checks use temporary data and mocks; they do not call OpenAI or Orange.
The virtual environment is only needed for running tests outside Docker.

```sh
python3.12 -m venv .venv-livekit
.venv-livekit/bin/pip install -r hola/requirements.txt -r hola/context-api/requirements.txt -r hola/web-chat/requirements.txt
.venv-livekit/bin/python -m unittest discover -s hola -p 'test_*.py' -v
.venv-livekit/bin/python -m unittest discover -s hola/context-api -p 'test_*.py' -v
.venv-livekit/bin/python -m unittest discover -s hola/web-chat -p 'test_*.py' -v
```

Shell examples with backslash continuations or heredocs in these guides use
POSIX shell syntax. On Windows, run those examples in WSL/Git Bash, or use the
API's interactive documentation for profile and prompt operations.
