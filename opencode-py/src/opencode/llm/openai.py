"""OpenAI implementation with flexible model selection."""

import sys
from typing import Optional

from opencode.llm.base import LLMProvider, LLMResponse, Message, ToolCall, ToolResult

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider with flexible model selection.

    Supports any OpenAI model - no restrictions.
    Examples: gpt-4, gpt-4-turbo, gpt-4o, gpt-3.5-turbo, o1-preview, etc.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4",
        base_url: Optional[str] = None,
    ):
        """Initialize the OpenAI provider.

        Args:
            api_key: OpenAI API key.
            model: Any OpenAI model name (no restrictions).
            base_url: Optional custom base URL (for Azure, proxies, etc.)
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self._client = None

    @property
    def client(self):
        """Lazy-load the OpenAI client."""
        if self._client is None and HAS_OPENAI and self.api_key:
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = openai.OpenAI(**kwargs)
        return self._client

    def is_available(self) -> bool:
        """Check if OpenAI is available."""
        return HAS_OPENAI and bool(self.api_key)

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] = None,
        system: str = None,
    ) -> LLMResponse:
        """Send a chat request to OpenAI.

        Args:
            messages: List of chat messages.
            tools: Optional list of tool schemas (will be converted to OpenAI format).
            system: Optional system prompt.

        Returns:
            LLMResponse with content and/or tool calls.
        """
        if not self.is_available():
            return LLMResponse(
                content="[Error] OpenAI API not available. Install: pip install openai",
                stop_reason="error"
            )

        # Build messages list
        openai_messages = []

        # Add system message if provided
        if system:
            openai_messages.append({"role": "system", "content": system})

        # Convert messages
        for msg in messages:
            if msg.role == "system":
                continue  # Already handled
            openai_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # Build request kwargs
        kwargs = {
            "model": self.model,
            "messages": openai_messages,
        }

        # Add tools if provided (convert from Anthropic to OpenAI format)
        if tools:
            openai_tools = self._convert_tools(tools)
            if openai_tools:
                kwargs["tools"] = openai_tools

        try:
            response = self.client.chat.completions.create(**kwargs)
            return self._parse_response(response)

        except openai.APIError as e:
            return LLMResponse(
                content=f"[API Error] {str(e)}",
                stop_reason="error"
            )
        except Exception as e:
            return LLMResponse(
                content=f"[Error] {str(e)}",
                stop_reason="error"
            )

    def _convert_tools(self, anthropic_tools: list[dict]) -> list[dict]:
        """Convert Anthropic tool format to OpenAI function format."""
        openai_tools = []
        for tool in anthropic_tools:
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {})
                }
            }
            openai_tools.append(openai_tool)
        return openai_tools

    def _parse_response(self, response) -> LLMResponse:
        """Parse OpenAI response into LLMResponse."""
        choice = response.choices[0]
        message = choice.message

        content = message.content or ""
        tool_calls = []

        # Parse tool calls if present
        if message.tool_calls:
            for tc in message.tool_calls:
                import json
                try:
                    args = json.loads(tc.function.arguments)
                except:
                    args = {}

                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args
                ))

        stop_reason = choice.finish_reason or "stop"

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=stop_reason
        )

    def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] = None,
        system: str = None,
    ) -> LLMResponse:
        """Send a streaming chat request to OpenAI."""
        if not self.is_available():
            return LLMResponse(
                content="[Error] OpenAI API not available.",
                stop_reason="error"
            )

        import json

        openai_messages = []
        if system:
            openai_messages.append({"role": "system", "content": system})

        for msg in messages:
            if msg.role == "system":
                continue
            openai_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        kwargs = {
            "model": self.model,
            "messages": openai_messages,
            "stream": True,
        }

        if tools:
            openai_tools = self._convert_tools(tools)
            if openai_tools:
                kwargs["tools"] = openai_tools

        try:
            collected_content = []
            tool_calls = []
            current_tool_calls = {}  # id -> {name, arguments}

            stream = self.client.chat.completions.create(**kwargs)

            for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # Handle text content
                if delta.content:
                    sys.stdout.write(delta.content)
                    sys.stdout.flush()
                    collected_content.append(delta.content)

                # Handle tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in current_tool_calls:
                            current_tool_calls[idx] = {
                                "id": tc.id or "",
                                "name": tc.function.name if tc.function else "",
                                "arguments": ""
                            }
                        if tc.id:
                            current_tool_calls[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                current_tool_calls[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                current_tool_calls[idx]["arguments"] += tc.function.arguments

            # Print newline after content
            if collected_content:
                print()

            # Parse tool calls
            for idx in sorted(current_tool_calls.keys()):
                tc_data = current_tool_calls[idx]
                try:
                    args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc_data["id"],
                    name=tc_data["name"],
                    arguments=args
                ))

            return LLMResponse(
                content="".join(collected_content),
                tool_calls=tool_calls,
                stop_reason="stop"
            )

        except openai.APIError as e:
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

        OpenAI format:
        1. Previous messages
        2. For each tool round:
           - Assistant message with tool_calls
           - Tool messages with results for each tool call
        """
        if not self.is_available():
            return LLMResponse(
                content="[Error] OpenAI API not available.",
                stop_reason="error"
            )

        import json

        # Build messages list
        openai_messages = []

        if system:
            openai_messages.append({"role": "system", "content": system})

        for msg in messages:
            if msg.role == "system":
                continue
            openai_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # Add ALL tool rounds (accumulated history)
        for rnd in tool_rounds:
            assistant_content = rnd.get("content", "")
            tool_calls = rnd.get("tool_calls", [])
            tool_results = rnd.get("results", [])

            # Add assistant message with tool calls
            assistant_tool_calls = []
            for tc in tool_calls:
                assistant_tool_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments)
                    }
                })
            openai_messages.append({
                "role": "assistant",
                "content": assistant_content or None,
                "tool_calls": assistant_tool_calls
            })

            # Add tool result messages
            for result in tool_results:
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": result.tool_id,
                    "content": result.content
                })

        kwargs = {
            "model": self.model,
            "messages": openai_messages,
        }

        if tools:
            openai_tools = self._convert_tools(tools)
            if openai_tools:
                kwargs["tools"] = openai_tools

        try:
            response = self.client.chat.completions.create(**kwargs)
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
        """Continue chat after tool execution with streaming."""
        if not self.is_available():
            return LLMResponse(
                content="[Error] OpenAI API not available.",
                stop_reason="error"
            )

        import json as json_module

        openai_messages = []
        if system:
            openai_messages.append({"role": "system", "content": system})

        for msg in messages:
            if msg.role == "system":
                continue
            openai_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # Add ALL tool rounds
        for rnd in tool_rounds:
            assistant_content = rnd.get("content", "")
            tool_calls_list = rnd.get("tool_calls", [])
            tool_results = rnd.get("results", [])

            assistant_tool_calls = []
            for tc in tool_calls_list:
                assistant_tool_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json_module.dumps(tc.arguments)
                    }
                })
            openai_messages.append({
                "role": "assistant",
                "content": assistant_content or None,
                "tool_calls": assistant_tool_calls
            })

            for result in tool_results:
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": result.tool_id,
                    "content": result.content
                })

        kwargs = {
            "model": self.model,
            "messages": openai_messages,
            "stream": True,
        }

        if tools:
            openai_tools = self._convert_tools(tools)
            if openai_tools:
                kwargs["tools"] = openai_tools

        try:
            collected_content = []
            tool_calls = []
            current_tool_calls = {}

            stream = self.client.chat.completions.create(**kwargs)

            for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                if delta.content:
                    sys.stdout.write(delta.content)
                    sys.stdout.flush()
                    collected_content.append(delta.content)

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in current_tool_calls:
                            current_tool_calls[idx] = {
                                "id": tc.id or "",
                                "name": tc.function.name if tc.function else "",
                                "arguments": ""
                            }
                        if tc.id:
                            current_tool_calls[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                current_tool_calls[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                current_tool_calls[idx]["arguments"] += tc.function.arguments

            if collected_content:
                print()

            for idx in sorted(current_tool_calls.keys()):
                tc_data = current_tool_calls[idx]
                try:
                    args = json_module.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                except json_module.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc_data["id"],
                    name=tc_data["name"],
                    arguments=args
                ))

            return LLMResponse(
                content="".join(collected_content),
                tool_calls=tool_calls,
                stop_reason="stop"
            )

        except Exception as e:
            return LLMResponse(
                content=f"[Error] {str(e)}",
                stop_reason="error"
            )


