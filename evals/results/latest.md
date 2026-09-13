# Evaluation results

- Backend: `local`
- Cases passed: **12/12**
- Pass rate: **100%**

| Case | Result | Outfits | Cost | Tool calls | Latency |
|---|---:|---:|---:|---:|---:|
| `school_standard` | PASS | 3 | $0 | 5 | 18 ms |
| `festive_standard` | PASS | 3 | $0 | 5 | 15 ms |
| `coastal_standard` | PASS | 3 | $96 | 6 | 14 ms |
| `multi_event_standard` | PASS | 9 | $96 | 8 | 30 ms |
| `school_zero_budget` | PASS | 3 | $0 | 5 | 13 ms |
| `festive_zero_budget` | PASS | 3 | $0 | 5 | 14 ms |
| `coastal_zero_budget` | PASS | 3 | $0 | 6 | 14 ms |
| `multi_event_zero_budget` | PASS | 9 | $0 | 8 | 16 ms |
| `coastal_maya_sneakers_unavailable` | PASS | 3 | $96 | 6 | 15 ms |
| `coastal_anaya_sneakers_unavailable` | PASS | 3 | $96 | 6 | 14 ms |
| `school_arjun_loafers_unavailable` | PASS | 3 | $0 | 5 | 14 ms |
| `festive_anaya_kurta_unavailable` | PASS | 3 | $0 | 5 | 13 ms |

Each case checks schema validity, workflow validity, participant coverage, hard constraints, budget, required tool calls, retrieval relevance, citation grounding, unavailable-item exclusion, and repeatability.
