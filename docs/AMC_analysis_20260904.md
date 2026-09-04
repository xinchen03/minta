# AMC 周期二四维解析(2026-09-04)

> 对象:① 榜首方案 ② 本轮主 app 接线代码 ③ 评测契约 ④ 官方基准管线
> 证据:官方站/规则/API 指南抓取、官方 repo 6 个 pipeline 全文、榜三
> ActiveMemoryIndex README(已核实)、MemoraX 公开材料与下载包、本仓库代码。

---

## 一、榜首方案解析:谁赢了、为什么、对 Minta 意味着什么

### 1.1 学术开源榜(文本)榜首区的真相:没有真正的"第一"

| 名次 | 系统 | 分 | 提交方式 | 信息可及性 |
|---|---|---|---|---|
| 1 | InvMem | 45.06 | 仓库 | 赛后不可搜(0 命中),内部未知 |
| 2 | Refind | 44.97 | 仓库 | 未知 |
| 3 | ActiveMemoryIndex | 44.84 | API | **公开 repo + 完整消融(本解析主依据)** |
| 10 | AML-Memory-MVP | 42.95 | 仓库 | — |

榜首三名的差距 **0.09–0.22 分**,远小于单臂噪声 → **榜一不具备方法学意义**;真正的方法学信息在 AMI 的公开消融里(见 1.3)。

### 1.2 MemoraX(商业榜首 58.02,断层 +12):不同范式的碾压

- **范式**:宣称 RL/端到端把"记忆内化进模型权重",非"外部附加检索"。商业榜 A 维度 89.89(开源榜 A 饱和 ~56-58)——检索式系统的天花板就是它的起点,符合"记在权重里=显式事实召回近乎无损"的解释。
- **下载包身份**(已核查):`memorax-code-main.zip` = 面向 coding agent 的客户端插件(npm memorax-code:claude/codex/codebuddy 启动器+hook runtime),**不是**上榜核心 → 核心闭源,公开材料无法复现其方法。
- **与套件同源观察**:官方 ScriptMem 管线引用的判分器上游是 `github.com/memorax-ai/ScriptMem`(MemoraX 组织)。商业榜首与套件内基准同属一家,是公开记录层面的**公允性疑点**——不扣帽子、不采信为结论,但值得在引用该榜成绩时保留谨慎;对开源榜无影响。
- **对 Minta 的结论**:训练资源/路线不在同一量级,"比它强"无意义;Minta 的赛道是开源可审计治理层,同场对手是 42-45 密集区的检索/治理系。

### 1.3 ActiveMemoryIndex(榜三):唯一完整公开的"赢家配方"

已核实的 README 消融(全部为 LoCoMo n=1540 实测):

| 结论 | 数字 | 我们的处置 |
|---|---|---|
| **填满 top_k** 单调增益 | K 1→100 准确率单调升,100 最佳(gold coverage .410→.940) | 采纳:默认 `min(top_k,100)` 填满 |
| **邻居窗口 r=1** | .6333→.6802,p<0.0001;r 1/2/3 无差异 → 发 1 | 采纳:默认 radius=1,同 Add chunk 内 |
| BM25 融合 | +27,p=0.094 不显著 → **移除** | A/B 不预设,代理分说话 |
| fact extraction 优先 | −7,p=0.64 → 无增益 | 不进默认 |
| agentic 二次搜索 | 零增益 → 默认关 | 不做 |
| gpt-4o-mini 第一人称 recall-query | 双嵌入 0.5/0.5 融合是最大 lever | 实验臂第一优先 |
| timestamp 放 content 内 | (register 匹配) | envelope 默认 on |
| **覆盖≠准确** | 最佳覆盖臂(0.961)准确率最差(0.5625);赢家臂 k=20 覆盖最低(0.609) | 纪律:只认端到端分 |
| 治理轴高分 = 无治理机制 | AMI 无 update/delete/冲突消解,D 轴 37.95 前五最高 | **evidence 层(保真+排序+provenance)即治理分** |

### 1.4 榜面能力画像:分差从哪来

学术榜七维均值形态(约):A 事实召回 **~56-58(饱和)** · B 多跳 ~45 · **C 时序 ~20-23(全榜洼地)** · D 治理 ~30-38 · E 个性化 ~52-57(近饱和) · **G 规则 ~26-31(洼地)** · **H 安全 ~25-35(洼地)**。