class CustomLLMProvider(LLMProvider):
    """Custom LLM provider for any OpenAI-compatible API.

    Works with:
    - Ollama (http://localhost:11434/v1)
    - LM Studio (http://localhost:1234/v1)
    - vLLM, text-generation-inference
    - Any OpenAI-compatible endpoint
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "not-needed",  # Some local servers don't need a key
    ):
        """Initialize custom LLM provider.

        Args:
            base_url: The API base URL (e.g., http://localhost:11434/v1)
            model: Model name to use
            api_key: API key (use "not-needed" for local servers)
        """
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self._client = None

    @property
    def client(self):
        """Lazy-load the OpenAI client with custom base URL."""
        if self._client is None and HAS_OPENAI:
            self._client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    def is_available(self) -> bool:
        """Check if the custom provider is available."""
        return HAS_OPENAI and bool(self.base_url)

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] = None,
        system: str = None,
    ) -> LLMResponse:
        """Send a chat request to the custom LLM.

        Args:
            messages: List of chat messages.
            tools: Optional list of tool schemas.
            system: Optional system prompt.

        Returns:
            LLMResponse with content and/or tool calls.
        """
        if not self.is_available():
            return LLMResponse(
                content="[Error] OpenAI library not available. Install: pip install openai",
                stop_reason="error"
            )

        # Build messages list
        openai_messages = []

        if system:
            openai_messages.append({"role": "system", "content": system})

        for msg in messages:
            if msg.role == "system":
                continue
            openai_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        kwargs = {
            "model": self.model,
            "messages": openai_messages,
        }

        # Only add tools if the server likely supports them
        # Many local LLMs don't support function calling
        if tools:
            try:
                openai_tools = self._convert_tools(tools)
                if openai_tools:
                    kwargs["tools"] = openai_tools
            except:
                pass  # Skip tools if conversion fails

        try:
            response = self.client.chat.completions.create(**kwargs)
            return self._parse_response(response)

        except Exception as e:
            # Try without tools if it failed
            if "tools" in kwargs:
                del kwargs["tools"]
                try:
                    response = self.client.chat.completions.create(**kwargs)
                    return self._parse_response(response)
                except Exception as e2:
                    return LLMResponse(
                        content=f"[Error] {str(e2)}",
                        stop_reason="error"
                    )
            return LLMResponse(
                content=f"[Error] {str(e)}",
                stop_reason="error"
            )

    def _convert_tools(self, anthropic_tools: list[dict]) -> list[dict]:
        """Convert tool format to OpenAI function format."""
        openai_tools = []
        for tool in anthropic_tools:
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {})
                }
            }
            openai_tools.append(openai_tool)
        return openai_tools

    def _parse_response(self, response) -> LLMResponse:
        """Parse response into LLMResponse."""
        choice = response.choices[0]
        message = choice.message

        content = message.content or ""
        tool_calls = []

        if hasattr(message, 'tool_calls') and message.tool_calls:
            import json
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except:
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args
                ))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=getattr(choice, 'finish_reason', 'stop') or 'stop'
        )

    def continue_with_tool_results(
        self,
        messages: list[Message],
        tool_rounds: list[dict],
        tools: list[dict] = None,
        system: str = None,
    ) -> LLMResponse:
        """Continue chat after tool execution."""
        if not self.is_available():
            return LLMResponse(
                content="[Error] Custom LLM not available.",
                stop_reason="error"
            )

        import json

        openai_messages = []

        if system:
            openai_messages.append({"role": "system", "content": system})

        for msg in messages:
            if msg.role == "system":
                continue
            openai_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # Add ALL tool rounds (accumulated history)
        for rnd in tool_rounds:
            assistant_content = rnd.get("content", "")
            tool_calls = rnd.get("tool_calls", [])
            tool_results = rnd.get("results", [])

            # Add assistant message with tool calls
            assistant_tool_calls = []
            for tc in tool_calls:
                assistant_tool_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments)
                    }
                })
            openai_messages.append({
                "role": "assistant",
                "content": assistant_content or None,
                "tool_calls": assistant_tool_calls
            })

            # Add tool result messages
            for result in tool_results:
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": result.tool_id,
                    "content": result.content
                })

        kwargs = {
            "model": self.model,
            "messages": openai_messages,
        }

        if tools:
            try:
                openai_tools = self._convert_tools(tools)
                if openai_tools:
                    kwargs["tools"] = openai_tools
            except:
                pass

        try:
            response = self.client.chat.completions.create(**kwargs)
            return self._parse_response(response)

        except Exception as e:
            # Try without tools if it failed
            if "tools" in kwargs:
                del kwargs["tools"]
                try:
                    response = self.client.chat.completions.create(**kwargs)
                    return self._parse_response(response)
                except Exception as e2:
                    return LLMResponse(
                        content=f"[Error] {str(e2)}",
                        stop_reason="error"
                    )
            return LLMResponse(
                content=f"[Error] {str(e)}",
                stop_reason="error"
            )

    def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] = None,
        system: str = None,
    ) -> LLMResponse:
        """Send a streaming chat request to the custom LLM."""
        if not self.is_available():
            return LLMResponse(
                content="[Error] OpenAI library not available.",
                stop_reason="error"
            )

        import json as json_module

        openai_messages = []
        if system:
            openai_messages.append({"role": "system", "content": system})

        for msg in messages:
            if msg.role == "system":
                continue
            openai_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        kwargs = {
            "model": self.model,
            "messages": openai_messages,
            "stream": True,
        }

        if tools:
            try:
                openai_tools = self._convert_tools(tools)
                if openai_tools:
                    kwargs["tools"] = openai_tools
            except:
                pass

        try:
            collected_content = []
            tool_calls_result = []
            current_tool_calls = {}

            stream = self.client.chat.completions.create(**kwargs)

            for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                if hasattr(delta, 'content') and delta.content:
                    sys.stdout.write(delta.content)
                    sys.stdout.flush()
                    collected_content.append(delta.content)

                if hasattr(delta, 'tool_calls') and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in current_tool_calls:
                            current_tool_calls[idx] = {
                                "id": tc.id or "",
                                "name": tc.function.name if tc.function else "",
                                "arguments": ""
                            }
                        if tc.id:
                            current_tool_calls[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                current_tool_calls[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                current_tool_calls[idx]["arguments"] += tc.function.arguments

            if collected_content:
                print()

            for idx in sorted(current_tool_calls.keys()):
                tc_data = current_tool_calls[idx]
                try:
                    args = json_module.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                except json_module.JSONDecodeError:
                    args = {}
                tool_calls_result.append(ToolCall(
                    id=tc_data["id"],
                    name=tc_data["name"],
                    arguments=args
                ))

            return LLMResponse(
                content="".join(collected_content),
                tool_calls=tool_calls_result,
                stop_reason="stop"
            )

        except Exception as e:
            # Fall back to non-streaming if streaming fails
            if "stream" in kwargs:
                del kwargs["stream"]
                try:
                    response = self.client.chat.completions.create(**kwargs)
                    return self._parse_response(response)
                except:
                    pass
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
        """Continue chat after tool execution with streaming."""
        if not self.is_available():
            return LLMResponse(
                content="[Error] Custom LLM not available.",
                stop_reason="error"
            )

        import json as json_module

        openai_messages = []
        if system:
            openai_messages.append({"role": "system", "content": system})

        for msg in messages:
            if msg.role == "system":
                continue
            openai_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        for rnd in tool_rounds:
            assistant_content = rnd.get("content", "")
            tool_calls_list = rnd.get("tool_calls", [])
            tool_results = rnd.get("results", [])

            assistant_tool_calls = []
            for tc in tool_calls_list:
                assistant_tool_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json_module.dumps(tc.arguments)
                    }
                })
            openai_messages.append({
                "role": "assistant",
                "content": assistant_content or None,
                "tool_calls": assistant_tool_calls
            })

            for result in tool_results:
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": result.tool_id,
                    "content": result.content
                })

        kwargs = {
            "model": self.model,
            "messages": openai_messages,
            "stream": True,
        }

        if tools:
            try:
                openai_tools = self._convert_tools(tools)
                if openai_tools:
                    kwargs["tools"] = openai_tools
            except:
                pass

        try:
            collected_content = []
            tool_calls_result = []
            current_tool_calls = {}

            stream = self.client.chat.completions.create(**kwargs)

            for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                if hasattr(delta, 'content') and delta.content:
                    sys.stdout.write(delta.content)
                    sys.stdout.flush()
                    collected_content.append(delta.content)

                if hasattr(delta, 'tool_calls') and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in current_tool_calls:
                            current_tool_calls[idx] = {
                                "id": tc.id or "",
                                "name": tc.function.name if tc.function else "",
                                "arguments": ""
                            }
                        if tc.id:
                            current_tool_calls[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                current_tool_calls[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                current_tool_calls[idx]["arguments"] += tc.function.arguments

            if collected_content:
                print()

            for idx in sorted(current_tool_calls.keys()):
                tc_data = current_tool_calls[idx]
                try:
                    args = json_module.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                except json_module.JSONDecodeError:
                    args = {}
                tool_calls_result.append(ToolCall(
                    id=tc_data["id"],
                    name=tc_data["name"],
                    arguments=args
                ))

            return LLMResponse(
                content="".join(collected_content),
                tool_calls=tool_calls_result,
                stop_reason="stop"
            )

        except Exception as e:
            # Fall back to non-streaming
            if "stream" in kwargs:
                del kwargs["stream"]
                try:
                    response = self.client.chat.completions.create(**kwargs)
                    return self._parse_response(response)
                except:
                    pass
            return LLMResponse(
                content=f"[Error] {str(e)}",
                stop_reason="error"
            )
