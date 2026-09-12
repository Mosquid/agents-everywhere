# hola phone agent stack

The phone-call infrastructure for [hola](../DOCS/PROJECT.md), a
social network for older adults. A Python agent talks with callers using
OpenAI GPT-Live, loads their profile and instructions from a local API, and
saves person-linked call audio and transcripts.

## What runs where

| Component | Runs on our server | Purpose |
| --- | --- | --- |
| LiveKit server | Yes | Rooms and real-time audio transport |
| LiveKit SIP | Yes | Connects telephone audio to LiveKit rooms |
| Orange proxy | Yes | Registers the Orange account and forwards SIP calls |
| Redis | Yes | LiveKit coordination and SIP configuration |
| Context API + SQLite | Yes | People, prompts, and call records |
| Python agent | Yes | Loads context, connects to GPT-Live, and records calls |
| GPT-Live | No — OpenAI API | Understands incoming audio and generates speech |

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
| `OPENAI_API_KEY` | OpenAI key with access to GPT-Live |
| `ORANGE_AUTH_USERNAME`, `ORANGE_PASSWORD`, `ORANGE_FROM_NUMBER` | Orange SIP account credentials and E.164 phone number |
| `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | Generated credentials for this installation's LiveKit server |
| `CONTEXT_READ_TOKEN`, `CONTEXT_ADMIN_TOKEN`, `CALL_WRITE_TOKEN` | Generated, distinct tokens for context lookup, administration, and call creation |

Orange Spain defaults are `ORANGE_DOMAIN=sip.orange.es`,
`ORANGE_PROXY_HOST=proxy2.sip.orange.es`, and `ORANGE_PROXY_PORT=5060`.
If your working account uses different values, add them to `.env`.

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
still required on each machine's network.

## Profiles and calls

The context API is available only on the server's loopback address at
`http://127.0.0.1:8090`. For a local installation, open the API documentation directly on the same
computer. An SSH tunnel is only needed when administering a remote installation.

Open `http://127.0.0.1:8090/docs` and authorize with `CONTEXT_ADMIN_TOKEN`.
See the [context API guide](context-api/README.md) for profile creation,
prompt updates, demo profiles, and all endpoints.

Incoming calls create a room and automatically dispatch the agent. Before
starting GPT-Live, the agent creates a call record and fetches the selected
person's context. The model uses client delegation; no secondary LLM or
external action tools are connected.

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

## Audio, transcripts, and storage

Each agent audio session saves stereo Ogg audio (person and agent on separate
channels) and a speaker-labelled transcript. Use the admin API to retrieve them:

| Endpoint | Result |
| --- | --- |
| `GET /people/{person_id}/calls` | Call history and recording status |
| `GET /calls/{call_id}` | Call metadata and person link |
| `GET /calls/{call_id}/audio` | Audio download |
| `GET /calls/{call_id}/transcript` | Transcript segments |

A call remains `incomplete` while recording or awaiting finalization. Normal
finalization marks it `completed`; known session failures are marked `failed`.
Abrupt shutdown can leave partial recordings. Transcripts are model-generated
and may contain recognition errors. Recording starts with the agent audio
session, not with carrier ringing.

| Docker volume | Contents |
| --- | --- |
| `hola_redis-data` | LiveKit/SIP state |
| `hola_context-data` | SQLite profiles and call records |
| `hola_call-recordings` | Audio, transcripts, and completion metadata |

Container recreation preserves these volumes. `docker compose down -v`
deletes them. Recordings are private and require admin API access; they are
not automatically shared with relatives or friends. Audio is still sent to
OpenAI for inference. Recording notice/permission management, automatic
retention, encryption at rest, and backups are not implemented by this stack.

## Existing deployment

The older installation on `192.168.1.195` is still at
`/home/inlanger/stacks/gpt-live`, with Compose project `gpt-live` and volumes
prefixed `gpt-live_`. This repository rename does not migrate that installation.
Do not start a second `hola` stack on the same ports or switch project names
without migrating the existing database, recordings, and Redis volumes.

## Network ports

| Service | Port / scope |
| --- | --- |
| LiveKit signaling | TCP 7880, LAN and loopback |
| LiveKit WebRTC | TCP 7881, UDP 7882 |
| LiveKit SIP | TCP/UDP 5060; RTP UDP 10000–10100 |
| Orange proxy | UDP 5064 and 5070 by default |
| Context API | TCP 8090, loopback only |
| Agent health | TCP 8089, loopback only |
| Redis | TCP 6379, Docker network only |
| Web chat | TCP 8092, host loopback only |

This configuration targets a LAN deployment. It does not provide public NAT
routing or TLS termination. A browser frontend needs HTTPS or localhost for
microphone access.
