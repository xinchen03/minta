# A/B 矩阵结果(2026-09-04,第一轮)

> 数据:LoCoMo locomo10 前 2 对话 × 60 题 = 120 题/配置;Answer+Judge 均为
> DeepSeek-chat(代理口径,只做臂间相对比较)。**n=120 → 单配置 95%CI ≈ ±9pt,
> <9pt 的差异视为噪声**;环境:默认 radius=1 + envelope on + fill100。
> runs 原始产物:`docs/eval-proxy/runs/matrix/`(gitignored)。

| 配置 | acc | Δ vs 基线 | cov@k | 判定 |
|---|---|---|---|---|
| **k100(基线)** | 0.450 | — | 0.754 | 默认 |
| recall(DeepSeek 改写) | 0.467 | +1.7pt | 0.754 | 噪声内;待大样本复核 + GPT 口径 |
| bm25 on | 0.442 | −0.8pt | 0.754 | 噪声内,偏负 → 保持关 |
| r0(关窗口) | 0.417 | −3.3pt | 0.784 | 噪声内,偏负 → 保持 r=1 |
| k40 | 0.408 | −4.2pt | 0.555 | 显著偏负 → fill-100 确认 |
| k20 | 0.358 | −9.2pt | 0.451 | 显著偏负 → fill-100 确认 |
| env_off(去 envelope) | 0.308 | **−14.2pt** | 0.754 | **显著破坏**(multi-hop 0.019) |

## 解读

1. **fill top_k=100 与 envelope 是硬收益**(AMI 结论在本代理数据上复现):
   - K 单调:100 > 40 > 20;
   - envelope off 时 **multi-hop 崩到 0.019**——相对时间类题目没有时间戳
     provenance 就几乎全错,这正是 AMI"ts 放 content"的依据。
2. **窗口 r=1 / BM25 / recall 三项在 n=120 落在噪声带**:方向分别
   +3.3(窗口有用,multi-hop +5.6pt)/ −0.8(BM25 无用)/ +1.7(recall 略正,
   single-hop +2.9pt)。默认配置维持 v1:r=1、bm25 off、recall off。
3. **recall 臂上线条件不变**:代码路线无 LLM 凭据 → 仅当自托管或平台注
   凭据时才可能启用;启用前必须用 **gpt-4o-mini**(条款口径)重新测量。

## 下一轮(确认中)

baseline vs recall,5 对话 × 199 题(n≈995/臂,CI ≈ ±3pt),跑完更新本文档。
