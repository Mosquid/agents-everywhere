# Self-hosted GPT-Live test stack

Linux Docker Compose stack: LiveKit, Redis, LiveKit SIP, and a Python GPT-Live
agent. The agent automatically joins new rooms and answers directly without a
backend LLM, matching the earlier latency tests.

Deployed on 192.168.1.195 at `/home/inlanger/stacks/gpt-live` on 2026-09-12.
All five containers are running, including the copied Orange registration proxy. Agent registration, its health endpoint, and a
real WebRTC audio round trip to GPT-Live were verified.

Create `.env` in this directory with:

```dotenv
LIVEKIT_NODE_IP=192.168.1.195
LIVEKIT_API_KEY=<generated-key>
LIVEKIT_API_SECRET=<generated-secret>
OPENAI_API_KEY=<existing-openai-key>
```

Use long random LiveKit credentials. The Docker build excludes environment
files; secrets are injected only at runtime. Keep `.env` mode 600.

```sh
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=80 livekit sip agent
```

LAN signaling is `ws://192.168.1.195:7880`; WebRTC uses TCP 7881 and UDP 7882.
SIP uses 5060 and RTP 10000–20000. Redis binds only to loopback port 16379.
The agent health endpoint is on loopback port 8089.

This is a LAN configuration, without public NAT routing or TLS termination.
Browser microphone use requires a secure frontend origin (HTTPS or localhost).
Orange registration uses `orange-proxy/`, copied unchanged from the concierge.
Its original runtime credentials are in remote `orange.env` (mode 600), excluded
from version control. Compose overrides the proxy destination to the new SIP
listener at 192.168.1.195 and disables verbose SIP tracing. Orange registration
succeeded with a 3600-second expiry.

Inbound trunk: `ST_hfGm3TsBdmVD` (restricted to the local proxy address).
Outbound trunk: `ST_RE9wbCUnkKhk` (through the proxy on port 5064).
Dispatch: `SDR_U9cENvuD2cET`, creates an `orange-` room per incoming call;
the unnamed GPT-Live agent joins automatically. No old concierge agent metadata
is used. An actual telephone call is still needed to verify carrier audio.

Recheck or provision the trunks on the server:
```sh
docker run --rm -i --network host --env-file .env --env-file orange.env gpt-live-agent python - < setup-orange.py
```

Stopped concierge containers: `livekit-agent`, `voxcpm2-tts`, `livekit-server`,
`livekit-sip`, `text-normalizer`, `orange-sip-proxy`, `livekit-redis`, and `call-api`.
Their containers, images, volumes, and deployment files are preserved.
The old Orange proxy remains stopped; its copy runs in this new stack.
The old call API remains stopped. Outbound dialing is configured at the trunk
level, but no calling tool or call API is connected to the GPT-Live agent.

Run the local end-to-end check from the workspace with
`.venv-livekit/bin/python livekit/smoke.py`. It sends the existing `input.wav`
through a fresh room, checks for returned speech, and saves a WAV in `results/`.
This checks audio transport and model response, not transcription accuracy or latency.

Sources:
- https://docs.livekit.io/transport/self-hosting/sip-server/
- https://docs.livekit.io/agents/models/realtime/plugins/gpt-live/
- https://docs.livekit.io/deploy/custom/deployments/
