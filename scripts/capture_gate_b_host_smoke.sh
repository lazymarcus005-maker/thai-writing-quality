#!/usr/bin/env bash
# T-010 Gate B: real-host smoke test of the thai-writing-quality skill + MCP server
# through Claude Code (headless). Captures a full request/response transcript.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="$REPO/.venv/bin/python"
SCRATCH="$(mktemp -d /tmp/twq-host-smoke.XXXXXX)"
OUT="$REPO/docs/evidence/gate-b"
mkdir -p "$OUT" "$SCRATCH/.claude/skills/thai-writing-quality"

# 1. Install the skill into the scratch host (Claude Code project-scope skills).
cp "$REPO/skills/thai-writing-quality/SKILL.md" "$SCRATCH/.claude/skills/thai-writing-quality/SKILL.md"

# 2. Sample Thai document with deliberate, realistic defects.
cat > "$SCRATCH/thai-sample.md" <<'DOC'
# รายงานสถานะระบบ

ขออนุญาติแจ้งผลการตรวจสอบระบบครับ
ทีมงานได้ทำการตรวจสอบ respones จาก API แล้วพบว่า endpoint /cxgateway/v1/member-xapi ตอบกลับด้วย status 500
ฐานข้อมูล Redis ทำงานช้าในช่วงเวลา 09:00-10:00 โดยมี latency p95 สูงถึง 850ms
DOC

# 3. MCP config pointing at the local stdio server.
cat > "$SCRATCH/.mcp.json" <<JSON
{
  "mcpServers": {
    "thai-writing-quality": {
      "command": "$PY",
      "args": ["-m", "thai_writing_mcp.server"],
      "env": {"TWQ_LOG_LEVEL": "ERROR", "PYTHONPATH": "$REPO/src"}
    }
  }
}
JSON

# 4. Drive the real host headlessly; stream-json records the full transcript
#    including MCP tool calls. The agent must follow the skill workflow
#    (validate/analyze -> correct in suggest mode, max 2 passes).
cd "$SCRATCH"
claude -p "You have the thai-writing-quality skill installed. Follow its workflow exactly: validate thai-sample.md with the MCP server, then get suggested corrections (suggest mode only), then reply with (1) the issues found and (2) the suggested fixed text. Max 2 tool passes." \
  --mcp-config "$SCRATCH/.mcp.json" --strict-mcp-config \
  --allowedTools "mcp__thai-writing-quality" \
  --output-format stream-json --verbose > "$OUT/host-transcript.jsonl"

# 5. Also capture the plain final answer for readability.
claude -p "Follow the thai-writing-quality skill workflow on thai-sample.md: validate, then thai_correct suggest mode, then output ONLY the suggested corrected text." \
  --mcp-config "$SCRATCH/.mcp.json" --strict-mcp-config \
  --allowedTools "mcp__thai-writing-quality" \
  --output-format json > "$OUT/host-final-answer.json"

# 6. Evidence summary.
python3 - "$OUT" <<'PYEOF'
import json, sys, pathlib
out = pathlib.Path(sys.argv[1])
lines = [json.loads(l) for l in (out / "host-transcript.jsonl").read_text().splitlines() if l.strip()]
tool_calls = []
for e in lines:
    for m in e.get("message", {}).get("content", []) if isinstance(e.get("message"), dict) else []:
        if isinstance(m, dict) and m.get("type") == "tool_use" and "mcp__" in m.get("name", ""):
            tool_calls.append({"tool": m["name"], "input": m["input"]})
final = json.loads((out / "host-final-answer.json").read_text())
summary = {
    "host": "Claude Code CLI (v2.1.251), headless print mode",
    "transport": "stdio (mcp config: thai-writing-quality)",
    "mcp_tool_calls": tool_calls,
    "final_result": final.get("result", "")[:2000],
    "num_turns": final.get("num_turns"),
}
(out / "host-smoke-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
print(f"mcp tool calls observed: {len(tool_calls)}")
for c in tool_calls:
    print(" -", c["tool"])
assert tool_calls, "NO MCP TOOL CALLS OBSERVED — smoke failed"
print("GATE B SMOKE: PASS")
PYEOF

rm -rf "$SCRATCH"
