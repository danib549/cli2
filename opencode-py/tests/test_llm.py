"""Tests for LLM module."""

import pytest

from opencode.llm.base import (
    Message,
    ToolCall,
    ToolResult,
    LLMResponse,
    LLMError,
    APIKeyError,
    ConnectionError,
    RateLimitError,
    ModelError,
    ContextLengthError,
    ResponseParseError,
    MockLLMProvider,
    SmartMockProvider,
)


# ============================================================================
# Message Tests
# ============================================================================

class TestMessage:
    """Tests for Message dataclass."""

    def test_create_user_message(self):
        """Test creating a user message."""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_create_assistant_message(self):
        """Test creating an assistant message."""
        msg = Message(role="assistant", content="Hi there")
        assert msg.role == "assistant"
        assert msg.content == "Hi there"

    def test_create_system_message(self):
        """Test creating a system message."""
        msg = Message(role="system", content="You are helpful")
        assert msg.role == "system"
        assert msg.content == "You are helpful"


# ============================================================================
# ToolCall Tests
# ============================================================================

class TestToolCall:
    """Tests for ToolCall dataclass."""

    def test_create_tool_call(self):
        """Test creating a tool call."""
        call = ToolCall(id="123", name="read", arguments={"path": "file.py"})
        assert call.id == "123"
        assert call.name == "read"
        assert call.arguments == {"path": "file.py"}

    def test_tool_call_default_arguments(self):
        """Test tool call with default empty arguments."""
        call = ToolCall(id="123", name="test")
        assert call.arguments == {}


# ============================================================================
# ToolResult Tests
# ============================================================================

class TestToolResultLLM:
    """Tests for ToolResult dataclass (LLM version)."""

    def test_create_tool_result(self):
        """Test creating a tool result."""
        result = ToolResult(tool_id="123", content="Success")
        assert result.tool_id == "123"
        assert result.content == "Success"
        assert result.is_error is False

    def test_create_error_result(self):
        """Test creating an error result."""
        result = ToolResult(tool_id="123", content="Failed", is_error=True)
        assert result.is_error is True


# ============================================================================
# LLMResponse Tests
# ============================================================================

class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_create_response(self):
        """Test creating a basic response."""
        response = LLMResponse(content="Hello!")
        assert response.content == "Hello!"
        assert response.tool_calls == []
        assert response.stop_reason == "end_turn"
        assert response.has_tool_calls is False

    def test_response_with_tool_calls(self):
        """Test response with tool calls."""
        calls = [ToolCall(id="1", name="read", arguments={"path": "file.py"})]
        response = LLMResponse(content="Reading file", tool_calls=calls)

        assert response.has_tool_calls is True
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "read"

    def test_response_custom_stop_reason(self):
        """Test response with custom stop reason."""
        response = LLMResponse(content="", stop_reason="tool_use")
        assert response.stop_reason == "tool_use"


# ============================================================================
# LLMError Tests
# ============================================================================

class TestLLMErrors:
    """Tests for LLM error classes."""

    def test_base_error(self):
        """Test base LLMError."""
        error = LLMError("Something failed", provider="test")
        assert "Something failed" in str(error)
        assert "[test]" in str(error)

    def test_error_with_suggestion(self):
        """Test error with suggestion."""
        error = LLMError("Failed", provider="test", suggestion="Try again")
        assert "Try again" in str(error)

    def test_api_key_error(self):
        """Test APIKeyError."""
        error = APIKeyError("anthropic")
        assert "API key" in str(error)
        assert "ANTHROPIC_API_KEY" in str(error)

    def test_connection_error(self):
        """Test ConnectionError."""
        error = ConnectionError("test", details="Timeout")
        assert "Connection failed" in str(error)
        assert "Timeout" in str(error)

    def test_rate_limit_error(self):
        """Test RateLimitError."""
        error = RateLimitError("test", retry_after=30)
        assert "Rate limit" in str(error)
        assert "30" in str(error)
        assert error.retry_after == 30

    def test_model_error(self):
        """Test ModelError."""
        error = ModelError("test", model="gpt-5")
        assert "gpt-5" in str(error)
        assert "not available" in str(error)

    def test_context_length_error(self):
        """Test ContextLengthError."""
        error = ContextLengthError("test", limit=4096)
        assert "Context length" in str(error)
        assert "4096" in str(error)

    def test_response_parse_error(self):
        """Test ResponseParseError."""
        error = ResponseParseError("test", details="Invalid JSON")
        assert "parse" in str(error).lower()
        assert "Invalid JSON" in str(error)


