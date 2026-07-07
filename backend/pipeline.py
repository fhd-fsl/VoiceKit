"""
Voice pipeline coordinator.

Orchestrates the real-time streaming pipeline that connects four layers:
    Telephony (inbound audio) -> STT -> LLM -> TTS -> Telephony (outbound audio)

Runs three concurrent async tasks per call session:
    1. Ingest: Telephony audio -> STT
    2. Process: STT transcripts -> LLM -> TTS
    3. Playback: TTS audio -> Telephony
"""

import asyncio
import logging
import time
from typing import AsyncIterator

from backend.telephony.base import TelephonyProvider
from backend.stt.base import STTProvider, Transcript
from backend.llm.base import LLMProvider, PipelineContext
from backend.tts.base import TTSProvider
from backend.rag.engine import RAGEngine
from backend.utils.audio import chunk_audio
from backend.tools.registry import TOOLS_SCHEMA, TOOL_FUNCTIONS

logger = logging.getLogger(__name__)

class VoicePipeline:
    """Coordinates a single voice call session through the full pipeline.

    Usage:
        pipeline = VoicePipeline(
            telephony=TelephonyProvider.from_twilio(),
            stt=STTProvider.from_deepgram(api_key=...),
            llm=LLMProvider.from_openai(api_key=...),
            tts=TTSProvider.from_elevenlabs(api_key=...),
        )
        await pipeline.run()
    """

    def __init__(
        self,
        *,
        telephony: TelephonyProvider,
        stt: STTProvider,
        llm: LLMProvider,
        tts: TTSProvider,
        rag: RAGEngine,
    ) -> None:
        self._telephony = telephony
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._rag = rag

        # Conversation state
        self._messages: list[dict[str, str]] = []
        self._play_until = 0.0  # Unix timestamp when Twilio finishes playing audio
        self._current_utterance = ""  # Accumulates transcript text

        # Queues for inter-task communication
        self._tts_audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._response_task: asyncio.Task | None = None

    async def run(self) -> None:
        """Run the full voice pipeline until the call ends.

        Starts the STT and TTS connections, then runs three concurrent
        tasks: ingest, process, and playback.
        """
        logger.info(
            "Starting voice pipeline (callSid=%s)", self._telephony.call_id
        )

        # Initialize provider connections
        await self._stt.connect()
        await self._tts.connect()

        # Run all pipeline tasks concurrently
        tasks = [
            asyncio.create_task(self._ingest_task(), name="ingest"),
            asyncio.create_task(self._process_task(), name="process"),
            asyncio.create_task(self._playback_task(), name="playback"),
        ]

        try:
            # Wait for the telephony connection to end (run() blocks)
            await self._telephony.run()
        except Exception:
            logger.exception("Error in telephony connection")
        finally:
            # Cancel all pipeline tasks
            for task in tasks:
                task.cancel()

            # Wait for tasks to finish
            await asyncio.gather(*tasks, return_exceptions=True)

            # Cleanup providers
            await self._stt.close()
            await self._tts.close()

            logger.info(
                "Voice pipeline ended (callSid=%s)", self._telephony.call_id
            )

    # ── Pipeline Tasks ───────────────────────────────────────────────

    async def _ingest_task(self) -> None:
        """Task 1: Read audio from telephony and feed it to STT.

        Continuously reads mu-law audio chunks from the telephony
        provider's inbound queue and sends them to the STT provider.
        """
        audio_queue = self._telephony.inbound_audio()
        try:
            while True:
                try:
                    audio = await asyncio.wait_for(audio_queue.get(), timeout=0.1)
                    await self._stt.send_audio(audio)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Error in ingest task")

    async def _process_task(self) -> None:
        """Task 2: Read transcripts from STT, generate LLM responses, synthesize TTS.

        This is the core intelligence loop:
        1. Accumulate transcript chunks into complete utterances
        2. When the speaker finishes (speech_final), send to LLM
        3. Stream LLM tokens into TTS
        4. Put TTS audio chunks on the playback queue

        Future extensibility: RAG retrieval and tool calling would be
        inserted between steps 1 and 2, populating the PipelineContext.
        """
        try:
            async for transcript in self._stt.transcripts():
                try:
                    await self._handle_transcript(transcript)
                except Exception as e:
                    logger.exception("Error handling transcript: %s", e)

        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Error in process task")

    async def _playback_task(self) -> None:
        """Task 3: Read TTS audio from the queue and send to telephony.

        Chunks audio into 20ms segments to match Twilio's expected cadence.
        """
        try:
            while True:
                try:
                    audio = await asyncio.wait_for(
                        self._tts_audio_queue.get(), timeout=0.1
                    )
                except asyncio.TimeoutError:
                    continue

                if audio is None:
                    continue

                # 1 byte = 1 sample at 8000 Hz, so len(audio) / 8000 = duration in seconds
                audio_duration = len(audio) / 8000.0
                
                # Update expected end time of the Twilio audio buffer
                current_time = time.time()
                if self._play_until < current_time:
                    self._play_until = current_time + audio_duration
                else:
                    self._play_until += audio_duration

                # Chunk the audio into 20ms segments for smooth playback
                try:
                    chunks = chunk_audio(audio, chunk_ms=20)
                    for chunk in chunks:
                        await self._telephony.send_audio(chunk)
                except Exception as e:
                    logger.exception("Error sending audio chunk to telephony: %s", e)

        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Error in playback task")

    # ── Transcript Handling ──────────────────────────────────────────

    async def _handle_transcript(self, transcript: Transcript) -> None:
        """Process a single transcript from STT.

        Accumulates text until the speaker finishes, then triggers
        the LLM -> TTS pipeline.
        """
        if not transcript.text and transcript.speech_final:
            # Empty speech_final = utterance boundary from VAD
            if self._current_utterance.strip():
                if self._response_task and not self._response_task.done():
                    self._response_task.cancel()
                self._response_task = asyncio.create_task(
                    self._generate_response(self._current_utterance.strip())
                )
                self._current_utterance = ""
            return

        if transcript.is_final:
            self._current_utterance += transcript.text + " "

            # Check for barge-in: user is speaking while AI is talking
            if time.time() < self._play_until:
                logger.info("Barge-in detected -- clearing audio buffer")
                await self._telephony.clear_audio()
                self._play_until = 0.0
                if self._response_task and not self._response_task.done():
                    self._response_task.cancel()
                # Drain the TTS audio queue
                while not self._tts_audio_queue.empty():
                    try:
                        self._tts_audio_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

            if transcript.speech_final:
                utterance = self._current_utterance.strip()
                if utterance:
                    if self._response_task and not self._response_task.done():
                        self._response_task.cancel()
                    self._response_task = asyncio.create_task(
                        self._generate_response(utterance)
                    )
                self._current_utterance = ""

    async def _generate_response(self, user_text: str) -> None:
        """Generate an AI response for the user's utterance.

        This is where future middleware (RAG, tool calling) would be
        inserted. The PipelineContext object is the extensibility point.

        Flow: user_text -> (optional RAG/tools) -> LLM -> TTS -> playback queue
        """
        logger.info("User said: %s", user_text)

        # Add user message to conversation history
        self._messages.append({"role": "user", "content": user_text})

        # Retrieve RAG context
        rag_results = await self._rag.retrieve(user_text)
        if rag_results:
            logger.info("RAG: Retrieved %d relevant chunks", len(rag_results))
            for i, chunk in enumerate(rag_results):
                logger.debug("RAG Chunk %d: %s", i + 1, chunk)

        # Build pipeline context
        context = PipelineContext(rag_results=rag_results if rag_results else None)

        full_response = ""

        start_time = time.time()

        try:
            # Create an async generator that captures the full response
            async def llm_token_stream() -> AsyncIterator[str]:
                nonlocal full_response
                first_token = True
                async for token in self._llm.generate(
                    self._messages, 
                    context,
                    tools=TOOLS_SCHEMA,
                    tool_functions=TOOL_FUNCTIONS
                ):
                    if first_token:
                        llm_latency = time.time() - start_time
                        logger.info("Latency [LLM TTFT]: %.3f seconds", llm_latency)
                        first_token = False
                    full_response += token
                    yield token

            # Pipe LLM tokens through TTS and into the playback queue
            first_chunk = True
            async for audio_chunk in self._tts.synthesize(llm_token_stream()):
                if first_chunk:
                    latency = time.time() - start_time
                    logger.info("Latency [Total TTFA]: %.3f seconds", latency)
                    first_chunk = False
                await self._tts_audio_queue.put(audio_chunk)

            # Signal end of this utterance's audio
            await self._tts_audio_queue.put(None)

            # Add assistant response to conversation history
            if full_response:
                self._messages.append(
                    {"role": "assistant", "content": full_response}
                )
                logger.info("Assistant said: %s", full_response)

        except Exception:
            logger.exception("Error generating response")
