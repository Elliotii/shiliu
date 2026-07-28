# V3.5 Frozen Auto Smoke Human Review Packet

## Summary

- Auto Q0/Q1/Q2 Recall: 9/9, 8/9, 9/9
- Router distributions: {"q0": {"lexical": 0, "hybrid": 10, "dense": 0, "other": 0}, "q1": {"lexical": 1, "hybrid": 9, "dense": 0, "other": 0}, "q2": {"lexical": 0, "hybrid": 29, "dense": 0, "other": 0}, "exact_entity": {"lexical": 3, "hybrid": 0, "dense": 0, "other": 0}}
- Router misses: 1
- Exact-entity regressions: 0
- Release Gate: passed

## Exceptional Queries

### V2C_C0C_958161474678bd3f:q1

- Query: SFT completion-only NEFTune
- Query view: q1
- Router decision / effective mode: lexical / lexical
- Auto hit / rank: False / None
- Lexical control: False
- Hybrid control: True
- Embedding invoked: False
- Latency: 1.3773331884294748 ms
- Failure classification: None
