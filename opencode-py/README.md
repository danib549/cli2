# OpenCode-Py

A local-first AI coding agent CLI with an interactive chat interface. OpenCode-Py helps you analyze, plan, and modify code using your choice of LLM provider.

## Features

- **Multi-Provider Support**: Anthropic (Claude), OpenAI (GPT), or any OpenAI-compatible API (Ollama, LM Studio, Azure OpenAI)
- **Three Operating Modes**: PLAN (read-only analysis), BUILD (full execution), REVIEW (deep architectural analysis)
- **Intelligent Tools**: File operations, code search, symbol navigation, shell commands
- **Session Management**: Save and restore conversation sessions
- **Workspace Safety**: Restricts file access to initialized directories
- **Git Integration**: Automatic checkpoints before destructive operations
- **Cross-Platform**: Works on Linux, macOS, and Windows

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/anthropics/opencode.git
cd opencode/opencode-py

# Install with pip
pip install -e .

# Or install with all optional dependencies
pip install -e ".[all]"
```

### Installation Options

The base installation is minimal. Add only what you need:

```bash
# Minimal install (CLI framework only, no LLM provider)
pip install -e .

# With Anthropic Claude support
pip install -e ".[anthropic]"

# With OpenAI GPT support
pip install -e ".[openai]"

# With both LLM providers
pip install -e ".[anthropic,openai]"

# Combine any extras you need
pip install -e ".[anthropic,pdf]"       # Claude + PDF
pip install -e ".[openai,excel]"        # GPT + Excel
pip install -e ".[openai,pdf,word]"     # GPT + PDF + Word
pip install -e ".[anthropic,openai,excel]"  # Both providers + Excel

# Full installation (all providers + all document types)
pip install -e ".[all]"
```

### Dependency Summary

| Extra | Packages | Purpose |
|-------|----------|---------|
| `anthropic` | anthropic | Claude models |
| `openai` | openai | GPT models, Azure, compatible APIs |
| `pdf` | pypdf | Read PDF files |
| `excel` | openpyxl | Read Excel files (.xlsx) |
| `word` | python-docx | Read Word files (.docx) |
| `docs` | All above | All document types |
| `all` | Everything | Full installation |

## Quick Start

### 1. Set Your API Key

**Linux/macOS:**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# Or for OpenAI:
export OPENAI_API_KEY="sk-..."
```

**Windows (Command Prompt):**
```cmd
set ANTHROPIC_API_KEY=sk-ant-...
```

**Windows (PowerShell):**
```powershell
$env:ANTHROPIC_API_KEY="sk-ant-..."
```

### 2. Start the Agent

```bash
opencode
```

### 3. Start Chatting

```
> Analyze the structure of this project
> Find all TODO comments in the codebase
> Refactor the authentication module
```

## Usage

### Command Line Options

```bash
# Start with defaults
opencode

# Start in read-only plan mode
opencode run --mode plan

# Use OpenAI instead of Anthropic
opencode run --provider openai --model gpt-4o

# Use local Ollama
opencode run --provider custom --model llama3 --base-url http://localhost:11434/v1

# Auto-execute mode (no confirmations)
opencode run --auto

# Initialize a workspace
opencode init

# Show configuration
opencode config
```

### Interactive Commands

Once inside the REPL, use `/` commands:

| Command | Description |
|---------|-------------|
| `/help` | Show all available commands |
| `/quit` or `/exit` | Exit the REPL |
| `/plan` | Switch to PLAN mode (read-only) |
| `/build` | Switch to BUILD mode (execution) |
| `/review [target]` | Switch to REVIEW mode (deep analysis) |
| `/review all` | Full project analysis (10 phases) |
| `/review phases` | Show/edit review phase configuration |
| `/mode` | Show current mode |
| `/auto` | Enable auto-execution |
| `/interactive` | Disable auto-execution |
| `/tools` | List available tools |
| `/config` | Show current configuration |
| `/init` | Initialize workspace |
| `/workspace` | Show workspace info |
| `/save [name]` | Save current session |
| `/load <id>` | Load a saved session |
| `/sessions` | List saved sessions |
| `/history` | Show conversation history |
| `/clear` | Clear conversation history |
| `/debug` | Toggle debug mode |

### Shell Commands

