---
name: wxo-create-template-filler
description: >
  Use when the user wants to turn a Word (.docx) template into a watsonx
  Orchestrate tool that fills it with data from OpenPages. Guides the full
  pipeline: inspect template → propose simplified template → query OpenPages
  to discover the data model → write an implementation plan → create a
  CLI-testable fill script and a self-contained single Orchestrate tool → add
  the tool to a target agent. Trigger phrases: "create a template filler",
  "build a docx tool from template", "automate document generation",
  "new document generator tool", "turn this template into a tool".
---

# wxo-create-template-filler

Turn a Word (.docx) report template into a working watsonx Orchestrate tool
that fetches live data from IBM OpenPages and fills the document automatically.
This procedure is proven for the Workpaper (Feuille de travail) flow and is
reproducible for any new document type.

---

## Proven architecture (do not deviate)

```
User: "Generate the <DocType> for '<Object Name>'"
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│  generate_<doc_type>_docx  (single Python @tool)         │
│                                                          │
│  • Calls the openpages-mcp proxy via JSON-RPC            │
│  • Runs N OPL queries to gather all data                 │
│  • Cleans: strips HTML, formats dates, etc.              │
│  • Calls fill_<doc_type>() to fill the OOXML template    │
│  • Returns .docx bytes → Orchestrate S3 download link    │
└──────────────────────────────────────────────────────────┘
        │
        ▼
Agent response: "Here is your <DocType> — [Download link]"
```

### Why a single Python tool instead of a two-node flow

| Problem | Why it matters |
|---------|----------------|
| Agentic flows with 2 nodes require a Pydantic-typed intermediate model and `input_schema=` wiring on every node | Extra complexity with no user-visible benefit |
| The flow engine wraps the whole pipeline in an opaque box that is harder to debug | A single `@tool` call is fully transparent in the agent trace |
| Direct OpenPages REST calls return HTML on TechZone | The Angular SPA intercepts all `/api/*` paths — the MCP proxy is still required regardless of architecture |

**Fix:** One Python `@tool` that calls the public MCP proxy server referenced in the .env file, keyword OPENPAGES_MCP_URL,
. Call it directly via JSON-RPC, assembles the data dict in-memory, and immediately calls
`fill_<doc_type>()` to return bytes.  The agent invokes the tool directly —
no flow, no intermediate JSON string hand-off.

---

## Inputs required from the user

Before starting, confirm you have all three.  If any are missing, use
`ask_followup_question` to collect them:

1. **Template file path** — the `.docx` to analyse (e.g. `input/audit_program_template.docx`).
2. **Top-level OpenPages object type** — the GRC object that is the root of the
   data hierarchy (e.g. `AuditProgram`, `Workpaper`).
3. **Sample object name** — one real instance of that object in OpenPages to use
   for discovery and testing (e.g. `01-01-Send notification letter-1`).

---

## Phase 1 — Template Inspection

### Step 1.1 — Read and understand the template

Unzip the OOXML and read `word/document.xml` to examine placeholder structure:

```bash
python -c "
import zipfile
with zipfile.ZipFile('<template_path>') as zf:
    print(zf.read('word/document.xml').decode('utf-8')[:8000])
"
```

Identify:
- **Scalar placeholders** — text strings like `<System>`, `{{DATE}}`,
  `[audit name]` that map to single field values.
- **Table sentinels** — placeholder rows that mark where dynamic table rows
  should be injected (e.g. `{{ROWS_PROCESSES}}`, `{{ROWS_CD3}}`).
- **Multi-paragraph sentinels** — a single placeholder like `{{AUDIT_OBJECTIVES}}`
  that should expand into multiple `<w:p>` elements.
- **Repeating sections** — patterns that repeat per data item.
- **Static content** — boilerplate text, headings, legal text, footers/headers.

### Step 1.2 — Propose a simplified template

Summarise your findings as a table:

| Section | Original content | Proposed treatment |
|---------|------------------|--------------------|
| Cover page | `<Audit Name>`, `<Date>`, etc. | Scalar `{{AUDIT_NAME}}`, `{{GENERATED_DATE}}` |
| Objectives | Free-text block | Multi-paragraph sentinel `{{AUDIT_OBJECTIVES}}` |
| Processes table | Row per process | Row sentinel `{{ROWS_PROCESSES}}` |
| … | … | … |