# ============================================================================
# MockLLMProvider Tests
# ============================================================================

class TestMockLLMProvider:
    """Tests for MockLLMProvider."""

    def test_is_available(self):
        """Test that mock is always available."""
        provider = MockLLMProvider()
        assert provider.is_available() is True

    def test_chat_echoes_message(self):
        """Test that chat echoes the last user message."""
        provider = MockLLMProvider()
        messages = [Message(role="user", content="Hello there")]

        response = provider.chat(messages)

        assert "[Mock]" in response.content
        assert "Hello there" in response.content

    def test_chat_with_canned_responses(self):
        """Test using canned responses."""
        provider = MockLLMProvider()
        provider.add_response("First response")
        provider.add_response("Second response")

        messages = [Message(role="user", content="Test")]

        response1 = provider.chat(messages)
        assert response1.content == "First response"

        response2 = provider.chat(messages)
        assert response2.content == "Second response"

    def test_continue_with_tool_results(self):
        """Test continuing with tool results."""
        provider = MockLLMProvider()

        tool_rounds = [{
            "content": "Checking...",
            "tool_calls": [],
            "results": [
                ToolResult(tool_id="1", content="File contents here"),
            ]
        }]

        response = provider.continue_with_tool_results(
            messages=[],
            tool_rounds=tool_rounds
        )

        assert "[Mock]" in response.content
        assert "results" in response.content.lower()


# ============================================================================
# SmartMockProvider Tests
# ============================================================================

class TestSmartMockProvider:
    """Tests for SmartMockProvider."""

    def test_is_available(self):
        """Test that smart mock is always available."""
        provider = SmartMockProvider()
        assert provider.is_available() is True

    def test_greeting_response(self):
        """Test greeting intent."""
        provider = SmartMockProvider()
        messages = [Message(role="user", content="Hello!")]

        response = provider.chat(messages)

        assert "Hello" in response.content or "help" in response.content.lower()

    def test_read_file_generates_tool_call(self):
        """Test that read file intent generates tool call."""
        provider = SmartMockProvider()
        messages = [Message(role="user", content="read file.py")]
        tools = [{"name": "read"}]

        response = provider.chat(messages, tools=tools)

        assert response.has_tool_calls is True
        assert response.tool_calls[0].name == "read"
        assert "file.py" in response.tool_calls[0].arguments.get("path", "")

    def test_list_files_generates_tool_call(self):
        """Test that list files intent generates tool call."""
        provider = SmartMockProvider()
        messages = [Message(role="user", content="list files")]
        tools = [{"name": "bash"}]

        response = provider.chat(messages, tools=tools)

        assert response.has_tool_calls is True
        assert response.tool_calls[0].name == "bash"
        assert "ls" in response.tool_calls[0].arguments.get("command", "")

    def test_git_status_generates_tool_call(self):
        """Test that git status intent generates tool call."""
        provider = SmartMockProvider()
        messages = [Message(role="user", content="git status")]
        tools = [{"name": "bash"}]

        response = provider.chat(messages, tools=tools)

        assert response.has_tool_calls is True
        assert "git status" in response.tool_calls[0].arguments.get("command", "")

    def test_show_pwd_generates_tool_call(self):
        """Test that show pwd intent generates tool call."""
        provider = SmartMockProvider()
        messages = [Message(role="user", content="what is the current directory")]
        tools = [{"name": "bash"}]

        response = provider.chat(messages, tools=tools)

        assert response.has_tool_calls is True
        assert "pwd" in response.tool_calls[0].arguments.get("command", "")

    def test_help_response(self):
        """Test help intent."""
        provider = SmartMockProvider()
        messages = [Message(role="user", content="help")]

        response = provider.chat(messages)

        assert "OpenCode" in response.content or "help" in response.content.lower()

    def test_no_tool_when_not_available(self):
        """Test that no tool call is made when tool is not available."""
        provider = SmartMockProvider()
        messages = [Message(role="user", content="read file.py")]
        tools = []  # No tools available

        response = provider.chat(messages)

        assert response.has_tool_calls is False
        assert "not available" in response.content

    def test_continue_with_tool_results(self):
        """Test continuing with tool results."""
        provider = SmartMockProvider()

        tool_rounds = [{
            "content": "Reading...",
            "tool_calls": [],
            "results": [
                ToolResult(tool_id="1", content="File contents: print('hello')"),
            ]
        }]

        response = provider.continue_with_tool_results(
            messages=[],
            tool_rounds=tool_rounds
        )

        assert "completed" in response.content.lower() or "success" in response.content.lower()

    def test_run_command_generates_tool_call(self):
        """Test that run command intent generates tool call."""
        provider = SmartMockProvider()
        messages = [Message(role="user", content="run echo hello")]
        tools = [{"name": "bash"}]

        response = provider.chat(messages, tools=tools)

        assert response.has_tool_calls is True
        assert "echo hello" in response.tool_calls[0].arguments.get("command", "")

    def test_who_are_you_response(self):
        """Test introduction intent."""
        provider = SmartMockProvider()
        messages = [Message(role="user", content="who are you")]

        response = provider.chat(messages)

        assert "OpenCode" in response.content

    def test_empty_message(self):
        """Test handling empty message."""
        provider = SmartMockProvider()
        messages = [Message(role="system", content="System prompt")]  # No user message

        response = provider.chat(messages)

        assert "didn't receive" in response.content.lower()


