# IMPLEMENTATION PLAN — generate_audit_program_summary_pptx

## 1. Overview

This tool generates a formatted executive Audit Report PowerPoint (.pptx) presentation from live IBM OpenPages data in a single `@tool` call. Given an `AuditProgram` object name (e.g. "Accounts Receivable - 2018") or Resource ID (e.g. "3420"), it fetches all audit metadata, audit sections/phases, findings, and issues via the MCP proxy, builds the structured data dictionary, and fills the PPTX template to return download-ready presentation bytes.

**Trigger phrase:** "Generate the audit report PPTX for '<audit name>'" / "Génère le rapport de la mission <nom>"

---

## 2. Data model (Confirmed with sample ID: 3420 "Accounts Receivable - 2018")

```
AuditProgram (root: ID 3420)
│  Resource ID, Name, Description, OPSS-Aud:Status, OPSS-Aud:Type,
│  OPSS-Aud:Result, OPSS-Aud:Scope, OPSS-Aud:Owner, OPSS-Aud:Closed,
│  OPSS-Aud:Scheduled Start/End Date, OPSS-Aud:Actual Start/End Date,
│  OPSS-Aud:Estimated Hours, OPSS-Aud:Actual Hours,
│  OPSS-Aud:Audit Period Start/End, OPSS-Aud:Audit Commitment
│
├── AuditPhase[] (children via JOIN [AuditPhase] ON PARENT([AuditProgram]))
│     Resource ID, Name, OPSS-AudPh:Type (Preparation, Field Work, Report, Quality Review),
│     OPSS-AudPh:Preparation Status, OPSS-AudPh:Review Status
│
├── Finding[] (children via JOIN [Finding] ON PARENT([AuditProgram]))
│     Resource ID, Name, Description, OPSS-Finding:Priority (High, Medium, Low),
│     OPSS-Finding:Impact, OPSS-Finding:Status, OPSS-Finding:Reportable,
│     OPSS-Finding:Preparer, OPSS-Finding:MgmtOwner,
│     OPSS-Finding:Recommendation, OPSS-Finding:MgmtResp
│
└── SOXIssue[] (children via JOIN [SOXIssue] ON PARENT([AuditProgram]))
      Resource ID, Name, Description, OPSS-Iss:Priority, OPSS-Iss:Impact,
      OPSS-Iss:Status, OPSS-Iss:Due Date, OPSS-Iss:Issue Type,
      OPSS-Iss:Assignee, OPSS-Iss:Resolution Status, OPSS-Iss:Management Response
```

---

## 3. Architecture

Following the proven single Python `@tool` architecture:

```
User: "Generate the audit report PPTX for 'Accounts Receivable - 2018'"
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│  generate_audit_program_summary_pptx (single @tool)      │
│                                                          │
│  • Calls MCP proxy JSON-RPC endpoint:                    │
│    https://generic-openpages-mcp-server.../mcp           │
│  • Query 1: AuditProgram metadata by ID or Name          │
│  • Query 2: Child AuditPhase objects (status & counts)   │
│  • Query 3: Child Finding objects                        │
│  • Query 4: Child SOXIssue objects                       │
│  • Cleans HTML, formats dates, calculates observations   │
│  • Calls fill_audit_program_summary_pptx(data)           │
│  • Returns raw PPTX bytes for download link              │
└──────────────────────────────────────────────────────────┘
        │
        ▼
Agent response: "Here is your Audit Report PPTX — [Download link]"
```

---

## 4. File Layout

```
tools/generate_audit_program_summary_pptx/
├── IMPLEMENTATION_PLAN.md                  ← THIS FILE
├── create_template.py                      ← Copies/generates base template with tokens
├── audit_program_summary_template_v1.pptx  ← Base PPTX template
├── fill_audit_program_summary_pptx.py      ← PPTX XML defragmentation & token replacement logic + CLI
├── generate_audit_program_summary_pptx.py  ← Single @tool calling MCP proxy + fill + returning bytes
├── audit_program_summary_pptx_example.json ← Verified live test data
├── requirements.txt                        ← requests + ibm-watsonx-orchestrate
├── __init__.py                             ← Empty
└── import-all.sh                           ← CLI import script
```

---

## 5. JSON Payload Shape