**Simplification rules:**
- Replace all placeholders with `{{UPPER_SNAKE}}` tokens inside italic grey runs
  (readable in Word, unique for regex replacement).
- For repeating table sections, replace body rows with a single sentinel row
  containing `{{ROWS_<SECTION_ID>}}` in the first cell.
- For multi-paragraph free-text, use a single paragraph sentinel `{{TOKEN}}`.
- Delete purely illustrative content (screenshots, sample data rows).
- Keep section headings, static policy text, page breaks, and footer/header.

⏸️ **PAUSE — present the simplified template proposal to the user for review.**
Use `ask_followup_question`:
> "Here is my proposal for the simplified template.  Does this look right,
> or would you like to adjust any section before I generate the file?"

---

## Phase 2 — OpenPages Data Discovery

### Step 2.1 — Fetch the OpenPages object type catalog

Use `openpages-mcp:list_resources` (URI: `openpages://catalog/object_types`) to
get the full catalog.  Cache it for the session.

### Step 2.2 — Fetch the schema for the top-level object type

Use `openpages-mcp:get_resource` with URI `openpages://schema/<ObjectType>`.
Note field names (case-sensitive, include group prefixes like `OPSS-Aud:Type`)
and child/parent relationships.

### Step 2.3 — Walk the data hierarchy using the sample object

Run `execute_openpages_query` queries to follow the hierarchy down to the leaf
data needed for each template section.  Pattern:

```sql
-- Level 0: find the sample object
SELECT [AuditProgram].[Resource ID], [AuditProgram].[Name],
       [AuditProgram].[OPSS-Aud:Status]
FROM [AuditProgram]
WHERE [AuditProgram].[Name] = 'Accounts Receivable - 2018'

-- Level 1: children (e.g. SOXProcess under AuditProgram)
SELECT [SOXProcess].[Resource ID], [SOXProcess].[Name],
       [SOXProcess].[Description], [SOXProcess].[Location]
FROM [AuditProgram]
JOIN [SOXProcess] ON PARENT([AuditProgram])
WHERE [AuditProgram].[Resource ID] = '3420'
```

Key JOIN syntax rules:
- `JOIN [ChildType] ON PARENT([FromType])` — traverse down (FROM has children)
- `JOIN [ParentType] ON CHILD([FromType])` — traverse up (FROM has parents)
- Use `ANCESTOR` / `DESCENDANT` for multi-level traversal
- **Never** use AS aliases — they are not supported

### Step 2.4 — Note the MCP proxy response double-wrapping

The `generic-openpages-mcp-server` proxy wraps results in two layers:

```
Outer JSON-RPC: {"result": {"content": [{"type": "text", "text": "<inner>"}]}}
Inner (rows):   {"result": [{"type": "text", "text": "<actual JSON>"}]}
Inner (0 rows): {"result": [{"type": "text", "text": "Query executed successfully. No results found."}]}
Actual data:    {"query": "...", "row_count": N, "results": [...]}
```

The `_mcp_query()` helper in `generate_<doc_type>_docx.py` handles all of
this, including the SSE (`text/event-stream`) response format.  The 0-row
case returns a plain string (not JSON) — guard with `try/except JSONDecodeError → return []`.

### Step 2.5 — Map template sections to OpenPages fields

Produce a mapping table:

| Template placeholder / section | OpenPages query | Field(s) |
|--------------------------------|-----------------|----------|
| `{{AUDIT_NAME}}` | Level-0 | `[AuditProgram].[Name]` |
| `{{GENERATED_DATE}}` | Runtime | Today's date |
| `{{AUDIT_OBJECTIVES}}` | Level-0 | `[AuditProgram].[OPSS-Aud:Objectives]` (HTML → plain text) |
| Processes table | Level-1 join | `[SOXProcess].[Name]`, `.Description`, `.Location` |
| … | … | … |

If any section cannot be mapped, use `ask_followup_question` to ask the user
(hardcode, omit, or add a new field to OpenPages).

---

## Phase 3 — Implementation Plan

### Step 3.1 — Determine the tool directory name

Convention: `tools/generate_<doc_type>_docx/`
(e.g. `tools/generate_workpaper_docx/`, `tools/generate_ssrs_docx/`)

### Step 3.2 — Write the implementation plan

Write `tools/<tool_dir>/IMPLEMENTATION_PLAN.md`.  Include:

