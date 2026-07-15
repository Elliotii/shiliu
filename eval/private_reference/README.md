# Private V3 reference material

This directory keeps schemas and editable templates in Git. Actual reference,
Gold Set, manifest, and candidate-list files are ignored by Git.

Before the first full real Discovery run:

1. Copy and complete `reference_taxonomy.template.yaml` using human judgment.
2. Copy and complete `gold_eval_set_40.template.jsonl` with exactly 40 reviewed items.
3. Run `python eval/freeze_reference.py --taxonomy <draft> --gold <draft> --version v1`.
4. Keep the generated manifest. Existing versions cannot be overwritten.

The reference taxonomy template uses JSON syntax because JSON is valid YAML and
can be validated without adding a YAML dependency.
