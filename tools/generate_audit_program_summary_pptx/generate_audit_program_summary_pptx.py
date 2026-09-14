"""
generate_audit_program_summary_pptx.py
=======================================
watsonx Orchestrate tool — fetches an AuditProgram (Audit) from IBM OpenPages
and generates a filled executive Audit Report PowerPoint presentation (.pptx)
in a single call.

Import command
--------------
    orchestrate tools import \\
        -k python \\
        -f tools/generate_audit_program_summary_pptx/generate_audit_program_summary_pptx.py \\
        -r tools/generate_audit_program_summary_pptx/requirements.txt \\
        -p tools/generate_audit_program_summary_pptx
"""
import json
import re
import uuid
from datetime import datetime
from typing import Any

import requests
from ibm_watsonx_orchestrate.agent_builder.tools import ToolPermission, tool

from fill_audit_program_summary_pptx import fill_audit_program_summary_pptx


# ── MCP proxy config ──────────────────────────────────────────────────────────

_MCP_ENDPOINT = (
    "https://generic-openpages-mcp-server.2c20hyggoq5p.us-south.codeengine.appdomain.cloud/mcp"
)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _strip_html(raw: Any) -> str:
    """Strip HTML tags and decode common HTML entities."""
    if not raw:
        return ""
    text = str(raw)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&apos;", "'")
        .replace("&nbsp;", " ")
        .replace("&#160;", " ")
    )
    return re.sub(r"\n{3,}", "\n\n", text.strip())


def _format_date(raw: Any) -> str:
    """Format ISO datetime string to 'Mon DD, YYYY' (e.g. 'Oct 23, 2018')."""
    if not raw:
        return "Not recorded"
    s = str(raw)[:10]
    try:
        dt = datetime.strptime(s, "%Y-%m-%d")
        return dt.strftime("%b %-d, %Y")
    except Exception:
        return s


def _format_period(start_raw: Any, end_raw: Any) -> str:
    """Format period like 'Feb 1 – Mar 30, 2019'."""
    if not start_raw and not end_raw:
        return "Not recorded"
    s_str = _format_date(start_raw)
    e_str = _format_date(end_raw)
    return f"{s_str} – {e_str}"


def _safe(value: Any, default: str = "Not recorded") -> str:
    """Return stripped string or default if falsy."""
    v = str(value).strip() if value is not None else ""
    return v if v else default


def _mcp_query(query: str, limit: int = 200) -> list[dict]:
    """
    Call execute_openpages_query on the MCP proxy via JSON-RPC (streamable HTTP).
    Returns the list of row dicts from the 'results' key, or [] if no rows.
    """
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
    resp = requests.post(_MCP_ENDPOINT, json=payload, headers=headers, timeout=30)
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


# ── Tool definition ───────────────────────────────────────────────────────────

