"""LLM subsystem.

Provides:
- LLMProvider base class
- AnthropicProvider implementation
- MockLLMProvider for testing
- PlanParser for extracting structured plans
"""

from opencode.llm.base import (
    LLMProvider,
    LLMResponse,
    Message,
    ToolCall,
    ToolResult,
)
from opencode.llm.anthropic import AnthropicProvider
from opencode.llm.openai import OpenAIProvider, CustomLLMProvider
from opencode.llm.parser import PlanParser, format_plan_prompt

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "Message",
    "ToolCall",
    "ToolResult",
    "AnthropicProvider",
    "OpenAIProvider",
    "CustomLLMProvider",
    "PlanParser",
    "format_plan_prompt",
]
