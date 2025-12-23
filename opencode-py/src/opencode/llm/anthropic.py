"""Anthropic Claude implementation."""

import json
import sys
from typing import Optional, Generator

from opencode.llm.base import LLMProvider, LLMResponse, Message, ToolCall, ToolResult

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        """Initialize the Anthropic provider.

        Args:
            api_key: Anthropic API key.
            model: Model to use (default: claude-sonnet-4-20250514).
        """
        self.api_key = api_key
        self.model = model
        self._client = None

    @property
    def client(self):
        """Lazy-load the Anthropic client."""
        if self._client is None and HAS_ANTHROPIC and self.api_key:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def is_available(self) -> bool:
        """Check if Anthropic is available."""
        return HAS_ANTHROPIC and bool(self.api_key)

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] = None,
        system: str = None,
    ) -> LLMResponse:
        """Send a chat request to Claude.

        Args:
            messages: List of chat messages.
            tools: Optional list of tool schemas (Anthropic format).
            system: Optional system prompt.

        Returns:
            LLMResponse with content and/or tool calls.
        """
        if not self.is_available():
            return LLMResponse(
                content="[Error] Anthropic API not available. Set ANTHROPIC_API_KEY.",
                stop_reason="error"
            )

        # Convert messages to Anthropic format
        anthropic_messages = []
        for msg in messages:
            if msg.role == "system":
                # System messages go in the system parameter
                continue
            anthropic_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # Build request kwargs
        kwargs = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": anthropic_messages,
        }

        if system:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = tools

        try:
            response = self.client.messages.create(**kwargs)
            return self._parse_response(response)

        except anthropic.APIError as e:
            return LLMResponse(
                content=f"[API Error] {str(e)}",
                stop_reason="error"
            )
        except Exception as e:
            return LLMResponse(
                content=f"[Error] {str(e)}",
                stop_reason="error"
            )

    def _parse_response(self, response) -> LLMResponse:
        """Parse Anthropic response into LLMResponse."""
        content_parts = []
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {}
                ))

        return LLMResponse(
            content="\n".join(content_parts),
            tool_calls=tool_calls,
            stop_reason=response.stop_reason or "end_turn"
        )

    def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] = None,
        system: str = None,
    ) -> LLMResponse:
        """Send a streaming chat request to Claude.

        Prints tokens as they arrive and returns the final response.
        """
        if not self.is_available():
            return LLMResponse(
                content="[Error] Anthropic API not available. Set ANTHROPIC_API_KEY.",
                stop_reason="error"
            )

        # Convert messages to Anthropic format
        anthropic_messages = []
        for msg in messages:
            if msg.role == "system":
                continue
            anthropic_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        kwargs = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": anthropic_messages,
        }

        if system:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = tools

        try:
            collected_content = []
            tool_calls = []
            current_tool_id = None
            current_tool_name = None
            current_tool_input = ""

            with self.client.messages.stream(**kwargs) as stream:
                for event in stream:
                    if event.type == "content_block_start":
                        if hasattr(event.content_block, 'type'):
                            if event.content_block.type == "tool_use":
                                current_tool_id = event.content_block.id
                                current_tool_name = event.content_block.name
                                current_tool_input = ""

                    elif event.type == "content_block_delta":
                        if hasattr(event.delta, 'text'):
                            # Text content - print immediately
                            text = event.delta.text
                            sys.stdout.write(text)
                            sys.stdout.flush()
                            collected_content.append(text)
                        elif hasattr(event.delta, 'partial_json'):
                            # Tool input JSON accumulating
                            current_tool_input += event.delta.partial_json

                    elif event.type == "content_block_stop":
                        if current_tool_id:
                            # Parse accumulated tool input
                            try:
                                args = json.loads(current_tool_input) if current_tool_input else {}
                            except json.JSONDecodeError:
                                args = {}
                            tool_calls.append(ToolCall(
                                id=current_tool_id,
                                name=current_tool_name,
                                arguments=args
                            ))
                            current_tool_id = None
                            current_tool_name = None
                            current_tool_input = ""

                # Print newline after streaming content
                if collected_content:
                    print()

                final_message = stream.get_final_message()
                stop_reason = final_message.stop_reason or "end_turn"

            return LLMResponse(
                content="".join(collected_content),
                tool_calls=tool_calls,
                stop_reason=stop_reason
            )

        except anthropic.APIError as e:
            return LLMResponse(
                content=f"[API Error] {str(e)}",
                stop_reason="error"
            )
        except Exception as e:
            return LLMResponse(
                content=f"[Error] {str(e)}",
                stop_reason="error"
            )

    def continue_with_tool_results(
        self,
        messages: list[Message],
        tool_rounds: list[dict],
        tools: list[dict] = None,
        system: str = None,
    ) -> LLMResponse:
        """Continue chat after tool execution.

        Args:
            messages: Previous user/assistant messages.
            tool_rounds: List of tool interaction rounds.
            tools: Tool schemas.
            system: System prompt.

        Returns:
            LLMResponse from continued conversation.
        """
        if not self.is_available():
            return LLMResponse(
                content="[Error] Anthropic API not available.",
                stop_reason="error"
            )

        # Convert messages to Anthropic format
        anthropic_messages = []
        for msg in messages:
            if msg.role == "system":
                continue
            anthropic_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # Add ALL tool rounds (accumulated history)
        for rnd in tool_rounds:
            assistant_content = rnd.get("content", "")
            tool_calls = rnd.get("tool_calls", [])
            tool_results = rnd.get("results", [])

            # Add assistant message with tool_use blocks
            assistant_content_blocks = []
            if assistant_content:
                assistant_content_blocks.append({
                    "type": "text",
                    "text": assistant_content
                })
            for tc in tool_calls:
                assistant_content_blocks.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments
                })
            anthropic_messages.append({
                "role": "assistant",
                "content": assistant_content_blocks
            })

            # Add tool results as a user message with tool_result blocks
            tool_result_content = []
            for result in tool_results:
                tool_result_content.append({
                    "type": "tool_result",
                    "tool_use_id": result.tool_id,
                    "content": result.content,
                    "is_error": result.is_error
                })
            anthropic_messages.append({
                "role": "user",
                "content": tool_result_content
            })

        kwargs = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": anthropic_messages,
        }

        if system:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = tools

        try:
            response = self.client.messages.create(**kwargs)
            return self._parse_response(response)

        except Exception as e:
            return LLMResponse(
                content=f"[Error] {str(e)}",
                stop_reason="error"
            )

    def continue_with_tool_results_stream(
        self,
        messages: list[Message],
        tool_rounds: list[dict],
        tools: list[dict] = None,
        system: str = None,
    ) -> LLMResponse:
        """Continue chat after tool execution with streaming output."""
        if not self.is_available():
            return LLMResponse(
                content="[Error] Anthropic API not available.",
                stop_reason="error"
            )

        # Convert messages to Anthropic format
        anthropic_messages = []
        for msg in messages:
            if msg.role == "system":
                continue
            anthropic_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # Add ALL tool rounds (accumulated history)
        for rnd in tool_rounds:
            assistant_content = rnd.get("content", "")
            tool_calls_list = rnd.get("tool_calls", [])
            tool_results = rnd.get("results", [])

            # Add assistant message with tool_use blocks
            assistant_content_blocks = []
            if assistant_content:
                assistant_content_blocks.append({
                    "type": "text",
                    "text": assistant_content
                })
            for tc in tool_calls_list:
                assistant_content_blocks.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments
                })
            anthropic_messages.append({
                "role": "assistant",
                "content": assistant_content_blocks
            })

            # Add tool results as a user message with tool_result blocks
            tool_result_content = []
            for result in tool_results:
                tool_result_content.append({
                    "type": "tool_result",
                    "tool_use_id": result.tool_id,
                    "content": result.content,
                    "is_error": result.is_error
                })
            anthropic_messages.append({
                "role": "user",
                "content": tool_result_content
            })

        kwargs = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": anthropic_messages,
        }

        if system:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = tools

        try:
            collected_content = []
            tool_calls = []
            current_tool_id = None
            current_tool_name = None
            current_tool_input = ""

            with self.client.messages.stream(**kwargs) as stream:
                for event in stream:
                    if event.type == "content_block_start":
                        if hasattr(event.content_block, 'type'):
                            if event.content_block.type == "tool_use":
                                current_tool_id = event.content_block.id
                                current_tool_name = event.content_block.name
                                current_tool_input = ""

                    elif event.type == "content_block_delta":
                        if hasattr(event.delta, 'text'):
                            text = event.delta.text
                            sys.stdout.write(text)
                            sys.stdout.flush()
                            collected_content.append(text)
                        elif hasattr(event.delta, 'partial_json'):
                            current_tool_input += event.delta.partial_json

                    elif event.type == "content_block_stop":
                        if current_tool_id:
                            try:
                                args = json.loads(current_tool_input) if current_tool_input else {}
                            except json.JSONDecodeError:
                                args = {}
                            tool_calls.append(ToolCall(
                                id=current_tool_id,
                                name=current_tool_name,
                                arguments=args
                            ))
                            current_tool_id = None
                            current_tool_name = None
                            current_tool_input = ""

                if collected_content:
                    print()

                final_message = stream.get_final_message()
                stop_reason = final_message.stop_reason or "end_turn"

            return LLMResponse(
                content="".join(collected_content),
                tool_calls=tool_calls,
                stop_reason=stop_reason
            )

        except Exception as e:
            return LLMResponse(
                content=f"[Error] {str(e)}",
                stop_reason="error"
            )
