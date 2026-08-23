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

> ⭐ 新消息(2026-08):**开放核心 v2** —— 记忆引擎 + 科研合规引擎 + 专家域包,并已接入 **DeepSeek Harness(验证通过)**。

---

## 为什么是 Minta

> **别人存记忆。Minta 校验什么是仍然为真的。**

记忆有三种时态:它*曾经*为真,它*现在*为真,它*今天还*为真。几乎所有的记忆系统都在优化第一种。Minta 为第二种和第三种而建。

| 别人做 | Minta 做 |
|---|---|
| "这是与你相关的记忆" | "其中 2 条相互冲突。1 条已过时。真相是这样的。" |
| 永远存着 | 检测过期的内容,标记,再由你决定 |
| 对记忆一视同仁 | 类型特定衰减:偏好比项目状态活得久 |
| 指望 LLM 自己判断 | 生命周期扫描 + 健康分 + **阶段门控**(禁止越阶声称) |

### 同一个智能体:带 Minta 与不带 Minta

| | 不带 Minta | 带 Minta |
|---|---|---|
| 一条事实过期了 | 继续用旧真相 | 标记陈旧、归档、展示给你 |
| 两条记忆打架 | 两个都返回,拼在一起 | 表面化矛盾,你来决策 |
| 你纠正了它 | 下一轮就忘 | 收件箱 → 你确认 → 变成规则 |
| 上下文膨胀 | 一万条记忆塞进一个 prompt | 按 token 预算打包的 Context Pack |

**内容导航** · [为什么是 Minta](#为什么是-minta) · [快速入门](#快速入门) · [功能](#功能) · [开放核心](#开放核心open-code-locked-assets) · [基准测试](#基准测试) · [DeepSeek Harness](#deepseek-harness) · [路线图](#路线图)

## 产品界面

完整 Minta 工作台(`Personal Context Layer`,V8.3 引擎 UI)。你看到的各层——研究驾驶舱、专家推理、记忆健康——对应下方引擎分层;开放核心的 dist 附带记忆中枢 UI,其余面板通过同一套 API 激活。

| | | |
|---|---|---|
| <img src="assets/ui/ui-hero.png" width="420"> | <img src="assets/ui/ui-context-draw.png" width="420"> |
| **Context Hub** — "停止让你的 AI 重复上手" | **Context Draw** — 3D 知识图谱 + 卡片召回 |
| <img src="assets/ui/ui-health.png" width="420"> | <img src="assets/ui/ui-inbox.png" width="420"> |
| **Context Health** — 生命周期仪表盘(衰减/冲突一目了然) | **Inbox** — 确认/丢弃纠正,反例审查 |
| <img src="assets/ui/ui-skills.png" width="420"> | <img src="assets/ui/ui-research.png" width="420"> |
| **Skills Library** — 50 个已注册工作流 | **Research Workspace** — 项目、证据、运行包 |

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
# DeepSeek Harness:dsh plugin --profile web add @xxinchen/dsh-plugin(或走 MCP → docs/dsh-integration.md)
```

Web 界面自动打开于 `http://127.0.0.1:8772` — 记忆健康仪表盘、3D 知识图谱、收件箱审核、专家面板。

### 配置与密钥(首次运行)

```bash
cp .env.example .env    # 编辑密钥
python -c "import secrets; print('MINTA_API_KEY=minta_'+secrets.token_hex(32))"  # 生成安全密钥
```

| 变量 | 默认 | 作用 |
|---|---|---|
| `MINTA_DATABASE_URL` | `sqlite:///./minta.db` | 零配置 SQLite;一行切 MySQL |
| `MINTA_JWT_SECRET` | *(必须设)* | 会话签名密钥——生成,别抄 |
| `MINTA_API_KEY` | 首次运行自动生成 | 程序化访问 + MCP(接编辑器 → `python minta_cli.py connect claude`) |

完整变量参考(SMTP、CORS、功能开关)→ [`docs/configuration.md`](docs/configuration.md)。编辑器接入 → [`docs/mcp-integration.md`](docs/mcp-integration.md)。

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

上表右侧的托管层属于**未来规划能力**——开放核心永远是完整可运行的记忆系统。

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


## DeepSeek Harness

已验证集成(2026-08):2 分钟内把 Minta 作为 DSH 的 MCP 服务器接入——`docs/dsh-integration.md` 有完整的 `cordis.patch.yml` 片段。开放核心插件包发布在 npm(`@xxinchen/dsh-plugin`)。

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
- 密钥:首次运行生成(`.minta_api_key`,永不提交);特权 API 默认关闭,除非显式配置。
- 披露策略见 `SECURITY.md`。

## 愿景:要去哪

记忆是简单的事,**真相才是产品**。agent 时代已经有很多"记更多"的系统,瓶颈反而是反面的:AI 自信地给出过期、矛盾或无据的声称。Minta 的答案是**上下文质量层**:记忆知道自己健康与否(`stale / conflict / redundant / fragile`),专家层知道自己的边界(校准覆盖),声称门控知道实际做过什么。长线叙事:

- **个人**:每个 AI 助手,每次会话都从"已理解你的上下文中枢"开始——停止重新上手你的 AI。
- **团队/企业**:记忆、专业、合规检查在课题组或临床单元间共享——带审计轨迹与治理报告。
- **垂直**:运动医学、临床分诊、制造专家包铺在同一引擎上,由用户纠错驱动(数据飞轮)。

## 社区与联系

- 🐛 **GitHub Issues** — bug、功能请求(响应快)
- 💬 **GitHub Discussions** — 问题、RFC、展示作品
- 📮 **科研联系** — 论文、合作、治理咨询:开 issue 打 `research` 标签或 Discussion 私信

## 求星

🔭 **如果 Minta 帮你省了一小时,点个 ★。** 一键,三秒——它会告诉下一位贡献者、集成者与审稿人:这个实验值得他们关注。

## 思想来源与传承

| 工作 | Minta 取什么 | Minta 不同在哪里 |
|---|---|---|
| **Mem0 / MemOS** | 记忆存储 + 混合检索 | 他们存,Minta *验*(衰减、冲突、冗余、碎片化) |
| **Vovk 2005, conformal** | 无分布覆盖保证 | 当作*元认知门*而非单纯估计器 |
| **JEPA(LeCun)** | 潜在空间预测而非原始空间 | 领域规则 > JEPA——有历史才预测 |
| **Ebbinghaus 遗忘(如 MemoryBank)** | 时间感知遗忘 | 类型特定半衰期:偏好 > 项目状态 |
| **Paperclip 文档维护** | 审计驱动维护 | 同一纪律,如今用于 AI 记忆而非文件 |

## 路线图

- **2026 Q4** — 托管 API(全精度、监控)、运动医学域包、npm 插件 v1
- **2027 Q1** — 企业私有化 + 治理审计报告;SME(结构映射)引擎公开
- **2027** — 多智能体共享记忆工作区(团队上下文层)

## 许可

Apache-2.0。上游捆绑资源保留各自许可证——后续若加入见 `skills/` 备注。