# ============================================================================
# LLMProvider Base Tests
# ============================================================================

class TestLLMProviderBase:
    """Tests for LLMProvider base class functionality."""

    def test_test_connection_on_mock(self):
        """Test test_connection on mock provider."""
        provider = MockLLMProvider()
        success, message = provider.test_connection()

        assert success is True
        assert "successful" in message.lower()

    def test_debug_logging(self, capsys):
        """Test debug logging."""
        provider = MockLLMProvider()
        provider.debug = True

        provider._log_debug("TEST", {"key": "value"})

        captured = capsys.readouterr()
        assert "DEBUG" in captured.out
        assert "TEST" in captured.out

    def test_debug_logging_disabled(self, capsys):
        """Test that debug logging is off by default."""
        provider = MockLLMProvider()
        provider._log_debug("TEST", {"key": "value"})

        captured = capsys.readouterr()
        assert "DEBUG" not in captured.out


# ============================================================================
# Connection and Certificate Error Tests
# ============================================================================

class TestConnectionErrors:
    """Tests for connection and SSL certificate error handling."""

    def test_connection_error_format(self):
        """Test ConnectionError message formatting."""
        error = ConnectionError("anthropic", details="SSL certificate verify failed")

        assert "Connection failed" in str(error)
        assert "SSL certificate" in str(error)
        assert "anthropic" in str(error).lower()

    def test_connection_error_suggestion(self):
        """Test ConnectionError includes helpful suggestion."""
        error = ConnectionError("test", details="Connection refused")

        assert "internet connection" in str(error).lower() or "endpoint" in str(error).lower()

    def test_connection_error_without_details(self):
        """Test ConnectionError without details."""
        error = ConnectionError("test")

        assert "Connection failed" in str(error)
        assert error.provider == "test"


class TestAPIProviderErrors:
    """Tests for API provider error handling (mocked)."""

    def test_anthropic_error_parsing_auth(self):
        """Test that authentication errors are properly classified."""
        # Test the error class directly
        error = APIKeyError("Anthropic")

        assert "API key" in str(error)
        assert "ANTHROPIC_API_KEY" in str(error)

    def test_anthropic_error_parsing_rate_limit(self):
        """Test rate limit error formatting."""
        error = RateLimitError("Anthropic", retry_after=60)

        assert "Rate limit" in str(error)
        assert "60" in str(error)
        assert error.retry_after == 60

    def test_anthropic_error_parsing_model(self):
        """Test model not found error."""
        error = ModelError("Anthropic", "claude-nonexistent")

        assert "claude-nonexistent" in str(error)
        assert "not available" in str(error)

    def test_anthropic_error_parsing_context_length(self):
        """Test context length error."""
        error = ContextLengthError("Anthropic", limit=200000)

        assert "Context length" in str(error)
        assert "200000" in str(error)


