# AMC 周期二 —— v3 冻结前验证记录(2026-09-16)

> 对象:拟议候选 `amc-2026-cycle2-v3`(截至本记录生成时尚未创建 tag)
> 环境:本地 Windows,Python 3.10(`.conda/envs/minta310`),零 LLM、零外网
> 复现脚本(未入库):`aml_eval_smoke.py`、`aml_latency_probe.py`、`aml_arm_ab.py`、
> `aml_ab_diagnose.py`;原始输出 `aml_eval_smoke.json`、`aml_latency_probe.json`、
> `aml_arm_ab.json`、`aml_ab_diagnose.json`

## 0. 结论摘要

1. 评测面(Add/Search 适配器)**契约与隔离全部通过**:本地全量测试 149 passed,
   公开边界检查通过,真实嵌入+重排的
   端到端 Add/Search 冒烟全部符合 AML 契约。
2. 实测**搜索延迟的支配项是重排(cross-encoder)**:N=200 时中位 185ms vs
   关掉重排 47ms(≈4×);N=1000 时 221ms vs 95ms(≈2.3×)。时间表达式臂
   (temporal)在本机测量中≈0 额外成本。
3. 两个候选臂(`recencyq`、`timeorder`)**本次未能取得可用的离线 gate**:
   LoCoMo-Refined 公开分片的 `evidence` id 与检索命中的 turn 不逐条对应
   (§3.1 有实证),因此 coverage 指标在该分片上不可用于判臂。**故本次不启用、
   不写进默认配置**;要启用必须先跑带 LLM 的 861 端到端 A/B。
4. v3 候选因此是一次**行为冻结快照**,不是配置变更:评测面代码与 `v2` 相同
   (评测面自 `v2` 起零改动),新增的是公开版产品侧修复与本文档；v3 tag
   已在此前提交创建，本次仅修正文档，不移动该 tag。

## 1. 代码与契约验证

### 1.1 全量测试

```
cd <minta-repository>
python -B -m pytest server\tests -q -p no:cacheprovider
→ 149 passed, 9 warnings in 181s
```

评测面相关测试(契约/鉴权/反过拟合)与记忆权威测试**全部通过**,包括
`test_eval_contract.py`、`test_eval_auth.py`、`test_eval_no_overfit.py`、
`test_memory_policy.py`、`test_autopilot_executor_unit.py`。

### 1.2 失败记录

本轮未出现测试失败。此前记录的 `test_domain_compiler.py` 权限失败来自只读
沙箱，而非代码行为；在可写工作树中已消失。该模块仍不在评测面
(`server.eval_app` 不 import 它)。

### 1.3 公开边界

```
python scripts/check_public_boundary.py → Public-boundary check passed
```

### 1.4 端到端 Add/Search 冒烟(真实权重,离线)

配置=镜像默认口径:`all-mpnet-base-v2`(本地等价路径)+ `ms-marco-MiniLM-L-6-v2`
重排 + `MINTA_EVAL_TEMPORAL=1`;数据为脚本内合成对话(94 条记忆)。

| 检查项 | 结果 |
|---|---|
| `GET /health` | `{"ok": true}` |
| `POST /add` 回显 | `success/request_id/user_id/session_id` 逐字节一致 |
| 同 `request_id` 重放 | 响应完全相同,记忆数不增(幂等) |
| `user_id` 隔离 | 另一 `user_id` 检索只返回自己的行;本 `user_id` 命中自身记忆 |
| `top_k` | `top_k=5` → 5 条;`top_k=100` → 全部 94 条;id 唯一 |
| envelope | `[2023-11-14T22:13:20+00:00] user: ...`(UTC ISO + role) |
| 无外部 LLM | Add/Search 全路径无网络调用 |

## 2. 实测搜索延迟(本机 CPU,`top_k=100`)

合成对话(同质化长文,便于线性外推),默认口径=重排开+temporal 开:

| 记忆数 N | 默认(重排开) 中位 | 重排关 中位 | 倍率 |
|---:|---:|---:|---:|
| 200 | 184.7 ms | 47.1 ms | 3.9× |
| 1000 | 221.2 ms | 94.6 ms | 2.3× |

补充:temporal 臂在查询不含时间表达式时与"全关"同价(95.8 vs 94.6 ms,
n=1000),即该臂的额外成本近 0。