> A/B/E 已被检索+答案管线卷平;C/D/G/H 才是分差来源——而它们几乎全靠 **evidence 的排序与保真**(新事实置顶但不删旧、原文+时间戳、不确定时不瞎给),不是靠任何"治理机制"。这就是 v3 "fidelity-first + context-first" 判断的实证基础。

---

## 二、本轮主 app 接线代码解析(M1-M3)

### 2.1 修复前的问题链(为什么曾经"全断")

```
routers/search.py  已写好 ──→ 从未 include_router(死代码)
embedding_service.search() ──→ 查询全局单集合 minta_memories,无 user 过滤
                                  ↑ 但集合永远是空的(没有任何写入方)
add_vector() ──→ 零调用点          ↑ Chroma 内置 ef 在 1.x 被移除 → 版本分裂
模型路径 D:/all-mpnet-base-v2 ──→ Linux 容器里不存在
search.py 假设 id 是数字 int() ──→ 实际 id 是 slug-xxxx 字符串
```

### 2.2 修复后的数据流(现在是通的)

```
写入侧(任一路径成功落库后,自动同步向量,失败只告警不阻断请求):
  POST /api/contextObjects ─┐
  PATCH  /api/contextObjects ┼→ vector_ops.index_object() ──→ chroma upsert
  inbox 归档 / 注册种子对象 ─┘     (metadata: user_id/status/type)
  DELETE /api/contextObjects ──→ vector_ops.drop_object() ──→ chroma delete

检索侧:
  POST /api/search
    → chroma query, where={"user_id": {"$in": [str(user.id), "global"]}}
    → 候选 id 列表
    → DB 二次过滤(权威层):id∈候选 ∩ (属主=我 ∨ 全局) ∩ status≠archived
        (默认还要求 active;include_stale=true 放行 stale)
    → 按 chroma 分数保序 → compact/full/pack 渐进披露 → time_aware 标注
```

### 2.3 关键设计决策

| 决策 | 理由 |
|---|---|
| **双过滤(向量层 where + DB 属主/状态 join)** | where 防检索侧泄漏;DB 是状态权威——旧向量/归档对象永远不会以"用户看不见"的形式浮出 |
| **fail-open 钩子(vector_ops)** | 向量故障绝不断写请求;但 E2E 证明这也会"静默失联" → 所以必须配 E2E 测试(本轮的教训) |
| chroma 内嵌 ST helper → 直连 sentence-transformers | chromadb 1.x 移除了该 helper;镜像 <0.6 与本地 1.5.9 通吃 |
| 索引文本 title+summary+body(截 2000) | 多数对象只有 title,原 build_index 只嵌 summary+body → 空文本向量 |
| 索引在 commit **之后** | 回滚时不产生幽灵向量 |

### 2.4 验证矩阵

- 6 个路由测试(假服务):写钩子生命周期、where 作用域、归档/stale 过滤、层输出、空结果
- 真实 mpnet+chroma 双用户 E2E:A 命中自己 0.866;B 同 query 只见自己的对象
- 全量 102 测试绿

---

## 三、评测契约解析(适配器逐条对应)

### 3.1 Add/Search 契约

| 项 | 要求 | 我们的实现 |
|---|---|---|
| Add 同步语义 | 200 前所有 message 已持久化且可搜;禁 202/轮询 | 单 SQLite 事务;embedding 先算后写 |
| Add 回显 | success:true + request_id/user_id/session_id 逐字节回显 | 原样回显 |
| 幂等 | 平台 408/425/429/5xx 有界重试;resume 重放 | request_id 请求级幂等,确定性 id `mem_<sha256(req:idx)[:16]>` |
| 原子 | 半途失败=零残留 | UNIQUE(request_id,msg_index)+ 全量嵌入先行 |
| Search 隔离 | user_id 唯一隔离键;session_id 只分组不过滤 | 结构隔离:每查询从该 user 行集出发 |
| Search 输出 | data[] 有序 ≤ top_k;id/content/score?/created_at?;空数组合法 | 同款;created_at 优先取源 ts |
| 禁生成答案 | Search 不得答最终题 | 无 LLM 路径(默认) |
| top_k | 官方 Full 用 100 | fill min(top_k,100) |

### 3.2 错误与重试矩阵

