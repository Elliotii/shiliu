# V3 Model Selection Harness

This directory contains the isolated Qwen/E5 bake-off harness. It reads the
formal `retrieval_units` table through SQLite `mode=ro` and writes candidate
vectors only to a separate experimental database outside the repository.

Fixed Qwen query instruction:

```text
Given a Chinese or English AI and software engineering knowledge retrieval query, retrieve the most relevant evidence passages.
```

Candidate output is fixed to 512 normalized float32 dimensions. Video units
reuse the current field-priority projection and 480-token content budget using
the candidate tokenizer. Transcript Chunk text, unit identity, timestamp bounds
and source provenance remain unchanged.

The Qwen adapter accepts only an absolute local directory, requires both
`HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, and passes
`local_files_only=True`. It must never be initialized before the manual download
checkpoint is satisfied.
