#!/usr/bin/env python3
"""
doc_check.py — Deterministic documentation drift checker.

Checks whether project documentation reflects the current state of the codebase.
Designed to run in CI (GitHub Actions) or as a pre-commit hook.

Exit codes:
  0 — All docs pass (or only warnings)
  1 — One or more docs have staleness issues (failures)
  2 — Script error (missing files, parse failures)

Usage:
    python scripts/doc_check.py                  # Full check
    python scripts/doc_check.py --diff-only      # Only check files changed in working tree
    python scripts/doc_check.py --staged-only    # Only check staged files
    python scripts/doc_check.py --since-commit HEAD~5  # Files changed since commit
    python scripts/doc_check.py --format json    # Machine-readable output
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    FAIL = "fail"


@dataclass
class Finding:
    doc: str
    check: str
    severity: Severity
    message: str
    suggestion: str = ""
    line_number: int | None = None

    def __str__(self) -> str:
        prefix = {
            Severity.INFO: "i",
            Severity.WARNING: "⚠",
            Severity.FAIL: "✗",
        }[self.severity]
        loc = f" (line {self.line_number})" if self.line_number else ""
        result = f"  {prefix} [{self.severity.value.upper()}] {self.doc}{loc}: {self.message}"
        if self.suggestion:
            result += f"\n    → {self.suggestion}"
        return result


@dataclass
class CheckResult:
    doc: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.FAIL]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.WARNING]

    @property
    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.INFO]

    def __str__(self) -> str:
        if not self.findings:
            return f"  ✓ {self.doc} — OK"
        lines = [f"  {self.doc} — {len(self.failures)} failures, {len(self.warnings)} warnings"]
        for f in self.findings:
            lines.append(str(f))
        return "\n".join(lines)


# ─── Helpers ──────────────────────────────────────────────────────────


def read_file(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def get_changed_files(
    since_commit: str | None = None, staged: bool = False, diff_only: bool = False
) -> set[str]:
    """Get set of changed file paths from git."""
    if staged:
        cmd = ["git", "diff", "--cached", "--name-only"]
    elif diff_only:
        cmd = ["git", "diff", "--name-only"]
    elif since_commit:
        cmd = ["git", "diff", "--name-only", since_commit]
    else:
        return set()  # No filter — check everything

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return set()


def file_exists(path: str) -> bool:
    return os.path.isfile(path)


def dir_exists(path: str) -> bool:
    return os.path.isdir(path)


def glob_exists(pattern: str) -> bool:
    """Check if any file matching a glob pattern exists."""
    from glob import glob

    return len(glob(pattern)) > 0


def find_files_recursive(directory: str, extension: str = ".py") -> set[str]:
    """Find all files with given extension recursively."""
    result = set()
    for root, _, files in os.walk(directory):
        for f in files:
            if f.endswith(extension):
                result.add(os.path.join(root, f))
    return result


def grep_in_files(pattern: str, files: set[str]) -> list[tuple[str, int, str]]:
    """Search for regex pattern in files. Returns (file, line_num, line) matches."""
    results = []
    compiled = re.compile(pattern)
    for filepath in files:
        try:
            with open(filepath, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if compiled.search(line):
                        results.append((filepath, i, line.strip()))
        except (FileNotFoundError, UnicodeDecodeError):
            continue
    return results


# ─── Check: Architecture (agents.md) ──────────────────────────────────


def check_architecture(project_root: str, changed_files: set[str]) -> CheckResult:
    """Check agents.md Project Structure against actual file tree."""
    result = CheckResult(doc="agents.md")
    agents_path = os.path.join(project_root, "agents.md")
    content = read_file(agents_path)
    if content is None:
        result.findings.append(
            Finding(
                doc="agents.md",
                check="existence",
                severity=Severity.WARNING,
                message="agents.md not found — skipping architecture check",
            )
        )
        return result

    # Extract the project structure tree (between ``` markers after "## 2. Project Structure")
    structure_match = re.search(r"## 2\. Project Structure\s*```\s*\n(.*?)```", content, re.DOTALL)
    if not structure_match:
        result.findings.append(
            Finding(
                doc="agents.md",
                check="structure_section",
                severity=Severity.WARNING,
                message="Could not find Project Structure code block in agents.md",
            )
        )
        return result

    tree_text = structure_match.group(1)

    # Extract file paths from the tree (lines that look like file entries)
    # Extract file paths from the tree (lines that look like file entries)
    tree_files: dict[str, str] = {}  # filename -> full path
    # Track directory context with a stack keyed by indentation depth.
    # Each entry: (depth, dir_name). When indentation decreases, pop deeper levels.
    dir_stack: list[tuple[int, str]] = [(0, "")]  # (depth, dir_name)

    for line in tree_text.splitlines():
        if not line.strip():
            continue

        # Count box-drawing chars before the name to determine nesting depth.
        raw = line.replace(" ", "")
        depth = 0
        for ch in raw:
            if ch in ("│", "├", "└", "─"):
                depth += 1
            else:
                break

        # Pop deeper levels when indentation decreases
        while len(dir_stack) > 1 and dir_stack[-1][0] >= depth:
            dir_stack.pop()

        # Track directory entries (lines ending with /)
        dir_match = re.search(r"[│├└─]\s*([\w_]+)/", line)
        if dir_match and "." not in dir_match.group(1):
            current_dir = dir_match.group(1)
            dir_stack.append((depth, current_dir))

        # Match file entries like "│   ├── models.py                 # Unit dataclass"
        m = re.search(r"[\│├└─]\s+([\w_]+\.[\w]+)", line)
        if m:
            fname = m.group(1)
            # Build path from the directory stack (skip root "" entry)
            parent = "/".join(d[1] for d in dir_stack if d[1])
            if parent:
                tree_files[fname] = parent + "/" + fname
            else:
                tree_files[fname] = fname

    if not tree_files:
        result.findings.append(
            Finding(
                doc="agents.md",
                check="structure_parse",
                severity=Severity.WARNING,
                message="Could not parse any file paths from Project Structure tree",
            )
        )
        return result

    # Check: files in tree that don't exist
    for _fname, fpath in sorted(tree_files.items()):
        full_path = os.path.join(project_root, fpath)
        if not file_exists(full_path):
            result.findings.append(
                Finding(
                    doc="agents.md",
                    check="stale_reference",
                    severity=Severity.FAIL,
                    message=f"File '{fpath}' listed in Project Structure but does not exist",
                    suggestion=f"Remove '{fpath}' from the tree, or restore the file",
                )
            )

    # Check: Python files in src dirs that aren't in the tree
    # Build reverse lookup: full path -> filename
    tree_by_fullpath = {v: k for k, v in tree_files.items()}
    src_dirs = ["gui", "data", "automation", "sync"]
    for src_dir in src_dirs:
        dir_path = os.path.join(project_root, src_dir)
        if not dir_exists(dir_path):
            continue
        for fname in sorted(os.listdir(dir_path)):
            if fname.endswith(".py") and fname != "__init__.py" and not fname.startswith("_"):
                full_path = f"{src_dir}/{fname}"
                if full_path not in tree_by_fullpath:
                    result.findings.append(
                        Finding(
                            doc="agents.md",
                            check="missing_file",
                            severity=Severity.WARNING,
                            message=f"File '{full_path}' exists but is not listed in Project Structure",
                            suggestion=f"Add '{full_path}' to the Project Structure tree",
                        )
                    )

    return result


# ─── Check: Bug Tracking (CODE_REVIEW.md) ─────────────────────────────


def check_bug_tracking(project_root: str, changed_files: set[str]) -> CheckResult:
    """Check CODE_REVIEW.md bug statuses against code."""
    result = CheckResult(doc="CODE_REVIEW.md")
    review_path = os.path.join(project_root, "CODE_REVIEW.md")
    content = read_file(review_path)
    if content is None:
        result.findings.append(
            Finding(
                doc="CODE_REVIEW.md",
                check="existence",
                severity=Severity.INFO,
                message="CODE_REVIEW.md not found — skipping bug tracking check",
            )
        )
        return result

    # Extract all bug entries: ### BUG-N: ... **Status**: **STATUS**
    bug_pattern = re.compile(
        r"### (BUG-\d+):\s*(.*?)\s*\n.*?\*\*Status\*\*:\s*\*?\*?([^*]+?)\*?\*?(?:\n|$)", re.DOTALL
    )

    all_py_files = find_files_recursive(project_root, ".py")
    # Exclude venv, __pycache__, .codegraph
    all_py_files = {
        f
        for f in all_py_files
        if "/venv/" not in f and "__pycache__" not in f and "/.codegraph/" not in f
    }

    for match in bug_pattern.finditer(content):
        bug_id = match.group(1)
        match.group(2).strip()
        status = match.group(3).strip()
        line_num = content[: match.start()].count("\n") + 1

        # Check: OPEN bugs — verify referenced files still exist
        if status == "OPEN":
            # Extract file references from the "File: `path`" line only
            file_refs_raw = re.findall(r"\*\*File\*\*:\s*`([^`]+\.py)`", match.group(0))
            seen = set()
            file_refs = []
            for ref in file_refs_raw:
                if ref not in seen:
                    seen.add(ref)
                    file_refs.append(ref)
            if file_refs:
                for ref in file_refs:
                    full_ref = os.path.join(project_root, ref)
                    if not file_exists(full_ref):
                        result.findings.append(
                            Finding(
                                doc="CODE_REVIEW.md",
                                check="bug_stale_ref",
                                severity=Severity.WARNING,
                                message=f"{bug_id} references '{ref}' which no longer exists",
                                line_number=line_num,
                                suggestion=f"Update {bug_id} file reference or mark as NOT REPRODUCABLE",
                            )
                        )

        # Check: FIXED bugs — verify the fix comment exists in code
        if "FIXED" in status:
            # Look for # BUG-XX or # BUG-XX: fixed comments
            fix_comments = grep_in_files(rf"# {bug_id}", all_py_files)
            if not fix_comments:
                # Not all fixed bugs have comments — this is informational
                result.findings.append(
                    Finding(
                        doc="CODE_REVIEW.md",
                        check="bug_fix_comment",
                        severity=Severity.INFO,
                        message=f"{bug_id} is marked FIXED but no '# {bug_id}' comment found in code",
                        line_number=line_num,
                        suggestion=f"Add '# {bug_id}: <brief fix description>' comment near the fix",
                    )
                )

        # Check: PARTIALLY FIXED — flag for review
        if "PARTIALLY" in status:
            result.findings.append(
                Finding(
                    doc="CODE_REVIEW.md",
                    check="bug_partial",
                    severity=Severity.WARNING,
                    message=f"{bug_id} is PARTIALLY FIXED — needs follow-up",
                    line_number=line_num,
                    suggestion=f"Review {bug_id} and either complete the fix or split into sub-bugs",
                )
            )

    return result


# ─── Check: Feature Plans (plans/*.md) ────────────────────────────────


def check_feature_plans(project_root: str, changed_files: set[str]) -> CheckResult:
    """Check plan statuses against codebase state."""
    result = CheckResult(doc="plans/*.md")
    plans_dir = os.path.join(project_root, "plans")
    if not dir_exists(plans_dir):
        result.findings.append(
            Finding(
                doc="plans/*.md",
                check="existence",
                severity=Severity.INFO,
                message="plans/ directory not found — skipping feature plan check",
            )
        )
        return result

    all_py_files = find_files_recursive(project_root, ".py")
    all_py_files = {
        f
        for f in all_py_files
        if "/venv/" not in f and "__pycache__" not in f and "/.codegraph/" not in f
    }

    for fname in sorted(os.listdir(plans_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(plans_dir, fname)
        content = read_file(fpath)
        if content is None:
            continue

        # Extract status
        status_match = re.search(r"\*\*Status\*\*:\s*(\S+)", content)
        if not status_match:
            continue
        status = status_match.group(1).strip()

        # Extract plan ID from filename (FEAT-N or IMP-N)
        id_match = re.search(r"(FEAT-\d+|IMP-\d+|MOC-[A-Z])", fname)
        plan_id = id_match.group(1) if id_match else fname

        # Check: NOT STARTED but code exists
        if status == "NOT_STARTED":
            # Look for files mentioned in the plan
            file_refs = re.findall(r"`([^`]+\.py)`", content)
            existing_refs = [
                ref for ref in file_refs if file_exists(os.path.join(project_root, ref))
            ]
            if existing_refs:
                result.findings.append(
                    Finding(
                        doc=fname,
                        check="plan_status",
                        severity=Severity.WARNING,
                        message=f"{plan_id} is NOT STARTED but {len(existing_refs)} referenced file(s) exist: {', '.join(existing_refs[:3])}",
                        suggestion="Update status to IN_PROGRESS or verify these files are unrelated",
                    )
                )

            # Also check for # FEAT-XX or # IMP-XX comments in code
            code_comments = grep_in_files(rf"# {plan_id}", all_py_files)
            if code_comments:
                result.findings.append(
                    Finding(
                        doc=fname,
                        check="plan_code_mismatch",
                        severity=Severity.WARNING,
                        message=f"{plan_id} is NOT STARTED but {len(code_comments)} code comment(s) reference it",
                        suggestion="Update status to IN_PROGRESS",
                    )
                )

        # Check: IN_PROGRESS or DONE but code is incomplete
        if status in ("IN_PROGRESS", "DONE"):
            file_refs = re.findall(r"`([^`]+\.py)`", content)
            missing_refs = [
                ref for ref in file_refs if not file_exists(os.path.join(project_root, ref))
            ]
            if missing_refs and status == "DONE":
                result.findings.append(
                    Finding(
                        doc=fname,
                        check="plan_incomplete",
                        severity=Severity.FAIL,
                        message=f"{plan_id} is DONE but {len(missing_refs)} referenced file(s) don't exist: {', '.join(missing_refs[:3])}",
                        suggestion="Verify these files were removed intentionally, or update the plan",
                    )
                )

        # Check: PROPOSED plans (MOC-*) — informational
        if status == "PROPOSED":
            result.findings.append(
                Finding(
                    doc=fname,
                    check="plan_proposed",
                    severity=Severity.INFO,
                    message=f"{plan_id} is PROPOSED — not yet scheduled",
                )
            )

    return result


# ─── Check: Onboarding (ONBOARDING_STEPS.md) ──────────────────────────


def check_onboarding(project_root: str, changed_files: set[str]) -> CheckResult:
    """Check ONBOARDING_STEPS.md widget references against UI code."""
    result = CheckResult(doc="ONBOARDING_STEPS.md")
    onboarding_path = os.path.join(project_root, "docs", "ONBOARDING_STEPS.md")
    content = read_file(onboarding_path)
    if content is None:
        # Try alternate location
        onboarding_path = os.path.join(project_root, "ONBOARDING_STEPS.md")
        content = read_file(onboarding_path)
    if content is None:
        result.findings.append(
            Finding(
                doc="ONBOARDING_STEPS.md",
                check="existence",
                severity=Severity.INFO,
                message="ONBOARDING_STEPS.md not found — skipping onboarding check",
            )
        )
        return result

    # Extract widget targets from the steps table (column 2)
    # Lines like: "| 1 | `calendar_panel` | Calendar & List & Alerts | ..."
    widget_names = set()
    for line in content.splitlines():
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.split("|")]
        if len(cols) >= 3:
            # Column 2 (index 2) is the widget target
            target = cols[2] if cols[2] and cols[2] != "Widget target" else None
            if target:
                # Extract backtick-wrapped names
                names = re.findall(r"`(\w+)`", target)
                widget_names.update(names)

    if not widget_names:
        result.findings.append(
            Finding(
                doc="ONBOARDING_STEPS.md",
                check="parse",
                severity=Severity.WARNING,
                message="Could not extract widget names from ONBOARDING_STEPS.md table",
            )
        )
        return result

    # Also extract from the objectName reference table at the bottom
    obj_table_match = re.search(r"\| objectName.*?\n\|[-|]*\n(.*?)(?:\n\n|\Z)", content, re.DOTALL)
    if obj_table_match:
        for line in obj_table_match.group(1).splitlines():
            if line.startswith("|"):
                cols = [c.strip() for c in line.split("|")]
                if len(cols) >= 2:
                    name = cols[1].strip("`")
                    if name and name != "Widget":
                        widget_names.add(name)

    # Check each widget name against UI code
    gui_dir = os.path.join(project_root, "gui")
    if not dir_exists(gui_dir):
        return result

    gui_files = find_files_recursive(gui_dir, ".py")

    for widget_name in sorted(widget_names):
        # Search for setObjectName("widget_name") or objectName() == "widget_name"
        pattern = rf'setObjectName\(["\']{re.escape(widget_name)}["\']\)'
        matches = grep_in_files(pattern, gui_files)
        if not matches:
            # Also check for self.setObjectName in class definitions
            pattern2 = rf"self\.{widget_name}\b.*=.*Q\w+\("
            matches2 = grep_in_files(pattern2, gui_files)
            if not matches2:
                result.findings.append(
                    Finding(
                        doc="ONBOARDING_STEPS.md",
                        check="widget_not_found",
                        severity=Severity.FAIL,
                        message=f"Widget '{widget_name}' referenced in onboarding but not found in gui/*.py",
                        suggestion=f"Remove '{widget_name}' from onboarding or verify the widget exists",
                    )
                )

    return result


# ─── Check: Computation Audit ─────────────────────────────────────────


def check_computation_audit(project_root: str, changed_files: set[str]) -> CheckResult:
    """Check COMPUTATION_AUDIT.md constants and references against code."""
    result = CheckResult(doc="COMPUTATION_AUDIT.md")
    audit_path = os.path.join(project_root, "docs", "COMPUTATION_AUDIT.md")
    content = read_file(audit_path)
    if content is None:
        result.findings.append(
            Finding(
                doc="COMPUTATION_AUDIT.md",
                check="existence",
                severity=Severity.INFO,
                message="COMPUTATION_AUDIT.md not found — skipping computation audit check",
            )
        )
        return result

    # Extract constants from the Constants Reference table
    # Pattern: | `CONSTANT_NAME` | value | file | description |
    constants_pattern = re.compile(r"\|\s*`(\w+)`\s*\|\s*([\d.]+)\s*\|\s*([\w./]+)\s*\|")

    all_py_files = find_files_recursive(project_root, ".py")
    all_py_files = {
        f
        for f in all_py_files
        if "/venv/" not in f and "__pycache__" not in f and "/.codegraph/" not in f
    }

    for match in constants_pattern.finditer(content):
        const_name = match.group(1)
        doc_value = match.group(2)
        doc_file = match.group(3)
        line_num = content[: match.start()].count("\n") + 1

        # Check: does the referenced file exist?
        full_file = os.path.join(project_root, doc_file)
        if not file_exists(full_file):
            result.findings.append(
                Finding(
                    doc="COMPUTATION_AUDIT.md",
                    check="stale_file_ref",
                    severity=Severity.FAIL,
                    message=f"Constant '{const_name}' references '{doc_file}' which doesn't exist",
                    line_number=line_num,
                    suggestion=f"Update file reference for '{const_name}'",
                )
            )
            continue

        # Check: does the constant value match the code?
        # Search for CONST_NAME = value or CONST_NAME: type = value
        value_pattern = rf"{re.escape(const_name)}\s*[:=]\s*(\S+)"
        code_matches = grep_in_files(value_pattern, {full_file})
        if code_matches:
            code_value = re.search(rf"{re.escape(const_name)}\s*[:=]\s*(\S+)", code_matches[0][2])
            if code_value:
                raw_val = code_value.group(1).rstrip(")").rstrip(",")
                # Normalize: 160.0 == 160, 10.0 == 10
                try:
                    doc_f = float(doc_value)
                    code_f = float(raw_val)
                    if abs(doc_f - code_f) > 0.001:
                        result.findings.append(
                            Finding(
                                doc="COMPUTATION_AUDIT.md",
                                check="stale_constant",
                                severity=Severity.FAIL,
                                message=f"Constant '{const_name}' is {doc_f} in audit but {code_f} in {doc_file}",
                                line_number=line_num,
                                suggestion=f"Update audit: | \\`{const_name}\\` | {code_f} | {doc_file} |",
                            )
                        )
                except ValueError:
                    # String comparison
                    if raw_val.strip("'\"") != doc_value.strip("'\""):
                        result.findings.append(
                            Finding(
                                doc="COMPUTATION_AUDIT.md",
                                check="stale_constant",
                                severity=Severity.WARNING,
                                message=f"Constant '{const_name}' value mismatch: audit='{doc_value}' code='{raw_val}'",
                                line_number=line_num,
                            )
                        )

    return result


# ─── Main ─────────────────────────────────────────────────────────────


def run_checks(project_root: str, changed_files: set[str], checks: list[str]) -> list[CheckResult]:
    """Run all requested checks and return results."""
    check_map = {
        "architecture": check_architecture,
        "bugs": check_bug_tracking,
        "plans": check_feature_plans,
        "onboarding": check_onboarding,
        "computation": check_computation_audit,
    }

    results = []
    for check_name in checks:
        if check_name in check_map:
            results.append(check_map[check_name](project_root, changed_files))
    return results


def format_report(results: list[CheckResult], fmt: str = "text") -> str:
    """Format results as text or JSON."""
    if fmt == "json":
        data = []
        for r in results:
            data.append(
                {
                    "doc": r.doc,
                    "failures": len(r.failures),
                    "warnings": len(r.warnings),
                    "findings": [
                        {
                            "check": f.check,
                            "severity": f.severity.value,
                            "message": f.message,
                            "suggestion": f.suggestion,
                            "line": f.line_number,
                        }
                        for f in r.findings
                    ],
                }
            )
        return json.dumps(data, indent=2)

    # Text format
    lines = ["# Doc Sync Report\n"]
    total_failures = sum(len(r.failures) for r in results)
    total_warnings = sum(len(r.warnings) for r in results)

    if total_failures == 0 and total_warnings == 0:
        lines.append("✓ All documentation checks passed.\n")
    else:
        docs_with_issues = sum(1 for r in results if r.findings)
        lines.append(
            f"{'✗' if total_failures > 0 else '⚠'} {docs_with_issues} doc(s) need attention: "
            f"{total_failures} failures, {total_warnings} warnings\n"
        )

    for r in results:
        lines.append(str(r))
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Check documentation freshness against codebase")
    parser.add_argument(
        "--diff-only",
        action="store_true",
        help="Only check docs related to files changed in working tree",
    )
    parser.add_argument(
        "--staged-only", action="store_true", help="Only check docs related to staged files"
    )
    parser.add_argument(
        "--since-commit",
        type=str,
        default=None,
        help="Only check docs related to files changed since this commit",
    )
    parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format (default: text)"
    )
    parser.add_argument(
        "--checks",
        nargs="+",
        choices=["architecture", "bugs", "plans", "onboarding", "computation", "all"],
        default=["all"],
        help="Which checks to run",
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=".",
        help="Project root directory (default: current directory)",
    )
    args = parser.parse_args()

    project_root = os.path.abspath(args.project_root)

    # Get changed files for filtering
    changed_files = set()
    if args.staged_only:
        changed_files = get_changed_files(staged=True)
    elif args.diff_only:
        changed_files = get_changed_files()
    elif args.since_commit:
        changed_files = get_changed_files(since_commit=args.since_commit)

    # Determine which checks to run
    checks = (
        ["architecture", "bugs", "plans", "onboarding", "computation"]
        if "all" in args.checks
        else args.checks
    )

    # Run checks
    results = run_checks(project_root, changed_files, checks)

    # Output
    report = format_report(results, args.format)
    print(report)

    # Exit code
    total_failures = sum(len(r.failures) for r in results)
    if total_failures > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
