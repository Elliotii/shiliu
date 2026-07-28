# AI Summary Diagnostic

```json
{
  "frozen_video_unit_section_counts": {
    "Title": 143,
    "Uploader": 143,
    "Summary Conclusion": 102,
    "Summary Key Points": 102,
    "Summary Detailed Notes": 102,
    "Summary Entities": 94,
    "Summary Chapters (video-level only)": 101,
    "Cleaned Transcript (video-level only)": 84,
    "Favorite Folders": 143,
    "Description": 127,
    "User Notes": 1
  },
  "fields": {
    "title": "indexed",
    "description": "indexed",
    "ai_conclusion": "indexed when present",
    "ai_key_points": "indexed when present",
    "ai_full_summary": "Summary Detailed Notes indexed when present",
    "ai_chapters": "indexed in lexical video unit; excluded from dense projection by field quota policy"
  },
  "video_unit_only_hit_count": 88,
  "relevant_video_unit_only_hits": 44,
  "not_relevant_video_unit_only_hits": 36,
  "examples": [
    {
      "query_id": "Q01",
      "mode": "hybrid",
      "video_id": 119,
      "human_label": "N",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q02",
      "mode": "lexical",
      "video_id": 65,
      "human_label": "R_evidence",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q02",
      "mode": "lexical",
      "video_id": 142,
      "human_label": "R_title",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q02",
      "mode": "lexical",
      "video_id": 71,
      "human_label": "R_evidence",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q02",
      "mode": "lexical",
      "video_id": 139,
      "human_label": "N",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q02",
      "mode": "lexical",
      "video_id": 3,
      "human_label": "R_evidence",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q02",
      "mode": "dense",
      "video_id": 65,
      "human_label": "R_evidence",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q02",
      "mode": "hybrid",
      "video_id": 65,
      "human_label": "R_evidence",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q02",
      "mode": "hybrid",
      "video_id": 142,
      "human_label": "R_title",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q02",
      "mode": "hybrid",
      "video_id": 139,
      "human_label": "N",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q02",
      "mode": "hybrid",
      "video_id": 50,
      "human_label": "N",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q03",
      "mode": "lexical",
      "video_id": 40,
      "human_label": "R_evidence",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q03",
      "mode": "lexical",
      "video_id": 39,
      "human_label": "R_evidence",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q03",
      "mode": "dense",
      "video_id": 137,
      "human_label": "N",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q03",
      "mode": "hybrid",
      "video_id": 137,
      "human_label": "N",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q04",
      "mode": "lexical",
      "video_id": 117,
      "human_label": "R_evidence",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q04",
      "mode": "lexical",
      "video_id": 115,
      "human_label": "R_evidence",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q04",
      "mode": "lexical",
      "video_id": 30,
      "human_label": "N",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q04",
      "mode": "lexical",
      "video_id": 32,
      "human_label": "N",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q04",
      "mode": "lexical",
      "video_id": 130,
      "human_label": "N",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q04",
      "mode": "hybrid",
      "video_id": 30,
      "human_label": "N",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q04",
      "mode": "hybrid",
      "video_id": 130,
      "human_label": "N",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q05",
      "mode": "lexical",
      "video_id": 68,
      "human_label": "R_evidence",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q07",
      "mode": "dense",
      "video_id": 137,
      "human_label": "R_title",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q07",
      "mode": "dense",
      "video_id": 108,
      "human_label": "N",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q07",
      "mode": "dense",
      "video_id": 45,
      "human_label": "N",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q07",
      "mode": "dense",
      "video_id": 44,
      "human_label": "U_title",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q07",
      "mode": "dense",
      "video_id": 112,
      "human_label": "U_title",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q07",
      "mode": "hybrid",
      "video_id": 137,
      "human_label": "R_title",
      "video_unit_only_in_raw_top50": true
    },
    {
      "query_id": "Q07",
      "mode": "hybrid",
      "video_id": 108,
      "human_label": "N",
      "video_unit_only_in_raw_top50": true
    }
  ],
  "authority_rule": "AI Summary supports discovery/navigation only; raw subtitle/ASR remains evidence, timing, and citation authority."
}
```
