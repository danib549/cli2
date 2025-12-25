"""OpenAI implementation with flexible model selection."""

import sys
from typing import Optional

from opencode.llm.base import (
    LLMProvider, LLMResponse, Message, ToolCall, ToolResult,
    LLMError, APIKeyError, ConnectionError, RateLimitError,
    ModelError, ContextLengthError
)

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


def _parse_openai_error(e: Exception, model: str = "") -> LLMError:
    """Convert OpenAI exceptions to structured LLMError."""
    error_str = str(e).lower()

    if HAS_OPENAI:
        if isinstance(e, openai.AuthenticationError):
            return APIKeyError("OpenAI")

        if isinstance(e, openai.RateLimitError):
            return RateLimitError("OpenAI")

        if isinstance(e, openai.NotFoundError):
            return ModelError("OpenAI", model)

        if isinstance(e, openai.BadRequestError):
            if "context_length" in error_str or "maximum context" in error_str:
                return ContextLengthError("OpenAI")
            return LLMError(str(e), "OpenAI", "Check your request format")

        if isinstance(e, openai.APIConnectionError):
            return ConnectionError("OpenAI", str(e))

        if isinstance(e, openai.APIError):
            return LLMError(str(e), "OpenAI")

    return LLMError(str(e), "OpenAI")


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
        debug: bool = False,
        ssl_verify: bool | str = True,
    ):
        """Initialize the OpenAI provider.

        Args:
            api_key: OpenAI API key.
            model: Any OpenAI model name (no restrictions).
            base_url: Optional custom base URL (for Azure, proxies, etc.)
            debug: Enable debug logging.
            ssl_verify: SSL verification (True, False, or path to CA bundle).
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.debug = debug
        self.ssl_verify = ssl_verify
        self._client = None

    @property
    def client(self):
        """Lazy-load the OpenAI client."""
        if self._client is None and HAS_OPENAI and self.api_key:
            import httpx

            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url

            # Configure SSL
            if self.ssl_verify is False:
                kwargs["http_client"] = httpx.Client(verify=False)
            elif isinstance(self.ssl_verify, str):
                kwargs["http_client"] = httpx.Client(verify=self.ssl_verify)

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

        # Debug logging
        self._log_debug("REQUEST", {
            "model": self.model,
            "messages": len(openai_messages),
            "tools": len(kwargs.get("tools", [])),
        })

        try:
            response = self.client.chat.completions.create(**kwargs)
            result = self._parse_response(response)

            self._log_debug("RESPONSE", {
                "content_length": len(result.content),
                "tool_calls": len(result.tool_calls),
                "stop_reason": result.stop_reason
            })

            return result

        except openai.APIError as e:
            error = _parse_openai_error(e, self.model)
            return LLMResponse(
                content=f"[Error] {error.format_message()}",
                stop_reason="error"
            )
        except Exception as e:
            return LLMResponse(
                content=f"[Error] Unexpected: {str(e)}",
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


def _parse_text_tool_calls(content: str, available_tools: list[str] = None) -> tuple[str, list]:
    """Parse tool calls from text output for models without native function calling.

    Supports formats:
    - [tool_name(arg1, arg2)]
    - [tool_name("arg1", key="value")]
    - tool_name(path="value")
    - ```tool_name(...)```

    Returns:
        Tuple of (cleaned_content, list of ToolCall objects)
    """
    import re
    import uuid

    tool_calls = []

    # Known tool names if not provided
    if available_tools is None:
        available_tools = [
            "read", "write", "edit", "bash", "glob", "grep",
            "tree", "outline", "find_definition", "find_references",
            "find_symbols", "rename_symbol"
        ]

    # Pattern to match tool calls: [tool(...)] or tool(...)
    # Handles nested parentheses and quoted strings
    tool_pattern = r'\[?(' + '|'.join(available_tools) + r')\s*\(((?:[^()]*|\([^()]*\))*)\)\]?'

    matches = list(re.finditer(tool_pattern, content, re.IGNORECASE))

    if not matches:
        return content, []

    for match in matches:
        tool_name = match.group(1).lower()
        args_str = match.group(2).strip()

        # Parse arguments
        arguments = {}

        if args_str:
            # Try to parse as key=value pairs first
            kv_pattern = r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^,\s\)]+))'
            kv_matches = re.findall(kv_pattern, args_str)

            if kv_matches:
                for kv in kv_matches:
                    key = kv[0]
                    # Get the non-empty value from the groups
                    value = kv[1] or kv[2] or kv[3]
                    arguments[key] = value
            else:
                # Try positional arguments - map to common parameter names
                # Remove quotes and split by comma
                pos_args = []
                current_arg = ""
                in_quotes = False
                quote_char = None

                for char in args_str:
                    if char in '"\'':
                        if not in_quotes:
                            in_quotes = True
                            quote_char = char
                        elif char == quote_char:
                            in_quotes = False
                            quote_char = None
                        else:
                            current_arg += char
                    elif char == ',' and not in_quotes:
                        if current_arg.strip():
                            pos_args.append(current_arg.strip())
                        current_arg = ""
                    else:
                        current_arg += char

                if current_arg.strip():
                    pos_args.append(current_arg.strip())

                # Map positional args to parameter names based on tool
                if tool_name == "read" and pos_args:
                    arguments["path"] = pos_args[0]
                elif tool_name == "write" and pos_args:
                    arguments["path"] = pos_args[0]
                    if len(pos_args) > 1:
                        arguments["content"] = pos_args[1]
                elif tool_name == "edit" and pos_args:
                    arguments["path"] = pos_args[0]
                    if len(pos_args) > 1:
                        arguments["old_string"] = pos_args[1]
                    if len(pos_args) > 2:
                        arguments["new_string"] = pos_args[2]
                elif tool_name == "bash" and pos_args:
                    arguments["command"] = pos_args[0]
                elif tool_name == "glob" and pos_args:
                    arguments["pattern"] = pos_args[0]
                elif tool_name == "grep" and pos_args:
                    arguments["pattern"] = pos_args[0]
                    if len(pos_args) > 1:
                        arguments["path"] = pos_args[1]
                elif tool_name == "tree" and pos_args:
                    arguments["path"] = pos_args[0]
                    if len(pos_args) > 1:
                        try:
                            arguments["depth"] = int(pos_args[1])
                        except ValueError:
                            pass
                elif tool_name in ("find_definition", "find_references", "find_symbols") and pos_args:
                    arguments["symbol"] = pos_args[0] if tool_name != "find_symbols" else pos_args[0]
                    if tool_name == "find_symbols":
                        arguments["query"] = pos_args[0]
                elif tool_name == "outline" and pos_args:
                    arguments["path"] = pos_args[0]

        # Create tool call
        tool_calls.append(ToolCall(
            id=f"text_call_{uuid.uuid4().hex[:8]}",
            name=tool_name,
            arguments=arguments
        ))

    # Remove tool calls from content to get clean text
    cleaned_content = content
    for match in reversed(matches):  # Reverse to preserve indices
        cleaned_content = cleaned_content[:match.start()] + cleaned_content[match.end():]

    # Clean up extra whitespace
    cleaned_content = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_content).strip()

    return cleaned_content, tool_calls


class CustomLLMProvider(LLMProvider):
    """Custom LLM provider for any OpenAI-compatible API.

    Works with:
    - Ollama (http://localhost:11434/v1)
    - LM Studio (http://localhost:1234/v1)
    - vLLM, text-generation-inference
    - Any OpenAI-compatible endpoint

    Includes text-based tool call parsing for models without native function calling
    (e.g., Gemma, LLaMA, Mistral via Ollama).
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "not-needed",  # Some local servers don't need a key
        debug: bool = False,
        parse_text_tools: bool = True,  # Enable text-based tool parsing
    ):
        """Initialize custom LLM provider.

        Args:
            base_url: The API base URL (e.g., http://localhost:11434/v1)
            model: Model name to use
            api_key: API key (use "not-needed" for local servers)
            debug: Enable debug logging.
            parse_text_tools: Parse tool calls from text for models without native function calling.
        """
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.debug = debug
        self.parse_text_tools = parse_text_tools
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
        """Parse response into LLMResponse.

        If the model doesn't support native function calling, attempts to parse
        tool calls from the text content (e.g., [read(path)] or bash(command)).
        """
        choice = response.choices[0]
        message = choice.message

        content = message.content or ""
        tool_calls = []

        # First try native tool calls
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

        # If no native tool calls and text parsing is enabled, try parsing from text
        if not tool_calls and self.parse_text_tools and content:
            cleaned_content, text_tool_calls = _parse_text_tool_calls(content)
            if text_tool_calls:
                content = cleaned_content
                tool_calls = text_tool_calls
                if self.debug:
                    print(f"[DEBUG] Parsed {len(text_tool_calls)} tool call(s) from text")

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

            # If no native tool calls, try parsing from text
            final_content = "".join(collected_content)
            if not tool_calls_result and self.parse_text_tools and final_content:
                cleaned_content, text_tool_calls = _parse_text_tool_calls(final_content)
                if text_tool_calls:
                    final_content = cleaned_content
                    tool_calls_result = text_tool_calls
                    if self.debug:
                        print(f"[DEBUG] Parsed {len(text_tool_calls)} tool call(s) from streamed text")

            return LLMResponse(
                content=final_content,
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

            # If no native tool calls, try parsing from text
            final_content = "".join(collected_content)
            if not tool_calls_result and self.parse_text_tools and final_content:
                cleaned_content, text_tool_calls = _parse_text_tool_calls(final_content)
                if text_tool_calls:
                    final_content = cleaned_content
                    tool_calls_result = text_tool_calls
                    if self.debug:
                        print(f"[DEBUG] Parsed {len(text_tool_calls)} tool call(s) from streamed text")

            return LLMResponse(
                content=final_content,
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
