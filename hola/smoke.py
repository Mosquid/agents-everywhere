"""Send input.wav through the deployed LiveKit room and save returned audio."""
import asyncio
import time
import os
import wave
from pathlib import Path
import numpy as np
from livekit import api, rtc

async def main():
    env = os.environ
    name = f'gpt-live-smoke-{int(time.time())}'
    token = (api.AccessToken(env['LIVEKIT_API_KEY'], env['LIVEKIT_API_SECRET'])
             .with_identity('smoke-client').with_grants(api.VideoGrants(room_join=True, room=name)).to_jwt())
    room = rtc.Room()
    ready = asyncio.Event()
    chunks, tasks = [], []
    async def receive(track):
        stream = rtc.AudioStream(track, sample_rate=24000, num_channels=1)
        try:
            async for event in stream:
                chunks.append(bytes(event.frame.data))
        finally:
            await stream.aclose()
    @room.on('track_subscribed')
    def subscribed(track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            tasks.append(asyncio.create_task(receive(track)))
            ready.set()
    try:
        await room.connect(os.environ.get('LIVEKIT_URL', 'ws://localhost:7880'), token)
        source = rtc.AudioSource(24000, 1, queue_size_ms=100)
        track = rtc.LocalAudioTrack.create_audio_track('smoke-microphone', source)
        await room.local_participant.publish_track(track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
        await asyncio.wait_for(ready.wait(), 45)
        await asyncio.sleep(3)
        with wave.open(str(Path(__file__).parent.parent / 'input.wav')) as w:
            assert w.getframerate() == 24000 and w.getnchannels() == 1 and w.getsampwidth() == 2
            pcm = w.readframes(w.getnframes())
        pcm += bytes(24000 * 2 * 12)
        for offset in range(0, len(pcm), 960):
            block = pcm[offset:offset+960].ljust(960, b'\0')
            await source.capture_frame(rtc.AudioFrame(block, 24000, 1, 480))
        await source.wait_for_playout()
    finally:
        await room.disconnect()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    audio = b''.join(chunks)
    output = Path(__file__).parent.parent / 'results' / f'{name}.wav'
    output.parent.mkdir(exist_ok=True)
    with wave.open(str(output), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(audio)
    samples = np.frombuffer(audio, dtype=np.int16).astype(float)
    voiced = int(np.count_nonzero(np.abs(samples) > 300))
    assert voiced > 2400, f'No substantial returned speech: {voiced} samples'
    print(f'PASS: received speech through LiveKit; recording: {output}')

asyncio.run(main())
