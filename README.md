# hola

A phone-based social network for older adults. The [project vision](DOCS/PROJECT.md)
is to help people stay connected with friends and family through ordinary phone
conversations.

The current prototype makes and receives calls through Orange SIP. A Python
agent uses OpenAI GPT-Live for conversation, loads the person's background and
a shared system prompt from a local API, saves audio, transcripts, and post-call
summaries linked to that person, and arranges the next call during conversation.
It can look up current weather when asked.

## Run hola

Install Docker with Compose (Docker Desktop on macOS/Windows, or Docker Engine
on Linux) and Python 3.10 or newer for the one-time configuration command.
You need an OpenAI key with GPT-Live access and your Orange SIP username,
password, and telephone number.

Clone this repository and run these commands from its root directory:

```sh
python3 hola/configure.py
docker compose up -d --build
```

On Windows, use `py hola/configure.py` if Python is installed as `py`.
Configuration asks for this computer's LAN IPv4 address and provider credentials,
generates the internal keys, and saves them in the root `.env`. Existing values
are preserved, including blank values; edit incorrect or blank settings in `.env`
directly. The script does not import credentials from older `hola/.env` or
`orange.env` files. Never commit the root `.env`. If your LAN address changes, update
`HOLA_HOST_IP` there and run `docker compose up -d` again.

Open [hola web chat](http://localhost:8092). The same Compose stack runs LiveKit,
SIP, Orange registration, Redis, the agent, the context API, and the web chat.
There are seven running services plus `sip-setup`, which provisions trunks
and exits. **`Exited (0)` for `sip-setup` means success.**
No SSH access, Node.js installation, or connection to another teammate's server
is needed. First startup downloads images and builds the Python services.

```sh
docker compose ps -a
docker compose logs --tail=50 agent orange-sip-proxy sip-setup
```

Stop with `docker compose down`; this preserves profiles and recordings. `docker compose down -v`
deletes the stored data. Keep the published voice/SIP ports reachable on your
network; Orange calls still require a network on which your Orange SIP account
can register and exchange audio. Container startup alone does not verify a
carrier call. Avoid simultaneous registration of one Orange account on multiple
computers; it can redirect incoming calls between them.

The first installation has no people saved. You can start web chat with its
default identity or [seed five fictional profiles](hola/context-api/README.md#synthetic-demo-profiles).
Profiles and the shared system prompt are managed through the
[context API](http://localhost:8090/docs), using `CONTEXT_ADMIN_TOKEN` from `.env`.

## Deploy and use

| Task | Guide |
| --- | --- |
| Understand services, configuration, and Orange | [Phone agent stack](hola/README.md) |
| Place an outbound call or receive incoming calls | [Profiles and calls](hola/README.md#profiles-and-calls) |
| Use the browser interface | [Web chat](hola/web-chat/README.md) |
| Manage people and the shared system prompt | [Context API](hola/context-api/README.md) |
| Retrieve a person's call history, recordings, and transcripts | [Call history and recordings](hola/context-api/README.md#call-history-and-recordings) |
| Set callback timing and inspect bookings and summaries | [Follow-up calls and summaries](hola/context-api/README.md#follow-up-calls-and-summaries) |
| Read the product vision | [Project](DOCS/PROJECT.md) |

The stack is defined in [`compose.yaml`](compose.yaml) at the repository root,
with Compose project name `hola`. All service addresses inside the stack use
Docker DNS (with loopback between SIP and the Orange proxy); the advertised
host address and provider credentials vary
between computers. See the phone stack guide for calling and network details.

LiveKit credentials authenticate against our own server; a LiveKit Cloud account
is not required. GPT-Live runs through the OpenAI API, so call audio and supplied
context go to OpenAI for inference. Scheduling tools use Responses delegation
with `gpt-5.6-luna`; post-call summaries also use that model and send the final
transcript to OpenAI.

## Current behavior and limits

People have stable IDs and can share phone numbers. Outbound calls select the
person explicitly; their saved number must match the dialled number. Incoming
calls from shared numbers need a person-selection flow that is not implemented.
Phone-number matching alone does not verify identity.

The agent loads the saved profile and shared prompt before starting conversation.
The agent proposes a follow-up based on the conversation, agrees an exact time
and timezone, and saves it through the API. Global limits default to **48–168
hours from the current call's start**, editable through `PUT /settings`.
The existing API container automatically dials due bookings through Orange;
the person must have a saved phone number. Cancellation and future-call opt-out
are supported. See the API guide for timing and failure behavior.
Each agent audio session records audio and transcripts to persistent local
storage; abrupt failures can leave partial recordings. The API exposes recording
status and admin-only retrieval.

After finalization, the API generates a structured summary with topics, reported
facts, and follow-up topics. Earlier transcripts and summaries are stored but
are not automatically loaded as memory.
Automatic profile updates, sharing news between friends and family, sharing
permissions, and wellbeing escalation remain unimplemented parts of the vision.
Recording permission management, automatic retention, encryption at rest, and
backups are also pending.
