# MCP Tool Contracts v1
All offsets are Unicode code-point positions into `original`, zero-based, half-open [start,end). Original text is immutable.

## thai_analyze
Input: `{text: string, profile?: 'general'|'formal'|'technical', glossary?: string[]}`.
Output: `{schema_version, engine_version, dictionary_version, original, protected_spans:[{start,end,kind}], issues:[Issue], summary:{count,by_category}}`.

## thai_correct
Input: `{text, profile?, mode?: 'suggest'|'safe_apply', max_changes?: integer, glossary?: string[]}`. `suggest` is default. In `safe_apply`, only whitelisted deterministic edits with passing invariant gate may be applied; otherwise emit suggestions.
Output: `{schema_version,original,corrected,patches:[{start,end,original,replacement,applied,reason}],issues,requires_review,validation}`.

## thai_validate
Input: `{text, profile?, glossary?}`. Output: `{schema_version,status:'PASS'|'WARN'|'FAIL',issues,protected_integrity,summary}`. A WARN is not a FAIL. `FAIL` needs deterministic evidence.

## thai_rewrite (P1)
Input: `{text,profile,preserve_meaning?:boolean}`. Output: `{original,proposed,patches,issues,requires_review:true,validation}`. Never automatically publish rewrite. The `preserve_meaning` flag requests behavior, not proof.

## Issue
`{id:string,rule_id:string,category:string,severity:'info'|'low'|'medium'|'high',start:int,end:int,original:string,suggestions:[{text:string,confidence:number|null,source:string}],message:string,protected:boolean,requires_review:boolean}`.

## Invariants
- `original[start:end] == issue.original` (Python code points).
- Proposed patches are nonoverlapping, bounded, reversibly mapped and include precondition matching.
- Protected spans identical in original and output, verified using markers/diff rather than simple substring containment.
- Numeric values, dates and units unchanged unless explicitly authorized.
- Candidate confidence must not be interpreted as probability before calibration.

## Tool selection
`thai_analyze` for diagnosis, `thai_validate` for preflight, `thai_correct` for suggested fixes, `thai_rewrite` only when user specifically needs prose/style changes. Default workflow is max two tool passes to avoid recursion.