You can run shell commands directly by prefixing with `!`:

```
> !git status
> !npm test
> !ls -la
```

Safe commands (like `ls`, `git status`, `pwd`) run automatically. Others require confirmation.

## Operating Modes

### PLAN Mode

Read-only mode for analysis and planning. Cannot modify files or run commands.

```
/plan
> Analyze the error handling in src/api/
> What are the security concerns in this module?
```

### BUILD Mode

Full execution mode. Can read, write, edit files and run shell commands.

```
/build
> Fix the bug in the login function
> Add input validation to the user form
```

### REVIEW Mode

Deep architectural analysis mode. Read-only but with comprehensive analysis prompts.

```
/review src/core/
/review all          # Full 10-phase project analysis
```

## Configuration

### Config File Locations

- **Global**: `~/.opencode/config.toml` (Linux/macOS) or `%APPDATA%\opencode\config.toml` (Windows)
- **Local**: `.opencode/config.toml` (per-project, overrides global)

### Example Configuration

```toml
[llm]
provider = "anthropic"           # or "openai", "custom"
model = "claude-sonnet-4-20250514"
# api_key = "sk-..."            # Better to use environment variables
# base_url = ""                 # For custom endpoints

[ssl]
# cert_path = "/path/to/ca-bundle.crt"
# verify = true

[complexity]
threshold = 0.6                  # Auto-plan trigger (0.0-1.0)
auto_plan = true

[execution]
auto_execute_safe = true
tool_timeout = 30
checkpoint_enabled = true
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic/Claude API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENCODE_API_KEY` | Generic API key (overrides others) |
| `OPENCODE_LLM_PROVIDER` | Provider: anthropic, openai, custom |
| `OPENCODE_LLM_MODEL` | Model name |
| `OPENCODE_BASE_URL` | Custom API endpoint |
| `OPENCODE_SSL_CERT_PATH` | Path to CA certificate |
| `OPENCODE_SSL_VERIFY` | Enable/disable SSL verification |
| `OPENCODE_DEBUG` | Enable debug output |

### Provider Examples

**Anthropic (Default):**
```toml
[llm]
provider = "anthropic"
model = "claude-sonnet-4-20250514"
```

**OpenAI:**
```toml
[llm]
provider = "openai"
model = "gpt-4o"
```

**Azure OpenAI:**
```toml
[llm]
provider = "openai"
model = "gpt-4"
base_url = "https://YOUR-RESOURCE.openai.azure.com/openai/deployments/YOUR-DEPLOYMENT"
```

**Ollama (Local):**
```toml
[llm]
provider = "custom"
model = "llama3"
base_url = "http://localhost:11434/v1"
```

**LM Studio (Local):**
```toml
[llm]
provider = "custom"
model = "local-model"
base_url = "http://localhost:1234/v1"
```

### SSL/TLS for Corporate Environments

```toml
[ssl]
cert_path = "/etc/pki/tls/certs/corporate-ca-bundle.crt"
verify = true
```

Or via environment:
```bash
export SSL_CERT_FILE="/path/to/ca-bundle.crt"
# or
export REQUESTS_CA_BUNDLE="/path/to/ca-bundle.crt"
```

## Available Tools

The AI agent has access to these tools:

### File Operations

| Tool | Description | Mode |
|------|-------------|------|
| `read` | Read file contents (supports text, Excel, Word, PDF) | All |
| `write` | Write/create files | BUILD |
| `edit` | Edit files with search/replace | BUILD |
| `glob` | Find files by pattern | All |
| `grep` | Search file contents with regex | All |
| `tree` | Show directory structure | All |
| `outline` | Show file structure (functions, classes) | All |

### Symbol Navigation

| Tool | Description | Mode |
|------|-------------|------|
| `find_definition` | Find where a symbol is defined | All |
| `find_references` | Find all references to a symbol | All |
| `find_symbols` | List all symbols in a file/directory | All |
| `rename_symbol` | Rename a symbol across files | BUILD |

### Shell

| Tool | Description | Mode |
|------|-------------|------|
| `bash` | Execute shell commands | BUILD |

## Project Instructions (iai.md)

Create an `iai.md` file in your project root to provide context to the AI:

