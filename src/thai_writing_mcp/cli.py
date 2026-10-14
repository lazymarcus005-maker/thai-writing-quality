"""thai-writing-check — exit-code quality gate for hosts, hooks and CI.

Gate C measured that hosts do not reliably call attached MCP tools
(skill+MCP stayed at the bare-model detection rate). An enforced hook on
the host side is the reliable path: this CLI wraps the same deterministic
engine as the MCP tools and speaks exit codes.

    thai-writing-check FILE [FILE...]     # 0=PASS 1=WARN 2=FAIL 3=error
    thai-writing-check --stdin < file
    thai-writing-check --hook             # host PreToolUse gate (see hooks/)

Files without Thai characters pass trivially (skip, exit 0) unless
``--force`` is given — hooks stay fast and quiet on pure-code edits.
``TWQ_GLOSSARY_FILE`` seeds a persistent project glossary. FAIL requires
deterministic evidence (bidi controls, confusables), so it is safe to
block on; WARN is reported but never blocks.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

EXIT_PASS, EXIT_WARN, EXIT_FAIL, EXIT_ERROR = 0, 1, 2, 3

_RE_THAI = re.compile(r"[\u0e00-\u0e7f]")

#: Tool inputs that carry the text a host is about to write.
_HOOKED_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def has_thai(text: str) -> bool:
    return bool(_RE_THAI.search(text))


def _build_engine():
    from thai_writing_mcp.config.glossary import config_from_env, default_config
    from thai_writing_mcp.core.pipeline import WritingEngine

    return WritingEngine(config_from_env() or default_config())


def _validate(text: str, profile: str) -> dict:
    return _build_engine().validate(text, profile=profile)


def _summarize(path: str, result: dict) -> str:
    by_cat = " ".join(f"{k}={v}" for k, v in sorted(result["summary"]["by_category"].items()))
    detail = f"; {by_cat}" if by_cat else ""
    return f"{path}: {result['status']} ({result['summary']['count']} issue(s){detail})"


def _status_to_exit(status: str) -> int:
    return {"PASS": EXIT_PASS, "WARN": EXIT_WARN, "FAIL": EXIT_FAIL}[status]


def run_files(files: list[str], *, profile: str, as_json: bool, force: bool) -> int:
    import pathlib

    exit_code = EXIT_PASS
    results: dict[str, dict] = {}
    for name in files:
        path = pathlib.Path(name)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot read {name}: {exc}", file=sys.stderr)
            return EXIT_ERROR
        if not text.strip() or (not has_thai(text) and not force):
            if as_json:
                results[name] = {"status": "PASS", "skipped": "no Thai content"}
            else:
                print(f"{name}: PASS (no Thai content; skipped)")
            continue
        try:
            result = _validate(text, profile=profile)
        except Exception as exc:  # engine errors surface as exit 3, never a traceback
            print(f"error: {name}: engine failure: {exc}", file=sys.stderr)
            return EXIT_ERROR
        results[name] = result
        if not as_json:
            print(_summarize(name, result))
        for issue in result["issues"]:
            preview = issue.get("preview", issue["original"])
            if issue["severity"] == "high":
                print(f"  [{issue['severity']}] {issue['rule_id']}: {preview}")
        exit_code = max(exit_code, _status_to_exit(result["status"]))
    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return exit_code


def run_hook(*, profile: str) -> int:
    """Host PreToolUse gate: read the hook payload from stdin.

    Emits ``{"decision": "block", "reason": ...}`` (Claude Code hook output
    format) only for FAIL verdicts; everything else allows the edit. Engine
    errors fail open with a stderr warning — a broken checker must not
    brick the host's editing, and FAIL (the blocking verdict) always needs
    deterministic evidence, so fail-open never bypasses a real gate.
    """

    try:
        payload = json.loads(sys.stdin.read())
    except ValueError:
        return EXIT_PASS  # not a hook payload we understand: allow
    if payload.get("tool_name") not in _HOOKED_TOOLS:
        return EXIT_PASS
    tool_input = payload.get("tool_input") or {}
    text = tool_input.get("content") or tool_input.get("new_string") or ""
    if not text or not has_thai(text):
        return EXIT_PASS
    try:
        result = _validate(text, profile=profile)
    except Exception as exc:
        print(f"thai-writing-check: engine unavailable, edit allowed: {exc}", file=sys.stderr)
        return EXIT_PASS
    if result["status"] != "FAIL":
        return EXIT_PASS
    findings = "\n".join(
        f"- {i['rule_id']}: {i.get('preview', i['original'])} — {i['message']}"
        for i in result["issues"]
        if i["severity"] == "high"
    )
    print(
        json.dumps(
            {
                "decision": "block",
                "reason": (
                    "thai-writing-quality FAIL (deterministic Unicode evidence — "
                    "likely bidi controls or confusable look-alikes):\n"
                    f"{findings}\n"
                    "Fix these characters, then retry the edit. "
                    "Run `thai-writing-check <file>` for details."
                ),
            },
            ensure_ascii=False,
        )
    )
    return EXIT_PASS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="thai-writing-check",
        description="Thai writing quality gate (exit 0=PASS 1=WARN 2=FAIL 3=error)",
    )
    parser.add_argument("files", nargs="*", help="files to check (UTF-8)")
    parser.add_argument("--stdin", action="store_true", help="read text from stdin")
    parser.add_argument(
        "--hook", action="store_true", help="host PreToolUse gate mode (JSON on stdin)"
    )
    parser.add_argument(
        "--profile", default="technical", choices=["general", "formal", "technical"]
    )
    parser.add_argument("--json", dest="as_json", action="store_true", help="JSON output")
    parser.add_argument("--force", action="store_true", help="check files without Thai too")
    args = parser.parse_args(argv)

    if args.hook:
        return run_hook(profile=args.profile)
    if args.stdin:
        text = sys.stdin.read()
        if not text:
            print("error: stdin is empty", file=sys.stderr)
            return EXIT_ERROR
        import pathlib
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as tmp:
            tmp.write(text)
        try:
            return run_files([tmp.name], profile=args.profile, as_json=args.as_json, force=True)
        finally:
            pathlib.Path(tmp.name).unlink(missing_ok=True)
    if not args.files:
        parser.error("no input: pass FILE..., --stdin, or --hook")
    return run_files(args.files, profile=args.profile, as_json=args.as_json, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