| 码 | 含义 | 平台行为 |
|---|---|---|
| 400/422 | 契约错 | 不重试 → 修正后重跑 smoke |
| 401/403 | 鉴权/越权 | 不重试 |
| 404 | 路径错 | 不重试 |
| 408/425/429/5xx | 瞬时 | Add 全重试;Search 重试同组**但 409 除外** |
| 409 | 状态冲突 | Add 有界重试;Search 不重试(等新 run label) |

### 3.3 Full gate 8 项与配额(双口径)

- Full checklist 第 3 项(已复核现行 api-guide 原文):"**Add/Search 使用的模型必须为 gpt-4o-mini**,平台将复现,分数显著不符可作废"——语义待报名澄清;我们的零 LLM baseline 不受影响,recall-query 臂一旦上线即用 4o-mini。
- 配额:平台通用 smoke 每小时 1 / full 每 3 月 1;第二届赛事通知另给"最多 2 次 Full + 30 天冷却、取最新有效"。工程按首次 Full 即正式准备。
- 数据义务:仅评测用途、不落 body/query/key、≤30 天删除 → 容器销毁即清 + TTL 兜底。
- 判定判分规则(公开模板透露):**时间粒度严格**(HOUR↔HOUR,禁日历换算,禁相对↔绝对互转)、列表题全含且**多答算错**、偏好题任一对即对、"prefer most recent supported memory"。

---

## 四、官方基准管线解析(6 个 pipeline 全读)

共性:全部经 `api_config.py`(ANSWER/JUDGE base/key/model env)走 chat/completions;**仓库不含语料/金标**,公开的只是"答题+判分"契约 → 无法离线复现官分,这就是代理自测只能"近似"的原因。

| 管线 | 测什么 | Answer 形态 | 判分 | 对适配器的含义 |
|---|---|---|---|---|
| **locomo-refined** | 多会话长程 QA(事实/时序/冲突) | 双 speaker 记忆块模板(记忆当 episodic raw observations;禁过度拒答;相对时间按 ts 转绝对) | LongMemEval 对齐**二分 judge**,时间粒度/列表规则最严 | content 必须自足可读;新事实置顶保旧;ts 必须进 envelope |
| **longmemeval-s / (refined)** | 长上下文证据 QA | 同款模板家族 | 二分 | 同上 |
| **beam** | RAG 问答(rubric 维度) | 仅用 context 直答 | rubric judge 0/0.5/1.0(正/负约束、语义容差),上游默认模型 Qwen3-14B | **平台 judge 非单一固定模型** → 代理分只做同模型相对比较 |
| **clbench** | 上下文学习 0-4k/16-32k | CL-Bench 模板(结构化题+选中记忆拼装) | 严格二分 rubric judge | 检索需覆盖两种上下文窗;长窗靠 fill-100 |
| **scriptmem** | 脚本化事件/关系/选择/排序 | 数据集自带指令 | **memorax-ai/ScriptMem 官方 exact-option 判分器** | 见 1.2 同源观察;排序题 = evidence 顺序敏感 |
| **personamem v1/v2** | 隐性人格偏好 | v1:官方 options 原串;v2:MCQ 确定性构选项 + 生成式 recall 句附加 | v1 官方 exact;v2 MCQ exact + narrow judge | E 维度近饱和区;偏好类题答"任一不矛盾"即过 |

### 4.1 综合含义(落到我们的适配器)

1. **content 的形态决定一切**:它会被原样塞进多种 Answer 模板(可能是 speaker 分块、可能是 options 原串、可能是 rubric context)→ 保真 + 自足 + 时间戳是唯一稳的策略(v3 已定)。
2. **判分横跨"二分 exact / rubric / exact-option"三种风格** → 不要为单一判分风格过拟合;evidence 完备(填满)天然覆盖所有风格。
3. **平台 judge 模型不透明**(BEAM 上游是 Qwen3-14B,gate 说系统模型 4o-mini)→ 本地 A/B 锁定同一 judge 模型做相对比较,绝对分不可跨模型外推。
4. ScriptMem 由 MemoraX 组织维护 → 商业榜首在自己(或合作方)贡献的基准上断层领跑,引用榜绩时建议加脚注式谨慎。

---

*证据源:AML 官方站(rules/api-guide/evaluation)、agent-memory-leaderboard repo(6 pipeline)、linxuhao/ActiveMemoryIndex README、memorax.ai 公开页与下载包、minta-open 本仓库代码。*
