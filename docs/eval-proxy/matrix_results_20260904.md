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

## 第二轮(确认,2026-09-04 14:16-14:44)

baseline vs recall(DeepSeek 改写),5 对话 × ~895 有效题/臂(n≈900,CI ≈ ±3pt):

| 臂 | acc | Δ | single-hop | multi-hop | temporal | open-domain | adversarial |
|---|---|---|---|---|---|---|---|
| **base(定案)** | **0.5866** | — | 0.359 | 0.346 | 0.370 | 0.794 | 0.534 |
| recall | 0.5832 | **−0.3pt** | 0.373 | 0.365 | 0.391 | 0.775 | 0.526 |

**结论:recall-query 臂在大样本下无增益(净 −0.3pt;仅 temporal/single-hop 微正,
open-domain/adversarial 微负)→ 不上默认配置。** 与零 LLM baseline 路线一致;
若未来自托管 + gpt-4o-mini 口径可再复测,不作为本周期提交配置。

## 第三轮定案(官方 LoCoMo-Refined 文本子集,n=861,DeepSeek 裁判)

baseline 0.7329 → **+temporal 0.7375**(时序类 0.778→0.806,+2.8pt;单跳
0.442→0.468)。时序臂零 LLM、纯检索重排、增益集中在设计目标类目 →
**默认开启**(Dockerfile `MINTA_EVAL_TEMPORAL=1`,env 可关,留作 Full#2 兜底)。

## 冻结配置(9/18)

```
默认 = radius=1 · envelope on · temporal on · fill min(top_k,100) · BM25 off · recall off · 零 LLM
```
