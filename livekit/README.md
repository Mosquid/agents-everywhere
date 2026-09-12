# Phone agent stack

The phone-call infrastructure for [Agents Everywhere](../DOCS/PROJECT.md), a
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

## Configuration

Run this stack on a Linux host with Docker Engine and Docker Compose. The
Compose file uses host networking for LiveKit, SIP, the Orange proxy, and the
agent. Commands below run from this `livekit/` directory on that host.

For an existing installation, retain its credentials. For a new installation,
create `.env` with all seven settings, replacing the placeholders:

```dotenv
LIVEKIT_NODE_IP=192.168.1.195
LIVEKIT_API_KEY=<locally-generated-key>
LIVEKIT_API_SECRET=<locally-generated-secret>
OPENAI_API_KEY=<your-openai-api-key>
CONTEXT_READ_TOKEN=<locally-generated-read-token>
CONTEXT_ADMIN_TOKEN=<locally-generated-admin-token>
CALL_WRITE_TOKEN=<locally-generated-call-token>
```

Generate a separate random value for each local key, secret, and token:

```sh
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

The three context API tokens must be distinct and at least 32 characters:

| Token | Access |
| --- | --- |
| `CONTEXT_READ_TOKEN` | Agent: read initial context and system prompt |
| `CALL_WRITE_TOKEN` | Agent: create person-linked call records |
| `CONTEXT_ADMIN_TOKEN` | Administrator: manage profiles/prompts and retrieve recordings |

Create `orange.env` with the account's SIP credentials. This file is required
by Compose. The minimal configuration uses the proxy's Orange Spain defaults:

```dotenv
ORANGE_AUTH_USERNAME=<orange-sip-username>
ORANGE_PASSWORD=<orange-sip-password>
ORANGE_FROM_NUMBER=<your-orange-number-in-E.164-format>
```

Keep any provider-specific domain, proxy, contact-port, or network settings
from an existing working account configuration. Optional settings and defaults
are defined in [`BridgeConfig.from_env`](orange-proxy/proxy.py). Compose sets
the proxy's LiveKit destination and disables verbose SIP tracing.

```sh
chmod 600 .env orange.env
```

Both environment files are excluded from Git and Docker build contexts.

## Start and connect Orange

```sh
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=50 context-api agent sip orange-sip-proxy
```

Create the inbound/outbound trunks and incoming-call dispatch rule:

```sh
docker run --rm -i --network host \
  --env-file .env --env-file orange.env \
  gpt-live-agent python - < setup-orange.py
```

The script prints the created trunk and dispatch IDs. It reuses existing
entries with the same names; it does not update their settings. The inbound
allowlist currently contains `192.168.1.195/32` in `setup-orange.py`; change it
to the proxy's source address before provisioning on a different host.

Confirm that the Orange proxy reports a successful registration and the agent
reports a registered worker. Then test an actual call to check carrier audio.

## Profiles and calls

The context API is available only on the server's loopback address at
`http://127.0.0.1:8090`. To use its interactive API documentation from your
computer, open an SSH tunnel:

```sh
ssh -N -L 8090:127.0.0.1:8090 <user>@<server>
```

Open `http://127.0.0.1:8090/docs` and authorize with `CONTEXT_ADMIN_TOKEN`.
See the [context API guide](context-api/README.md) for profile creation,
prompt updates, demo profiles, and all endpoints.

Incoming calls create a room and automatically dispatch the agent. Before
starting GPT-Live, the agent creates a call record and fetches the selected
person's context. The model uses client delegation; no secondary LLM or
external action tools are connected.

For an outbound call, select a person and use the outbound trunk ID printed
by the setup script. Replace all three placeholders below. **This command
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
| `gpt-live_redis-data` | LiveKit/SIP state |
| `gpt-live_context-data` | SQLite profiles and call records |
| `gpt-live_call-recordings` | Audio, transcripts, and completion metadata |

Container recreation preserves these volumes. `docker compose down -v`
deletes them. Recordings are private and require admin API access; they are
not automatically shared with relatives or friends. Audio is still sent to
OpenAI for inference. Recording notice/permission management, automatic
retention, encryption at rest, and backups are not implemented by this stack.

## Network ports

| Service | Port / scope |
| --- | --- |
| LiveKit signaling | TCP 7880, LAN and loopback |
| LiveKit WebRTC | TCP 7881, UDP 7882 |
| LiveKit SIP | TCP/UDP 5060; RTP UDP 10000–20000 |
| Orange proxy | UDP 5064 and 5070 by default |
| Context API | TCP 8090, loopback only |
| Agent health | TCP 8089, loopback only |
| Redis | TCP 16379, loopback only |

This configuration targets a LAN deployment. It does not provide public NAT
routing or TLS termination. A browser frontend needs HTTPS or localhost for
microphone access.