```json
{
  "audit_name": "Accounts Receivable",
  "audit_year": "2018",
  "full_name": "Accounts Receivable — 2018",
  "audit_type": "Financial Audit",
  "scope": "North America Retail Banking",
  "overall_result": "Fair",
  "owner": "alaudit",
  "status_summary": "Status: Completed · Not Closed · Resource ID: 3420",
  "description": "2018 Accounts Receivable Scheduled Audit — evaluating accounting policies...",
  "sched_start": "Oct 23, 2018",
  "act_start": "Actual: Sep 1, 2018",
  "sched_end": "Mar 14, 2019",
  "act_end": "Actual: Not recorded",
  "est_hours": "400",
  "act_hours": "Actual: Not recorded",
  "audit_period": "Feb 1 – Mar 30, 2019",
  "period_sub": "Audit Year: 2018 · Type: Financial",
  "entity_name": "Accounts Receivable",
  "entity_scope": "Scope: North America Retail Banking",
  "attention_note": "Audit started earlier than scheduled (Sep 1 vs Oct 23)...",
  "total_phases": "20",
  "phases_completed": "14",
  "phases_in_progress": "3",
  "phases_not_started": "3",
  "phases_changes_required": "1",
  "findings_total": "3",
  "findings_open": "3",
  "findings_reportable": "2",
  "findings_high": "1",
  "findings_sig_impact": "1",
  "issues_total": "2",
  "issues_open": "2",
  "issues_overdue": "2",
  "issues_high": "1",
  "issues_eval_in_progress": "2",
  "obs_1_text": "Both issues are overdue...",
  "obs_2_text": "FIND_0126 (Incorrect journal entries, High priority)...",
  "obs_3_text": "Audit is marked Completed but all Report and Quality Review phases are Not Started...",
  "obs_4_text": "Risk assessment review (01-06) has Changes Required status...",
  "obs_5_text": "10 of 11 preparation phases fully completed...",
  "rec_1": "Escalate both overdue issues and assign clear remediation owners and deadlines.",
  "rec_2": "Assign management owner and recommendation to FIND_0126 immediately.",
  "rec_3": "Resolve the risk assessment review (01-06) before starting report phases.",
  "rec_4": "Complete field work (02-01, 02-02, 02-03) and begin the report phase.",
  "rec_5": "Progress through Quality Review phases to achieve formal audit closure.",
  "phases": [...],
  "findings": [...],
  "issues": [...]
}
```

---

## 6. Slide-by-Slide Placeholder Strategy

1. **Slide 1 (Cover)**: `{{AUDIT_NAME}}`, `{{AUDIT_YEAR}}`, `{{AUDIT_TYPE}}`, `{{SCOPE}}`, `{{OVERALL_RESULT}}`, `{{OWNER}}`
2. **Slide 2 (Overview)**: `{{FULL_NAME}}`, `{{OVERALL_RESULT}}`, `{{STATUS_SUMMARY}}`, `{{DESCRIPTION}}`, `{{SCHED_START}}`, `{{ACT_START}}`, `{{SCHED_END}}`, `{{ACT_END}}`, `{{EST_HOURS}}`, `{{ACT_HOURS}}`, `{{AUDIT_PERIOD}}`, `{{PERIOD_SUB}}`, `{{ENTITY_NAME}}`, `{{ENTITY_SCOPE}}`, `{{ATTENTION_NOTE}}`
3. **Slide 3 (Phases)**: `{{PHASES_HEADER}}`, `{{PHASES_COMPLETED}}`, `{{PHASES_IN_PROGRESS}}`, `{{PHASES_NOT_STARTED}}`, `{{PHASES_CHANGES_REQUIRED}}`, and dynamic phase box text.
4. **Slide 4 (Findings)**: `{{FINDINGS_TOTAL_HEADER}}`, `{{FINDINGS_OPEN}}`, `{{FINDINGS_REPORTABLE}}`, `{{FINDINGS_HIGH}}`, `{{FINDINGS_SIG_IMPACT}}`, and finding card tokens.
5. **Slide 5 (Issues)**: `{{ISSUES_TOTAL_HEADER}}`, `{{ISSUES_OPEN}}`, `{{ISSUES_OVERDUE}}`, `{{ISSUES_HIGH}}`, `{{ISSUES_EVAL_IN_PROGRESS}}`, and issue card tokens.
6. **Slide 6 (Conclusion)**: `{{TOTAL_PHASES}}`, `{{FINDINGS_OPEN}}`, `{{ISSUES_OPEN}}`, `{{OBS_1_TEXT}}`..`{{OBS_5_TEXT}}`, `{{OVERALL_RESULT}}`, `{{STATUS_SUMMARY}}`, `{{REC_1}}`..`{{REC_5}}`

---

## 7. Key Decisions

| Decision | Rationale |
|---|---|
| Single `@tool` architecture | Avoids flow complexity and Pydantic schema bugs in WXO agent runner |
| OOXML zip manipulation + regex run defragmentation | Exact preservation of high-fidelity template layout, shapes, colors, fonts |
| Dynamic Observation Synthesis | Generates intelligent audit observations based on data anomalies (overdue issues, missing mgmt responses, blocked phases) |
| Standardized MCP endpoint | Uses `https://generic-openpages-mcp-server.2c20hyggoq5p.us-south.codeengine.appdomain.cloud/mcp` |
