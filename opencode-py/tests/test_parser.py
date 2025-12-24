"""Tests for PlanParser - plan extraction from LLM responses."""

import pytest

from opencode.llm.parser import PlanParser, format_plan_prompt


class TestPlanParserBasic:
    """Basic plan parsing tests."""

    def test_parse_standard_plan_format(self):
        """Test parsing standard PLAN: + STEPS: format."""
        parser = PlanParser()
        response = """
Let me analyze this task.

PLAN: Implement user authentication
STEPS:
1. Create user model with password hashing
2. Add login endpoint
3. Add logout endpoint
4. Add session management

Ready for BUILD mode? Say `build` to proceed.
"""
        plan = parser.parse(response)

        assert plan is not None
        assert plan.title == "Implement user authentication"
        assert len(plan.tasks) == 4
        assert plan.tasks[0].description == "Create user model with password hashing"
        assert plan.tasks[1].description == "Add login endpoint"
        assert plan.tasks[2].description == "Add logout endpoint"
        assert plan.tasks[3].description == "Add session management"

    def test_parse_alternative_format_without_steps_header(self):
        """Test parsing PLAN: followed directly by numbered list."""
        parser = PlanParser()
        response = """
PLAN: Refactor database layer

1. Extract connection pool to separate module
2. Add retry logic for transient failures
3. Implement connection health checks
"""
        plan = parser.parse(response)

        assert plan is not None
        assert plan.title == "Refactor database layer"
        assert len(plan.tasks) == 3

    def test_parse_markdown_style_plan(self):
        """Test parsing ## Plan: markdown format."""
        parser = PlanParser()
        response = """
## Plan: Add caching layer

Here's what we'll do:

1. Install Redis client
2. Create cache wrapper class
3. Add cache decorators
4. Update config for cache settings
"""
        plan = parser.parse(response)

        assert plan is not None
        assert plan.title == "Add caching layer"
        assert len(plan.tasks) == 4

    def test_parse_with_hash_plan(self):
        """Test parsing # Plan: format."""
        parser = PlanParser()
        response = """
# Plan: Fix memory leak

Investigation complete. Here's the plan:

1. Identify leaked objects using profiler
2. Fix circular references in event handlers
3. Add cleanup in __del__ methods
"""
        plan = parser.parse(response)

        assert plan is not None
        assert "Fix memory leak" in plan.title
        assert len(plan.tasks) == 3

    def test_parse_returns_none_for_no_plan(self):
        """Test that parse returns None when no plan found."""
        parser = PlanParser()
        response = """
I can help you with that. Let me read the file first.

The code looks good but has a few issues...
"""
        plan = parser.parse(response)
        assert plan is None

    def test_parse_returns_none_for_empty_steps(self):
        """Test that parse returns None when PLAN has no steps."""
        parser = PlanParser()
        response = """
PLAN: Do something

No specific steps here, just general guidance.
"""
        plan = parser.parse(response)
        assert plan is None


class TestPlanParserEdgeCases:
    """Edge cases for plan parsing."""

    def test_parse_steps_with_extra_content(self):
        """Test parsing steps that have explanatory text."""
        parser = PlanParser()
        response = """
PLAN: Update API endpoints
STEPS:
1. Modify /users endpoint to support pagination
2. Add rate limiting to all endpoints
3. Update OpenAPI documentation
"""
        plan = parser.parse(response)

        assert plan is not None
        assert len(plan.tasks) == 3
        assert "pagination" in plan.tasks[0].description

    def test_parse_with_multiline_title(self):
        """Test that title is extracted correctly even with complex text."""
        parser = PlanParser()
        response = """
PLAN: Complex multi-word title with special chars (v2.0)
STEPS:
1. First step
2. Second step
"""
        plan = parser.parse(response)

        assert plan is not None
        assert "Complex multi-word title" in plan.title

    def test_parse_with_content_between_plan_and_steps(self):
        """Test parsing with explanatory content between PLAN and STEPS."""
        parser = PlanParser()
        response = """
PLAN: Migrate to PostgreSQL

This migration requires careful planning. We need to ensure zero downtime.

STEPS:
1. Set up PostgreSQL instance
2. Create migration scripts
3. Run parallel writes
4. Switch reads to PostgreSQL
5. Decommission old database
"""
        plan = parser.parse(response)

        assert plan is not None
        assert plan.title == "Migrate to PostgreSQL"
        assert len(plan.tasks) == 5

    def test_parse_step_numbers_not_sequential(self):
        """Test that non-sequential step numbers are still parsed."""
        parser = PlanParser()
        response = """
PLAN: Fix issues
STEPS:
1. First fix
3. Third fix
5. Fifth fix
"""
        plan = parser.parse(response)

        assert plan is not None
        # Should still extract 3 steps
        assert len(plan.tasks) == 3

    def test_parse_single_step(self):
        """Test parsing a plan with only one step."""
        parser = PlanParser()
        response = """
PLAN: Quick fix
STEPS:
1. Update the version number in package.json
"""
        plan = parser.parse(response)

        assert plan is not None
        assert len(plan.tasks) == 1
        assert "version number" in plan.tasks[0].description