官方 LoCoMo-Refined 公开分片(10 对话、861 题、真实嵌入+默认重排):
**搜索中位 357 ms/题**(n=861)。写入侧:10 对话共 434 个 Add chunk
(按平台分块规则 ≤20 条/≤2000 词)在本机耗时约 285 s。

**解读**:重排是搜索延迟的支配项。仓库可复核的全量结果只有 dense-only
0.7329 与 temporal-only 0.7375；此前记录的 rerank 0.7422 没有随提交物
保留可复核产物，因此本记录不把它当作已验证成绩。若平台把搜索/总时间作为
资源约束或并列比较项，重排的 2.3–3.9× 延迟成本仍需与未量化的收益权衡。
**本轮保留镜像默认开启**，但明确不宣称 rerank 的全量准确率增益，并保留
`MINTA_EVAL_RERANK=0` 回退。

## 3. 两个候选臂的离线 A/B(未通过,故不启用)

### 3.1 为什么本次结果不能用于判臂

对 LoCoMo-Refined 公开分片按 `docs/eval-proxy/proxy_refined.py` 同款分块与
时间戳复现后,按 `evidence` dia_id 计算的 coverage@100 仅 0.117,且四臂
(A0 默认 / A1 +recencyq / A2 +timeorder / A3 两者)在 855 道含金标题上
**逐题完全一致**。诊断显示这不是"检索失效":

```
问:When did Caroline go to the LGBTQ support group?
金标 evidence 指向文本: "That event sounds great! ... I just had a big life change!"
检索 top-1(默认口径): "[2023-05-08T13:58:00+00:00] user: I went to a LGBTQ support group yesterday..."
问:When Jon has lost his job as a banker?
检索 top-1:           "[2023-01-20T16:05:00+00:00] user: Hey Gina! ... Lost my job as a banker yesterday..."
```

检索命中正确,而该分片的 `evidence` id 并不总落在同一个 turn 上,因此
coverage/dia_id 口径在本分片上不可用作判臂指标(与本仓库
`docs/eval-proxy/README.md` "coverage 仅为诊断" 的既有声明一致,本次进一步
证明它也不能当作臂间 gate)。四臂"完全一致"更可能反映该指标无分辨力,
而不是两臂真的零效应。

### 3.2 需要的证据(未完成)

`recencyq`、`timeorder` 要进默认配置,必须补:

1. LoCoMo-Refined 861 的**端到端** A/B(官方 Answer/Judge 模板;
   `recencyq` 已有 PersonaMem 双跑 +27pt pref-change 的支持,但缺 LoCoMo
   侧"不伤其他类目"的确认);
2. 判分器口径锁定(官方系统模型为 `gpt-4o-mini`;此前矩阵为 DeepSeek 口径,
   绝对值不可跨模型外推)。

两臂均已是 env 开关(`MINTA_EVAL_RECENCYQ`、`MINTA_EVAL_TIMEORDER`),
跑完 A/B 后只需一行改动即可并入默认,并在 v4 冻结。

## 4. 外部未决事项(与代码无关)

- **模型条款**:现行 Full 清单仍含 `gpt-4o-mini` 项,而第二届公告称内部架构
  不限。提交 Full 前需组委会书面澄清;零 LLM baseline 按"不调用即不受影响"
  准备,但披露文本与冻结配置必须一致。
- **Full 配额**:平台通用 full 每 3 月 1 次;本赛事通知另给"最多 2 次 Full +
  30 天冷却"。按首次 Full 即正式提交准备。

## 5. v3 候选内容（待 tag 冻结）

- 评测面:`server/eval_*.py`(自 `v2` 起零改动)。
- 默认口径(镜像内):`MINTA_EVAL_RADIUS=1`、`MINTA_EVAL_ENVELOPE=on`、
  `MINTA_EVAL_TEMPORAL=1`、`MINTA_EVAL_RERANK=1`、`MINTA_EVAL_BM25=0`、
  `MINTA_EVAL_RECALL_QUERY=0`、`MINTA_EVAL_RECENCYQ=0`、`MINTA_EVAL_TIMEORDER=0`、
  零 LLM。
- 产品侧修复(含 `v2` 之后合入):`fix(autopilot): honor policy queries and
  user memory authority`、`fix(search): prioritize relevant private memories`。
- 回退全部为环境变量(见上表),无需改代码。
