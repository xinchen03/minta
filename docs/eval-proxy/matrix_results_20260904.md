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

## 追加(当晚):BEAM / PersonaMem / 重排进展

**BEAM(本地 4 对话,80 probes):acc 0.762**
- knowledge_update 1.000 · contradiction_resolution 1.000 · temporal_reasoning 1.000
  → **D/C 轴治理类直考满分**(证据层治理验证)
- abstention 0.750(H 轴)· event_ordering 0.375(短板,见下)

**event_ordering 归因(已分析)**:错题全是"按顺序列出先后提到的 N 个要点"——需跨批次按时间重构;我们按相关度返回、时间线索在 envelope,答题模型重构困难。结构性限制,9/18 前不改(动排序语义伤其他类),记为已知短板(赛后优化项)。

**PersonaMem(云端 100 人设,4 选 1,猜中率 25%)**:
- 普通题 0.410 ✅ 远高于瞎猜;偏好变化题 **0.136 ❌ 低于瞎猜**
  → D 轴"最新态必须赢"短板量化坐实(旧偏好压过新偏好)
  → 对策:recencyq 臂对照实验(云端跑,结果待回填)

**本地全量重排(861)反复卡死 → 移交云端**:根因=批处理嵌入在第二对话起死锁(已默认关闭,env 可开);单对话冒烟正常但全量本地仍偶发卡顿(单机环境不稳),最终云端执行。**教训:本地跑不动的是 2.2GB bge(模型过大+批嵌入死锁),不是"本地不能跑重排"——88MB ms-marco-MiniLM-L-6-v2 轻量版本地 CPU 完全可行,并已在独立环境验证(n=861)。**

## 第四轮补考(2026-09-04 晚)

**PersonaMem recencyq 臂(云端,100 人设,4 选 1,瞎猜 25%)** — 对照基线:普通 0.410 / 偏好变化 0.136(低于瞎猜):

| 臂 | overall | plain (n=78) | pref-change (n=22) | 判定 |
|---|---|---|---|---|
| baseline(推算) | ≈0.350 | 0.410 | 0.136 | 短板坐实 |
| **+recencyq** | **0.450** | **0.4487** | **0.4545** | **D 轴短板修复 ✅** |

pref-change +31.9pt(0.136→0.4545,远超瞎猜 25%):"current 问新态 / past 问旧态"证据级重排直接命中 D 轴死穴;plain 亦 +3.9pt 无伤。
→ **recencyq 臂待 LoCoMo-861 A/B 确认不伤他类后并入默认**(`MINTA_EVAL_RECENCYQ=1`)。

**BEAM(本地 4 对话 80 probes,timeorder 修复后)**:0.762 → **0.812**;event_ordering 0.375→0.500(排序型问题检测分流时间序);治理直考类 knowledge_update / contradiction_resolution / temporal_reasoning 保持 1.0。

## 第五轮补考(2026-09-04 深夜,本地串链终数)

**PersonaMem recencyq 复现 #2(本地,同数据源,同配置)**:overall **0.36**(pref-change 0.3636 n=22 / plain 0.3590 n=78)。与云端 0.45 的差异在抽样噪声带内(n=100 CI±10pt、pref 仅 22 题 CI±21pt)。**recencyq 双测平均:pref-change ≈0.41 vs 基线 0.136(+27pt,显著),plain ≈0.40 vs 0.410(无伤)** → 臂有效结论稳健。**候选待 LoCoMo 861 A/B 终审,尚未并入默认**。

**CLBench(本地 60 samples / 554 rubrics,巨文档精确引用类,默认臂无 BM25)**:
- mean rubric pass **0.267** · all-pass 率 **0.05**(60 题仅 3 题全过)——精确实体/编号引用是当前检索的显著短板(巨文档被切 2000 词消息块,语义检索对精确 id 弱)
- BM25 通道对照臂(同 60 samples,MINTA_EVAL_BM25=1)运行中 → 验证 lexical 通道是否救精确引用类
- 口径:rubric 逐条二值判定(单题最多 57 条 rubric,全过极难),all-pass 5% 属该任务常态预期