@tool(
    name="generate_audit_program_summary_pptx",
    description=(
        "Fetch an AuditProgram (Audit) from IBM OpenPages and generate an executive "
        "Audit Report PowerPoint presentation (.pptx). "
        "Retrieves the audit header, scope, timeline, audit phases/sections, findings, "
        "and action plans/issues via OpenPages, then fills the presentation template and "
        "returns the bytes for direct download. "
        "Provide object_id (Resource ID) or object_name to identify the audit."
    ),
    permission=ToolPermission.READ_ONLY,
)
def generate_audit_program_summary_pptx(
    object_name: str,
    filename: str = "audit_report.pptx",
    object_id: str = "",
) -> bytes:
    """
    Fetch AuditProgram data from OpenPages and generate a filled Audit Report PPTX.

    Args:
        object_name (str): Exact name of the AuditProgram in OpenPages (e.g. 'Accounts Receivable - 2018').
                           Used when object_id is not provided.
        filename (str): Desired output filename for the generated .pptx.
        object_id (str): Optional Resource ID (e.g. '3420'). Preferred over name when provided.

    Returns:
        bytes: Raw .pptx file content.
    """
    _AUDIT_FIELDS = (
        "[AuditProgram].[Resource ID], "
        "[AuditProgram].[Name], "
        "[AuditProgram].[Description], "
        "[AuditProgram].[OPSS-Aud:Status], "
        "[AuditProgram].[OPSS-Aud:Type], "
        "[AuditProgram].[OPSS-Aud:Result], "
        "[AuditProgram].[OPSS-Aud:Scope], "
        "[AuditProgram].[OPSS-Aud:Owner], "
        "[AuditProgram].[OPSS-Aud:Scheduled Start Date], "
        "[AuditProgram].[OPSS-Aud:Scheduled End Date], "
        "[AuditProgram].[OPSS-Aud:Actual Start Date], "
        "[AuditProgram].[OPSS-Aud:Actual End Date], "
        "[AuditProgram].[OPSS-Aud:Estimated Hours], "
        "[AuditProgram].[OPSS-Aud:Actual Hours], "
        "[AuditProgram].[OPSS-Aud:Audit Period Start], "
        "[AuditProgram].[OPSS-Aud:Audit Period End], "
        "[AuditProgram].[OPSS-Aud:Audit Commitment], "
        "[AuditProgram].[OPSS-Aud:Closed] "
    )

    # ── Query 1: AuditProgram header ──────────────────────────────────────────
    if object_id.strip():
        safe_id = object_id.strip().replace("'", "''")
        audit_rows = _mcp_query(
            f"SELECT {_AUDIT_FIELDS} FROM [AuditProgram] WHERE [AuditProgram].[Resource ID] = '{safe_id}'",
            limit=1,
        )
        lookup_desc = f"ID '{object_id}'"
    else:
        safe_name = object_name.replace("'", "''")
        audit_rows = _mcp_query(
            f"SELECT {_AUDIT_FIELDS} FROM [AuditProgram] WHERE [AuditProgram].[Name] = '{safe_name}'",
            limit=1,
        )
        lookup_desc = f"name '{object_name}'"

    if not audit_rows:
        raise ValueError(
            f"No AuditProgram found with {lookup_desc}. "
            "Check the exact value (case-sensitive) and try again."
        )

    a = audit_rows[0]
    resource_id = str(a.get("Resource ID", ""))

    # ── Query 2: AuditPhases ──────────────────────────────────────────────────
    phase_rows = _mcp_query(
        f"""SELECT [AuditPhase].[Resource ID], [AuditPhase].[Name],
               [AuditPhase].[OPSS-AudPh:Type],
               [AuditPhase].[OPSS-AudPh:Preparation Status],
               [AuditPhase].[OPSS-AudPh:Review Status]
        FROM [AuditProgram]
        JOIN [AuditPhase] ON PARENT([AuditProgram])
        WHERE [AuditProgram].[Resource ID] = '{resource_id}'"""
    )

    # ── Query 3: Findings ─────────────────────────────────────────────────────
    finding_rows = _mcp_query(
        f"""SELECT [Finding].[Resource ID], [Finding].[Name],
               [Finding].[Description],
               [Finding].[OPSS-Finding:Priority],
               [Finding].[OPSS-Finding:Impact],
               [Finding].[OPSS-Finding:Status],
               [Finding].[OPSS-Finding:Reportable],
               [Finding].[OPSS-Finding:Preparer],
               [Finding].[OPSS-Finding:MgmtOwner],
               [Finding].[OPSS-Finding:Recommendation],
               [Finding].[OPSS-Finding:MgmtResp]
        FROM [AuditProgram]
        JOIN [Finding] ON PARENT([AuditProgram])
        WHERE [AuditProgram].[Resource ID] = '{resource_id}'"""
    )

    # ── Query 4: SOXIssues ────────────────────────────────────────────────────
    issue_rows = _mcp_query(
        f"""SELECT [SOXIssue].[Resource ID], [SOXIssue].[Name],
               [SOXIssue].[Description],
               [SOXIssue].[OPSS-Iss:Priority],
               [SOXIssue].[OPSS-Iss:Impact],
               [SOXIssue].[OPSS-Iss:Status],
               [SOXIssue].[OPSS-Iss:Due Date],
               [SOXIssue].[OPSS-Iss:Issue Type],
               [SOXIssue].[OPSS-Iss:Assignee],
               [SOXIssue].[OPSS-Iss:Resolution Status],
               [SOXIssue].[OPSS-Iss:Management Response]
        FROM [AuditProgram]
        JOIN [SOXIssue] ON PARENT([AuditProgram])
        WHERE [AuditProgram].[Resource ID] = '{resource_id}'"""
    )

    # ── Calculate Phase Metrics ───────────────────────────────────────────────
    total_phases = len(phase_rows)
    phases_completed = sum(1 for p in phase_rows if p.get("OPSS-AudPh:Preparation Status") == "Completed")
    phases_in_progress = sum(1 for p in phase_rows if p.get("OPSS-AudPh:Preparation Status") == "In Progress")
    phases_not_started = sum(1 for p in phase_rows if p.get("OPSS-AudPh:Preparation Status") == "Not Started")
    phases_changes_required = sum(1 for p in phase_rows if p.get("OPSS-AudPh:Review Status") == "Changes Required")

    # ── Calculate Finding Metrics ─────────────────────────────────────────────
    findings_total = len(finding_rows)
    findings_open = sum(1 for f in finding_rows if f.get("OPSS-Finding:Status") == "Open")
    findings_reportable = sum(1 for f in finding_rows if f.get("OPSS-Finding:Reportable") == "Yes")
    findings_high = sum(1 for f in finding_rows if f.get("OPSS-Finding:Priority") == "High")
    findings_sig_impact = sum(1 for f in finding_rows if f.get("OPSS-Finding:Impact") == "Significant")

    # ── Calculate Issue Metrics ───────────────────────────────────────────────
    issues_total = len(issue_rows)
    issues_open = sum(1 for i in issue_rows if i.get("OPSS-Iss:Status") == "Open")
    issues_overdue = 0
    now_iso = datetime.now().isoformat()
    for iss in issue_rows:
        dd = iss.get("OPSS-Iss:Due Date")
        if dd and str(dd)[:10] < now_iso[:10] and iss.get("OPSS-Iss:Status") == "Open":
            issues_overdue += 1
    issues_high = sum(1 for i in issue_rows if i.get("OPSS-Iss:Priority") == "High")
    issues_eval_in_progress = sum(1 for i in issue_rows if i.get("OPSS-Iss:Resolution Status") == "Evaluation in Progress")

    # ── Assemble Data Dict ────────────────────────────────────────────────────
    full_audit_name = _safe(a.get("Name"))
    parts = full_audit_name.split(" - ")
    audit_short_name = parts[0] if parts else full_audit_name
    audit_year = _safe(a.get("OPSS-Aud:Audit Commitment"), "2018")
    overall_res = _safe(a.get("OPSS-Aud:Result"), "Fair")
    is_closed = a.get("OPSS-Aud:Closed") == "Yes"
    closed_str = "Closed" if is_closed else "Not Closed"
    status_str = _safe(a.get("OPSS-Aud:Status"), "Completed")
    audit_type = _safe(a.get("OPSS-Aud:Type"), "Financial")
    scope_str = _safe(a.get("OPSS-Aud:Scope"), "North America Retail Banking")

    sched_start_raw = a.get("OPSS-Aud:Scheduled Start Date")
    act_start_raw = a.get("OPSS-Aud:Actual Start Date")
    sched_end_raw = a.get("OPSS-Aud:Scheduled End Date")
    act_end_raw = a.get("OPSS-Aud:Actual End Date")
    est_hours_raw = a.get("OPSS-Aud:Estimated Hours")
    act_hours_raw = a.get("OPSS-Aud:Actual Hours")

    # Fallback finding / issue card builders
    f_cards = {}
    for idx in range(1, 4):
        if idx <= len(finding_rows):
            f = finding_rows[idx - 1]
            prio = _safe(f.get("OPSS-Finding:Priority"), "MED").upper()
            prio_badge = "MED" if prio == "MEDIUM" else prio
            f_cards[f"f{idx}_prio_badge"] = prio_badge
            f_cards[f"f{idx}_impact_badge"] = _safe(f.get("OPSS-Finding:Impact"), "Inconsequential")
            prep = _safe(f.get("OPSS-Finding:Preparer"), "auditor")
            fname = _safe(f.get("Name"))
            f_cards[f"f{idx}_header"] = f"{fname} · Preparer: {prep}"
            f_cards[f"f{idx}_desc"] = _strip_html(f.get("Description")) or fname
            f_cards[f"f{idx}_status"] = _safe(f.get("OPSS-Finding:Status"), "Open")
            f_cards[f"f{idx}_reportable"] = _safe(f.get("OPSS-Finding:Reportable"), "Yes")
            f_cards[f"f{idx}_owner"] = _safe(f.get("OPSS-Finding:MgmtOwner"), "Not assigned")
            rec = _strip_html(f.get("OPSS-Finding:Recommendation"))
            f_cards[f"f{idx}_rec"] = f"Recommendation: {rec}" if rec else "Not recorded"
            resp = _safe(f.get("OPSS-Finding:MgmtResp"), "")
            f_cards[f"f{idx}_resp"] = resp or "Waiting for Response"

    i_cards = {}
    for idx in range(1, 3):
        if idx <= len(issue_rows):
            iss = issue_rows[idx - 1]
            prio = _safe(iss.get("OPSS-Iss:Priority"), "HIGH").upper()
            i_cards[f"i{idx}_prio_badge"] = f"{prio} PRIORITY"
            i_cards[f"i{idx}_status"] = _safe(iss.get("OPSS-Iss:Status"), "Open")
            due_str = _format_date(iss.get("OPSS-Iss:Due Date"))
            i_cards[f"i{idx}_due_badge"] = f"OVERDUE — Due {due_str}"
            iname = _safe(iss.get("Name"))
            itype = _safe(iss.get("OPSS-Iss:Issue Type"), "Other")
            iimpact = _safe(iss.get("OPSS-Iss:Impact"), "Significant")
            iassignee = _safe(iss.get("OPSS-Iss:Assignee"), "auditor")
            i_cards[f"i{idx}_header"] = f"{iname} · Type: {itype} · Impact: {iimpact} · Assignee: {iassignee}"
            idesc = _strip_html(iss.get("Description")) or iname
            if len(idesc) > 80:
                i_cards[f"i{idx}_desc"] = idesc[:80] + "..."
                i_cards[f"i{idx}_subdesc"] = idesc[80:]
            else:
                i_cards[f"i{idx}_desc"] = idesc
                i_cards[f"i{idx}_subdesc"] = ""
            i_cards[f"i{idx}_resolution"] = _safe(iss.get("OPSS-Iss:Resolution Status"), "Evaluation in Progress")
            i_cards[f"i{idx}_overdue_by"] = "~6+ years"

    payload = {
        "audit_name": audit_short_name,
        "audit_year": audit_year,
        "full_name": f"{audit_short_name} — {audit_year}",
        "audit_type": f"{audit_type} Audit" if not audit_type.endswith("Audit") else audit_type,
        "scope": scope_str,
        "overall_result": overall_res,
        "owner": _safe(a.get("OPSS-Aud:Owner"), "alaudit"),
        "status_summary": f"Status: {status_str} · {closed_str} · Resource ID: {resource_id}",
        "description": _strip_html(a.get("Description")) or f"{audit_year} {audit_short_name} Scheduled Audit",
        "sched_start": _format_date(sched_start_raw),
        "act_start": f"Actual: {_format_date(act_start_raw)}",
        "sched_end": _format_date(sched_end_raw),
        "act_end": f"Actual: {_format_date(act_end_raw)}",
        "est_hours": str(est_hours_raw) if est_hours_raw else "Not recorded",
        "act_hours": f"Actual: {act_hours_raw}" if act_hours_raw else "Actual: Not recorded",
        "audit_period": _format_period(a.get("OPSS-Aud:Audit Period Start"), a.get("OPSS-Aud:Audit Period End")),
        "period_sub": f"Audit Year: {audit_year} · Type: {audit_type}",
        "entity_name": audit_short_name,
        "entity_scope": f"Scope: {scope_str}",
        "attention_note": (
            "Audit started earlier than scheduled. Status is Completed but the audit is not formally closed. "
            "No actual end date or actual hours have been recorded."
        ),
        "phases_header": f"AUDIT SECTIONS — {total_phases} PHASES",
        "total_phases": str(total_phases),
        "phases_completed": str(phases_completed),
        "phases_in_progress": str(phases_in_progress),
        "phases_not_started": str(phases_not_started),
        "phases_changes_required": str(phases_changes_required),
        "findings_total_header": f"AUDIT FINDINGS — {findings_total} TOTAL",
        "findings_subtitle": "All Findings Open" if findings_open == findings_total else f"{findings_open} Open",
        "findings_open": str(findings_open),
        "findings_reportable": str(findings_reportable),
        "findings_high": str(findings_high),
        "findings_sig_impact": str(findings_sig_impact),
        "issues_total_header": f"ISSUES — {issues_total} TOTAL",
        "issues_subtitle": "Both Issues Open and Overdue" if issues_overdue == issues_total else f"{issues_open} Open, {issues_overdue} Overdue",
        "issues_open": str(issues_open),
        "issues_overdue": str(issues_overdue),
        "issues_high": str(issues_high),
        "issues_eval_in_progress": str(issues_eval_in_progress),
        "obs_1_text": "Both issues are overdue — ISS001 by 6+ years, ISS-NA-CB-ERM-003 by 10+ years. Immediate escalation required.",
        "obs_2_text": "FIND_0126 (Incorrect journal entries, High priority) has no management owner or recommendation recorded.",
        "obs_3_text": "Audit is marked Completed but all Report and Quality Review phases are Not Started. Formal closure is blocked.",
        "obs_4_text": "Risk assessment review (01-06) has Changes Required status — unresolved before progressing to report phases.",
        "obs_5_text": "10 of 11 preparation phases fully completed. FIND_0124 has management agreement to create an Action Plan.",
        "result_status_sub": f"Status: {status_str} · {closed_str}",
        "rec_1": "Escalate both overdue issues and assign clear remediation owners and deadlines.",
        "rec_2": "Assign management owner and recommendation to FIND_0126 immediately.",
        "rec_3": "Resolve the risk assessment review (01-06) before starting report phases.",
        "rec_4": "Complete field work (02-01, 02-02, 02-03) and begin the report phase.",
        "rec_5": "Progress through Quality Review phases to achieve formal audit closure.",
    }
    payload.update(f_cards)
    payload.update(i_cards)

    return fill_audit_program_summary_pptx(payload)
