# Minta × Agent Memory Challenge 2026 周期二 —— 提交材料与运行说明

> 仓库:`github.com/xinchen03/minta`(公开,minta-open 线)
> 组别:文本赛道 · 开源方法榜(学术·代码路线优先,API 自托管为 fallback)
> 目标冻结:2026-09-18 `git tag amc-2026-cycle2-v1`;报名 2026-09-20 开放

## 1. 方法披露(学术榜材料)

**系统名称**:Minta — lifecycle-aware memory management for personalized LLM agents
(评测适配器见 `server/eval_app.py` 等 `server/eval_*` 模块,独立于业务服务运行)

- **方法来源**:原创系统。技术报告:论文《Minta: Lifecycle-Aware Memory
  Management for Personalized LLM Agents》(投稿审稿中);本仓库公开历史与
  本文档为方法依据。
- **评测配置(周期二 v1,零 LLM baseline)**:Add 按平台契约原文无损存储 +
  本地 mpnet 嵌入 + SQLite 原子落库;Search 按 `user_id` 严格隔离,dense
  检索 → 命中邻接轮次窗口(radius=1,同 Add chunk 内)→ 检索侧去重 →
  填满 `min(top_k,100)`;返回 `[UTC ts] role: 原文` 最小 provenance
  envelope。**Add/Search 全路径不调用任何外部 LLM/API**(gpt-4o-mini 条款
  语义待报名时向组委会澄清;若条款要求必须实际调用,将按当期 API 指南在
  baseline 附加合规调用并更新本文件)。
- **本次改动声明**:仅新增 `server/eval_*` 模块、`scripts/fetch_eval_models.py`、
  测试与本文档;未改动既有业务路由/数据模型/前端。
- **复用与致谢**:嵌入模型 `sentence-transformers/all-mpnet-base-v2`
  (Apache-2.0),镜像构建时下载 bake,不随源码分发;评测基准归属各上游
  (AML 套件:LocoMo/LongMemEval/BEAM/PersonaMem 等)。

## 2. 运行说明(代码提交路线)

```bash
# 构建(镜像内已 bake 嵌入模型;网络仅构建时需要,可 --build-arg 换镜像源)
docker build -t minta-eval .

# 评测模式启动(独立工厂 app,不加载业务服务)
docker run --rm -p 8772:8772 minta-eval \
    uvicorn server.eval_app:create_eval_app --factory \
    --host 0.0.0.0 --port 8772
# 健康检查:GET /ping 或 /health

# 冒烟自检
curl -s localhost:8772/health
curl -s localhost:8772/add  -H 'Content-Type: application/json' -d '{
  "request_id":"smoke:1","user_id":"eval:smoke:u","session_id":"s0",
  "messages":[{"role":"user","content":"hello memory","timestamp":1700000000000}]}'
curl -s localhost:8772/search -H 'Content-Type: application/json' -d '{
  "query":"hello","user_id":"eval:smoke:u","top_k":10}'
```

**环境变量(评测相关)**

| 变量 | 默认 | 说明 |
|---|---|---|
| `MINTA_EVAL_DB` | `sqlite:////data/eval.db` | 评测数据单库;`user_id` 即命名空间 |
| `MINTA_EVAL_TTL_HOURS` | `720` | 过期清理(自托管路线 30 天删除义务;平台部署容器随任务销毁) |
| `MINTA_EVAL_EMBED_MODEL` | 镜像内 `/models/...` | 本地嵌入权重(本地开发可指向 `D:/all-mpnet-base-v2`) |
| `MINTA_EVAL_RADIUS` | `1` | 邻接轮次窗口半径(0 关闭) |
| `MINTA_EVAL_ENVELOPE` | `on` | role/timestamp envelope(off 返回裸原文) |
| `MINTA_EVAL_EMBED` | `1` | 置 0 = 完全离线基线(不加载嵌入) |
| `MINTA_EVAL_BM25` / `_OPTIONS` / `_RECALL_QUERY` … | 全 `0`/off | 实验臂,默认关闭;见 `server/eval_experiments.py` |

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
- [ ] 公开仓库固定 commit(tag `amc-2026-cycle2-v1`);README/Docker/入口齐全
- [ ] `pytest server/tests/` 全绿(96 项)

## 4. 本地调优工具(不影响提交物)

`docs/eval-proxy/`:公开 LoCoMo + 官方模板的私有代理打分(README 内含用法)。
结果仅作臂间比较,不进本文件。
