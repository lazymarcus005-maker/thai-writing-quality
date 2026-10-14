"""thai-writing-check CLI: the host-side gate (hooks/README.md contract).

Exit codes: 0=PASS/skip, 1=WARN, 2=FAIL, 3=error. Hook mode blocks only
on FAIL (deterministic evidence) and allows everything else.
"""

from __future__ import annotations

import io
import json
import sys

from thai_writing_mcp import cli

BIDI_TEXT = "สวัสดี \u202e ครับ"  # bidi control: deterministic FAIL
WARN_TEXT = "ขออนุญาติ deploy API ไป production"  # spelling: WARN
CLEAN_TEXT = "ประมวลผลคำขอเรียบร้อยแล้ว"


def _hook(payload: dict, capsys) -> tuple[int, str]:
    stdin = io.StringIO(json.dumps(payload))
    old, sys.stdin = sys.stdin, stdin
    try:
        code = cli.run_hook(profile="general")
    finally:
        sys.stdin = old
    out = capsys.readouterr().out
    return code, out


class TestFileMode:
    def test_fail_exit_2(self, tmp_path, capsys) -> None:
        f = tmp_path / "a.md"
        f.write_text(BIDI_TEXT, encoding="utf-8")
        assert cli.main([str(f)]) == 2
        assert "FAIL" in capsys.readouterr().out

    def test_warn_exit_1(self, tmp_path, capsys) -> None:
        f = tmp_path / "b.md"
        f.write_text(WARN_TEXT, encoding="utf-8")
        assert cli.main([str(f)]) == 1

    def test_pass_exit_0(self, tmp_path) -> None:
        f = tmp_path / "c.md"
        f.write_text(CLEAN_TEXT, encoding="utf-8")
        assert cli.main([str(f), "--profile", "general"]) == 0

    def test_no_thai_skipped_fast_path(self, tmp_path, capsys) -> None:
        f = tmp_path / "d.py"
        f.write_text("def main():\n    return 42\n", encoding="utf-8")
        assert cli.main([str(f)]) == 0
        assert "no Thai content" in capsys.readouterr().out

    def test_missing_file_exit_3(self, tmp_path) -> None:
        assert cli.main([str(tmp_path / "nope.md")]) == 3

    def test_force_checks_non_thai(self, tmp_path) -> None:
        f = tmp_path / "e.md"
        f.write_text("hello world", encoding="utf-8")
        assert cli.main([str(f), "--force"]) == 0  # checked, still clean

    def test_json_output(self, tmp_path, capsys) -> None:
        f = tmp_path / "f.md"
        f.write_text(WARN_TEXT, encoding="utf-8")
        assert cli.main([str(f), "--json"]) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload[str(f)]["status"] == "WARN"


class TestHookMode:
    def test_hook_blocks_fail_verdict(self, capsys) -> None:
        code, out = _hook(
            {"tool_name": "Write", "tool_input": {"file_path": "x.md", "content": BIDI_TEXT}},
            capsys,
        )
        decision = json.loads(out)
        assert code == 0  # hook protocol: exit 0 + decision JSON
        assert decision["decision"] == "block"
        assert "bidi" in decision["reason"].lower()

    def test_hook_allows_warn(self, capsys) -> None:
        code, out = _hook(
            {"tool_name": "Write", "tool_input": {"file_path": "x.md", "content": WARN_TEXT}},
            capsys,
        )
        assert code == 0 and out == ""

    def test_hook_allows_edit_new_string(self, capsys) -> None:
        code, out = _hook(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "x.md", "old_string": "a", "new_string": BIDI_TEXT},
            },
            capsys,
        )
        decision = json.loads(out)
        assert decision["decision"] == "block"

    def test_hook_ignores_unhooked_tools(self, capsys) -> None:
        code, out = _hook(
            {"tool_name": "Bash", "tool_input": {"command": BIDI_TEXT}}, capsys
        )
        assert code == 0 and out == ""

    def test_hook_ignores_non_thai(self, capsys) -> None:
        code, out = _hook(
            {"tool_name": "Write", "tool_input": {"content": "just english"}}, capsys
        )
        assert code == 0 and out == ""

    def test_hook_bad_json_allows(self, capsys, monkeypatch) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
        assert cli.run_hook(profile="general") == 0