class TestAnthropicProviderUnit:
    """Unit tests for AnthropicProvider (without API calls)."""

    def test_provider_not_available_without_key(self):
        """Test provider reports unavailable without API key."""
        try:
            from opencode.llm.anthropic import AnthropicProvider, HAS_ANTHROPIC

            provider = AnthropicProvider(api_key="", model="claude-sonnet-4-20250514")

            if HAS_ANTHROPIC:
                assert provider.is_available() is False
        except ImportError:
            pytest.skip("anthropic library not installed")

    def test_provider_available_with_key(self):
        """Test provider reports available with API key."""
        try:
            from opencode.llm.anthropic import AnthropicProvider, HAS_ANTHROPIC

            provider = AnthropicProvider(api_key="test-key", model="claude-sonnet-4-20250514")

            if HAS_ANTHROPIC:
                assert provider.is_available() is True
            else:
                assert provider.is_available() is False
        except ImportError:
            pytest.skip("anthropic library not installed")

    def test_chat_returns_error_when_unavailable(self):
        """Test that chat returns error response when provider is unavailable."""
        try:
            from opencode.llm.anthropic import AnthropicProvider

            provider = AnthropicProvider(api_key="", model="claude-sonnet-4-20250514")
            response = provider.chat(messages=[Message(role="user", content="test")])

            assert "Error" in response.content or "not available" in response.content.lower()
            assert response.stop_reason == "error"
        except ImportError:
            pytest.skip("anthropic library not installed")


class TestOpenAIProviderUnit:
    """Unit tests for OpenAI/Custom provider (without API calls)."""

    def test_openai_provider_not_available_without_key(self):
        """Test OpenAI provider reports unavailable without API key."""
        try:
            from opencode.llm.openai import OpenAIProvider, HAS_OPENAI

            provider = OpenAIProvider(api_key="", model="gpt-4")

            if HAS_OPENAI:
                assert provider.is_available() is False
        except ImportError:
            pytest.skip("openai library not installed")

    def test_custom_provider_not_available_without_base_url(self):
        """Test custom provider reports unavailable without base_url."""
        try:
            from opencode.llm.openai import CustomLLMProvider, HAS_OPENAI

            provider = CustomLLMProvider(
                api_key="test-key",
                base_url="",  # No base_url
                model="llama3"
            )

            if HAS_OPENAI:
                # CustomLLMProvider requires base_url, not api_key
                assert provider.is_available() is False
        except ImportError:
            pytest.skip("openai library not installed")

    def test_custom_provider_available_with_base_url(self):
        """Test custom provider is available with base_url (key optional for local LLMs)."""
        try:
            from opencode.llm.openai import CustomLLMProvider, HAS_OPENAI

            provider = CustomLLMProvider(
                api_key="",  # No key needed for local LLMs like Ollama
                base_url="http://localhost:11434/v1",
                model="llama3"
            )

            if HAS_OPENAI:
                # CustomLLMProvider only requires base_url
                assert provider.is_available() is True
        except ImportError:
            pytest.skip("openai library not installed")

    def test_custom_provider_with_base_url(self):
        """Test custom provider accepts base_url."""
        try:
            from opencode.llm.openai import CustomLLMProvider

            provider = CustomLLMProvider(
                api_key="test-key",
                base_url="http://localhost:11434/v1",
                model="llama3"
            )

            assert provider.base_url == "http://localhost:11434/v1"
            assert provider.model == "llama3"
        except ImportError:
            pytest.skip("openai library not installed")

    def test_openai_provider_ssl_verify_option(self):
        """Test OpenAI provider accepts ssl_verify option."""
        try:
            from opencode.llm.openai import OpenAIProvider

            # Test with SSL verification disabled
            provider = OpenAIProvider(
                api_key="test-key",
                model="gpt-4",
                ssl_verify=False
            )
            assert provider.ssl_verify is False

            # Test with custom CA bundle path
            provider2 = OpenAIProvider(
                api_key="test-key",
                model="gpt-4",
                ssl_verify="/path/to/ca-bundle.crt"
            )
            assert provider2.ssl_verify == "/path/to/ca-bundle.crt"

            # Test default (True)
            provider3 = OpenAIProvider(
                api_key="test-key",
                model="gpt-4"
            )
            assert provider3.ssl_verify is True
        except ImportError:
            pytest.skip("openai library not installed")
