# P7A Mechanical Validation Guide

Run:

`.venv/bin/python scripts/validate_p7a_gold_packet.py`

The validator checks upstream hashes, the 14/10 and 7/5 assignment, exact Locked
Query records, placeholder-aware P6 field completeness, neutral navigation,
Transcript Identity hashes/counts, role separation, packet hashes, and Frozen
completion isolation. It does not validate semantic Gold because P7A creates no
Gold.
