"""LLM subsystem.

Provides:
- LLMProvider base class
- AnthropicProvider implementation
- MockLLMProvider for testing
- PlanParser for extracting structured plans
- LLMError classes for structured error handling
"""

from opencode.llm.base import (
    LLMProvider,
    LLMResponse,
    Message,
    ToolCall,
    ToolResult,
    # Error classes
    LLMError,
    APIKeyError,
    ConnectionError,
    RateLimitError,
    ModelError,
    ContextLengthError,
    ResponseParseError,
)
from opencode.llm.anthropic import AnthropicProvider
from opencode.llm.openai import OpenAIProvider, CustomLLMProvider
from opencode.llm.parser import PlanParser, format_plan_prompt

__all__ = [
    # Core classes
    "LLMProvider",
    "LLMResponse",
    "Message",
    "ToolCall",
    "ToolResult",
    # Providers
    "AnthropicProvider",
    "OpenAIProvider",
    "CustomLLMProvider",
    # Errors
    "LLMError",
    "APIKeyError",
    "ConnectionError",
    "RateLimitError",
    "ModelError",
    "ContextLengthError",
    "ResponseParseError",
    # Parser
    "PlanParser",
    "format_plan_prompt",
]
