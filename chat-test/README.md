# Browser chat test

Test the deployed GPT-Live agent without dialing a phone number or using a microphone.

## Run

From the repository root, using Python 3.12:

```sh
python3.12 -m venv .venv-livekit
.venv-livekit/bin/pip install -r livekit/requirements.txt
npm ci --prefix chat-test
.venv-livekit/bin/python chat-test/server.py
```

Create `livekit/.env` with the existing server's `LIVEKIT_API_KEY` and
`LIVEKIT_API_SECRET`. Never commit that file. The prototype targets
`ws://192.168.1.195:7880` and requires access to that LAN.
Open http://localhost:8092 and click **Start test**. Click **End test** when done.

## How it works

1. The local server issues a short-lived token for a new test room.
2. The browser joins the room, and the deployed agent joins automatically.
3. The client sends a visible test-setup message saying the simulated recipient
   answered and asking the agent to greet them. This is an ordinary `lk.chat`
   message, not a real SIP event or a replacement system prompt.
4. You type replies over `lk.chat`; the UI displays the agent's
   `lk.transcription` streams.

The browser sends generated silence to keep GPT-Live processing. It never asks
for microphone access and attaches no audio playback element. GPT-Live still
produces audio internally, so its normal API charges apply; there are no Orange
calls or telephone charges from this client.

This tests the real deployed model with its default prompt, without selecting a
recipient profile. Sessions follow the deployed agent's current recording and
persistence behavior. It does not test SIP routing, carrier audio, or actual
call-answer timing.

The HTTP server binds only to loopback and validates the token request's Origin.
API credentials stay on the server; the browser receives only a room token.
The client SDK is pinned by package-lock.json.

Verified: typed conversation with correct recall across two turns. An earlier
experiment without the generated silence produced no model reply.

Verified automatic opening: Start test produced “Hi there! Thanks for picking up—how’s your day going?” without user speech or a phone call.
