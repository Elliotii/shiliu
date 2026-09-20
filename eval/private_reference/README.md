# Private V3 Silver reference material

This directory keeps schemas in Git. Actual Silver Reference, call audits,
disagreements, manifests, and candidate lists are ignored by Git.

Before the first full real Discovery run:

1. Freeze the target Corpus Snapshot.
2. Run the isolated Silver generator with Evaluator A, B, and C.
3. Freeze the resulting taxonomy, approximately 40 reviewed rows,
   disagreements, and per-call audit using `eval/freeze_silver_reference.py`.
4. Keep the generated manifest. Existing versions cannot be overwritten.

Silver files use JSON syntax where the filename is YAML because JSON is valid
YAML and can be validated without adding a dependency. Silver Agreement must
never be described as true accuracy.
