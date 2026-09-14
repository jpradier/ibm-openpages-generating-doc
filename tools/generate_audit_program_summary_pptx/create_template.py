"""
create_template.py — build audit_program_summary_template_v1.pptx
from input/AR-2018-Audit-Report.pptx by replacing instance-specific values with tokens.
"""
import io
import os
import re
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORIGINAL = os.path.join(
    os.path.dirname(os.path.dirname(_HERE)),
    "input",
    "AR-2018-Audit-Report.pptx",
)
_OUTPUT = os.path.join(_HERE, "audit_program_summary_template_v1.pptx")


def _patch_slide1(xml: str) -> str:
    # Title / cover
    xml = xml.replace("<a:t>Accounts Receivable</a:t>", "<a:t>{{AUDIT_NAME}}</a:t>")
    xml = xml.replace("<a:t>2018</a:t>", "<a:t>{{AUDIT_YEAR}}</a:t>")
    xml = xml.replace("<a:t>Financial Audit</a:t>", "<a:t>{{AUDIT_TYPE}}</a:t>")
    xml = xml.replace("<a:t>North America Retail Banking</a:t>", "<a:t>{{SCOPE}}</a:t>")
    xml = xml.replace("<a:t>Fair</a:t>", "<a:t>{{OVERALL_RESULT}}</a:t>")
    xml = xml.replace("<a:t>alaudit</a:t>", "<a:t>{{OWNER}}</a:t>")
    return xml


def _patch_slide2(xml: str) -> str:
    # Overview
    xml = xml.replace("<a:t>Accounts Receivable — 2018</a:t>", "<a:t>{{FULL_NAME}}</a:t>")
    xml = xml.replace("<a:t>Fair</a:t>", "<a:t>{{OVERALL_RESULT}}</a:t>")
    xml = xml.replace(
        "<a:t>Status: Completed · Not Closed · Resource ID: 3420</a:t>",
        "<a:t>{{STATUS_SUMMARY}}</a:t>",
    )
    xml = re.sub(
        r"<a:t>2018 Accounts Receivable Scheduled Audit.*?</a:t>",
        "<a:t>{{DESCRIPTION}}</a:t>",
        xml,
    )
    xml = xml.replace("<a:t>Oct 23, 2018</a:t>", "<a:t>{{SCHED_START}}</a:t>")
    xml = xml.replace("<a:t>Actual: Sep 1, 2018</a:t>", "<a:t>{{ACT_START}}</a:t>")
    xml = xml.replace("<a:t>Mar 14, 2019</a:t>", "<a:t>{{SCHED_END}}</a:t>")
    xml = xml.replace("<a:t>Actual: Not recorded</a:t>", "<a:t>{{ACT_END}}</a:t>", 1)
    xml = xml.replace("<a:t>400</a:t>", "<a:t>{{EST_HOURS}}</a:t>")
    xml = xml.replace("<a:t>Actual: Not recorded</a:t>", "<a:t>{{ACT_HOURS}}</a:t>", 1)
    xml = xml.replace("<a:t>Feb 1 – Mar 30, 2019</a:t>", "<a:t>{{AUDIT_PERIOD}}</a:t>")
    xml = xml.replace("<a:t>Audit Year: 2018 · Type: Financial</a:t>", "<a:t>{{PERIOD_SUB}}</a:t>")
    xml = xml.replace("<a:t>Accounts Receivable</a:t>", "<a:t>{{ENTITY_NAME}}</a:t>")
    xml = xml.replace("<a:t>Scope: North America Retail Banking</a:t>", "<a:t>{{ENTITY_SCOPE}}</a:t>")
    xml = re.sub(
        r"<a:t>Audit started earlier than scheduled.*?</a:t>",
        "<a:t>{{ATTENTION_NOTE}}</a:t>",
        xml,
    )
    return xml


def _patch_slide3(xml: str) -> str:
    # Phases KPI numbers
    xml = re.sub(
        r"(<a:t>)AUDIT SECTIONS — \d+ PHASES(</a:t>)",
        r"\g<1>{{PHASES_HEADER}}\g<2>",
        xml,
    )
    xml = re.sub(r"(<a:t>)14(</a:t>)", r"\g<1>{{PHASES_COMPLETED}}\g<2>", xml)
    # The others: 3 in progress, 3 not started, 1 changes required
    xml = re.sub(r"(<a:t>)3(</a:t>)", r"\g<1>{{PHASES_IN_PROGRESS}}\g<2>", xml, count=1)
    xml = re.sub(r"(<a:t>)3(</a:t>)", r"\g<1>{{PHASES_NOT_STARTED}}\g<2>", xml, count=1)
    xml = re.sub(r"(<a:t>)1(</a:t>)", r"\g<1>{{PHASES_CHANGES_REQUIRED}}\g<2>", xml, count=1)
    return xml


