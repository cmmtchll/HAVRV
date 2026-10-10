"""Tests for the quality-scale checklist auditor."""

from pathlib import Path

from scripts.quality_scale_audit import (
    _ALL_RULES,
    _render_report,
    _validate_rules,
)


def test_audit_requires_every_official_rule() -> None:
    """Report omitted criteria instead of silently skipping them."""
    errors = _validate_rules({}, Path.cwd())

    assert len(errors) == 1
    assert "Missing official rules" in errors[0]
    assert len(_ALL_RULES) == 54


def test_audit_requires_evidence_for_done_rules(tmp_path: Path) -> None:
    """Reject a done status without a verifiable repository artifact."""
    errors = _validate_rules(
        {
            rule: {"status": "done", "comment": "No evidence supplied."}
            for rule in _ALL_RULES
        },
        tmp_path,
    )

    assert len(errors) == len(_ALL_RULES)
    assert all("no file evidence" in error for error in errors)


def test_report_shows_unmet_and_exempt_criteria() -> None:
    """Distinguish incomplete criteria from justified non-applicable rules."""
    rules = {
        rule: {
            "status": "todo" if rule == "parallel-updates" else "exempt",
            "comment": "Not applicable to this integration.",
        }
        for rule in _ALL_RULES
    }

    report = _render_report(rules)

    assert "| Bronze | 20 / 20 | READY (checklist only) |" in report
    assert "| Silver | 9 / 10 | NOT MET |" in report
    assert "**TODO** `parallel-updates`" in report
    assert "**EXEMPT** `appropriate-polling`" in report
