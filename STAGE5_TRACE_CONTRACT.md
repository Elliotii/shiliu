# Stage 5 End-to-End Trace Contract

Version: `v3.5-stage5-root-trace-v1`

Every request has one Root Trace with `trace_id`, `request_id`, `query_hash`,
timestamps, total latency, final status, and ordered stage spans:

1. `retrieval`
2. `candidate_builder`
3. `fine_selector`
4. `mechanical_gate`
5. `semantic_judge_or_bypass`

Every span records component version, input/output hashes, status, timestamps,
latency, retry count, error type, and Root Trace parent identity.

The Judge span additionally records provider, model, temperature, Prompt and
Policy versions, parse status, raw-response hash, and Evidence IDs used. Raw
responses, secrets, cookies, private chain of thought, and credentials are not
persisted.

Traces are atomically persisted as JSON in the existing application logs tree:
`<logs_dir>/stage5_traces/<trace_id>.json`.

