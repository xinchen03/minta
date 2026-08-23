<p align="center">
  <img src="assets/logo.png" alt="Minta" width="420">
</p>

<p align="center">
  <b>面向 AI 智能体的上下文质量层。</b><br>
  你的 AI 记得,但 Minta 告诉你:它什么时候记<u>错</u>了——以及什么它<u>没资格声称</u>。
</p>

<p align="center">
  <a href="README.md">English</a> · <b>中文</b> · <a href="README_ja.md">日本語</a>
</p>

<p align="center">
  <a href="#license"><img src="https://img.shields.io/badge/license-Apache--2.0-blue"></a>
  <a href="#快速入门"><img src="https://img.shields.io/badge/python-3.9%2B-green"></a>
  <a href="#deepseek-harness"><img src="https://img.shields.io/badge/DeepSeek%20Harness-verified-purple"></a>
  <a href="#基准测试"><img src="https://img.shields.io/badge/MCP-19%20tools-orange"></a>
</p>

> ⭐ 新消息(2026-08):**开放核心 v2** —— 记忆引擎 + 科研合规引擎 + 专家域包,并已接入 **DeepSeek Harness(验证通过)**。质量层背后的论文正在 *Information Processing & Management* 外审中。

---

## 为什么是 Minta

所有记忆系统都在"存得更多"。Minta 负责的是:让智能体所知道的**依然为真**——并且不能声称它没做过的事。

| 别人做 | Minta 做 |
|---|---|
| "这是与你相关的记忆" | "其中 2 条相互冲突。1 条已过时。真相是这样的。" |
| 永远存着 | 检测过期的内容,标记,再由你决定 |
| 对记忆一视同仁 | 类型特定衰减:偏好比项目状态活得久 |
| 指望 LLM 自己判断 | 生命周期扫描 + 健康分 + **阶段门控**(禁止越阶声称) |