1. **Overview** — one paragraph: what the tool does and trigger phrase.
2. **Data model** — the OpenPages hierarchy with confirmed Resource IDs.
3. **Architecture diagram** — ASCII showing User → Agent → single `@tool` → .docx.
4. **File layout** — complete directory tree with `← NEW` / `← MODIFIED`.
5. **JSON payload shape** — the internal data dict built inside the tool before
   calling `fill_<doc_type>()`.
6. **Template filling strategy** — for each placeholder, the injection approach:
   - scalar: `str.replace()` (last, after all injections)
   - paragraph sentinel: string-split (`rfind`/`find`) — see Phase 4
   - row sentinel: regex matching the single sentinel `<w:tr>` — see Phase 4
7. **Implementation steps** — ordered checklist.
8. **Key decisions** — a table of design choices and rationale.
9. **Out of scope** — what is explicitly not handled.

⏸️ **PAUSE — present the plan to the user for review before proceeding.**

---

## Phase 4 — Implementation

Proceed only after the user approves the plan.

### Step 4.1 — Create the simplified template with `create_template.py`

Write `tools/<tool_dir>/create_template.py` — a **pure Python stdlib** script
(no `python-docx`, no external deps) that generates the simplified `.docx`
template programmatically from raw OOXML strings.

Key rules:
- Build `word/document.xml` as a single string with f-strings.
- Use `w:type="pct"` or `w:type="dxa"` (twips) for cell widths — **must match
  the original template**.  Inspect `<w:tcW>` in the original first.
- Scalar sentinels in italic grey runs:
  ```python
  '<w:r><w:rPr><w:i/><w:iCs/><w:color w:val="888888"/>'
  '<w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr>'
  '<w:t xml:space="preserve">{{AUDIT_NAME}}</w:t></w:r>'
  ```
- Row sentinels: a single `<w:tr>` with the token in the first cell.
- Paragraph sentinels: a bare `<w:p>` with the token in an italic run.
- Write all required OOXML parts: `[Content_Types].xml`, `_rels/.rels`,
  `word/_rels/document.xml.rels`, `word/settings.xml`, `word/styles.xml`.

Run it:
```bash
python tools/<tool_dir>/create_template.py
```

### Step 4.2 — Create the filler script `fill_<doc_type>.py`

Write `tools/<tool_dir>/fill_<doc_type>.py` — core fill logic **plus CLI entry
point**.  This file is also imported by the Orchestrate `@tool` wrapper.

**Required structure** (copy from `tools/generate_workpaper_docx/fill_workpaper.py`):

```
module docstring        — JSON input shape (document it clearly)
stdlib imports          — argparse, io, json, os, re, zipfile, datetime
_HERE / TEMPLATE_PATH  — os.path.join(os.path.dirname(os.path.abspath(__file__)), ...)
OOXML helpers           — _xe(), _run(), _tc(), _data_cell(), _hdr_cell()
Column width constants  — match the template's w:type (pct or dxa)
Table builders          — _build_<entity>_rows(items) → str (OOXML <w:tr>…</w:tr>)
_merge_runs(xml)        — mandatory; defragments Word-split runs
_inject_*(xml, data)    — one function per injection type
_replace_scalars(xml, mapping)
fill_<doc_type>(data)   — main function: unpack → merge → inject → replace → repack → bytes
    Injection ORDER (critical):
    1. _merge_runs()
    2. Paragraph-sentinel injections (_inject_*_para)  ← BEFORE row sentinels
    3. Row-sentinel injections (_inject_*_rows)         ← BEFORE scalar replacement
    4. _replace_scalars()                               ← LAST
CLI argparse block      — --json FILE --out FILE
```

**Critical correctness rules:**

1. **Always call `_merge_runs()` first** — Word splits `{{TOKEN}}` across
   multiple `<w:r>` elements with different revision IDs.

2. **Paragraph sentinels use string-split, not regex:**
   ```python
   def _inject_objectives(xml: str, text: str) -> str:
       token = "{{AUDIT_OBJECTIVES}}"
       idx = xml.find(token)
       if idx == -1: return xml
       # Find nearest <w:p> open tag (not <w:pPr>)
       p_start = -1
       for tag in ("<w:p>", "<w:p "):
           pos = xml.rfind(tag, 0, idx)
           if pos > p_start: p_start = pos
       p_end = xml.find("</w:p>", idx) + len("</w:p>")
       # Build replacement paragraphs…
       return xml[:p_start] + replacement + xml[p_end:]
   ```

