# hola web chat interface

Talk to the agent in your local Compose stack through typed chat or a microphone.
For telephone setup and calls, use the [phone stack guide](../README.md).

## Run

Follow the [root quick start](../../README.md#run-hola). The web chat is built and
started by `docker compose up -d --build`, including its locked browser SDK.
Open [localhost:8092](http://localhost:8092) on the computer running Docker.
No separate Python or Node server needs to be started. The published interface
and accepted token origins are local-only; opening it through a LAN IP is not
supported by the current configuration.

Click **Start test**, then type or enable the microphone and sound. Click
**End test** to disconnect. Microphone and playback start off. Ending a session
stops capture and playback.

The container uses `CONTEXT_API_URL` to contact the API directly and
`LIVEKIT_PUBLIC_URL` for the address handed to the browser. Compose sets these
to `http://context-api:8090` and `ws://localhost:7880`. API credentials stay on
the server, and the token endpoint accepts only the local web chat origins.

## Behavior and persistence

Each test creates a new room. A visible `lk.chat` message describes a simulated
pickup and asks the agent to greet you. Typed replies use `lk.chat`; the UI
shows `lk.transcription` streams. Generated silence keeps the audio track active
when the mic is off. GPT-Live still generates speech with playback muted, so
OpenAI charges apply. The web chat interface does not dial or incur Orange telephone charges.

Choose **Recipient context** before starting. The selector loads saved profiles
with an `rtc:` external key and nonempty background directly from the context
API. The API admin token stays in the web server container. Only person IDs,
names, and languages are sent to the browser. The server validates the selection and uses
that person's browser identity in the room token. The selector is locked during
a session. The default option uses `chat-tester`, resolved as `rtc:chat-tester`.
Repeated default sessions share that person record and call history. A fresh
installation has only the default option until you
[seed or create profiles](../context-api/README.md#synthetic-demo-profiles).
Refresh the page after adding profiles.

The agent links each call to the selected person and loads the shared prompt
and their profile. Earlier transcripts are not automatically loaded into the
conversation. There is no individual user authentication.

Audio and transcripts are saved using the deployed agent's recording path,
including typed messages and agent audio when playback is muted. With the mic
off, the person's audio channel contains generated silence. Retrieve these calls
through the [context API](../context-api/README.md). Recording starts
with the agent audio session and can remain incomplete after an abrupt failure.

The local microphone meter measures input; agent state and recognition feedback
are separate signals. Docker publishes the web server on host loopback; the
Python server checks the token request's Origin. Credentials stay on the server; the browser receives a 30-minute room
token. The SDK is locked by `package-lock.json`. This tool does not test SIP
routing, carrier audio, or real call-answer timing.

## If a session does not start

Run `docker compose ps -a` from the repository root, then inspect
`docker compose logs --tail=50 web-chat agent context-api livekit`.
An empty selector on a fresh database is normal. “Cannot load saved identities”
means the web server could not read the context API. A connected browser still
needs a registered agent and an OpenAI key with GPT-Live access to receive replies.

The first greeting can take several seconds. If replies time out, inspect the
agent logs; the UI's timeout alone cannot distinguish model delay from an API
or connection failure. For microphone input, grant permission when enabling it.
The local meter shows captured sound; recognized words appear separately.

Web chat behavior was verified locally on macOS with OrbStack on 2026-09-12.
See [stack verification](../README.md#troubleshooting-and-verification) for the
scope of that test and the automated test commands.
