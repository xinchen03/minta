# Benchmark Status

## LoCoMo Retrieval (diagnostic only)
| Metric | Score |
|---|---:|
| Recall@5 | 66.4% |
| Recall@10 | 84.6% |
| Recall@20 | 97.1% |

## Memory Quality (primary)
| Metric | Score |
|---|---:|
| Conflict F1 | 67.8% (benchmark) / 0.81 (paper) |
| Staleness UFA | 0.86 (paper) |

## Fact Spine (experimental)
| Pipeline | Ev Recall@20 | Token F1 | Temporal F1 |
|---|---:|---:|---:|
| Chunk baseline | - | 15-20% | 28.6% |
| Fact Spine v0.1 | 68.0% | 24.3% | 43.0% |
| Oracle | 92.0% | 36.9% | - |
| Fact Spine v0.2 | TBD | TBD | TBD |