3. **Row sentinels use a regex that matches only the sentinel `<w:tr>`:**
   ```python
   pattern = re.compile(
       r"<w:tr\b[^>]*>(?:(?!<w:tr).)*?" + re.escape("{{ROWS_PROCESSES}}") + r".*?</w:tr>",
       re.DOTALL,
   )
   xml = pattern.sub(_build_process_rows(processes), xml, count=1)
   ```

4. **Cell widths in injected rows MUST match the template's `w:type`**.
   Use `w:type="dxa"` if the template uses `dxa`, `pct` if it uses `pct`.

5. **Strip HTML from rich-text fields** — OpenPages `Description`, `Scope`,
   `Objectives` fields contain `<p>`, `<br>`, `<span>` tags.  Use `_strip_html()`.

6. **`[Content_Types].xml` cleanup** — if the original template was generated
   by `docx-js`, it may include an `obfuscatedFont` Default entry that references
   `.odttf` files that don't exist.  Remove it:
   ```python
   ct = re.sub(
       r'\s*<Default[^/]*/?\s*ContentType="[^"]*obfuscatedFont"[^>]*/?>',
       "", ct,
   )
   ```

Smoke-test:
```bash
cd tools/<tool_dir>
python fill_<doc_type>.py --json <doc_type>_example.json --out /tmp/test.docx
```

Verify output:
```bash
python -c "
import zipfile, re
with zipfile.ZipFile('/tmp/test.docx') as zf:
    xml = zf.read('word/document.xml').decode('utf-8')
print('Tables :', xml.count('<w:tbl>'))
print('Rows   :', xml.count('<w:tr ') + xml.count('<w:tr>'))
remaining = re.findall(r'\{\{[A-Z_0-9]+\}\}', xml)
print('Unfilled sentinels:', sorted(set(remaining)))
"
```
Expected: correct table/row counts, **zero unfilled sentinels**.

### Step 4.3 — Create the example JSON file

Write `tools/<tool_dir>/<doc_type>_example.json` with live data fetched from
OpenPages for the sample object (use the queries from Phase 2).

### Step 4.4 — Create `generate_<doc_type>_docx.py` (the single tool)

Write `tools/<tool_dir>/generate_<doc_type>_docx.py`.

This is the **only** Orchestrate tool needed.  It combines all data-fetching
and document-generation logic in a single `@tool` function.

Copy the complete `_mcp_query()` helper from
`tools/generate_workpaper_docx/generate_workpaper_docx.py` verbatim — it
handles SSE vs JSON, double-wrapping, and the 0-row plain-string case.

Structure:

```python
"""
generate_<doc_type>_docx.py
===========================
watsonx Orchestrate tool — fetches <DocType> data from IBM OpenPages and
generates a filled Word document (.docx) in a single call.

Import command
--------------
    orchestrate tools import \\
        -k python \\
        -f tools/<tool_dir>/generate_<doc_type>_docx.py \\
        -r tools/<tool_dir>/requirements.txt \\
        -p tools/<tool_dir>
"""

import json, re, uuid
from typing import Any
import requests
from ibm_watsonx_orchestrate.agent_builder.tools import ToolPermission, tool
from fill_<doc_type> import fill_<doc_type>

# MCP proxy endpoint
_MCP_ENDPOINT = (
    "<to_be_replaced_with_the_mcp_url>
)

# Helpers
def _strip_html(raw): ...   # strip <p>, <br>, &nbsp; etc.
def _date(raw): ...         # return first 10 chars or "—"
def _safe(value): ...       # str(value).strip() or "—"
def _mcp_query(query, limit=100) -> list[dict]: ...  # COPY VERBATIM

@tool(
    name="generate_<doc_type>_docx",
    description=(
        "Fetch <DocType> data from IBM OpenPages and generate a filled "
        "Word document (.docx). "
        "Provide object_id (Resource ID) to uniquely identify the object when "
        "multiple objects share the same name."
    ),
    permission=ToolPermission.READ_ONLY,
)
def generate_<doc_type>_docx(
    object_name: str,
    filename: str = "<doc_type>.docx",
    object_id: str = "",
) -> bytes:
    """
    Args:
        object_name (str): Exact name of the top-level OpenPages object.
                           Used only when object_id is not provided.
        filename (str): Desired output filename for the .docx.
        object_id (str): Optional Resource ID. Preferred over name when provided.

    Returns:
        bytes: Raw .docx file content.
    """
    # 1. Run OPL queries to gather all data
    # 2. Build a clean data dict
    # 3. Call fill_<doc_type>(data) and return the bytes
    ...
```

