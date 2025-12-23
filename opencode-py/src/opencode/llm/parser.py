"""Plan response parser."""

import re
from typing import Optional

from opencode.tracker import Plan


class PlanParser:
    """Parse structured plans from LLM responses."""

    # Pattern for PLAN: title followed by STEPS: list
    PLAN_PATTERN = re.compile(
        r"PLAN:\s*(.+?)(?:\n|$)"
        r"(?:.*?)"
        r"STEPS:\s*\n((?:\d+\..+\n?)+)",
        re.MULTILINE | re.DOTALL
    )

    # Alternative pattern for numbered lists without explicit STEPS:
    ALT_PLAN_PATTERN = re.compile(
        r"PLAN:\s*(.+?)(?:\n|$)"
        r"(?:.*?)"
        r"((?:\d+\.\s+.+\n?)+)",
        re.MULTILINE | re.DOTALL
    )

    # Markdown-style pattern: ## Plan: title
    MD_PLAN_PATTERN = re.compile(
        r"#+\s*Plan:\s*(.+?)(?:\n|$)"
        r"(?:.*?)"
        r"((?:\d+\.\s+.+\n?)+)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )

    # Pattern for step lines
    STEP_PATTERN = re.compile(r"^\d+\.\s*(.+)$", re.MULTILINE)

    def parse(self, response: str) -> Optional[Plan]:
        """Parse a plan from LLM response text.

        Args:
            response: The LLM response text.

        Returns:
            Plan object if found, None otherwise.
        """
        # Try main pattern first
        match = self.PLAN_PATTERN.search(response)
        if not match:
            match = self.ALT_PLAN_PATTERN.search(response)
        if not match:
            match = self.MD_PLAN_PATTERN.search(response)

        if not match:
            return None

        title = match.group(1).strip()
        steps_text = match.group(2)

        plan = Plan(title=title)

        # Extract individual steps
        for step_match in self.STEP_PATTERN.finditer(steps_text):
            step_desc = step_match.group(1).strip()
            if step_desc:
                plan.add_task(step_desc)

        # Only return if we found actual steps
        if plan.tasks:
            return plan

        return None

    def has_plan(self, response: str) -> bool:
        """Check if response contains a plan."""
        return bool(self.PLAN_PATTERN.search(response) or
                    self.ALT_PLAN_PATTERN.search(response))

    def has_confirmation_prompt(self, response: str) -> bool:
        """Check if response asks for build confirmation."""
        patterns = [
            r"ready for build mode",
            r"say.*build.*to proceed",
            r"confirm.*build",
            r"proceed with implementation",
        ]
        response_lower = response.lower()
        return any(re.search(p, response_lower) for p in patterns)

    def extract_step_announcement(self, response: str) -> Optional[tuple[int, str]]:
        """Extract step announcement like '[Step N] description'.

        Returns:
            Tuple of (step_number, action) or None.
        """
        pattern = r"\[Step\s+(\d+)\]\s*(.+?)(?:\n|$)"
        match = re.search(pattern, response)
        if match:
            return int(match.group(1)), match.group(2).strip()
        return None

    def extract_step_completion(self, response: str) -> Optional[int]:
        """Extract step completion like '[Step N] Done'.

        Returns:
            Step number or None.
        """
        pattern = r"\[Step\s+(\d+)\]\s*(?:Done|Completed|Finished)"
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None


def format_plan_prompt() -> str:
    """Get instructions for LLM to output structured plans."""
    return """
When given a complex task, output a structured plan using this format:

PLAN: <Brief title describing the task>
STEPS:
1. <First step description>
2. <Second step description>
3. <Third step description>
...

After listing steps, end with:
"Ready for BUILD mode? Say `build` to proceed."

During execution, announce each step:
"[Step N] <description>"

And mark completion:
"[Step N] Done."
"""
