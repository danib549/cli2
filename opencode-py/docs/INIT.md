# Workspace Initialization

OpenCode-Py requires an initialized workspace to operate. This ensures file access is controlled and configurations are project-specific.

## Quick Start

```bash
cd your-project
opencode init
opencode
```

Or just run `opencode` - it will auto-initialize if needed.

## What `init` Does

Creates a `.opencode/` directory with:

```
.opencode/
├── config.toml      # Local configuration (overrides global)
├── workspace.json   # Workspace metadata
└── .gitignore       # Ignores sensitive files
```

## Commands

### Initialize Workspace

```bash
# Initialize current directory
opencode init

# Initialize specific directory
opencode init /path/to/project

# Inside REPL
/init
```

### Check Workspace Status

```bash
# Inside REPL
/workspace
```

Output:
```
Workspace: /home/user/myproject
Config dir: /home/user/myproject/.opencode
Local config: /home/user/myproject/.opencode/config.toml

Global config: /home/user/.opencode/config.toml
```

## Auto-Initialization

When you run `opencode` in a directory without a workspace:
- It automatically initializes the workspace
- Creates `.opencode/` directory
- You can start working immediately

## File Access Boundaries

Once initialized, OpenCode-Py can access **all files and subfolders** within the workspace:

```
/home/user/myproject/          <- Workspace root
├── .opencode/                 <- ✓ Allowed
├── iai.md                     <- ✓ Allowed (project instructions)
├── src/                       <- ✓ Allowed
│   └── app.py                 <- ✓ Allowed
│   └── utils/                 <- ✓ Allowed (subfolders too!)
│       └── helpers.py         <- ✓ Allowed
├── tests/                     <- ✓ Allowed
└── README.md                  <- ✓ Allowed

/home/user/other-project/      <- ✗ BLOCKED (outside workspace)
/etc/passwd                    <- ✗ BLOCKED (outside workspace)
```

Attempting to access files outside the workspace returns an error:
```
[Error] Access denied: '/etc/passwd' is outside workspace boundaries.
Workspace root: /home/user/myproject
```

## Configuration Hierarchy

```
1. Global config     ~/.opencode/config.toml (or %APPDATA%\opencode\config.toml)
2. Local config      .opencode/config.toml (only if workspace initialized)
3. Environment vars  OPENCODE_* variables (highest priority)
```

Local config only loads from initialized workspaces - no implicit config file detection.

## Local Config Example

`.opencode/config.toml`:
```toml
[llm]
provider = "openai"
model = "gpt-4o"

[complexity]
threshold = 0.5    # More sensitive auto-planning

[execution]
auto_execute_safe = true
```

## Git Integration

The `.opencode/` directory includes a `.gitignore` that ignores:
- `config.toml` (may contain API keys)
- `*.log` files

You can commit `.opencode/workspace.json` to share workspace settings with your team.

## Multiple Workspaces

Each project has its own workspace:

```bash
cd ~/project-a
opencode init    # Creates ~/project-a/.opencode/

cd ~/project-b
opencode init    # Creates ~/project-b/.opencode/
```

Each workspace has independent:
- Local configuration
- File access boundaries
- Git checkpoints