**内容导航** · [为什么是 Minta](#为什么是-minta) · [快速入门](#快速入门) · [功能](#功能) · [开放核心](#开放核心open-code-locked-assets) · [基准测试](#基准测试) · [DeepSeek Harness](#deepseek-harness) · [路线图](#路线图)

## 演示与截图

<p align="center">
  <img src="assets/dashboard.png" alt="Minta 仪表盘 — 记忆健康、知识图谱、收件箱" width="860">
</p>

<details>
<summary><b>▶ 查看演示视频</b>(本地优先,8772 UI)</summary>

<video src="assets/demo.mp4" controls width="860"></video>
若无法播放,clone 后直接打开 <code>assets/demo.mp4</code>。
</details>

三层的引擎:

```
L1 记忆治理  →  stale / conflict / redundant / fragile——发现问题,而非堆积存储
L2 专家知识  →  从你的纠错中晋升出的规则,按领域分类
L3 声称门控  →  agent 不能声称没做过的阶段(数模/科研工作流)——附带校准置信度
```

## 快速入门

**60 秒。** 本地优先,无云,开放核心无需订阅。

```bash
git clone https://github.com/xinchen03/minta.git
cd minta
python -m pip install -r server/requirements.txt
python minta_cli.py start          # API :8772 · Autopilot :18730 · MCP :18721
```

或用 Docker:`docker compose up -d`。然后接入你的智能体:

```bash
# 任意 MCP 编辑器/智能体 — Claude Code / Codex / Cursor / dsh
python minta_cli.py connect claude
# DeepSeek Harness(已验证)→ 见 docs/dsh-integration.md
```

Web 界面自动打开于 `http://127.0.0.1:8772` — 记忆健康仪表盘、3D 知识图谱、收件箱审核、专家面板。

## 功能

| 层 | 特性 | 你得到什么 |
|---|---|---|
| 记忆 | 混合检索(向量+BM25+实体+FTS) | 选中正确的记忆,不是碰巧相关的 |
| 记忆 | 生命周期引擎(衰减/冲突/冗余/碎片化) | 质量检查按计划跑,不靠运气 |
| 纠错环 | 收件箱 + 反例捕获(钩子:SessionStart → UserPromptSubmit → PostToolUse → Stop) | 你纠正的会成为规则——在你确认之后 |
| 专家域 | 多域规则(踝/膝/颈椎损伤、ISO9001、PRISMA…)+ CUMCM 阶段工作流 | 带信任指标的领域推理 |
| 科研 | 手稿清单 + 合规规则评估器 | "这稿符合投稿清单吗?"——提交前 |
| 元认知 | 共形置信度(校准、数据锁定) | agent 给出的"知道",带覆盖保证 |
| 交付 | 编译版 Web UI + MCP(19 工具,stdio+HTTP)+ DSH 插件已验证 | 三个入口,一份记忆 |

## 开放核心(Open Code, Locked Assets)

| 本仓库(Apache-2.0,免费) | 通过 API Key / 企业许可 |
|---|---|
| 记忆引擎——完整可运行 | 托管引擎 + 监控 |
| 质量内核算法(共形/规则晋升/决策图/编译器) | 全精度:自动校准、私域 |
| 科研合规引擎 + 域包 | 运动医学 / 临床域包 |
| Web dist · MCP · DSH 集成 · 12 篇指南 | 数据飞轮:校准集、权重、规则库 |

**商业分界线是"累积精度",不是代码。** 你可以 clone 一切;但克隆不了 1,000 个用户纠错后沉淀进校准的东西。

## 基准测试

<img src="assets/benchmark_comparison.png" alt="记忆质量对比——只有 Minta 衡量冲突与陈旧度">

| 检测 | 指标 | 分数 | Mem0 | Hindsight |
|---|---|---|---|---|
| 冲突 | F₁ | 0.81(held-out,5 个未见过领域) | 无 | 无 |
| 陈旧 | UFA | 0.86(12 对事实模板) | 无 | 无 |
| 冗余 | 压缩 RR | 0.67(25 个簇) | 无 | 无 |
| 碎片化 | MCR | 0.746(15 组片段) | 无 | 无 |
| 检索(LoCoMo) | Recall@20 | 97.1% | — | — |

## 科研优先

Minta 最初就是科研工作流的记忆层——文献笔记、稿件清单、期刊合规、裁决门控的诉求追踪。见 `runtime/compliance/` 与 `docs/interaction-guide.md`。

配套执行技能(Apache-2.0,独立仓库):[nature-skills](https://github.com/Yuan1z0825/nature-skills) — 阅读、制图、引用、润色。

**引用:** Chen X. 等,《Governing Synthetic Athlete Monitoring Data…》(JSAMS 外审);以及 IP&M 记忆质量论文(可按需索取)。

## DeepSeek Harness

已验证集成(2026-08):2 分钟内把 Minta 作为 DSH 的 MCP 服务器接入——`docs/dsh-integration.md` 有完整的 `cordis.patch.yml` 片段。开放核心插件包发布在 npm(`@minta/dsh-plugin`)。

## 构建与贡献

```bash
python scripts/build_open_release.py   # 同步发布线(A 级)
python -m pytest tests/                # 服务端测试
```

欢迎 good-first-issue PR:`entity_linker` 英文模式、更真实的演示场景。详见 `CONTRIBUTING.md`。

## 指南

[交互指南](docs/interaction-guide.md) · [启动顺序](docs/startup-chain.md) · [DSH 集成](docs/dsh-integration.md) · [配置](docs/configuration.md) · [用户指南](docs/user-guide.md) · [MCP 集成](docs/mcp-integration.md)

## 数据与隐私

- 本地优先:数据库、向量、日志留在你的机器;默认零遥测。
- 数据导出/删除:`GET /api/user/export-data` · `DELETE /api/user/delete-data`(需认证)。
- 密钥:首次运行生成(`.minta_api_key`,永不提交);`MINTA_ADMIN_IDS` 管理后台接口门槛(不设=无人可入)。
- 披露策略见 `SECURITY.md`。

## 路线图

- 2026 Q4 — 托管 API(全精度、监控),运动医学域包
- 2027 Q1 — 企业私有化部署 + 治理审计报告
- v2.1 — IP&M 论文复现脚本

## 许可

Apache-2.0。上游捆绑资源保留各自许可证——后续若加入见 `skills/` 备注。
