# GPT-Live direct-response latency check

This tests five fresh GPT-Live-1 sessions with a prerecorded synthetic English
utterance, paced at real time in 20 ms chunks. Client delegation is configured;
no backend model is called. Any delegation request is counted and excludes that
trial from the latency summary.

Install `requirements.txt` in a Python environment. Export `OPENAI_API_KEY`
(or load your existing `.env` into the shell), then run:

```sh
python benchmark.py
```

The fixture asks: “Repeat exactly: the blue bicycle is beside the window.”
It was generated locally using:

```sh
say -o input.wav --data-format=LEI16@24000 --channels=1 'Repeat exactly: the blue bicycle is beside the window.'
```

Run `python benchmark.py --check` to check the fixture without API access.

Metrics are measured on the client: estimated input speech end to first received
audio packet, first packet containing non-silent audio, and first output text.
Speech end uses an amplitude threshold of 200/32768. These are approximate
network-inclusive response latencies, not playback latency or backend text TTFT.
Negative values indicate output before estimated speech end. Startup is separate.
Raw output PCM (mono 24 kHz signed 16-bit little-endian), transcripts, event logs,
and usage are saved under `results/`. Check transcripts for a correct response;
the latency summary does not grade answer correctness. Five trials are a smoke
test, not a reliable p95 estimate.

Each trial is capped at 22 seconds including connection setup. Five such voice
sessions are approximately $0.092 at $0.05/min if all cap time were billable.
No backend costs are incurred by this runner.

## Multi-turn comparison

Run `python benchmark.py --multiturn` to send the same fixture ten
times in one continuous session, retaining the original instructions and voice.
Each turn includes the same 500 ms leading silence and ten seconds of trailing
silence. Audio is padded to complete 20 ms chunks. The session is capped at
the input duration plus 20 seconds. Results are in `results/multiturn-*`.
`usage` on the final turn is the whole session's usage, not that turn alone.
`lastNonSilentAudioMs` helps check that output finished before the next input.
Compare turn 1 with turns 2–10; repetition also changes conversation context,
so any improvement cannot specifically establish a cache effect.

References:
- https://developers.openai.com/api/docs/guides/voice-websockets?api=live
- https://developers.openai.com/api/docs/guides/live-delegation

Use `--trials 1` for one fresh session, or `--multiturn --turns 2` for a
short two-turn check. The runner uses aiohttp WebSockets directly.