def _patch_slide4(xml: str) -> str:
    # Findings
    xml = re.sub(
        r"(<a:t>)AUDIT FINDINGS — \d+ TOTAL(</a:t>)",
        r"\g<1>{{FINDINGS_TOTAL_HEADER}}\g<2>",
        xml,
    )
    xml = xml.replace("<a:t>All Findings Open</a:t>", "<a:t>{{FINDINGS_SUBTITLE}}</a:t>")
    xml = re.sub(r"(<a:t>)3(</a:t>)", r"\g<1>{{FINDINGS_OPEN}}\g<2>", xml, count=1)
    xml = re.sub(r"(<a:t>)2(</a:t>)", r"\g<1>{{FINDINGS_REPORTABLE}}\g<2>", xml, count=1)
    xml = re.sub(r"(<a:t>)1(</a:t>)", r"\g<1>{{FINDINGS_HIGH}}\g<2>", xml, count=1)
    xml = re.sub(r"(<a:t>)1(</a:t>)", r"\g<1>{{FINDINGS_SIG_IMPACT}}\g<2>", xml, count=1)

    # Finding 1 card
    xml = xml.replace("<a:t>HIGH</a:t>", "<a:t>{{F1_PRIO_BADGE}}</a:t>")
    xml = xml.replace("<a:t>Inconsequential</a:t>", "<a:t>{{F1_IMPACT_BADGE}}</a:t>")
    xml = re.sub(r"<a:t>FIND_0126 · Preparer: ivyaudit</a:t>", "<a:t>{{F1_HEADER}}</a:t>", xml)
    xml = xml.replace("<a:t>Incorrect journal entries</a:t>", "<a:t>{{F1_DESC}}</a:t>")
    xml = re.sub(r"(<a:t>)Open(</a:t>)", r"\g<1>{{F1_STATUS}}\g<2>", xml, count=1)
    xml = re.sub(r"(<a:t>)Yes(</a:t>)", r"\g<1>{{F1_REPORTABLE}}\g<2>", xml, count=1)
    xml = xml.replace("<a:t>Not assigned</a:t>", "<a:t>{{F1_OWNER}}</a:t>")
    xml = xml.replace("<a:t>Not recorded</a:t>", "<a:t>{{F1_REC}}</a:t>")

    # Finding 2 card
    xml = xml.replace("<a:t>MED</a:t>", "<a:t>{{F2_PRIO_BADGE}}</a:t>")
    xml = xml.replace("<a:t>Significant</a:t>", "<a:t>{{F2_IMPACT_BADGE}}</a:t>")
    xml = re.sub(r"<a:t>FIND_0124 · Preparer: georgeaudit</a:t>", "<a:t>{{F2_HEADER}}</a:t>", xml)
    xml = re.sub(r"<a:t>Cycle diagrams do not exist.*?</a:t>", "<a:t>{{F2_DESC}}</a:t>", xml)
    xml = re.sub(r"<a:t>Recommendation: Cycle diagrams needed.*?</a:t>", "<a:t>{{F2_REC}}</a:t>", xml)
    xml = re.sub(r"(<a:t>)Open(</a:t>)", r"\g<1>{{F2_STATUS}}\g<2>", xml, count=1)
    xml = re.sub(r"(<a:t>)Yes(</a:t>)", r"\g<1>{{F2_REPORTABLE}}\g<2>", xml, count=1)
    xml = xml.replace("<a:t>Agree, will create Action Plan</a:t>", "<a:t>{{F2_RESP}}</a:t>")

    # Finding 3 card
    xml = xml.replace("<a:t>LOW</a:t>", "<a:t>{{F3_PRIO_BADGE}}</a:t>")
    xml = xml.replace("<a:t>More Than Incons.</a:t>", "<a:t>{{F3_IMPACT_BADGE}}</a:t>")
    xml = re.sub(r"<a:t>FIND_0097 · Preparer: georgeaudit</a:t>", "<a:t>{{F3_HEADER}}</a:t>", xml)
    xml = re.sub(r"<a:t>Training of new managers.*?</a:t>", "<a:t>{{F3_DESC}}</a:t>", xml)
    xml = re.sub(r"<a:t>Recommendation: Management should provide.*?</a:t>", "<a:t>{{F3_REC}}</a:t>", xml)
    xml = re.sub(r"(<a:t>)Open(</a:t>)", r"\g<1>{{F3_STATUS}}\g<2>", xml, count=1)
    xml = re.sub(r"(<a:t>)No(</a:t>)", r"\g<1>{{F3_REPORTABLE}}\g<2>", xml, count=1)
    xml = xml.replace("<a:t>processowner</a:t>", "<a:t>{{F3_OWNER}}</a:t>")
    return xml


