"""Deepgram live streaming speech-to-text.

Key and model are pulled from the settings store when the stream opens, so a
dashboard change applies to the next utterance without a restart. Kept as the
STT provider (accurate live streaming that finalizes by button-release);
swappable behind this module if ever needed.
"""
import asyncio
import logging

from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)

from . import settings_store

log = logging.getLogger("stt")


class STTError(Exception):
    pass


class DeepgramStreamer:
    def __init__(self) -> None:
        key = settings_store.get("deepgram_api_key")
        if not key:
            raise STTError("Deepgram API key not set (configure it in the dashboard)")
        options = DeepgramClientOptions(options={"keepalive": "true"})
        self._client = DeepgramClient(key, options)
        self._model = settings_store.get("deepgram_model", "nova-3")
        self._rate = int(settings_store.get("sample_rate", 16000))
        self._conn = None
        self._final_parts: list[str] = []
        self._closed = asyncio.Event()

    async def open(self) -> None:
        self._final_parts = []
        self._closed.clear()
        self._conn = self._client.listen.asyncwebsocket.v("1")
        self._conn.on(LiveTranscriptionEvents.Transcript, self._on_transcript)
        self._conn.on(LiveTranscriptionEvents.Error, self._on_error)
        self._conn.on(LiveTranscriptionEvents.Close, self._on_close)

        opts = LiveOptions(
            model=self._model,
            language="en-US",
            encoding="linear16",
            sample_rate=self._rate,
            channels=1,
            smart_format=True,
            interim_results=False,
        )
        if not await self._conn.start(opts):
            raise STTError("Deepgram live connection failed to start")

    async def send(self, pcm: bytes) -> None:
        if self._conn is not None:
            await self._conn.send(pcm)

    async def finish(self, timeout: float = 5.0) -> str:
        if self._conn is None:
            return ""
        try:
            await self._conn.finish()
            try:
                await asyncio.wait_for(self._closed.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                log.warning("Deepgram close timed out; using partial transcript")
        finally:
            self._conn = None
        return " ".join(p for p in self._final_parts if p).strip()

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


async def test_deepgram() -> dict:
    """Validate the Deepgram key by opening and immediately closing a live
    stream (exercises the exact auth path the voice pipeline uses)."""
    streamer = DeepgramStreamer()
    await streamer.open()
    await streamer.finish(timeout=2.0)
    return {"ok": True, "model": streamer._model}
