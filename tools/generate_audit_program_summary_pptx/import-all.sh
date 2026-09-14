#!/usr/bin/env bash
# import-all.sh
# Imports the generate_audit_program_summary_pptx tool into watsonx Orchestrate.
#
# Usage:
#   cd tools/generate_audit_program_summary_pptx
#   ./import-all.sh
#
# Prerequisites:
#   - orchestrate env activate <your-env>

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

echo "==> Importing generate_audit_program_summary_pptx tool..."
orchestrate tools import -k python \
  -f "${SCRIPT_DIR}/generate_audit_program_summary_pptx.py" \
  -r "${SCRIPT_DIR}/requirements.txt" \
  -p "${SCRIPT_DIR}"

echo ""
echo "✅  Import complete."
echo ""
echo "    Verify with:"
echo "      orchestrate tools list | grep audit_program_summary"
