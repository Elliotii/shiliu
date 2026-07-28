# Product Search Call Chain — Pre-change Audit

Audit date: 2026-07-25

```text
Search page template (`src/shiliu/templates/search.html`)
  -> browser state and JSON payload (`src/shiliu/static/search.js`)
  -> POST /api/search (`src/shiliu/web.py`)
  -> ProductSearchRequest / ProductSearchService (`src/shiliu/retrieval/product_search.py`)
  -> SearchOrchestrator.search_raw (`src/shiliu/retrieval/orchestrator.py`)
  -> SearchPlanner.plan / Auto Router (`src/shiliu/retrieval/planner.py`)
  -> planned retrieval mode -> executed retrieval mode
```

## Resolved current locations

| Boundary | Location | Pre-change behavior |
| --- | --- | --- |
| Initial selected UI mode | `search.html` mode `<select>` first option | `lexical` |
| Browser fallback/restoration/reset default | `search.js` | `lexical` |
| Browser request payload | `search.js: requestPayload` | always sends its selected `mode` |
| Product API schema | `ProductSearchRequest.mode` | omitted `mode` resolves to `lexical` |
| Product service | `ProductSearchService.search_with_raw` | forwards the resolved mode as `SearchRequest.mode` |
| Raw API schema | `SearchRequest.mode` | `lexical`; outside this product-default change |
| Auto Router | `SearchPlanner.plan` | `auto` routes exact entities to lexical, otherwise hybrid |

## Existing trace surface

`retrieval_search_traces` already records a resolved `requested_mode`, `planned_mode`, `executed_mode`, and one `routing_reason`. The linked presentation trace records product grouping. It does not distinguish a Product API omission from an explicit mode, nor persist a product-default wiring version, `default_applied`, a router invocation flag, or an embedding invocation flag.

The wiring change will preserve the router and retrieval behavior, retain the raw trace, and add the missing product-request provenance to the existing linked presentation trace and Product API plan response.
