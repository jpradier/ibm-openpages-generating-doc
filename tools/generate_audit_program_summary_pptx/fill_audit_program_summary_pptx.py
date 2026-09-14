"""
fill_audit_program_summary_pptx.py
===================================
Core OOXML fill logic for the Audit Program (Mission) summary PPTX generator.

Usage (CLI):
    python3 fill_audit_program_summary_pptx.py --json audit_program_summary_pptx_example.json --out /tmp/report.pptx
"""
import argparse
import io
import json
import os
import re
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(_HERE, "audit_program_summary_template_v1.pptx")


def _esc(text: str) -> str:
    """Escape XML special characters for use inside element content (<a:t>)."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _merge_runs(xml: str) -> str:
    """
    Defragment tokens split across <a:r> elements by PowerPoint.
    """
    pattern = re.compile(
        r'(<a:t>)(.*?)(</a:t></a:r>)'
        r'(<a:r>(?:<a:rPr[^>]*/>|<a:rPr[^>]*>.*?</a:rPr>)\s*<a:t>)'
        r'(.*?)'
        r'(</a:t></a:r>)',
        re.DOTALL,
    )
    for _ in range(20):
        merged = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{m.group(5)}{m.group(6)}', xml)
        if merged == xml:
            break
        xml = merged
    return xml


def fill_audit_program_summary_pptx(data: dict) -> bytes:
    """
    Fill the 6-slide audit summary PPTX template with data dictionary values.

    Args:
        data: dict containing scalar values for tokens.

    Returns:
        bytes: raw .pptx file content.
    """
    # Map all dictionary keys to uppercase {{TOKEN}} placeholders
    scalars = {}
    for k, v in data.items():
        if isinstance(v, (str, int, float)):
            token = f"{{{{{k.upper()}}}}}"
            scalars[token] = str(v)

    src = zipfile.ZipFile(TEMPLATE_PATH, "r")
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            raw = src.read(item.filename)

            if item.filename.startswith("ppt/slides/slide") and item.filename.endswith(".xml"):
                xml = raw.decode("utf-8")
                xml = _merge_runs(xml)

                for token, value in scalars.items():
                    if token in xml:
                        xml = xml.replace(token, _esc(value))

                raw = xml.encode("utf-8")

            dst.writestr(item, raw)

    src.close()
    buf.seek(0)
    return buf.read()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fill audit summary PPTX template.")
    parser.add_argument("--json", required=True, help="Path to input JSON file")
    parser.add_argument("--out", required=True, help="Output .pptx path")
    args = parser.parse_args()

    with open(args.json, "r", encoding="utf-8") as f:
        payload = json.load(f)

    pptx_bytes = fill_audit_program_summary_pptx(payload)

    with open(args.out, "wb") as f:
        f.write(pptx_bytes)

    print(f"✅  Written: {args.out}")

    # Verify
    zf = zipfile.ZipFile(args.out)
    for i in range(1, 7):
        xml = zf.read(f"ppt/slides/slide{i}.xml").decode("utf-8")
        unfilled = re.findall(r"\{\{[A-Z_0-9]+\}\}", xml)
        print(f"  Slide {i} unfilled: {sorted(set(unfilled))}")
    zf.close()
