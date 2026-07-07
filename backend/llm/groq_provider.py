"""
Groq streaming LLM provider.

Uses Groq's OpenAI-compatible API to stream Llama-3 completions
at extremely low latency.
"""

import json
import logging
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from backend.llm.base import PipelineContext
from backend.prompts import DEFAULT_SYSTEM_PROMPT

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
        messages: list[dict[str, Any]],
        context: PipelineContext | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_functions: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream text tokens for the given conversation."""
        full_messages = self._build_messages(messages, context)

        logger.debug(
            "Groq request: model=%s, messages=%d",
            self._model,
            len(full_messages),
        )

        try:
            kwargs = {}
            if tools:
                kwargs["tools"] = tools

            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=full_messages,
                stream=True,
                temperature=self._kwargs.get("temperature", 0.7),
                max_tokens=self._kwargs.get("max_tokens", 300),
                **kwargs
            )

            # Accumulate tool calls across chunks
            tool_call_accumulators = {}

            async for chunk in stream:
                delta = chunk.choices[0].delta
                
                # Check for tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.index not in tool_call_accumulators:
                            tool_call_accumulators[tc.index] = {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name or "",
                                    "arguments": tc.function.arguments or ""
                                }
                            }
                        else:
                            if tc.function.name:
                                tool_call_accumulators[tc.index]["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_call_accumulators[tc.index]["function"]["arguments"] += tc.function.arguments
                    continue
                
                # Otherwise, yield text token
                if delta.content:
                    yield delta.content
                    
            # If tool calls were accumulated, execute them
            if tool_call_accumulators and tool_functions:
                logger.info("Groq triggered %d tool call(s)", len(tool_call_accumulators))
                
                # Reconstruct the tool call message
                tool_calls = []
                for tc_idx, tc_data in sorted(tool_call_accumulators.items()):
                    tool_calls.append(tc_data)
                
                # Append assistant's tool call request to messages
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": tool_calls
                })
                
                # Execute tools and append results
                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    fn_args = tc["function"]["arguments"]
                    
                    try:
                        args_dict = json.loads(fn_args) if fn_args else {}
                        if fn_name in tool_functions:
                            logger.info("Executing tool: %s(%s)", fn_name, fn_args)
                            result = await tool_functions[fn_name](**args_dict)
                        else:
                            logger.warning("Tool not found: %s", fn_name)
                            result = f"Error: Tool {fn_name} not found"
                    except Exception as e:
                        logger.exception("Error executing tool %s", fn_name)
                        result = f"Error executing tool: {e}"
                        
                    # Append tool result
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": fn_name,
                        "content": str(result)
                    })
                    
                # Recurse to get the final response!
                async for token in self.generate(messages, context, tools, tool_functions):
                    yield token

        except Exception as e:
            logger.exception("Error during Groq streaming: %s", e)
            yield "I'm sorry, I'm having trouble connecting to my brain right now."

    def _build_messages(
        self,
        messages: list[dict[str, Any]],
        context: PipelineContext | None,
    ) -> list[dict[str, Any]]:
        """Build the full message list with system prompt and context."""
        full_messages: list[dict[str, Any]] = [
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