### Step 4.5 — Create supporting files

**`__init__.py`** — empty file.  **Must NOT import from sibling modules.**
The Orchestrate runtime uses `--package-root`; top-level imports fail at deploy time.

**`requirements.txt`:**
```
requests
ibm-watsonx-orchestrate @ https://test-files.pythonhosted.org/packages/2a/18/fb8646080ede20a9a716585a901718a1f523aeb450b852a05006ef2ff898/ibm_watsonx_orchestrate-2.12.0-py3-none-any.whl
```

**`import-all.sh`:**
```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

echo "==> Importing generate_<doc_type>_docx tool..."
orchestrate tools import -k python \
  -f "${SCRIPT_DIR}/generate_<doc_type>_docx.py" \
  -r "${SCRIPT_DIR}/requirements.txt" \
  -p "${SCRIPT_DIR}"

echo ""
echo "✅  Import complete."
echo "    Verify: orchestrate tools list | grep <doc_type>"
```
Then: `chmod +x tools/<tool_dir>/import-all.sh`

### Step 4.6 — Import the tool

```bash
orchestrate env activate <your-env>
tools/<tool_dir>/import-all.sh
```

Verify:
```bash
orchestrate tools list | grep <doc_type>
```

### Step 4.7 — Add the tool to the target agent

In the agent YAML (e.g. `agents/GRC_Agent.yaml`), add to the `tools:` list:
```yaml
tools:
- generate_<doc_type>_docx
```

Add starter prompts:
```yaml
starter_prompts:
  prompts:
  - id: <doc_type>0
    title: Generate the <DocType> for "<sample_object_name>"
    subtitle: ''
    prompt: Generate the <DocType> for "<sample_object_name>"
    state: active
```

Re-import the agent:
```bash
orchestrate agents import -f agents/GRC_Agent.yaml
```

---

## Phase 5 — Validation

### Step 5.1 — CLI smoke test

```bash
cd tools/<tool_dir>
python fill_<doc_type>.py --json <doc_type>_example.json --out /tmp/<DocType>_test.docx
```

### Step 5.2 — Verify output

```bash
python -c "
import zipfile, re
with zipfile.ZipFile('/tmp/<DocType>_test.docx') as zf:
    xml = zf.read('word/document.xml').decode('utf-8')
print('Tables :', xml.count('<w:tbl>'))
print('Rows   :', xml.count('<w:tr ') + xml.count('<w:tr>'))
remaining = re.findall(r'\{\{[A-Z_0-9]+\}\}', xml)
print('Unfilled sentinels:', sorted(set(remaining)))
"
```

Expected: correct table/row counts, **zero unfilled sentinels**.

### Step 5.3 — Report completion

Tell the user:
- ✅ Files created (list each with its path)
- ✅ Tool imported to Orchestrate
- ✅ Agent updated with the new tool and starter prompt
- The starter prompt they can use to test in the Orchestrate UI
- Any known limitations or manual steps remaining

---

## Reference: proven file layout

```
tools/<tool_dir>/
├── create_template.py                 ← generates the simplified .docx template (stdlib only)
├── <doc_type>_template_v1.docx        ← the simplified template (generated by create_template.py)
├── fill_<doc_type>.py                 ← core OOXML fill logic + CLI entry point
├── generate_<doc_type>_docx.py        ← single @tool: MCP queries + fill + return bytes
├── <doc_type>_example.json            ← live sample data from OpenPages
├── requirements.txt                   ← requests + ibm-watsonx-orchestrate wheel
├── __init__.py                        ← empty (must NOT import from siblings)
├── import-all.sh                      ← single tool import
└── IMPLEMENTATION_PLAN.md             ← written in Phase 3
```

---

## Reference: critical gotchas table

