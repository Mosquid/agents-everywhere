# hola web chat interface

Talk to the deployed LiveKit agent through typed chat or a microphone. For telephone setup and calls, use the
[phone stack guide](../README.md).

## Setup and run

You need Python 3.12, Node.js with npm, LAN access, and an already running phone
stack including the agent and context API. The interface's server URL is fixed in
`server.py` to `ws://192.168.1.195:7880`.

From the repository root:

```sh
python3.12 -m venv .venv-livekit
.venv-livekit/bin/pip install -r hola/requirements.txt
npm ci --prefix hola/web-chat
```

Before starting the server, ensure `hola/.env` contains the existing
self-hosted LiveKit server's credentials. Reuse the file if already configured;
otherwise create it with these matching server values:

```dotenv
LIVEKIT_API_KEY=<existing-local-livekit-key>
LIVEKIT_API_SECRET=<existing-local-livekit-secret>
```

Use plain `KEY=value` lines without quotes or `export`; the server reads the
file directly. Never commit it. These are credentials for our local LiveKit
server. OpenAI access is configured on the deployed agent.

```sh
.venv-livekit/bin/python hola/web-chat/server.py
```

Open [localhost:8092](http://localhost:8092), click **Start test**, and use
**End test** to disconnect. Microphone and playback start off. Enable them with
**Enable microphone** and **Enable sound**. Ending the test stops capture and
playback. Localhost supports browser microphone permission.

## Behavior and persistence

Each test creates a new room. A visible `lk.chat` message describes a simulated
pickup and asks the agent to greet you. Typed replies use `lk.chat`; the UI
shows `lk.transcription` streams. Generated silence keeps the audio track active
when the mic is off. GPT-Live still generates speech with playback muted, so
OpenAI charges apply. The web chat interface does not dial or incur Orange telephone charges.

Choose **Recipient context** before starting. The selector loads saved profiles
with an `rtc:` external key over SSH to `192.168.1.195`; local SSH access is
required. The API admin token stays on the server. Only person IDs, names, and
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
are separate signals. The server binds to loopback and checks the token request's
Origin. Credentials stay on the server; the browser receives a 30-minute room
token. The SDK is locked by `package-lock.json`. This tool does not test SIP
routing, carrier audio, or real call-answer timing.
