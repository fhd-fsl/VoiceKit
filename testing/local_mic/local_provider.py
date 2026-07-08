"""
Local microphone and speaker telephony provider for testing.

Bypasses Twilio entirely. Captures 16-bit PCM audio from the default
microphone, converts it to mu-law to stream to the pipeline, and plays
mu-law output from the pipeline back through the default speakers.
"""

import asyncio
import logging
import queue
import threading

import pyaudio

from backend.utils.audio import decode_mulaw, encode_mulaw

logger = logging.getLogger(__name__)


class LocalAudioProvider:
    """Local microphone/speaker implementation of TelephonyProvider."""

    def __init__(self) -> None:
        self._running = False
        self._inbound_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._outbound_queue: queue.Queue[bytes] = queue.Queue()
        
        self._mark_counter = 0

        self.p = pyaudio.PyAudio()
        self.rate = 8000
        self.chunk = 160  # 20ms chunks

        self.in_stream = None
        self.out_stream = None

        self._mic_thread = None
        self._speaker_thread = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def stream_id(self) -> str:
        return "local_stream"

    @property
    def call_id(self) -> str:
        return "local_call"

    async def connect(self, websocket=None) -> None:
        """Initialize the PyAudio streams. Ignores the websocket parameter."""
        pass

    async def run(self) -> None:
        """Main loop that starts background threads and keeps the pipeline alive."""
        self._running = True
        
        self.in_stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk
        )
        self.out_stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.rate,
            output=True,
            frames_per_buffer=self.chunk
        )
        
        loop = asyncio.get_running_loop()
        
        def mic_reader():
            while self._running:
                try:
                    # Read PCM audio from microphone
                    data = self.in_stream.read(self.chunk, exception_on_overflow=False)
                    # Convert PCM to mu-law for the pipeline
                    mulaw_data = encode_mulaw(data)
                    # Push safely to asyncio queue
                    loop.call_soon_threadsafe(self._inbound_queue.put_nowait, mulaw_data)
                except Exception as e:
                    if self._running:
                        logger.debug("Local mic reader error: %s", e)
                        
        self._mic_thread = threading.Thread(target=mic_reader, daemon=True)
        self._mic_thread.start()
        
        def speaker_writer():
            while self._running:
                try:
                    # Block waiting for outbound audio from the TTS provider
                    mulaw_data = self._outbound_queue.get(timeout=0.1)
                    # Convert mu-law back to PCM for PyAudio playback
                    pcm_data = decode_mulaw(mulaw_data)
                    self.out_stream.write(pcm_data)
                except queue.Empty:
                    pass
                except Exception as e:
                    if self._running:
                        logger.debug("Local speaker writer error: %s", e)
                        
        self._speaker_thread = threading.Thread(target=speaker_writer, daemon=True)
        self._speaker_thread.start()
        
        logger.info("Local audio streams started. Speak into your microphone!")
        
        try:
            while self._running:
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.info("Local provider cancelled")
            
    def inbound_audio(self) -> asyncio.Queue[bytes]:
        """Queue of raw mu-law audio chunks from the local microphone."""
        return self._inbound_queue

    async def send_audio(self, mulaw_bytes: bytes) -> None:
        """Send mu-law audio to the local speaker."""
        if self._running:
            self._outbound_queue.put(mulaw_bytes)

    async def send_mark(self, label: str | None = None) -> str:
        """Simulate a playback position mark."""
        self._mark_counter += 1
        label = label or f"mark_{self._mark_counter}"
        return label

    async def clear_audio(self) -> None:
        """Flush the outbound audio buffer (for barge-in)."""
        while not self._outbound_queue.empty():
            try:
                self._outbound_queue.get_nowait()
            except queue.Empty:
                break
        logger.info("Local audio buffer cleared")

    async def close(self) -> None:
        """Gracefully close the PyAudio streams."""
        self._running = False
        if self.in_stream:
            self.in_stream.stop_stream()
            self.in_stream.close()
        if self.out_stream:
            self.out_stream.stop_stream()
            self.out_stream.close()
        self.p.terminate()
        logger.info("Local audio streams closed")
