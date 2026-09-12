# hola

A phone-based social network for older adults. The [project vision](DOCS/PROJECT.md)
is to help people stay connected with friends and family through ordinary phone
conversations.

The current prototype makes and receives calls through Orange SIP. A Python
agent uses OpenAI GPT-Live for conversation, loads the person's background and
a shared system prompt from a local API, and saves audio and transcripts linked
to that person.

## Run hola

Install Docker with Compose (Docker Desktop on macOS/Windows, or Docker Engine
on Linux) and Python 3.10 or newer for the one-time configuration command.
You need an OpenAI key with GPT-Live access and your Orange SIP username,
password, and telephone number.

From the repository root:

```sh
python3 hola/configure.py
docker compose up -d --build
```

On Windows, use `py hola/configure.py` if Python is installed as `py`.
Configuration asks for this computer's LAN IPv4 address and provider credentials,
generates the internal keys, and saves them in the root `.env`. Existing values
are preserved. Never commit that file. If your LAN address changes, update
`HOLA_HOST_IP` there and run `docker compose up -d` again.

Open [hola web chat](http://localhost:8092). The same Compose stack runs LiveKit,
SIP, Orange registration, Redis, the agent, the context API, and the web chat.
Trunks are provisioned automatically by `sip-setup`; it exits after success.
No SSH access, Node.js installation, or connection to another teammate's server
is needed. First startup downloads images and builds the Python services.

```sh
docker compose ps -a
docker compose logs --tail=50 agent orange-sip-proxy sip-setup
docker compose down
```

Stopping the stack preserves profiles and recordings. `docker compose down -v`
deletes the stored data. Keep the published voice/SIP ports reachable on your
network; Orange calls still require a network on which your Orange SIP account
can register and exchange audio. Container startup alone does not verify a
carrier call. Avoid simultaneous registration of one Orange account on multiple
computers; it can redirect incoming calls between them.

To add the five fictional people for browser conversations:

```sh
docker compose exec -T -e CONTEXT_ADMIN_TOKEN='<value from .env>' agent python seed-people.py
```

They have no phone numbers unless you provide `DEMO_PHONE` and
`DEMO_ALTERNATE_PHONE`. Seeding again replaces those demo profiles.

## Deploy and use

| Task | Guide |
| --- | --- |
| Deploy the containers and connect Orange | [Phone agent stack](hola/README.md) |
| Place an outbound call or receive incoming calls | [Profiles and calls](hola/README.md#profiles-and-calls) |
| Manage people and the shared system prompt | [Context API](hola/context-api/README.md) |
| Retrieve a person's call history, recordings, and transcripts | [Call history and recordings](hola/context-api/README.md#call-history-and-recordings) |
| Read the product vision | [Project](DOCS/PROJECT.md) |

The stack is defined in [`compose.yaml`](compose.yaml) at the repository root,
with Compose project name `hola`. All service addresses inside the stack use
Docker DNS; only the advertised host address and provider credentials vary
between computers. See the phone stack guide for calling and network details.

LiveKit credentials authenticate against our own server; a LiveKit Cloud account
is not required. GPT-Live runs through the OpenAI API, so call audio and supplied
context go to OpenAI for inference.

## Current behavior and limits

People have stable IDs and can share phone numbers. Outbound calls select the
person explicitly; their saved number must match the dialled number. Incoming
calls from shared numbers need a person-selection flow that is not implemented.
Phone-number matching alone does not verify identity.

The agent loads the saved profile and shared prompt before starting conversation.
Each agent audio session records audio and transcripts to persistent local
storage; abrupt failures can leave partial recordings. The API exposes recording
status and admin-only retrieval.

Earlier transcripts are stored but are not automatically loaded as memory.
Automatic profile updates, sharing news between friends and family, sharing
permissions, and wellbeing escalation remain unimplemented parts of the vision.
Recording permission management, automatic retention, encryption at rest, and
backups are also pending.
