# Reviewer Output Repair v2

Version: `v3.5-review-output-repair-prompt-v2`.

Repair formatting/schema/reference errors in the original output using only the original output, listed validation errors, and the original case packet. Preserve semantic intent. Do not add outside knowledge, system predictions, Gold, adjudication, or another review. Return only corrected `v3.5-annotation-review-v2` JSON. This repair is permitted once; a second failure is terminal `invalid`.

