# Minta × AMC 代理评测(proxy evaluation)

> **定位**:周期二(2026-09-20 开放)Full 前的**私有调优信号**。官方只公开
> Answer/Eval 契约、不公开语料与金标;本目录用公开 LoCoMo 数据 + 官方模板
> 复刻打分流程,近似但不等于官方成绩(数据分布不同)。**纪律:只认端到端
> 分数,不追 retrieval coverage(榜三公开消融的反例)。**

## 结构

| 文件 | 作用 |
|---|---|
| `proxy_eval.py` | runner:LoCoMo → `/add`(平台分块规则)→ `/search` → 官方 Answer/Judge 模板打分 |
| `templates.py` | AML 官方 locomo-refined Answer/Judge 提示词,**逐字提取**,仅供本地私有打分 |
| `runs/` | 运行产物(SQLite + items.jsonl + summary.json),gitignored,跑完即删 |

## 用法(仓库 dev 环境,anaconda python)

```bash
# 检索干跑(无需 LLM key;验证链路 + coverage 诊断)
D:/pycharm/anaconda/python.exe docs/eval-proxy/proxy_eval.py \
  --max-convs 2 --max-questions 20

# 全打分 —— 接口可切换(OpenAI 兼容)。当前无 GPT key 时用 DeepSeek:
export DEEPSEEK_API_KEY=sk-...
D:/pycharm/anaconda/python.exe docs/eval-proxy/proxy_eval.py \
  --max-convs 10 --top-k 100

# 换回 GPT(与参赛口径一致):
export PROXY_LLM_BASE=https://api.openai.com/v1
export PROXY_LLM_KEY=sk-...
export PROXY_LLM_MODEL=gpt-4o-mini
D:/pycharm/anaconda/python.exe docs/eval-proxy/proxy_eval.py \
  --max-convs 10 --top-k 100
```

> **模型口径说明**:代理分只用于臂间相对比较(同一 judge 模型下 A/B 才可比),
> 绝对值不等于官方成绩。官方系统模型为 gpt-4o-mini 口径,DeepSeek 跑出的
> 绝对分仅供调优方向参考;换 GPT 后矩阵需整套重跑。

嵌入模型默认 `D:/all-mpnet-base-v2`(存在时自动),可用 `MINTA_EVAL_EMBED_MODEL`
覆盖。检索行为由 minta-open eval 适配器的 env 开关控制,例如 A/B:

```bash
MINTA_EVAL_RADIUS=1 MINTA_EVAL_ENVELOPE=on   # 默认(窗口 r=1 + envelope)
MINTA_EVAL_RADIUS=0                          # 关窗口
MINTA_EVAL_BM25=1                            # 开 BM25
MINTA_EVAL_OPTIONS=1                         # 开 options 扩展(MC)
MINTA_EVAL_RECALL_QUERY=1 MINTA_EVAL_LLM_BASE=... MINTA_EVAL_LLM_KEY=... \
MINTA_EVAL_LLM_MODEL=gpt-4o-mini             # 开第一人称 recall-query
```

## 与官方评测的差异(已知,记录在案)

1. **时间戳合成**:LoCoMo turn 无独立时间戳,按 `session_N_date_time` +
   turn 序号 ×60s 合成(与 Minta-next 历史 runner 同源解析格式)。官方平台
   发送的时间戳语义以 smoke 实测为准。
2. **speaker 名称**:Add 契约只传 `user/assistant` role,无姓名;代理与官方
   同构地只在 envelope 携带 role(所有参赛系统面对相同信息)。
3. **答案渲染**:官方模板支持双 speaker 分块,代理用单块(fallback 路径,
   `retrieved_context`),role 前缀已内嵌于每条 content。
4. coverage 仅为诊断(evidence dia_id ↔ memory id 精确命中),不作为调优目标。

## 数据卫生

runs/ 含评测内容与检索文本:仅评测用途、不落任何日志、跑完删除目录;
minta-open eval 适配器本身不记录 request body/query/content/key。