def _patch_slide5(xml: str) -> str:
    # Issues
    xml = re.sub(
        r"(<a:t>)ISSUES — \d+ TOTAL(</a:t>)",
        r"\g<1>{{ISSUES_TOTAL_HEADER}}\g<2>",
        xml,
    )
    xml = xml.replace("<a:t>Both Issues Open and Overdue</a:t>", "<a:t>{{ISSUES_SUBTITLE}}</a:t>")
    xml = re.sub(r"(<a:t>)2(</a:t>)", r"\g<1>{{ISSUES_OPEN}}\g<2>", xml, count=1)
    xml = re.sub(r"(<a:t>)2(</a:t>)", r"\g<1>{{ISSUES_OVERDUE}}\g<2>", xml, count=1)
    xml = re.sub(r"(<a:t>)1(</a:t>)", r"\g<1>{{ISSUES_HIGH}}\g<2>", xml, count=1)
    xml = re.sub(r"(<a:t>)2(</a:t>)", r"\g<1>{{ISSUES_EVAL_IN_PROGRESS}}\g<2>", xml, count=1)

    # Issue 1 card
    xml = re.sub(r"(<a:t>)HIGH PRIORITY(</a:t>)", r"\g<1>{{I1_PRIO_BADGE}}\g<2>", xml, count=1)
    xml = re.sub(r"(<a:t>)Open(</a:t>)", r"\g<1>{{I1_STATUS}}\g<2>", xml, count=1)
    xml = xml.replace("<a:t>OVERDUE — Due Nov 30, 2018</a:t>", "<a:t>{{I1_DUE_BADGE}}</a:t>")
    xml = re.sub(
        r"<a:t>ISS001 · Type: Control Activity Missing · Impact: Significant · Assignee: georgeaudit</a:t>",
        "<a:t>{{I1_HEADER}}</a:t>",
        xml,
    )
    xml = xml.replace("<a:t>Certification requirements lacking</a:t>", "<a:t>{{I1_DESC}}</a:t>")
    xml = re.sub(r"(<a:t>)Evaluation in Progress(</a:t>)", r"\g<1>{{I1_RESOLUTION}}\g<2>", xml, count=1)
    xml = xml.replace("<a:t>~6+ years</a:t>", "<a:t>{{I1_OVERDUE_BY}}</a:t>")

    # Issue 2 card
    xml = re.sub(r"(<a:t>)MEDIUM PRIORITY(</a:t>)", r"\g<1>{{I2_PRIO_BADGE}}\g<2>", xml, count=1)
    xml = re.sub(r"(<a:t>)Open(</a:t>)", r"\g<1>{{I2_STATUS}}\g<2>", xml, count=1)
    xml = xml.replace("<a:t>OVERDUE — Due Nov 7, 2014</a:t>", "<a:t>{{I2_DUE_BADGE}}</a:t>")
    xml = re.sub(
        r"<a:t>ISS-NA-CB-ERM-003 · Type: Other · Impact: Inconsequential · Assignee: itdirector2</a:t>",
        "<a:t>{{I2_HEADER}}</a:t>",
        xml,
    )
    xml = xml.replace(
        "<a:t>Implement company-wide project to enhance corporate governance</a:t>",
        "<a:t>{{I2_DESC}}</a:t>",
    )
    xml = xml.replace(
        "<a:t>Complete revision of Policies, Rules and Procedures within the company</a:t>",
        "<a:t>{{I2_SUBDESC}}</a:t>",
    )
    xml = re.sub(r"(<a:t>)Evaluation in Progress(</a:t>)", r"\g<1>{{I2_RESOLUTION}}\g<2>", xml, count=1)
    xml = xml.replace("<a:t>~10+ years</a:t>", "<a:t>{{I2_OVERDUE_BY}}</a:t>")
    return xml


