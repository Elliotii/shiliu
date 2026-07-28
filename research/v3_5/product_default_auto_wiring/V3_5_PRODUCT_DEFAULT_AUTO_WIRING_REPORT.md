# V3.5 Stage 3R-QC-W — Product Default Auto Wiring Report

## Outcome

**Stage 3R-QC-W Complete.** The Product Search default is now Auto on both the main web search entry and `POST /api/search` when `mode` is omitted. The retrieval algorithms and Auto Router remain unchanged.

The product wiring version is `v3-product-search-default-auto-v1`. It means only that the frozen V3 retrieval is now entered through Auto by default; it does not identify a new retrieval algorithm, router, or hybrid version.

## Changes

Production wiring changed in:

- `src/shiliu/templates/search.html`: Auto is the selected initial mode.
- `src/shiliu/static/search.js`: missing/restored/reset browser mode defaults to Auto; the request payload continues to send the selected mode explicitly, so the first request sends `mode: auto`.
- `src/shiliu/retrieval/product_search.py`: Product API omission resolves to Auto and records Product-request provenance in the existing linked presentation trace.
- `src/shiliu/eval_v3_5/stage3a_inputs.py`: the historical Stage 3A replay now supplies `mode="lexical"` explicitly so it retains its frozen semantics.

The UI retains Auto, Lexical, Dense, and Hybrid. No result UI, filters, scope, Top-K, or fallback behavior was changed.

## Default and Override Contract

| Request | Resolved mode | Router invoked | Effective mode |
| --- | --- | --- | --- |
| UI first request | `auto` | yes | existing router decision |
| Product API omits mode | `auto` | yes | existing router decision |
| Explicit `lexical` | `lexical` | no | `lexical` |
| Explicit `dense` | `dense` | no | `dense` |
| Explicit `hybrid` | `hybrid` | no | `hybrid` |
| Explicit `auto` | `auto` | yes | existing router decision |

For Auto requests, `router_decision` is the existing planned mode and `effective_mode` is the executed mode. The tested exact entity `MCP` routes to lexical with `embedding_invoked=false`; the tested semantic question routes to hybrid with `embedding_invoked=true`. Router decision and effective mode matched in the normal Auto paths tested.

## Trace Contract

The existing linked Product Presentation trace now persists the Product request provenance rather than introducing a parallel trace system:

- `requested_mode` (null when Product API default was applied)
- `default_applied` and `configured_default_mode`
- `router_invoked`, `router_version`, `router_decision`, and `router_reason_codes`
- `effective_mode` and `embedding_invoked`
- `product_default_wiring_version`

The Product API response exposes the same fields in its existing `plan` object. Existing raw trace fields (`planned_mode`, `executed_mode`, `routing_reason`) remain intact.

## Compatibility

The internal-call audit found one active historical replay that omitted mode: the Stage 3A frozen projection. It now declares `mode="lexical"` explicitly. Explicit callers were retained. No evidence of a released external client was found.

Historical frozen Auto and Stage 3R-QC records retain their lexical pre-change assertions as records of the validation precondition; their assets were not edited.

## Regression

- Targeted retrieval, API, UI, lifecycle, explicit-mode, trace, frozen-history, and isolation regression: **262 passed**.
- Full repository regression: **923 passed**.
- Runtime errors in the validated test executions: **0**.

The test suite exercised scope/filter forwarding and existing product result schemas. Existing lifecycle tests cover lazy provider construction/reuse; the new Auto route assertions verify lexical routes do not invoke embedding and semantic Auto routes do invoke the hybrid path.

## Boundaries and Next Step

No Router rules, retrieval algorithms, index, Stress Track A, Product Query Set, F1A, or F1B were changed or run. The known `SFT completion-only NEFTune` router boundary was not modified.

This wiring is accepted and is ready for the separately authorized **Stress Track A Auto Product View Refresh**. The current session can close.
