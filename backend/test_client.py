#!/usr/bin/env python3
"""Local test harness that impersonates the Pico over the WebSocket.

It streams a 16 kHz / 16-bit / mono WAV in ~512-byte PCM frames, exactly
like the firmware will, so you can validate Deepgram -> Claude -> SQLite
before any hardware exists.

Usage:
    python test_client.py speech.wav
    python test_client.py speech.wav --url ws://localhost:8080/ws/voice

The WAV must be 16 kHz, mono, 16-bit PCM. Convert anything else with:
    ffmpeg -i input.m4a -ar 16000 -ac 1 -sample_fmt s16 speech.wav
"""
import argparse
import asyncio
import json
import os
import sys
import wave

import websockets

CHUNK_BYTES = 512  # matches the firmware's static PCM chunk buffer


def read_pcm(path: str) -> bytes:
    with wave.open(path, "rb") as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            sys.exit(
                f"WAV must be 16kHz/mono/16-bit; got "
                f"{w.getframerate()}Hz {w.getnchannels()}ch "
                f"{w.getsampwidth() * 8}-bit. See the ffmpeg line in this file."
            )
        return w.readframes(w.getnframes())


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("wav", help="16kHz/mono/16-bit PCM WAV file")
    ap.add_argument("--url", default="ws://localhost:8080/ws/voice")
    ap.add_argument(
        "--token",
        default=os.environ.get("PICO_AUTH_TOKEN", ""),
        help="defaults to $PICO_AUTH_TOKEN",
    )
    ap.add_argument("--device-id", default="pico-01")
    args = ap.parse_args()

    pcm = read_pcm(args.wav)
    print(f"Loaded {len(pcm)} bytes of PCM ({len(pcm) / 2 / 16000:.1f}s)")

    async with websockets.connect(args.url, max_size=None) as ws:
        await ws.send(json.dumps(
            {"type": "auth", "token": args.token, "device_id": args.device_id}
        ))
        print("<-", await ws.recv())  # expect {"type":"ready"}

        await ws.send(json.dumps({"type": "start"}))

        # Stream frames roughly at real time (16 bytes/sample-pair... 512B
        # of 16-bit mono = 256 samples = 16 ms). Sleeping keeps Deepgram's
        # pacing realistic.
        for i in range(0, len(pcm), CHUNK_BYTES):
            await ws.send(pcm[i:i + CHUNK_BYTES])
            await asyncio.sleep(0.016)

        await ws.send(json.dumps({"type": "stop"}))
        print("Sent stop; waiting for response...")

        reply = await ws.recv()
        print("<-", reply)
        data = json.loads(reply)
        if data.get("type") == "response":
            print("\n=== ASSISTANT ===\n" + data["text"])


if __name__ == "__main__":
    asyncio.run(main())
