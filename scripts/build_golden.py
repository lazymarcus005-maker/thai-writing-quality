#!/usr/bin/env python3
"""Build the expanded golden dataset (T-011).

Hand-curated sentence families plus bounded programmatic variations.
Every record carries `source` (provenance family) so train/dev/test can be
split BY SOURCE to avoid leakage. Labels are derived from construction
(the substituted value IS the expected literal), authored and reviewed by
the implementing agent — they are NOT independent human annotations; the
benchmark report states this limitation explicitly.

Schema (superset of the seed fixtures):
  id, text, profile, expected_issues, protected_literals, expected_behavior,
  notes, source, [expected_suggestions], [expected_offsets]
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parents[1] / "data" / "golden" / "golden-v1.jsonl"

records: list[dict] = []


def add(
    rid: str,
    text: str,
    profile: str,
    behavior: str,
    expected: list[str] | None = None,
    protected: list[str] | None = None,
    source: str = "",
    suggestions: dict[str, str] | None = None,
    offsets: dict[str, list[int]] | None = None,
    notes: str = "",
) -> None:
    rec: dict = {
        "id": rid,
        "text": text,
        "profile": profile,
        "expected_behavior": behavior,
        "expected_issues": expected or [],
        "protected_literals": protected or [],
        "source": source,
        "notes": notes or "agent-curated 2026-10-11",
    }
    if suggestions:
        rec["expected_suggestions"] = suggestions
    if offsets:
        rec["expected_offsets"] = offsets
    records.append(rec)


# --- 1. Thai canonical misspellings (handwritten) ---------------------------
add("th-canon-001", "ขออนุญาติแจ้งผลการดำเนินงาน", "formal", "suggest",
    ["อนุญาติ"], [], "th-canonical", {"อนุญาติ": "อนุญาต"})
add("th-canon-002", "กรุณาอนุญาติก่อนดำเนินการต่อไป", "formal", "suggest",
    ["อนุญาติ"], [], "th-canonical", {"อนุญาติ": "อนุญาต"})
add("th-canon-003", "ฝ่ายขายต้องได้รับอนุญาติจากผู้จัดการก่อน", "formal", "suggest",
    ["อนุญาติ"], [], "th-canonical", {"อนุญาติ": "อนุญาต"})
add("th-canon-004", "ระบบจะส่งอีเมล์ยืนยันตัวตนถึงผู้ใช้", "general", "suggest",
    ["อีเมล์"], [], "th-canonical", {"อีเมล์": "อีเมล"})
add("th-canon-005", "เราปรับปรุงแอปพลิเคชั่นให้เสถียรขึ้น", "general", "suggest",
    ["แอปพลิเคชั่น"], [], "th-canonical", {"แอปพลิเคชั่น": "แอปพลิเคชัน"})
add("th-canon-006", "ประชุมกำหนดวันพฤษจิกายนที่จะถึง", "formal", "suggest",
    ["พฤษจิกายน"], [], "th-canonical", {"พฤษจิกายน": "พฤศจิกายน"})
for i, svc in enumerate(["ยืนยันตัวตน", "ชำระเงิน", "จัดส่ง", "ยกเลิก"], 1):
    add(f"th-canon-t{i:03d}", f"ผู้ใช้ต้องกดอนุญาติเพื่อ{svc}ตามขั้นตอน", "general", "suggest",
        ["อนุญาติ"], [], "th-canonical-template", {"อนุญาติ": "อนุญาต"})

# --- 2. English typos (handwritten) ------------------------------------------
add("en-typo-001", "ตรวจสอบ respones จาก API", "technical", "suggest",
    ["respones"], ["API"], "en-typo", {"respones": "response"})
add("en-typo-002", "ผมได้ recieve อีเมลแจ้งเตือนแล้ว", "general", "suggest",
    ["recieve"], [], "en-typo", {"recieve": "receive"})
add("en-typo-003", "ตรวจสอบให้แน่ใจว่าไม่มี seperate config ระหว่าง env", "technical", "suggest",
    ["seperate"], [], "en-typo", {"seperate": "separate"})
add("en-typo-004", "job นี้ occured หลังจาก deploy ล่าสุด", "technical", "suggest",
    ["occured"], ["deploy"], "en-typo", {"occured": "occurred"})
add("en-typo-005", "แก้ verison ในไฟล์ package ก่อน build", "technical", "suggest",
    ["verison"], [], "en-typo", {"verison": "version"})
add("en-typo-006", "ฟังก์ชันนี้รับ paramter สองตัว", "technical", "suggest",
    ["paramter"], [], "en-typo", {"paramter": "parameter"})
add("en-typo-007", "fix teh bug ที่เกิดจาก race condition", "technical", "suggest",
    ["teh"], [], "en-typo", {"teh": "the"})
add("en-typo-008", "ตรวจสอบ adress ของ callback server ด้วย", "technical", "suggest",
    ["adress"], [], "en-typo", {"adress": "address"})
for i, w in enumerate(["respones", "recieve", "sucessful"], 1):
    add(f"en-typo-t{i:03d}", f"log แสดงคำว่า {w} ซ้ำหลายครั้งในไฟล์รายงาน", "technical", "suggest",
        [w], [], "en-typo-template")

# --- 3. Mixed Thai-English prose (spec examples) ------------------------------
add("mix-101", "ขออนุญาติ deploy API ไป production", "technical", "suggest",
    ["อนุญาติ"], ["deploy", "API", "production"], "mixed", {"อนุญาติ": "อนุญาต"})
add("mix-102", "รัน unit test บน Kubernetes ก่อน merge", "technical", "no-change",
    [], ["Kubernetes"], "mixed")
add("mix-103", "ฐานข้อมูล Redis ทำงานช้า", "technical", "no-change",
    [], ["Redis"], "mixed")
add(
    "mix-104",
    "endpoint /cxgateway/v1/member-xapi มี status 500",
    "technical",
    "no-protected-change",
    [],
    ["/cxgateway/v1/member-xapi", "500"],
    "mixed",
)
add("mix-105", "ใช้ `HttpClient` และ timeout 2s", "technical", "no-protected-change",
    [], ["`HttpClient`", "2s"], "mixed")
add("mix-106", "เราใช้ Docker สำหรับ build และ OpenTelemetry สำหรับ trace", "technical", "no-change",
    [], ["Docker", "OpenTelemetry"], "mixed")

# --- 4. Unicode anomalies ------------------------------------------------------
add("uni-101", "ข้อความนี้มี \u202e ซ่อนอยู่ข้างใน", "general", "flag",
    ["\u202e"], [], "unicode-anomaly", {"\u202e": ""})
add("uni-102", "รหัสผ่าน\u200bที่ส่งมามีช่องว่างล่องหน", "general", "flag",
    ["\u200b"], [], "unicode-anomaly", {"\u200b": ""})
add("uni-103", "โค้ด ＡＰＩ ในเอกสารต้องเป็นตัวอักษรปกติ", "general", "flag",
    ["ＡＰＩ"], [], "unicode-anomaly", {"ＡＰＩ": "API"})
for i, ch in enumerate(["\u202a", "\u202b", "\u2066"], 1):
    add(f"uni-t{i:03d}", f"ข้อความทดสอบ {ch} มีอักขระควบคุมทิศทาง", "general", "flag",
        [ch], [], "unicode-anomaly-template", {ch: ""})

# --- 5. Protected content guards ------------------------------------------------
routes = ["/cxgateway/v1/member-xapi", "/cxgateway/v1/payment-xapi", "/cxutility/api/v2/orders"]
for i, r in enumerate(routes, 1):
    add(f"guard-route-{i:03d}", f"เรียก {r} แล้วได้ HTTP 500", "technical", "no-protected-change",
        [], [r, "500"], "guard-routes")
codes = ["x = compute_total(cart)", "return jsonify(resp)", "await client.connect()"]
for i, c in enumerate(codes, 1):
    add(f"guard-code-{i:03d}", f"ตัวอย่างโค้ด: `{c}` ใช้ตามนี้", "technical", "no-protected-change",
        [], [f"`{c}`"], "guard-code")
jsons = [
    '{"BICode":"TH01","count":500}',
    '{"status":"ok","latency_ms":42}',
    '{"items":[1,2,3],"total":3}',
]
for i, j in enumerate(jsons, 1):
    add(f"guard-json-{i:03d}", f"server ตอบกลับ {j} ตามที่กำหนด", "technical", "no-protected-change",
        [], [json.loads(j) and j], "guard-json")
paths = ["src/config/app.yaml", "docs/setup/guide.md", "lib/utils/parser.py"]
for i, p in enumerate(paths, 1):
    add(f"guard-path-{i:03d}", f"แก้ไขไฟล์ {p} ก่อนรันระบบ", "technical", "no-protected-change",
        [], [p], "guard-paths")
urls = ["https://api.example.com/v1/status", "https://docs.example.co.th/guide", "https://internal.site:8443/health"]
for i, u in enumerate(urls, 1):
    add(f"guard-url-{i:03d}", f"ดูรายละเอียดได้ที่ {u} ตามสะดวก", "technical", "no-protected-change",
        [], [u], "guard-urls")
idents = [
    ("p95", "latency p95 อยู่ในเกณฑ์ปกติ"),
    ("v2", "ใช้ schema v2 แล้ว"),
    ("x86", "build สำหรับ x86 เท่านั้น"),
]
for i, (t, s) in enumerate(idents, 1):
    add(f"guard-ident-{i:03d}", s, "technical", "no-protected-change", [], [t], "guard-idents")

# --- 6. Numbers and dates --------------------------------------------------------
for i, (sentence, _lit) in enumerate([
    ("ระบบจะปรับปรุงวันที่ 2026-10-15 ประมาณ 3,000 รายการ", None),
    ("ประมวลผลแล้ว 12,500 รายการภายใน 45 นาที", None),
    ("งบประมาณ 250,000 บาท ตามแผนที่อนุมัติไว้", None),
    ("รอบปัจจุบันเร็วขึ้น 35% จากไตรมาสก่อน", None),
], 1):
    add(f"num-{i:03d}", sentence, "formal", "no-protected-change", [], [], "numbers-dates")

# --- 7. Clean Thai controls (must yield zero issues) ------------------------------
cleans = [
    ("ประมวลผลคำขอเรียบร้อยแล้ว", "general"),
    ("ทีมงานประชุมกันทุกวันจันทร์เช้า", "formal"),
    ("เอกสารฉบับนี้จัดทำขึ้นเพื่อประกอบการพิจารณา", "formal"),
    ("ระบบสำรองข้อมูลทำงานตามปกติทุกคืน", "general"),
    ("ลูกค้าสามารถตรวจสอบสถานะคำสั่งซื้อได้ในหน้าเว็บ", "general"),
    ("การชำระเงินจะตรวจสอบภายในหนึ่งวันทำการ", "formal"),
    ("ข้อมูลส่วนบุคคลได้รับการปกป้องตามนโยบาย", "formal"),
    ("โปรดลงชื่อในแบบฟอร์มก่อนส่งกลับภายในสิ้นเดือน", "formal"),
    ("ผลการทดสอบผ่านทุกขั้นตอนตามแผนที่วางไว้", "general"),
    ("ประตูอัตโนมัติจะปิดเมื่อไม่มีการใช้งาน", "general"),
]
for i, (sentence, prof) in enumerate(cleans, 1):
    add(f"clean-{i:03d}", sentence, prof, "no-change", [], [], "clean-thai")
cleans_mixed = [
    ("deploy เสร็จแล้ว production ปกติ", "technical"),
    ("cache ถูกล้างตามรอบที่กำหนด", "technical"),
    ("เรา monitor ระบบผ่าน dashboard หลัก", "technical"),
    ("ทีม dev รับผิดชอบ service นี้เต็มเวลา", "technical"),
    ("release ครั้งต่อไปกำหนดไว้ปลายเดือน", "technical"),
    ("backup ทุกคืนเก็บไว้ 30 วัน", "technical"),
]
for i, (sentence, prof) in enumerate(cleans_mixed, 1):
    add(f"clean-mix-{i:03d}", sentence, prof, "no-change", [], [], "clean-mixed")

# --- 8. Semantic-risk (must abstain, no auto changes) ------------------------------
add("sem-101", "ผู้ป่วยมีอาการแย่ลงหลังได้รับยา", "formal", "no-meaning-change",
    [], ["แย่ลง"], "semantic-risk")
add("sem-102", "ธนาคารข้างทางเปิดตอนเจ็ดโมเช้า", "general", "no-meaning-change",
    [], [], "semantic-risk")
add("sem-103", "สัญญาฉบับนี้มีผลบังคับเมื่อผู้ซื้อชำระเงินมัดจำแล้ว", "formal", "no-meaning-change",
    [], [], "semantic-risk")
add("sem-104", "อย่าลบข้อมูลก่อนสำรองเสร็จเด็ดขาด", "general", "no-meaning-change",
    [], [], "semantic-risk")

# --- 9. Unknown-token review (formal profile) ---------------------------------------
for i, tok in enumerate(["Zyxpan", "Qorvia", "Truvex"], 1):
    add(f"review-{i:03d}", f"บริษัทใช้ซอฟต์แวร์ {tok} ในสำนักงานใหญ่", "formal", "review",
        [tok], [], "review-unknown")

# --- 10. Programmatic template expansion (labels derived from construction) --------
SERVICES = ["member", "payment", "order", "inventory", "report", "notify", "auth", "search"]
for i, svc in enumerate(SERVICES, 1):
    route = f"/cxgateway/v1/{svc}-xapi"
    add(f"tmpl-route-{i:03d}", f"เรียก {route} ตอบกลับด้วย status 200", "technical",
        "no-protected-change", [], [route, "200"], "template-routes")
UNITS = ["2s", "150ms", "3.5GB", "80%", "12kg", "25km", "5min", "100฿"]
for i, u in enumerate(UNITS, 1):
    add(f"tmpl-unit-{i:03d}", f"ค่าที่วัดได้คือ {u} ตามรายงาน", "technical",
        "no-protected-change", [], [u], "template-units")
DATES = ["2026-01-05", "2026-03-17", "2026-06-30", "2026-09-11", "2025-12-24", "2027-02-08"]
for i, d in enumerate(DATES, 1):
    add(f"tmpl-date-{i:03d}", f"กำหนดส่งมอบวันที่ {d} ตามสัญญา", "formal",
        "no-protected-change", [], [d], "template-dates")
CODES = [
    "config.timeout = 30", "user.is_active == true", "order.total_price > 0",
    "return render(template)", "data.pop('cache', None)", "x := fetch_all(rows)",
]
for i, c in enumerate(CODES, 1):
    add(f"tmpl-code-{i:03d}", f"ใช้โค้ด `{c}` ตามตัวอย่าง", "technical",
        "no-protected-change", [], [f"`{c}`"], "template-code")
TYPO_VALUES = [("respones", "response"), ("recieve", "receive"), ("verison", "version")]
for i, (w, fix) in enumerate(TYPO_VALUES * 3, 1):
    add(f"tmpl-typo-{i:03d}", f"พบคำว่า {w} ในบันทึกฉบับที่ {i}", "technical",
        "suggest", [w], [], "template-typos", {w: fix})
CANON_VALUES = ["อนุญาติ", "อีเมล์", "แอปพลิเคชั่น"]
CANON_FIX = {"อนุญาติ": "อนุญาต", "อีเมล์": "อีเมล", "แอปพลิเคชั่น": "แอปพลิเคชัน"}
for i, w in enumerate(CANON_VALUES * 3, 1):
    add(f"tmpl-canon-{i:03d}", f"เอกสารฉบับที่ {i} ระบุคำว่า {w} ไว้", "formal",
        "suggest", [w], [], "template-canonical", {w: CANON_FIX[w]})
BIDI_CHARS = ["\u202c", "\u202d", "\u2067", "\u2068", "\u2069"]
for i, ch in enumerate(BIDI_CHARS, 1):
    add(f"tmpl-bidi-{i:03d}", f"ตัวอย่างที่ {i} มีอักขระ {ch} แทรกอยู่", "general",
        "flag", [ch], [], "template-bidi", {ch: ""})

# --- 11. Seed fixtures re-labeled with source ---------------------------------------
SEEDS = Path(__file__).parents[1] / "tests" / "fixtures" / "golden.jsonl"
for line in SEEDS.read_text().splitlines():
    if not line.strip():
        continue
    rec = json.loads(line)
    rec["source"] = "seed"
    rec["notes"] = "original seed fixture (handoff bundle)"
    records.append(rec)

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"wrote {len(records)} records -> {OUT}")
