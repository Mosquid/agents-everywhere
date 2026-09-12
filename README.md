# hola.world

**A social network through phone calls.**

![hola illustrated story: a phone conversation connects someone with a friend and helps arrange social support.](https://hola-care-spain.roman-rodomansky.chatgpt.site/assets/hola-illustrated-story.png)

hola helps people stay connected through ordinary phone conversations. The vision is a proactive AI agent that listens, remembers, and connects people with friends, family, and their wider circle.

The project starts with older adults and families, while exploring how the same approach can support younger adults and people settling into a new country. The experience centres on a familiar interaction: answering a phone call and talking about your week.

[Project website and presentation](https://hola-care-spain.roman-rodomansky.chatgpt.site) · [Technical project vision](DOCS/PROJECT.md)

## Why hola?

Loneliness can affect people at any age. Our presentation explores this challenge in Spain and across Europe, and asks how regular conversations can help people feel more connected.

hola aims to make staying in touch easier: a short call becomes an opportunity to share news, hear about loved ones, make plans, and ask for support.

## The experience we are building

The website presents this intended journey:

1. **Receive a regular phone call.** The agent checks in, initially around once a week.
2. **Talk about your week.** Spend a few minutes sharing everyday experiences, stories, and concerns.
3. **Hear news from your circle.** Learn what friends and family have been doing.
4. **Keep your network updated.** Share appropriate updates with the people you choose.
5. **Connect with support when needed.** Bring relevant concerns to chosen contacts.

For example, hearing that a friend is making paella next week could become the starting point for a conversation or a plan to meet.

**This is the product vision. The current prototype implements the calling and conversation infrastructure; network sharing, persistent conversational memory, scheduling, and support escalation are still planned.**

## Current prototype

The prototype makes and receives calls through Orange SIP. A Python agent uses OpenAI GPT-Live for conversation, loads the person's background and a shared system prompt from a local API, and saves audio and transcripts linked to that person.

The stack includes:

| Component | Purpose |
| --- | --- |
| OpenAI GPT-Live | Voice conversation |
| Python agent | Conversation orchestration and profile loading |
| LiveKit and SIP | Real-time audio and telephone integration |
| Orange SIP proxy | Carrier registration and call connectivity |
| Context API | Profiles, shared prompt, and call history |
| Web chat | Browser interface for trying the agent |
| Redis | Supporting infrastructure |
| Docker Compose | Local configuration and service deployment |

LiveKit credentials authenticate against our own server; a LiveKit Cloud account is not required.

## Run hola

### Prerequisites

- Docker with Compose: Docker Desktop on macOS/Windows, or Docker Engine with Compose on Linux.
- Python 3.10 or newer for the one-time configuration command.
- An OpenAI API key with GPT-Live access.
- Your Orange SIP username, password, and telephone number.
- A network on which your Orange SIP account can register and exchange audio.

### Start the stack

Clone this repository and run these commands from its root directory:

```sh
python3 hola/configure.py
docker compose up -d --build
```

On Windows, use `py hola/configure.py` if Python is installed as `py`.

Configuration asks for this computer's LAN IPv4 address and provider credentials, generates the internal keys, and saves them in the root `.env`.

Existing values are preserved, including blank values. Edit incorrect or blank settings in `.env` directly. The script does not import credentials from older `hola/.env` or `orange.env` files.

Never commit the root `.env`. If your LAN address changes, update `HOLA_HOST_IP` there and run:

```sh
docker compose up -d
```

### Open the browser interface

Open [hola web chat](http://localhost:8092).

The same Compose stack runs LiveKit, SIP, Orange registration, Redis, the agent, the context API, and the web chat. There are seven running services plus `sip-setup`, which provisions trunks and exits.

**`Exited (0)` for `sip-setup` means success.**

No SSH access, Node.js installation, or connection to another teammate's server is needed. First startup downloads images and builds the Python services.

### Check service status

```sh
docker compose ps -a
docker compose logs --tail=50 agent orange-sip-proxy sip-setup
```

Container startup alone does not verify a carrier call. Keep the published voice/SIP ports reachable on your network.

Avoid simultaneous registration of one Orange account on multiple computers; it can redirect incoming calls between them.

### Add profiles

The first installation has no people saved. You can start web chat with its default identity or [seed five fictional profiles](hola/context-api/README.md#synthetic-demo-profiles).

Manage profiles and the shared system prompt through the [context API](http://localhost:8090/docs), using `CONTEXT_ADMIN_TOKEN` from `.env`.

### Stop the stack

```sh
docker compose down
```

This preserves profiles and recordings.

**`docker compose down -v` deletes the stored data.**

## Deploy and use

| Task | Guide |
| --- | --- |
| Understand services, configuration, and Orange | [Phone agent stack](hola/README.md) |
| Place an outbound call or receive incoming calls | [Profiles and calls](hola/README.md#profiles-and-calls) |
| Use the browser interface | [Web chat](hola/web-chat/README.md) |
| Manage people and the shared system prompt | [Context API](hola/context-api/README.md) |
| Retrieve call history, recordings, and transcripts | [Call history and recordings](hola/context-api/README.md#call-history-and-recordings) |
| Read the product vision | [Project](DOCS/PROJECT.md) |
| Explore the presentation and demo | [Project website](https://hola-care-spain.roman-rodomansky.chatgpt.site) |

The stack is defined in [`compose.yaml`](compose.yaml) at the repository root, with Compose project name `hola`.

Service addresses inside the stack use Docker DNS, with loopback between SIP and the Orange proxy. The advertised host address and provider credentials vary between computers. See the phone stack guide for calling and network details.

## Current behavior and limits

### Profiles and identity

People have stable IDs and can share phone numbers. Outbound calls select the person explicitly; their saved number must match the dialled number.

Incoming calls from shared numbers need a person-selection flow that is not implemented. Phone-number matching alone does not verify identity.

### Conversation and memory

The agent loads the saved profile and shared prompt before starting a conversation.

The initial prompt is a generic conversation-test prompt. It does not implement the full social-network workflow presented on the website.

Earlier transcripts are stored but are not automatically loaded as memory. Automatic profile updates and sharing news between friends and family are not implemented.

### Recordings and data

Each agent audio session records audio and transcripts to persistent local storage. Abrupt failures can leave partial recordings. The API exposes recording status and admin-only retrieval.

GPT-Live runs through the OpenAI API, so call audio and supplied context go to OpenAI for inference.

Recording permission management, sharing permissions, automatic retention, encryption at rest, and backups remain pending.

## Roadmap

The website outlines several directions for future development:

- **Adaptive call timing:** adjust the next check-in based on the conversation and the person's situation.
- **Conversational memory:** use previous conversations to maintain continuity and update profiles.
- **Updates within a chosen circle:** exchange news with friends and family through explicit sharing permissions.
- **Support escalation:** notify chosen contacts when a situation needs attention.
- **Autobiography feed:** preserve life stories shared during conversations.
- **A familiar point of contact:** let people call the agent whenever they want to talk.
- **Shared activities:** suggest someone in the person's circle to invite to an activity.
- **Monthly life snapshots:** create recaps, with optional sharing on X after approval.
- **Possible wellbeing changes:** explore flagging mental-health or dementia-related changes for professional review. These concepts require clinical validation.

These are planned capabilities and research directions.

## Who could use hola?

The presentation explores two routes:

- **B2C:** families who want to stay connected with parents and relatives.
- **B2G2C:** government programmes that help residents build and maintain social connections.

The long-term goal is simple: make an ordinary phone call a regular opportunity for connection, shared stories, and support.
