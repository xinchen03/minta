# Minta — 会自我检查的记忆系统

<p align="center">
  <img src="assets/logo.png" alt="Minta Logo" width="500">
</p>

<p align="center">
  <b>不止让 AI 记住，更让 AI 记对。<br>具备自我纠错能力的下一代 AI 记忆引擎。</b>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.9%2B-green"></a>
  <a href="#"><img src="https://img.shields.io/badge/MCP-19%20tools-purple"></a>
  <a href="README.md"><img src="https://img.shields.io/badge/lang-EN-blue"></a>
</p>

> **一个具备自我纠错与记忆质量治理能力的 AI 记忆引擎。**

---

**目录** [多模态能力](#minta-能处理什么) · [快速开始](#️-30-秒上手) · [记忆健康](#差异不只有记忆更有记忆健康) · [部署指南](#保持连接所有-agent-通用) · [基准测试](#-基准测试) · [架构](#️-架构) · [对比竞品](#-vs-竞品) · [研究](#-研究基础) · [愿景](#-我们在往哪走) · [协议](#-协议)

---

## 你遇到过。

你告诉 AI 助手"我把认证从 NextAuth 换成了 Clerk"。两周后，它自信地给你推荐 NextAuth 的配置方案。

你说过团队从 3 人扩到了 7 人。AI 还在问"你的 3 人小团队最近怎么样？"

你和它一起做了 3 个月的项目。但当你问"我现在用的什么框架？"，它在 10,000 条散落的记忆里翻找、猜测、答错。

**这不是 bug。这是记忆衰退。** 每一个记住你的 AI，都在被过时的事实、矛盾的偏好、重复的信息慢慢填满。没有人在检查。

## 我们在检查。

Minta 是 AI 时代的**第一个记忆质量层**。所有记忆系统都在追求"存得更多"，Minta 追求的是"保持正确"。

| 别人做什么 | Minta 做什么 |
|-----------|------------|
| "这是你相关的记忆" | "2 条冲突。1 条过期。真相在这里。" |
| 所有东西永远存着 | 检测过期、标记、归档 |
| 所有记忆一视同仁 | 分类型衰减：偏好比项目状态更持久 |
| 寄希望于 LLM 自己判断 | 跑一次生命周期扫描，给你健康分数，让你决定 |

## 差异：不只有记忆，更有记忆健康

其他记忆系统像个硬盘——存着就行。Minta 像个免疫系统——检测哪里出了问题。

**五大维度，持续监控记忆健康：**

```
D_S  过时率       "你 200 天前说的，现在还成立吗？"
D_R  冗余率       "同一件事你说了 3 遍。合并？"
D_C  冲突率       "这两条互相矛盾。哪个是对的？"
D_F  碎片率       "团队信息分散在 4 条记录里。聚类？"
D_V  完整率       "这条记忆没有来源。能信吗？"
```

全部本地计算，零 API 调用。你的数据不离开你的电脑。

## 故事：Alex 的 60 秒

Alex 是位创业者。他的 AI 编程助手陪他工作了 3 个月。但有些东西正在记忆里腐烂……

→ **安装后：** 运行 `minta start`，打开 `http://localhost:8772/story`。内置 25 条演示数据 + 6 个预设问题，看 Minta 如何在 1 秒内全部检测出来。

---

<p align="center">
  <video src="assets/demo.mp4" autoplay muted loop playsinline width="800"></video>
</p>

## Minta 能处理什么

Minta 接收你日常使用的所有内容。上线即稳定，路线图透明。

| | 状态 | 说明 |
|---|:---:|---|
| **文字 & 聊天** | ✅ 已上线 | 对话、文档、笔记——核心场景。一切变成可检索的记忆 |
| **图片 & 截图** | ✅ 已上线 | OCR + 图片描述。搜白板照片跟搜文字一样 |
| **邮件** | ✅ 已上线 | 解析 .eml 文件。你的收件箱成为记忆的一部分 |
| **语音** | 🔜 即将上线 | 会议录音、语音笔记——集成轻量，迭代快 |
| **视频** | 📋 规划中 | 视频抽帧 + 转写 + 场景识别——面向企业会议、培训 |

全程本地运行。不上传、不联网、三秒安装。

## ⚡ 30 秒上手

```bash
pip install minta
minta init                  # 首次配置（只做一次）
minta launch                # 启动服务 + 配置 AI
```

打开 http://localhost:8772 —— 你的记忆仪表盘已上线。

### 支持哪些 AI？

`minta launch` 自动为所有支持的编辑器配置 MCP。你的记忆跨平台跟随你。

| 命令 | AI 编辑器 | 做了什么 |
|------|----------|---------|
| `minta launch` | Claude Code（默认） | 写入 `~/.claude/settings.json` |
| `minta launch --cursor` | Cursor IDE | 写入 `~/.cursor/mcp.json` |
| `minta launch --codex` | Codex CLI | 写入 `~/.codex/mcp.json` |
| `minta launch --vscode` | VS Code / Copilot | 写入 `~/.vscode/mcp.json` |
| `minta launch --all` | 所有以上 | 一次性全部配置 |

### 日常使用

```bash
minta status               # 服务健康吗？
minta stop                 # 关闭后台服务
minta start                # 重新启动
```

### 保持连接（所有 Agent 通用）

MCP 是协议，不是启动器——每个 AI 在启动时读取 MCP 配置并尝试连接。你只需要让 Minta 先跑起来。

| 方法 | 操作 | 适用 |
|------|------|------|
| 一键桌面图标 | `Setup-Desktop-Shortcut.ps1`（Win）/ `.command`（Mac）/ Linux 用 `Start-Minta.sh` | 所有 Agent |
| 双击启动器 | `Start-Minta.vbs`（Win）/ `Start-Minta.sh`（Mac/Linux） | 所有 Agent |
| 开机自启 | Win: 启动文件夹 · Mac: LaunchAgent · Linux: autostart | 所有 Agent |
| Claude Code hooks | 复制 `hooks/` 到 Claude Code hooks 目录 | 仅 Claude Code |

<details>
<summary><b>macOS / Linux 详细设置</b></summary>

```bash
chmod +x Start-Minta.sh

# 开机自启 (macOS):
cp scripts/com.minta.starter.plist ~/Library/LaunchAgents/
# 然后编辑 plist 文件，把路径改成 minta-start-silent.sh 的完整路径

# 开机自启 (Linux):
cp scripts/minta-start-silent.sh ~/.config/autostart/
```
</details>

> **桌面端 / Web 端用户：** 静默启动器就是为你准备的。双击即跑，不用终端，Minta 在后台静默运行。然后打开你的 AI（Claude Desktop、Cursor、VS Code）——只要跑过一次 `minta launch --all`，就自动连接了。

### Docker

```bash
git clone https://github.com/xinchen03/minta.git && cd minta
docker compose up -d       # 启动 (http://localhost:8772)
docker compose down        # 停止
```

数据持久化在 Docker 卷中。MCP 运行在 `http://localhost:18721/mcp`。

---

## 🔌 MCP 工具

19 个工具，通过标准 MCP 协议可用：

| 类别 | 工具 |
|------|------|
| 上下文 CRUD | `minta_read_context`、`minta_write_context`、`minta_search_context`、`minta_get_pack`、`minta_get_slot`、`minta_update_slot` |
| 收件箱 | `minta_list_inbox`、`minta_append_inbox`、`minta_confirm_inbox`、`minta_discard_inbox` |
| 专家系统 | `minta_expert_infer`、`minta_expert_list`、`minta_expert_consult`、`minta_expert_trust`、`minta_expert_feedback` |
| 自动驾驶 | `minta_autopilot_preflight`、`minta_autopilot_postflight` |
| 认证 | `minta_login` |
| 对话 | `minta_chat` |

```bash
# 为你的 AI 编辑器自动配置：
minta connect           # Claude Code
minta connect --cursor  # Cursor IDE
minta connect --codex   # Codex CLI
minta connect --vscode  # VS Code / Copilot
minta connect --all     # 全部
```

---

## 🧠 Minta 独特之处

### 四大生命周期机制（零 LLM 成本）

| 机制 | 检测什么 | 怎么做 |
|------|---------|--------|
| **过时检测** | 太久没用的记忆 | 分类型指数衰减（100-200 天半衰期） |
| **冲突检测** | 互相矛盾的记忆 | 逻辑回归 + 否定绕过门控 |
| **冗余检测** | 几乎重复的记忆 | 余弦相似度 + 阈值校准 |
| **碎片检测** | 分散的相关记忆 | DBSCAN 聚类 + 共享标签 |

### 反例学习
Minta 检测到你纠正 AI → 自动捕获教训 → 永不再犯。

### 人机协作
所有自动发现进 **Inbox** 等待审核。不经你允许，什么都不改。

### 平台无关
生成 **Context Pack**，对接任何 AI —— Claude、ChatGPT、Gemini、Cursor、本地模型。

---

## 📊 基准测试

### 记忆质量（Minta 独有的指标分类——竞争对手没有）

| 检测维度 | 指标 | 得分 | Mem0 | Hindsight |
|---------|------|:---:|------|-----------|
| 冲突检测 | F₁ | 0.81（跨 5 个未见领域） | 无 | 无 |
| 过时检测 | UFA | 0.86（12 对事实模板） | 无 | 无 |
| 冗余压缩 | RR | 0.67（25 个聚类） | 无 | 无 |
| 碎片整合 | MCR | 0.746（15 个碎片集，中位 115d） | 无 | 无 |

> 所有指标在互斥评估集上测量，与标定数据无交叠。完整论文准备中。

### 我们也跑了标准测试

在 LoCoMo 基准上（10 段长对话、1,986 道题、11,958 条事实）：

| 测什么 | 结果 | 大白话 |
|--------|:----:|--------|
| 能找到正确的对话吗？ | **97.1%** | 几乎不会找错聊天记录 |
| 能找到正确的事实吗？ | **82.6%** | 在 12K 条细碎事实中精准定位 |
| 能回答正确吗？（AI 评判） | **53.1%** | 重排器已就绪，预计提升至 55-58% |

> 这是检索管线的常规测试。Minta 真正的贡献是上面的记忆质量四个指标——没人做过。

![效能对比图](assets/benchmark_comparison.png)

---

## 🏗️ 架构

```
┌──────────────────────────────────────────────────┐
│  Claude Code / Cursor / 任何 AI                   │
│         │  MCP（19 个工具）                       │
├─────────┼────────────────────────────────────────┤
│  Minta API 服务器 (:8772)                         │
│  ├── Context Objects（类型化记忆存储）             │
│  ├── Lifecycle Scanner（4 种检测机制）             │
│  ├── Autopilot（起飞前 / 降落后）                  │
│  └── Context Pack Builder（上下文包构建）           │
├──────────────────────────────────────────────────┤
│  存储层                                          │
│  ├── SQLite（结构化数据 + FTS5 全文搜索）          │
│  └── ChromaDB（向量嵌入，768 维）                  │
└──────────────────────────────────────────────────┘
```

**记忆分层：**
- **L0 工作记忆**（RAM）：7 个固定槽位，最近上下文（<1ms）
- **L1 近期记忆**（RAM 缓存 + 磁盘）：ChromaDB LRU + SQLite 页缓存（~5ms）
- **L2 长期记忆**（磁盘）：全量向量 + 文本存储（无限容量）

**零外部依赖。** 无需 Docker、无需 Redis、无需 API 密钥。

---

## 🆚 vs 竞品

### 功能矩阵

| | **Minta** | Mem0 | Letta | Zep | LangMem | Hindsight | MemoryLake |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **开源** | ✅ MIT | ✅ Apache 2.0 | ✅ Apache 2.0 | ✅ Community | ✅ MIT | ✅ MIT | ❌ |
| **本地优先** | ✅ pip install | ✅ SDK | ✅ pip | ❌ Neo4j+Docker | ✅ pip | ❌ Docker | ❌ Cloud |
| **结构化记忆类型** | ✅ 5 种 | ❌ 扁平 | ✅ Agent内 | ✅ 图 | ❌ 缓冲 | ❌ | ✅ 6 种 |
| **冲突检测** | ✅ F₁=0.81 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **过时检测** | ✅ 分类型 | ❌ | ❌ | ⚠️ 时间边 | ❌ | ❌ | ❌ |
| **冗余检测** | ✅ 余弦+Jaccard | ⚠️ 基础去重 | ❌ | ❌ | ❌ | ❌ | ❌ |
| **碎片检测** | ✅ DBSCAN | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **反例学习** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **人机协作（Inbox）** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Git 式版本** | ✅ Inbox审计 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **跨平台 Context Pack** | ✅ MCP | ❌ 仅API | ❌ | ❌ | ❌ | ❌ | ❌ |
| **多 Agent 共享** | ✅ | ❌ | ❌ 绑定Agent | ✅ | ❌ | ❌ | ✅ |
| **零 LLM 成本（生命周期）** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **MCP 协议** | ✅ 19 工具 | ❌ | ❌ | ❌ | ✅ SDK | ❌ | ❌ |

### LoCoMo 基准

| 系统 | 分数 | 备注 |
|------|:----:|------|
| MemoryLake | 94.03% | 闭源，纯云端 |
| Backboard | 90.1% | |
| Hindsight | 89.6% | 需 Docker |
| Memobase | 75.8% | |
| Zep | 75.1% | 需 Neo4j |
| Mem0 | 66.9% | 高级功能需付费 |
| LangMem | 58.1% | |
| **Minta** | **独特赛道** | 记忆质量四个指标——没人做过 |

> 来源：[Backboard.io LoCoMo 基准](https://github.com/Backboard-io/Backboard-Locomo-Benchmark)、Vectorize.io、ACL 2024。分数为各系统自报。Minta 不和其他系统比检索——我们测量的是一个全新的维度：**记忆质量**。

### 为什么 Minta 不一样

其他记忆系统帮 AI **记住更多**。Minta 帮 AI **记住对的**。

| | 其他记忆系统 | Minta |
|---|------------|-------|
| **冲突** | "这是你的 10 条相关记忆" | "3 条互相矛盾。这条是对的。" |
| **过时** | "我存了你的偏好" | "你的偏好 2 周前变了。现在更新。" |
| **纠正** | 反复犯同样的错误 | 从纠正中学习，永不再犯 |
| **质量** | 10,000 条记忆，15% 过期 | 10,000 条记忆，<1% 过期（自动维护） |
| **可迁移** | 锁定在一个 AI 里 | Context Pack 可给任何 AI 用 |

---

## 📄 研究基础

Minta 的记忆质量机制基于 **Context Debt 理论**——一个描述 AI 记忆如何退化以及如何检测退化的形式化框架。完整论文准备投稿中。

**核心发现：**
- 分类型衰减常数（S_type: 100-200 天半衰期），基于 N=60 人工标注校准
- 冲突检测：5 折交叉验证 F₁=0.683，跨 5 个未见领域 F₁=0.81
- 跨维度效应：孤立衰减干预会加剧碎片化——四个机制必须协同工作

所有基准测试、评估数据和标定参数均包含在本仓库中。

---

## 🔭 我们在往哪走

每个 AI 都需要记忆。但没有质量控制的记忆，只是一个带搜索功能的垃圾桶。

我们正在建设 AI 时代的**记忆质量层**——就像数据库有了 ACID、CI/CD 有了测试、代码有了 linting。记忆需要自己的正确性保障。Minta 就是这份保障。

**愿景：**

> 每个 AI 都将拥有记忆。问题不再是"它能记住吗？"——而是"它的记忆可信吗？"Minta 正在构建 AI 记忆的信任层。

**路线图：**

```
现在       记忆健康      过时、冲突、冗余、碎片。
                         四项没人测量的指标。零 API 调用。
                         文字、图片、邮件——全部离线解析。

下一步     记忆结构      从孤立的事实到活的知识图谱。
                         依赖自动发现，级联更新，
                         语音输入。信念随证据演化。

然后       记忆推理      一个能预测记忆如何变化的世界模型。
                         跨领域推理的专家系统。
                         视频处理——面向企业会议、培训。

未来       记忆平台      多模态、多租户、企业级。
                         面向领域专家的可视化规则编辑器。
                         MIT 开源内核。Pro 服务团队与垂直行业。
```

---

## 👥 加入我们

现在还很早。记忆质量这个品类还不存在——我们在创造它。

如果你在做 AI Agent、RAG 系统、或者个人 AI 助手，你一定感受过记忆衰退的问题。你知道光存储记忆不够——总要有人检查它们是否仍然正确。

**我们在找：**
- **早期用户**——在自己的 AI 工作流中跑 Minta。告诉我们哪里坏了。
- **贡献者**——核心引擎是 MIT 协议。图记忆、多模态接入、评估工具——选一个方向开始构建。
- **研究者**——如果你研究 Agent Memory、上下文工程或知识管理，来聊聊。Context Debt 框架完整文档化且可复现。
- **设计伙伴**——在构建需要可信记忆的 AI 产品？Minta 可以做你的记忆质量后端。

**这不是一份创业计划书。这是一份定义新赛道的邀请。**

→ [xxinchen03@gmail.com](mailto:xxinchen03@gmail.com) | [github.com/xinchen03/minta](https://github.com/xinchen03)

---

## 📜 协议

**开源范围：** 核心记忆引擎、全部四种质量检测机制、混合检索管线、MCP 工具、CLI、基准测试与评估脚本——完全开源（MIT）。企业级功能——多租户、可视化规则编辑器、领域专家模块与标定规则包——将在后续版本中分开发布。

核心引擎：**MIT** —— 自由使用、修改、分发。  
专家规则与标定数据：**BSL** —— 个人使用免费，商业使用需授权。

详见 [LICENSE](LICENSE)。

---

<p align="center">
  <b>Built by <a href="https://github.com/xinchen03">Xin Chen（陈鑫）</a></b>
</p>
