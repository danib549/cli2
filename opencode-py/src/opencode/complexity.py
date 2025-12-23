"""Task complexity analysis."""

import re
from dataclasses import dataclass


@dataclass
class ComplexityResult:
    """Result of complexity analysis."""
    score: float
    should_plan: bool
    signals: list[str]


class ComplexityAnalyzer:
    """Analyze task complexity to decide on auto-planning."""

    # Complexity signals with weights
    # Higher weight = stronger signal of complexity
    SIGNALS = {
        # High complexity - restructuring
        r"\brefactor\b": 0.35,
        r"\brestructure\b": 0.35,
        r"\bmigrate\b": 0.35,
        r"\brewrite\b": 0.30,
        r"\barchitect\b": 0.30,
        r"\bredesign\b": 0.30,

        # High complexity - scope indicators
        r"\ball\s+files?\b": 0.30,
        r"\bentire\b": 0.25,
        r"\bevery\s+\w+": 0.25,
        r"\bacross\s+the\b": 0.25,
        r"\bthroughout\b": 0.20,
        r"\bwhole\s+\w+": 0.20,

        # Medium complexity - multi-step indicators
        r"\bfirst\b.*\bthen\b": 0.25,
        r"\bstep\s+\d+": 0.20,
        r"\band\s+then\b": 0.15,
        r"\bafter\s+that\b": 0.15,
        r"\bfinally\b": 0.15,

        # Medium complexity - creation/building
        r"\bcreate\s+a\s+new\b": 0.20,
        r"\bbuild\s+a\b": 0.20,
        r"\bimplement\s+a\b": 0.20,
        r"\bset\s*up\b": 0.15,
        r"\binitialize\b": 0.15,

        # Medium complexity - ambiguous scope
        r"\bfix\s+(?:the\s+)?bugs?\b": 0.20,
        r"\bimprove\b": 0.15,
        r"\boptimize\b": 0.20,
        r"\benhance\b": 0.15,
        r"\bupdate\s+(?:the\s+)?\w+s\b": 0.15,  # "update controllers" (plural)

        # Low complexity - but adds up
        r"\bmultiple\b": 0.15,
        r"\bseveral\b": 0.15,
        r"\bvarious\b": 0.10,
        r"\bintegrate\b": 0.15,
        r"\bconnect\b": 0.10,

        # Feature indicators
        r"\bfeature\b": 0.15,
        r"\bmodule\b": 0.10,
        r"\bsystem\b": 0.15,
        r"\bcomponent\b": 0.10,
        r"\bservice\b": 0.10,
    }

    def __init__(self, threshold: float = 0.6):
        """Initialize analyzer.

        Args:
            threshold: Score threshold for auto-planning (0.0-1.0).
        """
        self.threshold = threshold
        self._compiled_patterns = {
            re.compile(pattern, re.IGNORECASE): weight
            for pattern, weight in self.SIGNALS.items()
        }

    def analyze(self, text: str) -> ComplexityResult:
        """Analyze text for complexity signals.

        Args:
            text: The user's task description.

        Returns:
            ComplexityResult with score, decision, and matched signals.
        """
        score = 0.0
        matched_signals = []

        for pattern, weight in self._compiled_patterns.items():
            if pattern.search(text):
                score += weight
                # Extract the signal name from pattern
                signal_name = pattern.pattern.replace(r"\b", "").replace("\\s+", " ")
                matched_signals.append(signal_name)

        # Cap at 1.0
        score = min(1.0, score)

        return ComplexityResult(
            score=score,
            should_plan=score >= self.threshold,
            signals=matched_signals
        )

    def set_threshold(self, value: float) -> None:
        """Set the complexity threshold.

        Args:
            value: New threshold (0.0-1.0).
        """
        self.threshold = max(0.0, min(1.0, value))

    def should_auto_plan(self, text: str) -> bool:
        """Quick check if text should trigger auto-planning.

        Args:
            text: The user's task description.

        Returns:
            True if complexity exceeds threshold.
        """
        return self.analyze(text).should_plan

    def explain(self, text: str) -> str:
        """Get a human-readable explanation of complexity analysis.

        Args:
            text: The user's task description.

        Returns:
            Formatted explanation string.
        """
        result = self.analyze(text)

        lines = [
            f"Complexity Score: {result.score:.2f} (threshold: {self.threshold:.2f})",
            f"Auto-Plan: {'Yes' if result.should_plan else 'No'}",
        ]

        if result.signals:
            lines.append("Signals detected:")
            for signal in result.signals[:5]:  # Limit to top 5
                lines.append(f"  - {signal}")

        return "\n".join(lines)
