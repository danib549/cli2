# LLM Configuration Guide

This guide explains how to configure different LLM providers for OpenCode-Py.

## Supported Providers

| Provider | Models | API Key Variable |
|----------|--------|------------------|
| Anthropic | Claude 3.5, Claude 3 | `ANTHROPIC_API_KEY` |
| OpenAI | GPT-4, GPT-4o, GPT-3.5, o1 | `OPENAI_API_KEY` |
| Custom | Any OpenAI-compatible | `OPENCODE_API_KEY` |

## Quick Setup

### Anthropic (Claude)

```bash
# Linux/macOS
export ANTHROPIC_API_KEY="sk-ant-..."

# Windows CMD
set ANTHROPIC_API_KEY=sk-ant-...

# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

### OpenAI

```bash
# Linux/macOS
export OPENAI_API_KEY="sk-..."

# Windows CMD
set OPENAI_API_KEY=sk-...

# Windows PowerShell
$env:OPENAI_API_KEY = "sk-..."
```

### Custom Provider (Ollama, LM Studio, vLLM, etc.)

```bash
# Linux/macOS
export OPENCODE_BASE_URL="http://localhost:11434/v1"
export OPENCODE_LLM_MODEL="llama3"
export OPENCODE_LLM_PROVIDER="custom"

# Windows CMD
set OPENCODE_BASE_URL=http://localhost:11434/v1
set OPENCODE_LLM_MODEL=llama3
set OPENCODE_LLM_PROVIDER=custom

# Windows PowerShell
$env:OPENCODE_BASE_URL = "http://localhost:11434/v1"
$env:OPENCODE_LLM_MODEL = "llama3"
$env:OPENCODE_LLM_PROVIDER = "custom"
```

## Configuration File

### Location

| OS | Global Config | Local Config |
|----|---------------|--------------|
| Linux/macOS | `~/.opencode/config.toml` | `.opencode/config.toml` |
| Windows | `%APPDATA%\opencode\config.toml` | `.opencode\config.toml` |

### Example Configurations

#### Anthropic Claude

```toml
[llm]
provider = "anthropic"
model = "claude-sonnet-4-20250514"
# Other models: claude-3-opus-20240229, claude-3-haiku-20240307
```

#### OpenAI GPT-4

```toml
[llm]
provider = "openai"
model = "gpt-4o"
# Other models: gpt-4, gpt-4-turbo, gpt-3.5-turbo, o1-preview, o1-mini
```

#### OpenAI with Azure

```toml
[llm]
provider = "openai"
model = "gpt-4"
base_url = "https://your-resource.openai.azure.com/openai/deployments/your-deployment"
```

#### Ollama (Local)

```toml
[llm]
provider = "custom"
model = "llama3"
base_url = "http://localhost:11434/v1"
```

#### LM Studio (Local)

```toml
[llm]
provider = "custom"
model = "local-model"
base_url = "http://localhost:1234/v1"
```

#### Together AI

```toml
[llm]
provider = "custom"
model = "meta-llama/Llama-3-70b-chat-hf"
base_url = "https://api.together.xyz/v1"
# Set OPENCODE_API_KEY=your-together-api-key
```

#### Groq

```toml
[llm]
provider = "custom"
model = "llama3-70b-8192"
base_url = "https://api.groq.com/openai/v1"
# Set OPENCODE_API_KEY=your-groq-api-key
```

#### OpenRouter

```toml
[llm]
provider = "custom"
model = "anthropic/claude-3-sonnet"
base_url = "https://openrouter.ai/api/v1"
# Set OPENCODE_API_KEY=your-openrouter-api-key
```

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key | `sk-ant-...` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `OPENCODE_API_KEY` | Generic API key (highest priority) | `your-key` |
| `OPENCODE_LLM_PROVIDER` | Override provider | `anthropic`, `openai`, `custom` |
| `OPENCODE_LLM_MODEL` | Override model | `gpt-4o`, `llama3` |
| `OPENCODE_BASE_URL` | Custom API endpoint | `http://localhost:11434/v1` |

## Priority Order

Configuration is loaded in this order (later overrides earlier):

1. **Defaults** - Anthropic Claude Sonnet
2. **Global config** - `~/.opencode/config.toml`
3. **Local config** - `.opencode/config.toml` in workspace
4. **Environment variables** - Highest priority

## CLI Overrides

You can override settings per-session:

```bash
# Use a different provider
opencode --provider openai --model gpt-4o

# Use a custom endpoint
opencode --provider custom --model llama3 --base-url http://localhost:11434/v1
```

## Verify Configuration

Run `opencode` and check the startup message:

```
OpenCode-Py v0.1.0
Provider: openai | Model: gpt-4o
Mode: BUILD/INTERACTIVE
```

Or use `/config` command inside the REPL to see full configuration.

## Troubleshooting

### "No LLM provider configured"

- Check if API key environment variable is set
- Verify config file syntax (TOML format)
- Make sure `[llm]` section header exists in config

### Wrong model being used

- Environment variables override config files
- Check with `/config` to see which config files are loaded
- Use `--model` flag to override

### Custom provider not working

- Ensure the endpoint is OpenAI-compatible
- Check if `base_url` ends with `/v1`
- Some providers need specific model names
