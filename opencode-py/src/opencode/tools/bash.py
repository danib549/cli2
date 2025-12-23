"""Bash shell tool."""

import subprocess
import sys
import select
import os

from opencode.tools.base import Tool, ToolResult


class BashTool(Tool):
    """Execute shell commands."""

    name = "bash"
    description = "Execute a shell command and return the output"
    requires_build_mode = True

    # Commands that might mutate the filesystem
    MUTATING_PATTERNS = [
        "rm ", "rm\t", "rmdir",
        "mv ", "mv\t",
        "cp ", "cp\t",
        "mkdir ", "mkdir\t",
        "touch ", "touch\t",
        "chmod ", "chown ",
        "> ", ">> ",
        "git commit", "git push", "git checkout", "git reset",
        "git merge", "git rebase", "git cherry-pick",
        "npm install", "npm uninstall", "npm update",
        "pip install", "pip uninstall",
        "apt ", "apt-get ", "brew ", "yum ", "dnf ",
        "docker ", "kubectl ",
    ]

    def execute(self, command: str) -> ToolResult:
        """Execute a shell command.

        Args:
            command: The shell command to run.

        Returns:
            ToolResult with command output.
        """
        self._check_mode()

        # Get timeout from config or default
        timeout = 30
        if self.config:
            timeout = self.config.tool_timeout

        # Checkpoint before potentially mutating commands
        if self._is_mutating(command):
            self._checkpoint(f"Before bash: {command[:50]}")

        # Show command being executed
        print(f"\033[36m$ {command}\033[0m")

        try:
            # Use Popen for real-time output streaming
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                cwd=None,
            )

            stdout_lines = []
            stderr_lines = []

            # Cross-platform real-time output reading
            if os.name == 'nt':
                # Windows: use threads for non-blocking read
                import threading
                import queue

                def reader(pipe, q, color=None):
                    for line in iter(pipe.readline, ''):
                        q.put((line, color))
                    pipe.close()

                q = queue.Queue()
                stdout_thread = threading.Thread(
                    target=reader, args=(process.stdout, q, None), daemon=True
                )
                stderr_thread = threading.Thread(
                    target=reader, args=(process.stderr, q, '\033[33m'), daemon=True
                )
                stdout_thread.start()
                stderr_thread.start()

                import time
                start_time = time.time()
                while process.poll() is None or not q.empty():
                    if time.time() - start_time > timeout:
                        process.kill()
                        return ToolResult.fail(f"Command timed out after {timeout}s")
                    try:
                        line, color = q.get(timeout=0.1)
                        line = line.rstrip('\n\r')
                        if color:
                            print(f"{color}{line}\033[0m")
                            stderr_lines.append(line)
                        else:
                            print(line)
                            stdout_lines.append(line)
                    except queue.Empty:
                        pass

                stdout_thread.join(timeout=1)
                stderr_thread.join(timeout=1)
            else:
                # Unix: use select for non-blocking read
                import time
                start_time = time.time()

                while process.poll() is None:
                    if time.time() - start_time > timeout:
                        process.kill()
                        return ToolResult.fail(f"Command timed out after {timeout}s")

                    # Check for readable output
                    readable, _, _ = select.select(
                        [process.stdout, process.stderr], [], [], 0.1
                    )

                    for stream in readable:
                        line = stream.readline()
                        if line:
                            line = line.rstrip('\n\r')
                            if stream == process.stderr:
                                print(f"\033[33m{line}\033[0m")
                                stderr_lines.append(line)
                            else:
                                print(line)
                                stdout_lines.append(line)

                # Read any remaining output
                for line in process.stdout:
                    line = line.rstrip('\n\r')
                    print(line)
                    stdout_lines.append(line)
                for line in process.stderr:
                    line = line.rstrip('\n\r')
                    print(f"\033[33m{line}\033[0m")
                    stderr_lines.append(line)

            # Build output for LLM
            output = '\n'.join(stdout_lines)
            if stderr_lines:
                output += f"\n[stderr]\n" + '\n'.join(stderr_lines)

            # Truncate for LLM context (display already shown in real-time)
            lines = output.splitlines()
            if len(lines) > 50:
                output = '\n'.join(lines[:50]) + f"\n... ({len(lines) - 50} more lines)"

            if process.returncode == 0:
                return ToolResult.ok(output)
            else:
                return ToolResult.fail(
                    f"Exit code {process.returncode}",
                    output=output
                )

        except Exception as e:
            return ToolResult.fail(str(e))

    def _is_mutating(self, command: str) -> bool:
        """Check if command might mutate the filesystem."""
        cmd_lower = command.lower()
        return any(p in cmd_lower for p in self.MUTATING_PATTERNS)

    def get_schema(self) -> dict:
        """Return JSON schema for LLM function calling."""
        return {
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                }
            },
            "required": ["command"]
        }