class TestHasPlan:
    """Tests for has_plan() method."""

    def test_has_plan_with_standard_format(self):
        """Test has_plan detects standard format."""
        parser = PlanParser()
        response = """
PLAN: Do something
STEPS:
1. First step
"""
        assert parser.has_plan(response) is True

    def test_has_plan_with_alternative_format(self):
        """Test has_plan detects alternative format."""
        parser = PlanParser()
        response = """
PLAN: Do something

1. First step
2. Second step
"""
        assert parser.has_plan(response) is True

    def test_has_plan_false_for_no_plan(self):
        """Test has_plan returns False when no plan."""
        parser = PlanParser()
        response = "Just some regular text without a plan."
        assert parser.has_plan(response) is False

    def test_has_plan_false_for_plan_keyword_in_text(self):
        """Test has_plan doesn't match 'plan' in regular text."""
        parser = PlanParser()
        response = "We should plan this carefully before proceeding."
        assert parser.has_plan(response) is False


class TestHasConfirmationPrompt:
    """Tests for has_confirmation_prompt() method."""

    def test_detects_ready_for_build_mode(self):
        """Test detection of 'ready for build mode'."""
        parser = PlanParser()
        response = "Ready for BUILD mode? Say `build` to proceed."
        assert parser.has_confirmation_prompt(response) is True

    def test_detects_say_build_to_proceed(self):
        """Test detection of 'say build to proceed'."""
        parser = PlanParser()
        response = "When you're ready, say build to proceed with implementation."
        assert parser.has_confirmation_prompt(response) is True

    def test_detects_confirm_build(self):
        """Test detection of 'confirm build'."""
        parser = PlanParser()
        response = "Please confirm build to start the implementation."
        assert parser.has_confirmation_prompt(response) is True

    def test_detects_proceed_with_implementation(self):
        """Test detection of 'proceed with implementation'."""
        parser = PlanParser()
        response = "Type 'yes' to proceed with implementation."
        assert parser.has_confirmation_prompt(response) is True

    def test_no_confirmation_in_regular_text(self):
        """Test that regular text doesn't trigger confirmation detection."""
        parser = PlanParser()
        response = "I'll help you build this feature. Let me start planning."
        assert parser.has_confirmation_prompt(response) is False


class TestStepAnnouncement:
    """Tests for extract_step_announcement() method."""

    def test_extract_step_announcement_basic(self):
        """Test extracting basic step announcement."""
        parser = PlanParser()
        response = "[Step 1] Creating the user model"
        result = parser.extract_step_announcement(response)

        assert result is not None
        step_num, action = result
        assert step_num == 1
        assert action == "Creating the user model"

    def test_extract_step_announcement_with_context(self):
        """Test extracting step announcement from larger text."""
        parser = PlanParser()
        response = """
Starting implementation now.

[Step 2] Adding the login endpoint

I'll create the route handler...
"""
        result = parser.extract_step_announcement(response)

        assert result is not None
        step_num, action = result
        assert step_num == 2
        assert "Adding the login endpoint" in action

    def test_extract_step_announcement_high_number(self):
        """Test extracting step with high step number."""
        parser = PlanParser()
        response = "[Step 15] Final cleanup and documentation"
        result = parser.extract_step_announcement(response)

        assert result is not None
        step_num, action = result
        assert step_num == 15

    def test_extract_step_announcement_none_when_missing(self):
        """Test returns None when no step announcement."""
        parser = PlanParser()
        response = "I'm working on the implementation."
        result = parser.extract_step_announcement(response)
        assert result is None


class TestStepCompletion:
    """Tests for extract_step_completion() method."""

    def test_extract_step_completion_done(self):
        """Test extracting step completion with 'Done'."""
        parser = PlanParser()
        response = "[Step 1] Done"
        result = parser.extract_step_completion(response)
        assert result == 1

    def test_extract_step_completion_completed(self):
        """Test extracting step completion with 'Completed'."""
        parser = PlanParser()
        response = "[Step 3] Completed"
        result = parser.extract_step_completion(response)
        assert result == 3

    def test_extract_step_completion_finished(self):
        """Test extracting step completion with 'Finished'."""
        parser = PlanParser()
        response = "[Step 5] Finished"
        result = parser.extract_step_completion(response)
        assert result == 5

    def test_extract_step_completion_case_insensitive(self):
        """Test step completion is case insensitive."""
        parser = PlanParser()

        assert parser.extract_step_completion("[Step 1] DONE") == 1
        assert parser.extract_step_completion("[Step 2] done") == 2
        assert parser.extract_step_completion("[Step 3] DoNe") == 3

    def test_extract_step_completion_with_context(self):
        """Test extracting step completion from larger text."""
        parser = PlanParser()
        response = """
The file has been updated successfully.

[Step 4] Done

Moving on to the next step...
"""
        result = parser.extract_step_completion(response)
        assert result == 4

    def test_extract_step_completion_none_when_missing(self):
        """Test returns None when no step completion."""
        parser = PlanParser()
        response = "[Step 1] Working on it..."
        result = parser.extract_step_completion(response)
        assert result is None


class TestFormatPlanPrompt:
    """Tests for format_plan_prompt() helper."""

    def test_format_plan_prompt_contains_structure(self):
        """Test that format_plan_prompt returns expected structure."""
        prompt = format_plan_prompt()

        assert "PLAN:" in prompt
        assert "STEPS:" in prompt
        assert "[Step" in prompt
        assert "Done" in prompt or "build" in prompt.lower()

    def test_format_plan_prompt_is_string(self):
        """Test that format_plan_prompt returns a string."""
        prompt = format_plan_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 50  # Should be a substantial prompt