| Gotcha | Fix |
|--------|-----|
| Word splits `{{TOKEN}}` across multiple `<w:r>` elements | Always call `_merge_runs()` **first** |
| Paragraph regex `.*?` with `DOTALL` spans `</w:p>` boundaries | Use string-split (`rfind`/`find`) for paragraph sentinels — never regex |
| Row sentinel injected after paragraph sentinel regex eats cross-table content | Always inject paragraph sentinels **BEFORE** row sentinels |
| Template uses `w:type="pct"` but injected rows use `dxa` | Inspect `<w:tcW>` in template XML; match width type exactly |
| `__init__.py` imports from sibling module | Keep `__init__.py` empty; the `-p` / `--package-root` flag handles imports |
| MCP proxy returns `text/event-stream` (SSE) not plain JSON | Parse SSE lines; take the last `data:` line with content |
| MCP proxy 0-row response is a plain string, not JSON | Wrap `json.loads(inner_text)` in `try/except JSONDecodeError → return []` |
| `docx-js` template includes `obfuscatedFont` content type with no actual font files | Strip it from `[Content_Types].xml` with a regex in `fill_<doc_type>.py` |
| OpenPages rich-text fields contain HTML (`<p>`, `<br>`, `&nbsp;`) | Call `_strip_html()` on Description, Scope, Objectives before putting in the payload |
| Agent YAML `style:` must be `react` not `react_core` | Use `style: react` — `react_core` is not a valid WXO ADK value |
| `orchestrate agents import` fails on `context_variables: null` | Use `context_variables: []` (empty list, not null) |
| Multiple objects share the same name in OpenPages | Add an `object_id` parameter; prefer ID-based lookup in the tool |

---

## Reference: `_mcp_query()` — copy this verbatim

This helper handles all MCP proxy quirks (SSE, double-wrapping, 0-row case).
Copy it unchanged into every new `generate_*_docx` tool:

```python
def _mcp_query(query: str, limit: int = 100) -> list[dict]:
    """
    Call execute_openpages_query on the MCP proxy via JSON-RPC (streamable HTTP).
    Returns the list of row dicts from the 'results' key, or [] if no rows.
    """
    import uuid, json, requests
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {
            "name": "execute_openpages_query",
            "arguments": {"query": query, "limit": limit, "format": "json"},
        },
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    resp = requests.post(
        "<mcp_url>",
        json=payload, headers=headers, timeout=30,
    )
    resp.raise_for_status()

    ct = resp.headers.get("content-type", "")
    raw_text = resp.text

    # Handle SSE response
    if "text/event-stream" in ct or raw_text.strip().startswith("data:"):
        result_json = None
        for line in raw_text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                data_str = line[5:].strip()
                if data_str and data_str != "[DONE]":
                    try:
                        result_json = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
        if result_json is None:
            raise ValueError(f"No valid SSE data frame: {raw_text[:500]}")
        body = result_json
    else:
        body = resp.json()

    # Unwrap outer JSON-RPC envelope
    rpc_result = body.get("result", body)
    content = rpc_result.get("content", [])
    outer_text = next((c["text"] for c in content if c.get("type") == "text"), None)
    if outer_text is None:
        raise ValueError(f"No text content in MCP response: {body}")

    try:
        obj = json.loads(outer_text)
    except json.JSONDecodeError:
        return []  # 0-row plain-string response at outer level

    # Handle double-wrapping: {"result": [{"type": "text", "text": "<JSON or plain>"}]}
    if isinstance(obj, dict) and "result" in obj and "results" not in obj:
        inner_list = obj.get("result", [])
        inner_text = next(
            (c["text"] for c in inner_list if isinstance(c, dict) and c.get("type") == "text"),
            None,
        )
        if not inner_text:
            return []
        try:
            obj = json.loads(inner_text)
        except json.JSONDecodeError:
            return []  # "Query executed successfully. No results found."

    if isinstance(obj, dict) and "results" in obj:
        return obj["results"]
    if isinstance(obj, list):
        return obj
    return []
```

---

## Reference: WXO environment details (this project)

| Setting | Value |
|---------|-------|
| Environment name | `itz-environment` |
| WXO API key | see `.env` / `WXO_API_KEY` |
| Activate | `echo "<api_key>" \| orchestrate env activate itz-environment` |
| OpenPages base URL | see `.env` / `OPENPAGES_BASE_URL` |
| MCP proxy base URL | `<mcp_url>` |
| Test agent | `GRC_Agent` |
| Reference tool implementation | `tools/generate_workpaper_docx/generate_workpaper_docx.py` |