```markdown
# Project: My Application

## Overview
This is a web application built with React and Node.js.

## Architecture
- Frontend: React + TypeScript
- Backend: Express.js
- Database: PostgreSQL

## Coding Standards
- Use TypeScript strict mode
- Follow ESLint rules
- Write tests for all new features

## Important Notes
- Never commit API keys
- Always run tests before committing
```

## Workspaces

Initialize a workspace to restrict file access:

```bash
cd my-project
opencode init
```

This creates:
- `.opencode/config.toml` - Local configuration
- `.opencode/workspace.json` - Workspace metadata
- `iai.md` - Project instructions for the AI

## Session Management

Save your conversation for later:

```
/save my-refactoring-session
```

List and load sessions:

```
/sessions
/load abc123
```

## Review Mode

### Basic Review

```
/review src/api/
```

Analyzes a specific path with 8 dimensions:
1. Structure & Organization
2. Function/Class Signatures
3. Code Flow & Execution Paths
4. Dependencies & Coupling
5. Testing Considerations
6. Security Review
7. Performance Patterns
8. Code Quality

### Full Project Review

```
/review all
```

Runs 10 comprehensive phases:
1. Project Mapping (structure, dependency graphs)
2. Data & Control Flow (inputs, outputs, flow diagrams)
3. Protocols & Interfaces (APIs, serialization)
4. State Management (globals, singletons, transitions)
5. Security Analysis (vulnerabilities, trust boundaries)
6. Component Analysis (per-module breakdown)
7. Call Graphs (entry points, call trees)
8. Quality Metrics (LOC, patterns, docs)
9. Testing Analysis (coverage, recommendations)
10. Executive Summary (synthesis, action items)

### Customize Review Phases

```
/review phases
```

Creates `~/.opencode/review_phases.toml` for customization.

## Development

### Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

### Project Structure

```
opencode-py/
├── src/opencode/
│   ├── cli.py           # Main REPL and CLI entry point
│   ├── config.py        # Configuration management
│   ├── mode.py          # PLAN/BUILD/REVIEW mode management
│   ├── workspace.py     # Workspace and file access control
│   ├── permissions.py   # Permission gating for tools
│   ├── complexity.py    # Task complexity analysis
│   ├── session.py       # Session save/load
│   ├── git.py           # Git integration
│   ├── llm/
│   │   ├── base.py      # Base LLM interface
│   │   ├── anthropic.py # Anthropic/Claude provider
│   │   ├── openai.py    # OpenAI provider
│   │   └── parser.py    # Response parsing
│   └── tools/
│       ├── base.py      # Base tool class
│       ├── registry.py  # Tool registry
│       ├── read.py      # File reading (text, Excel, Word, PDF)
│       ├── write.py     # File writing
│       ├── edit.py      # File editing
│       ├── glob.py      # File pattern matching
│       ├── grep.py      # Content search
│       ├── tree.py      # Directory tree
│       ├── outline.py   # Code structure outline
│       ├── bash.py      # Shell command execution
│       └── find_*.py    # Symbol navigation tools
├── tests/               # Test suite
└── pyproject.toml       # Project configuration
```

## Security

- **Workspace Isolation**: File operations restricted to initialized workspace
- **Permission Gating**: Dangerous operations require confirmation
- **Git Checkpoints**: Automatic commits before destructive changes
- **No Secrets in Config**: API keys should use environment variables
- **SSL/TLS Support**: Custom CA certificates for corporate environments

## Troubleshooting

### API Key Not Found

```bash
# Check if set
echo $ANTHROPIC_API_KEY

# Set it
export ANTHROPIC_API_KEY="sk-ant-..."
```

### SSL Certificate Errors

```bash
# Use custom CA bundle
export SSL_CERT_FILE="/path/to/ca-bundle.crt"

# Or disable verification (not recommended)
export OPENCODE_SSL_VERIFY="false"
```

### Streaming Issues

If you experience issues with streaming responses:

```toml
[llm]
stream = false
```

### Debug Mode

```bash
OPENCODE_DEBUG=1 opencode run
```

Or inside the REPL:
```
/debug
```

## License

MIT License - See LICENSE file for details.

## Contributing

Contributions are welcome! Please read the contributing guidelines before submitting PRs.

## Support

- Issues: https://github.com/anthropics/opencode/issues
- Documentation: https://github.com/anthropics/opencode
