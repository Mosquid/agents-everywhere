"""Benchmark direct GPT-Live responses with real-time PCM input."""
import argparse
import asyncio
import base64
import json
import os
import statistics
import struct
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parent
INSTRUCTIONS = ('Do not greet. Listen to the user and directly repeat the requested '
                'phrase once. Do not delegate. No explanation or extra speech.')


def fixture():
    with wave.open(str(ROOT / 'input.wav')) as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
            raise ValueError('Expected mono PCM16 at 24 kHz')
        pcm = wav.readframes(wav.getnframes())
    voiced = [i for i, (value,) in enumerate(struct.iter_unpack('<h', pcm)) if abs(value) > 200]
    if not voiced:
        raise ValueError('Fixture has no detectable speech')
    speech_end_ms = 500 + (voiced[-1] + 1) / 24
    clip = bytes(24000) + pcm + bytes(48000 * 10)
    clip += bytes(-len(clip) % 960)
    return clip, speech_end_ms


def new_result(trial):
    return dict(trial=trial, firstAudioPacketMs=None, firstNonSilentAudioMs=None,
                firstOutputTextMs=None, transcript='', inputTranscript='',
                delegations=0, usage=None, maxSendLatenessMs=0)


async def run_session(client, clip, speech_end_ms, turns, first_trial, directory, cap):
    results = [new_result(first_trial)]
    output, events = [], []
    opened = time.perf_counter()
    stream_start = None
    turn_start = None
    sender = None
    finalized = False
    try:
        async with asyncio.timeout(cap):
            async with client.ws_connect('wss://api.openai.com/v1/live/sessions',
                    headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY']}) as ws:
                await ws.send_json({'type': 'session.start', 'session': {
                    'model': 'gpt-live-1', 'instructions': INSTRUCTIONS,
                    'audio': {'format': {'type': 'audio/pcm', 'rate': 24000},
                              'output': {'voice': 'marin'}},
                    'delegation': {'type': 'client'}}})

                async def send_audio():
                    nonlocal turn_start
                    for offset in range(0, len(clip) * turns, 960):
                        target = stream_start + offset / 48000
                        await asyncio.sleep(max(0, target - time.perf_counter()))
                        local_offset = offset % len(clip)
                        if offset and local_offset == 0:
                            results.append(new_result(first_trial + len(results)))
                            turn_start = target
                        result = results[-1]
                        result['maxSendLatenessMs'] = max(result['maxSendLatenessMs'],
                                                         (time.perf_counter() - target) * 1000)
                        await ws.send_json({'type': 'session.input_audio.append',
                            'audio': base64.b64encode(clip[local_offset:local_offset+960]).decode()})
                    await ws.send_json({'type': 'session.close'})

                async for message in ws:
                    if message.type == aiohttp.WSMsgType.ERROR:
                        raise RuntimeError('WebSocket transport error')
                    if message.type != aiohttp.WSMsgType.TEXT:
                        continue
                    event = json.loads(message.data)
                    now = time.perf_counter()
                    kind = event['type']
                    events.append({**event, 'elapsedMs': (now-opened)*1000,
                        **({'delta':'[saved as PCM]'} if kind == 'session.output_audio.delta' else {})})
                    result = results[-1]
                    if kind == 'error':
                        raise RuntimeError(event.get('error', {}).get('message', 'API error'))
                    if kind == 'session.started':
                        result['startupMs'] = (now-opened)*1000
                        stream_start = turn_start = time.perf_counter()
                        sender = asyncio.create_task(send_audio())
                    latency = None if turn_start is None else (now-turn_start)*1000-speech_end_ms
                    if kind == 'session.output_audio.delta':
                        audio = base64.b64decode(event['delta'])
                        output.append(audio)
                        if result['firstAudioPacketMs'] is None:
                            result['firstAudioPacketMs'] = latency
                        if any(abs(value) > 200 for (value,) in struct.iter_unpack('<h', audio)):
                            if result['firstNonSilentAudioMs'] is None:
                                result['firstNonSilentAudioMs'] = latency
                            result['lastNonSilentAudioMs'] = latency
                    elif kind == 'session.output_transcript.delta':
                        if result['firstOutputTextMs'] is None:
                            result['firstOutputTextMs'] = latency
                        result['transcript'] += event['delta']
                    elif kind == 'session.input_transcript.delta':
                        result['inputTranscript'] += event['delta']
                    elif kind == 'session.delegation.created':
                        result['delegations'] += 1
                    elif kind == 'session.closed':
                        result['usage'] = event.get('usage')
                        finalized = True
                        break
                if sender and sender.done():
                    sender.result()
                if not finalized:
                    raise RuntimeError('Session ended without final usage')
    except Exception as error:
        results[-1]['error'] = str(error) or type(error).__name__
    finally:
        if sender:
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)
        (directory / f'trial-{first_trial}.pcm').write_bytes(b''.join(output))
        (directory / f'trial-{first_trial}.events.json').write_text(json.dumps(events, indent=2))
    return results


async def main(args):
    clip, speech_end_ms = fixture()
    print(f'Estimated input speech end: {speech_end_ms:.2f} ms; threshold 200/32768')
    if args.check:
        return
    if not os.environ.get('OPENAI_API_KEY'):
        raise SystemExit('Export OPENAI_API_KEY before running the benchmark')
    turns = args.turns if args.multiturn else 1
    sessions = 1 if args.multiturn else args.trials
    stamp = datetime.now(timezone.utc).isoformat().replace(':', '-')
    directory = ROOT / 'results' / (('multiturn-' if args.multiturn else '') + stamp)
    directory.mkdir(parents=True)
    results = []
    async with aiohttp.ClientSession() as client:
        for trial in range(1, sessions+1):
            cap = max(22, turns*len(clip)/48000+20) if args.multiturn else 22
            batch = await run_session(client, clip, speech_end_ms, turns, trial, directory, cap)
            results.extend(batch)
            (directory / 'results.json').write_text(json.dumps(results, indent=2))
            print(json.dumps(batch, indent=2))
            if any('error' in row for row in batch):
                break
    valid = [r for r in results if 'error' not in r and not r['delegations'] and r['firstNonSilentAudioMs'] is not None]
    latencies = [r['firstNonSilentAudioMs'] for r in valid]
    later = [r['firstNonSilentAudioMs'] for r in valid if r['trial'] > 1]
    print(json.dumps({'validTrials':len(valid), 'medianMs':statistics.median(latencies) if latencies else None,
        'minMs':min(latencies, default=None), 'maxMs':max(latencies, default=None),
        **({'laterTurnMedianMs':statistics.median(later) if later else None} if args.multiturn else {}),
        'results':str(directory)}, indent=2))
    if any('error' in r for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate input without API access')
    parser.add_argument('--multiturn', action='store_true', help='Reuse one session across turns')
    parser.add_argument('--trials', type=int, default=5)
    parser.add_argument('--turns', type=int, default=10)
    args = parser.parse_args()
    if args.trials < 1 or args.turns < 1:
        parser.error('Trials and turns must be positive')
    asyncio.run(main(args))
