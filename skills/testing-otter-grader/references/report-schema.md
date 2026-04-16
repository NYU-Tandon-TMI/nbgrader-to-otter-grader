# Error Report Schema

The report is the interface between the Testing Agent and the Refactoring Agent.
`generate_report.py` produces this format. Every error includes enough detail
for the Refactoring Agent to locate and fix the issue programmatically.

## Top-Level Structure

```json
{
  "notebook": "homework-0-instructor.ipynb",
  "pipeline_status": "pass | fail",
  "stages": { ... },
  "summary": { ... }
}
```

## Stages

### otter_assign (Stage 1)

```json
{
  "status": "pass | fail | skipped",
  "duration_seconds": 12.3,
  "warnings": [],
  "error_patterns": ["otter_assign_syntax"],
  "stderr_snippet": "first 500 chars of stderr"
}
```

### output_structure (Stage 2)

```json
{
  "status": "pass | fail | skipped",
  "checks_passed": 5,
  "checks_total": 7,
  "failed_checks": [
    {"name": "autograder_zip", "status": "fail", "message": "..."}
  ]
}
```

### student_notebook (Stage 3)

```json
{
  "status": "pass | fail | skipped",
  "issues": [
    {
      "severity": "error | warning",
      "question": "q5",
      "cell_index": 32,
      "issue_type": "leaked_solution",
      "message": "Human-readable description",
      "cell_content_snippet": "first 200 chars of problematic cell",
      "fix_action": "Specific instruction for Refactoring Agent"
    }
  ]
}
```

### autograder_tests (Stage 4)

```json
{
  "status": "pass | fail | skipped",
  "total_score": 5.0,
  "total_possible": 6.0,
  "per_question": {
    "q1": {"score": 1.0, "possible": 1.0, "status": "pass"},
    "q5": {
      "score": 0.0,
      "possible": 1.0,
      "status": "fail",
      "error_type": "AssertionError",
      "traceback": "full traceback text"
    }
  }
}
```

## Summary

```json
{
  "total_errors": 2,
  "total_warnings": 0,
  "failing_questions": ["q5"],
  "fix_actions": [
    "q5: Refactoring Agent: add # SOLUTION marker to solution line in instructor notebook",
    "q5: Refactoring Agent: fix solution or test code for the failing question"
  ]
}
```

## Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `severity` | `"error" \| "warning"` | Errors block grading; warnings are suspicious but functional |
| `issue_type` | string | Machine-parseable category (see [error-patterns.md](error-patterns.md)) |
| `cell_index` | integer | Cell in the relevant notebook; -1 if not cell-specific |
| `fix_action` | string | Actionable instruction for the Refactoring Agent |
| `cell_content_snippet` | string | First 200 chars of the problematic cell |
| `question` | string \| null | Question name (e.g., "q5") if applicable |
