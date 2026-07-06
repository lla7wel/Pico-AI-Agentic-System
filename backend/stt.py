"""Deepgram live streaming speech-to-text.

One DeepgramStreamer wraps a single utterance: open() starts a live
socket, send() forwards PCM frames as they arrive from the Pico, and
finish() closes the stream and returns the assembled final transcript.

Nova-3 is fed raw 16 kHz / 16-bit / mono little-endian PCM (linear16),
which is exactly what the firmware streams — no transcoding needed.

Pinned against deepgram-sdk 3.x (see requirements.txt). The event
callback signature is the one place that changes across SDK majors; if
you bump the SDK and transcripts come back empty, check _on_transcript.
"""
import asyncio
import logging

from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)

from config import DEEPGRAM_API_KEY, SAMPLE_RATE

log = logging.getLogger("stt")


class DeepgramStreamer:
    def __init__(self) -> None:
        # keepalive stops Deepgram from closing the socket during brief
        # silences between the button press and the first words.
        options = DeepgramClientOptions(options={"keepalive": "true"})
        self._client = DeepgramClient(DEEPGRAM_API_KEY, options)
        self._conn = None
        self._final_parts: list[str] = []
        # Set when Deepgram signals the stream has fully closed.
        self._closed = asyncio.Event()

    async def open(self) -> None:
        self._final_parts = []
        self._closed.clear()
        self._conn = self._client.listen.asyncwebsocket.v("1")

        self._conn.on(LiveTranscriptionEvents.Transcript, self._on_transcript)
        self._conn.on(LiveTranscriptionEvents.Error, self._on_error)
        self._conn.on(LiveTranscriptionEvents.Close, self._on_close)

        opts = LiveOptions(
            model="nova-3",
            language="en-US",
            encoding="linear16",
            sample_rate=SAMPLE_RATE,
            channels=1,
            smart_format=True,
            interim_results=False,  # we only care about stabilized finals
        )
        if not await self._conn.start(opts):
            raise RuntimeError("Deepgram live connection failed to start")
        log.info("Deepgram stream opened")

    async def send(self, pcm: bytes) -> None:
        """Forward one raw PCM frame to Deepgram (non-blocking)."""
        if self._conn is not None:
            await self._conn.send(pcm)

    async def finish(self, timeout: float = 5.0) -> str:
        """Close the stream and return the full transcript."""
        if self._conn is None:
            return ""
        try:
            await self._conn.finish()
            # Give Deepgram a moment to flush any trailing final segment.
            try:
                await asyncio.wait_for(self._closed.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                log.warning("Deepgram close timed out; using what we have")
        finally:
            self._conn = None
        return " ".join(p for p in self._final_parts if p).strip()

    # --- Deepgram event callbacks --------------------------------------
    # SDK 3.x invokes these as handler(connection, result=..., **kwargs).
    async def _on_transcript(self, _conn, result, **kwargs) -> None:
        try:
            alt = result.channel.alternatives[0]
        except (AttributeError, IndexError):
            return
        text = (alt.transcript or "").strip()
        if text and getattr(result, "is_final", False):
            self._final_parts.append(text)

    async def _on_error(self, _conn, error, **kwargs) -> None:
        log.error("Deepgram error: %s", error)

    async def _on_close(self, _conn, *args, **kwargs) -> None:
        self._closed.set()
