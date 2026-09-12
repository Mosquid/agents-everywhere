# hola web chat interface

Talk to the deployed LiveKit agent through typed chat or a microphone. For telephone setup and calls, use the
[phone stack guide](../README.md).

## Run

Follow the [root quick start](../../README.md#run-hola). The web chat is built and
started by `docker compose up -d --build`, including its locked browser SDK.
Open [localhost:8092](http://localhost:8092). No separate Python or Node server
needs to be started.

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
with an `rtc:` external key directly from the context API. The API admin token stays on the server. Only person IDs, names, and
languages are sent to the browser. The server validates the selection and uses
that person's browser identity in the room token. The selector is locked during
a session. The default option uses `chat-tester`, resolved as `rtc:chat-tester`.

The agent links each call to the selected person and loads the shared prompt
and their profile. Earlier transcripts are not automatically loaded into the
conversation. There is no individual user authentication.

Audio and transcripts are saved using the deployed agent's recording path,
including typed messages and agent audio when playback is muted. With the mic
off, the person's audio channel contains generated silence. Retrieve these calls
through the [context API](../context-api/README.md). Recording starts
with the agent audio session and can remain incomplete after an abrupt failure.

The local microphone meter measures input; agent state and recognition feedback
are separate signals. Docker publishes the web server on host loopback and checks the token request's
Origin. Credentials stay on the server; the browser receives a 30-minute room
token. The SDK is locked by `package-lock.json`. This tool does not test SIP
routing, carrier audio, or real call-answer timing.
