# Minta × 第二届 Agent Memory Challenge 2026 —— 提交材料与运行说明

> 主办:中国图像图形学会(CSIG)
> 承办:南京大学、浙江大学、Datawhale、CSIG 企业联络与标准化工作委员会
> 统一评测平台:Agent Memory Leaderboard(AML)
> 仓库:`github.com/xinchen03/minta`(公开,minta-open 线)
> 赛道/组别:文本赛道 · 开源方法榜(学术榜)
> 报名:2026-09-20 00:00 起开放;内部目标冻结:2026-09-18
> 候选比赛版本:由本仓库最新的不可变 `amc-2026-cycle2-*` tag 标识;
> 早期候选 tag 保持不变。验证记录见 `docs/AMC_cycle2_readiness_20260916.md`。

`main` 是持续更新的公开产品线;比赛 tag 是 Full 评测绑定的固定快照。
现有 `amc-2026-cycle2-v1` 保留为早期候选,不得移动或覆盖。

## 1. 方法披露(学术榜材料)

**系统名称**:Minta — lifecycle-aware memory management for personalized LLM agents
(评测适配器见 `server/eval_app.py` 等 `server/eval_*` 模块,独立于业务服务运行)

- **方法来源**:原创系统。技术报告:论文《Minta: Lifecycle-Aware Memory
  Management for Personalized LLM Agents》(投稿审稿中);本仓库公开历史与
  本文档为方法依据。
- **评测配置(当前候选,零 LLM)**:Add 按平台契约原文无损存储 +
  本地 mpnet 嵌入 + SQLite 原子落库;Search 按 `user_id` 严格隔离,dense
  检索 → 命中邻接轮次窗口(radius=1,同 Add chunk 内)→ 检索侧去重 →
  填满 `min(top_k,100)`;返回 `[UTC ts] role: 原文` 最小 provenance
  envelope。**Add/Search 全路径不调用任何外部 LLM/API**。平台统一完成
  Answer/Eval;最终提交以当期 API 指南和赛事说明为准。
- **参评实现边界**:平台只运行 `server.eval_app:create_eval_app`,参评路径由
  `server/eval_*` 模块、`scripts/fetch_eval_models.py`、Dockerfile、测试和
  本文档组成。公开产品业务路由与前端虽同仓维护,但不由比赛容器加载,
  也不属于 Add/Search 计分路径。
- **复用与致谢**:嵌入模型 `sentence-transformers/all-mpnet-base-v2`
  (Apache-2.0),镜像构建时下载 bake,不随源码分发;评测基准归属各上游
  (AML 套件:LocoMo/LongMemEval/BEAM/PersonaMem 等)。

## 2. 运行说明(自托管路线)

> 第二期要求参赛方**自行部署公网可访问的 Add/Search API**;AML 不代为部署,
> 不接受仅提交仓库、镜像或启动说明。以下为**我方部署**所用的构建与启动方式;
> 公开仓库与固定 commit 作为开放性、署名与复现材料。

```bash
# 构建(镜像内已 bake 嵌入模型;网络仅构建时需要,可 --build-arg 换镜像源)
docker build -t minta-eval .

# 评测模式启动(独立工厂 app,不加载业务服务)
docker run --rm -p 8000:8000 minta-eval
# 健康检查:GET /ping 或 /health

# 冒烟自检
curl -s localhost:8000/health
curl -s localhost:8000/add  -H 'Content-Type: application/json' -d '{
  "request_id":"smoke:1","user_id":"eval:smoke:u","session_id":"s0",
  "messages":[{"role":"user","content":"hello memory","timestamp":1700000000000}]}'
curl -s localhost:8000/search -H 'Content-Type: application/json' -d '{
  "query":"hello","user_id":"eval:smoke:u","top_k":10}'
```

**环境变量(评测相关)**

| 变量 | 默认 | 说明 |
|---|---|---|
| `MINTA_EVAL_DB` | `sqlite:////data/eval.db` | 评测数据单库;`user_id` 即命名空间 |
| `MINTA_EVAL_TTL_HOURS` | `720` | 过期清理;自托管容器长期运行,TTL 为兜底删除(≤30 天) |
| `MINTA_EVAL_EMBED_MODEL` | 镜像内 `/models/...` | 本地嵌入权重(本地开发可指向 `<local-model-path>`) |
| `MINTA_EVAL_RADIUS` | `1` | 邻接轮次窗口半径(0 关闭) |
| `MINTA_EVAL_ENVELOPE` | `on` | role/timestamp envelope(off 返回裸原文) |
| `MINTA_EVAL_EMBED` | `1` | 置 0 = 完全离线基线(不加载嵌入) |
| `MINTA_EVAL_BM25` / `_OPTIONS` / `_RECALL_QUERY` … | 全 `0`/off | 实验臂,默认关闭;见 `server/eval_experiments.py` |

鉴权可通过 `MINTA_EVAL_API_KEY` 开启;`X-Api-Key`、
`Authorization: Bearer` 与 `Authorization: Token` 三种方式均受支持,
`/health` 与 `/ping` 始终无需鉴权。

**数据生命周期与日志声明**:评测数据仅用于当期评测;适配器不落任何
request/memory/query/key 日志(仅非敏感启动与错误日志);容器销毁即清,
TTL 兜底清理 ≤30 天。

**Full 配额口径(如实陈述)**:
> AML 平台通用标准配额当前为 smoke 每小时 1 次、full 每 3 个月 1 次;
> 第二届 Agent Memory Challenge 官方赛事通知另规定本赛事周期最多 2 次
> Full、成功或部分完成后进入 30 天冷却、最终取最新有效 Full。参赛执行
> 以第二届报名页面最终生效规则为准;本仓库按首次 Full 即正式提交准备,
> 若确认 2 次则第二次作升级机会。

## 3. 合规自查(对照 Full gate)

- [ ] Add 同步:200 前全部消息已持久化且可搜(单事务;embedding 先算后写)
- [ ] request_id 幂等:重试/续跑重放 → 同 id 同数据同响应
- [ ] Search 不生成答案;返回有序 `data[]` ≤ top_k,字段齐
- [ ] `user_id` 严格隔离:测试 `test_search_strict_user_isolation` 等断言
- [ ] 无硬编码、无基准泄漏、无提示注入、无人工实时作答
- [ ] 官方书面确认第二届 Add/Search 的模型条款;冻结配置与披露保持一致
- [ ] 公开仓库固定 commit(不可变 `amc-2026-cycle2-*` tag);README/Docker/入口齐全
- [ ] `pytest server/tests/`、公开边界检查与比赛 Docker 冒烟全绿

## 4. 本地调优工具(不影响提交物)

`docs/eval-proxy/`:公开 LoCoMo + 官方模板的私有代理打分(README 内含用法)。
结果仅作臂间比较,不进本文件。
