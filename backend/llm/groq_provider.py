"""
Groq streaming LLM provider.

Uses Groq's OpenAI-compatible API to stream Llama-3 completions
at extremely low latency.
"""

import logging
from typing import AsyncIterator

from openai import AsyncOpenAI

from backend.llm.base import PipelineContext
from backend.llm.openai_provider import DEFAULT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class GroqLLM:
    """Groq implementation of LLMProvider.

    Streams chat completion tokens using the AsyncOpenAI client
    pointed at the Groq API endpoint.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "llama-3.1-8b-instant",
        system_prompt: str | None = None,
        **kwargs,
    ) -> None:
        self._client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1", 
            api_key=api_key
        )
        self._model = model
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._kwargs = kwargs

    async def generate(
        self,
        messages: list[dict[str, str]],
        context: PipelineContext | None = None,
    ) -> AsyncIterator[str]:
        """Stream text tokens for the given conversation."""
        full_messages = self._build_messages(messages, context)

        logger.debug(
            "Groq request: model=%s, messages=%d",
            self._model,
            len(full_messages),
        )

        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=full_messages,
                stream=True,
                temperature=self._kwargs.get("temperature", 0.7),
                max_tokens=self._kwargs.get("max_tokens", 300),
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    yield token

        except Exception:
            logger.exception("Error during Groq streaming")
            raise

    def _build_messages(
        self,
        messages: list[dict[str, str]],
        context: PipelineContext | None,
    ) -> list[dict[str, str]]:
        """Build the full message list with system prompt and context."""
        full_messages: list[dict[str, str]] = [
            {"role": "system", "content": self._system_prompt}
        ]

        # Inject RAG results as additional system context (future use)
        if context and context.rag_results:
            rag_text = "\n\n".join(context.rag_results)
            full_messages.append(
                {
                    "role": "system",
                    "content": (
                        "The following information was retrieved and may be "
                        f"relevant to the user's question:\n\n{rag_text}"
                    ),
                }
            )

        # Inject tool results (future use)
        if context and context.tool_results:
            for result in context.tool_results:
                full_messages.append(
                    {
                        "role": "system",
                        "content": f"Tool result: {result}",
                    }
                )

        # Add conversation history
        full_messages.extend(messages)

        return full_messages
