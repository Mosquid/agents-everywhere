# hola

A phone-based social network for older adults. The [project vision](DOCS/PROJECT.md)
is to help people stay connected with friends and family through ordinary phone
conversations.

The current prototype makes and receives calls through Orange SIP. A Python
agent uses OpenAI GPT-Live for conversation, loads the person's background and
a shared system prompt from a local API, and saves audio and transcripts linked
to that person.

## Deploy and use

| Task | Guide |
| --- | --- |
| Deploy the containers and connect Orange | [Phone agent stack](hola/README.md) |
| Place an outbound call or receive incoming calls | [Profiles and calls](hola/README.md#profiles-and-calls) |
| Manage people and the shared system prompt | [Context API](hola/context-api/README.md) |
| Retrieve a person's call history, recordings, and transcripts | [Call history and recordings](hola/context-api/README.md#call-history-and-recordings) |
| Read the product vision | [Project](DOCS/PROJECT.md) |

The stack is defined in [`compose.yaml`](compose.yaml) at the repository root,
with Compose project name `hola`. Start with the phone stack guide. The current deployment targets a Linux host
on the LAN, with self-hosted LiveKit, its SIP service, an Orange registration
proxy, Redis, the Python agent, and the context API with SQLite.

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

## Developer checks

The [latency benchmark](benchmark.py) tests GPT-Live directly and excludes
the telephone path. The [browser tester](chat-test/README.md) is an optional
local development tool for exercising the deployed agent without a phone call.