def _patch_slide6(xml: str) -> str:
    # Conclusion & Recommendations
    xml = re.sub(r"(<a:t>)20(</a:t>)", r"\g<1>{{TOTAL_PHASES}}\g<2>", xml, count=1)
    xml = re.sub(r"(<a:t>)3(</a:t>)", r"\g<1>{{FINDINGS_OPEN}}\g<2>", xml, count=1)
    xml = re.sub(r"(<a:t>)2(</a:t>)", r"\g<1>{{ISSUES_OPEN}}\g<2>", xml, count=1)

    # Observations
    xml = re.sub(
        r"<a:t>Both issues are overdue.*?Immediate escalation required\.</a:t>",
        "<a:t>{{OBS_1_TEXT}}</a:t>",
        xml,
    )
    xml = re.sub(
        r"<a:t>FIND_0126 \(Incorrect journal entries.*?</a:t>",
        "<a:t>{{OBS_2_TEXT}}</a:t>",
        xml,
    )
    xml = re.sub(
        r"<a:t>Audit is marked Completed but all Report and Quality Review.*?</a:t>",
        "<a:t>{{OBS_3_TEXT}}</a:t>",
        xml,
    )
    xml = re.sub(
        r"<a:t>Risk assessment review \(01-06\) has Changes Required status.*?</a:t>",
        "<a:t>{{OBS_4_TEXT}}</a:t>",
        xml,
    )
    xml = re.sub(
        r"<a:t>10 of 11 preparation phases fully completed.*?</a:t>",
        "<a:t>{{OBS_5_TEXT}}</a:t>",
        xml,
    )

    xml = xml.replace("<a:t>Fair</a:t>", "<a:t>{{OVERALL_RESULT}}</a:t>")
    xml = xml.replace("<a:t>Status: Completed · Not Closed</a:t>", "<a:t>{{RESULT_STATUS_SUB}}</a:t>")

    # Recommended actions
    xml = re.sub(r"<a:t>Escalate both overdue issues.*?</a:t>", "<a:t>{{REC_1}}</a:t>", xml)
    xml = re.sub(r"<a:t>Assign management owner and recommendation to FIND_0126.*?</a:t>", "<a:t>{{REC_2}}</a:t>", xml)
    xml = re.sub(r"<a:t>Resolve the risk assessment review \(01-06\).*?</a:t>", "<a:t>{{REC_3}}</a:t>", xml)
    xml = re.sub(r"<a:t>Complete field work.*?</a:t>", "<a:t>{{REC_4}}</a:t>", xml)
    xml = re.sub(r"<a:t>Progress through Quality Review.*?</a:t>", "<a:t>{{REC_5}}</a:t>", xml)
    return xml


SLIDE_PATCHES = {
    "ppt/slides/slide1.xml": _patch_slide1,
    "ppt/slides/slide2.xml": _patch_slide2,
    "ppt/slides/slide3.xml": _patch_slide3,
    "ppt/slides/slide4.xml": _patch_slide4,
    "ppt/slides/slide5.xml": _patch_slide5,
    "ppt/slides/slide6.xml": _patch_slide6,
}


def build_template() -> None:
    src = zipfile.ZipFile(_ORIGINAL, "r")
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)

            if item.filename in SLIDE_PATCHES:
                xml = data.decode("utf-8")
                xml = SLIDE_PATCHES[item.filename](xml)
                data = xml.encode("utf-8")

            dst.writestr(item, data)

    src.close()

    with open(_OUTPUT, "wb") as f:
        f.write(buf.getvalue())

    print(f"✅  Template generated: {_OUTPUT}")
    _verify(_OUTPUT)


def _verify(path: str) -> None:
    zf = zipfile.ZipFile(path)
    for i in range(1, 7):
        xml = zf.read(f"ppt/slides/slide{i}.xml").decode("utf-8")
        tokens = re.findall(r"\{\{[A-Z_0-9]+\}\}", xml)
        print(f"  Slide {i}: {len(tokens)} tokens -> {sorted(set(tokens))}")
    zf.close()


if __name__ == "__main__":
    build_template()
