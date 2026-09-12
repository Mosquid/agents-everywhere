import OpenAI from 'openai';
import { LiveWS } from 'openai/resources/live/ws';
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';

// Fixture: mono PCM16 little-endian, 24 kHz, generated with macOS say.
const wav = readFileSync(new URL('./input.wav', import.meta.url));
let pcm;
for (let offset = 12; offset + 8 <= wav.length;) {
  const size = wav.readUInt32LE(offset + 4);
  const name = wav.toString('ascii', offset, offset + 4);
  if (name === 'fmt ' && (wav.readUInt16LE(offset + 8) !== 1 ||
      wav.readUInt16LE(offset + 10) !== 1 || wav.readUInt32LE(offset + 12) !== 24000 ||
      wav.readUInt16LE(offset + 22) !== 16)) throw new Error('Expected mono PCM16 at 24 kHz');
  if (name === 'data') pcm = wav.subarray(offset + 8, offset + 8 + size);
  offset += 8 + size + (size % 2);
}
if (!pcm?.length) throw new Error('Missing WAV audio');
let lastSpeechSample = 0;
for (let i = 0; i < pcm.length; i += 2) {
  if (Math.abs(pcm.readInt16LE(i)) > 200) lastSpeechSample = i / 2;
}
const speechEndMs = 500 + (lastSpeechSample + 1) / 24;
const input = Buffer.concat([Buffer.alloc(24000), pcm, Buffer.alloc(48000 * 10)]);
console.log(`Fixture: ${pcm.length / 48000}s, estimated speech end: ${speechEndMs}ms (threshold 200/32768)`);
if (process.argv.includes('--check')) process.exit(0);
if (!process.env.OPENAI_API_KEY) throw new Error('Set OPENAI_API_KEY locally or use node --env-file=.env benchmark.mjs');

const directory = new URL(`./results/${new Date().toISOString().replaceAll(':', '-')}/`, import.meta.url);
mkdirSync(directory, { recursive: true });
const results = [];
for (let trial = 1; trial <= 5; trial++) {
  const result = { trial, firstAudioPacketMs: null, firstNonSilentAudioMs: null,
    firstOutputTextMs: null, transcript: '', inputTranscript: '', delegations: 0,
    usage: null, maxSendLatenessMs: 0 };
  const output = [];
  const events = [];
  const opened = performance.now();
  const ws = new LiveWS(new OpenAI());
  let streamStart, stopped = false, finalized = false, sender;
  const deadline = setTimeout(() => ws.close(), 22000);
  try {
    for await (const item of ws) {
      if (item.type === 'open') ws.send({ type: 'session.start', session: {
        model: 'gpt-live-1',
        instructions: 'Do not greet. Listen to the user and directly repeat the requested phrase once. Do not delegate. No explanation or extra speech.',
        audio: { format: { type: 'audio/pcm', rate: 24000 }, output: { voice: 'marin' } },
        delegation: { type: 'client' },
      } });
      if (item.type === 'error') throw new Error(item.error.message);
      if (item.type !== 'message') continue;
      const event = item.message;
      const now = performance.now();
      events.push({ elapsedMs: now - opened, ...event,
        ...(event.type === 'session.output_audio.delta' ? { delta: '[saved as PCM]' } : {}) });
      if (event.type === 'session.started') {
        result.startupMs = now - opened;
        streamStart = performance.now();
        sender = (async () => {
          for (let offset = 0; offset < input.length && !stopped; offset += 960) {
            const target = streamStart + offset / 48;
            await sleep(Math.max(0, target - performance.now()));
            if (stopped) break;
            result.maxSendLatenessMs = Math.max(result.maxSendLatenessMs, performance.now() - target);
            ws.send({ type: 'session.input_audio.append', audio: input.subarray(offset, offset + 960).toString('base64') });
          }
          if (!stopped) ws.send({ type: 'session.close' });
        })();
      }
      const latency = streamStart === undefined ? null : now - streamStart - speechEndMs;
      if (event.type === 'session.output_audio.delta') {
        const bytes = Buffer.from(event.delta, 'base64');
        output.push(bytes);
        result.firstAudioPacketMs ??= latency;
        for (let i = 0; i + 1 < bytes.length; i += 2) {
          if (Math.abs(bytes.readInt16LE(i)) > 200) { result.firstNonSilentAudioMs ??= latency; break; }
        }
      }
      if (event.type === 'session.output_transcript.delta') {
        result.firstOutputTextMs ??= latency;
        result.transcript += event.delta;
      }
      if (event.type === 'session.input_transcript.delta') result.inputTranscript += event.delta;
      if (event.type === 'session.delegation.created') result.delegations++;
      if (event.type === 'session.closed') { result.usage = event.usage; finalized = true; break; }
    }
    if (!finalized) throw new Error('Session ended without final usage');
  } catch (error) {
    result.error = error.message;
  } finally {
    stopped = true;
    clearTimeout(deadline);
    ws.close();
    await sender;
    writeFileSync(new URL(`trial-${trial}.pcm`, directory), Buffer.concat(output));
    writeFileSync(new URL(`trial-${trial}.events.json`, directory), JSON.stringify(events, null, 2));
  }
  results.push(result);
  writeFileSync(new URL('results.json', directory), JSON.stringify(results, null, 2));
  console.log(result);
  if (result.error) break;
}
const valid = results.filter(r => !r.error && !r.delegations && r.firstNonSilentAudioMs !== null);
const sorted = valid.map(r => r.firstNonSilentAudioMs).sort((a, b) => a - b);
console.log({ validTrials: valid.length, medianMs: sorted[Math.floor(sorted.length / 2)],
  minMs: sorted[0], maxMs: sorted.at(-1), results: directory.pathname });
