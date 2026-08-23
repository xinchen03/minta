# Minta Architecture Overview

> Personal Context Layer — AI 时代的上下文基础设施
> 用于决定论文选题方向的完整架构参考

---

## 一、系统架构图

```
┌─────────────────────────────────────────────────────────┐
│                   用户浏览器 (Web App)                     │
│  React 18 + TypeScript + Tailwind + Three.js             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │ 抽卡交互  │ │ Brief    │ │ 卡片网格  │ │ 3D 知识图谱│  │
│  │ CardDraw │ │ Builder  │ │ Context  │ │ Knowledge │  │
│  │          │ │ (M3)     │ │ Objects  │ │ Graph     │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │ 收件箱    │ │ 搜索/筛选 │ │ 设置     │ │ Admin后台  │  │
│  │ Inbox    │ │ Filter   │ │ Settings │ │ (xinChen)  │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP (fetch /api/*)
                       ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI Server (port 8772)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │ Auth     │ │ Context  │ │ Inbox    │ │ Comments  │  │
│  │ 注册/登录 │ │ Objects  │ │ 收件箱   │ │ 评论      │  │
│  │ JWT/API  │ │ CRUD     │ │ 归档/分类 │ │ 审核/回复 │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │ API Keys │ │ Skills   │ │ Upload   │ │ Admin     │  │
│  │ 密钥管理  │ │ 技能库   │ │ 头像/封面 │ │ 用户统计  │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘  │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Email Verification (QQ SMTP)                     │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       │ SQLAlchemy ORM
                       ▼
┌─────────────────────────────────────────────────────────┐
│              MySQL 8.0 Database                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │ users    │ │ context  │ │ inbox    │ │ comments  │  │
│  │ id,      │ │ _objects  │ │ _items   │ │ id,       │  │
│  │ username │ │ id,      │ │ id,      │ │ object_id │  │
│  │ email    │ │ user_id  │ │ user_id  │ │ user_id   │  │
│  │ password │ │ type     │ │ text     │ │ content   │  │
│  │ avatar   │ │ title    │ │ conf     │ │ parent_id │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘  │
│  ┌──────────┐ ┌──────────┐                               │
│  │ api_keys │ │ skills   │  (5 表 + 3 索引)              │
│  └──────────┘ └──────────┘                               │
└──────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│              MCP Server Layer                             │
│                                                          │
│  ┌─────────────────┐    ┌─────────────────────────┐     │
│  │ minta_mcp.py    │    │ minta_mcp_http.py       │     │
│  │ Stdio Transport │    │ HTTP/SSE Transport      │     │
│  │ (本地 Agent)     │    │ (远程 Agent, 端口18721)  │     │
│  │                 │    │                         │     │
│  │ Tools:          │    │ POST /mcp → 相同 tools  │     │
│  │  minta_login    │    │ GET  /health            │     │
│  │  minta_read     │    │                         │     │
│  │  minta_write    │    │ 适配: Cursor / Cline /  │     │
│  │  minta_append   │    │ 通义灵码 / TRAE / Codex │     │
│  │  minta_search   │    │ 华为云码道 / 文心快码   │     │
│  └─────────────────┘    └─────────────────────────┘     │
│                                                          │
│  所有工具 → 调用 FastAPI (127.0.0.1:8772)               │
└──────────────────────────────────────────────────────────┘
```

---

## 二、后端文件清单 (server/)

### 核心层
| 文件 | 职责 | 关键内容 |
|------|------|---------|
| `main.py` | 入口 + CORS + 日志中间件 + 静态文件服务 | 生产模式同时也 Serve 前端 |
| `config.py` | MySQL 连接 + SMTP 配置（全部支持环境变量） | `MINTA_DATABASE_URL`, `MINTA_SMTP_*` |
| `key_utils.py` | API Key 生成/验证（bcrypt hash） | `minta_` 前缀 + 随机 32 位 |

### ORM 模型 (models/)
| 文件 | 表名 | 字段 |
|------|------|------|
| `context_object.py` | `context_objects` | id, user_id, type, title, summary, body, tags(JSON), source, status, confidence, cover_image, is_public, created_at, updated_at |
| `inbox.py` | `inbox_items` | id, user_id, text, type, confidence, tags(JSON), status(pending/archived), created_at |
| `api_key.py` | `api_keys` | id, user_id, name, key_prefix, key_hash, last_used_at, request_count, revoked |
| `skill.py` | `skills` | id, name, name_zh, group, color, icon, description, tags(JSON) |

### 路由 (routers/)
| 文件 | 路径前缀 | 核心 API | 认证 |
|------|----------|----------|------|
| `auth.py` | `/api/auth` | POST login, register / GET me / PATCH me | JWT / API Key |
| `context_objects.py` | `/api/contextObjects` | GET list, POST create, DELETE /{id}, GET /stats | JWT (user_id 隔离) |
| `inbox.py` | `/api/inbox` | GET (pending+archived), POST archive/discard/append | JWT |
| `comments.py` | `/api/comments` | GET /{objectId}, POST create（内容审核+限流） | JWT |
| `api_keys.py` | `/api/keys` | GET list, POST create, DELETE /{id} | JWT |
| `skills.py` | `/api/skills` | GET list（按 user_id 隔离） | JWT |
| `upload.py` | `/api/upload` | POST /cover, POST /avatar | 无（公开上传后配） |
| `verification.py` | `/api/auth` | POST /send-code, POST /verify-code | QQ SMTP |
| `admin.py` | `/api/admin` | GET /stats, GET /users（仅 xinChen） | JWT + id=8 检查 |

---

## 三、前端文件清单 (web/src/)

### 入口 & 路由
| 文件 | 职责 |
|------|------|
| `app/App.tsx` | HashRouter + AuthProvider + BriefSelectionProvider |
| `contexts/AuthContext.tsx` | 全局认证状态（token/username/email/avatarUrl） |
| `contexts/LanguageContext.tsx` | 中英文切换 |

### 主页面 (features/organize/)
| 文件 | 职责 |
|------|------|
| `KnowledgeBase.tsx` | 三列布局编排器（~400 行），集成所有面板 |
| `KnowledgeGraph.tsx` | Three.js 3D 知识图谱（节点+连线+点击跳转+标签） |
| `HeroSection.tsx` | Three.js Shader 品牌动画 |
| `SkillsSection.tsx` | 技能库展示 |
| `Dashboard.tsx` | Context Health 统计仪表盘 |

### 核心功能 (features/)
| 模块 | 文件 | 功能 |
|------|------|------|
| **抽卡** | `recall/CardDraw/` (8 文件) | 卡堆→抽取→翻转→View Details/Add to Brief/Draw another |
| **社区抽卡** | `recall/CardDraw/community-demo.ts` | 12 条精选 + Source 切换 + Save to My Library |
| **Brief** | `recall/BriefBuilder/` (2 文件) | M3: 选场景→选卡片→生成 Context Pack→一键复制 |
| **收件箱** | `continue/InboxPanel.tsx` | 反例审核→分类→归档/丢弃（对接 MySQL API） |
| **搜索** | `search/` (3 文件) | FilterPanel + SortOptions + 实时过滤 |
| **设置** | `settings/` (3 文件) | 头像上传/邮箱编辑/语言/外观/API Key 管理 |
| **登录** | `auth/LoginPage.tsx` | 侧分式登录/注册 + 邮箱验证接入口 |
| **管理** | `admin/AdminPanel.tsx` | 用户列表+系统统计（仅 xinChen） |
| **新建** | `capture/CaptureForm.tsx` | M4: 新建 Context Object 表单 |

### 组件 (components/)
| 文件 | 职责 |
|------|------|
| `DetailModal.tsx` | 详情弹窗（Markdown 渲染+评论+分享+删除） |
| `Sidebar.tsx` | 左侧导航栏 |
| `TocPanel.tsx` | 右侧目录面板 |
| `cards/ContextObjectCard.tsx` | 知识卡片 |
| `cards/SkillCard.tsx` | 技能卡片 |

### 支撑
| 文件 | 职责 |
|------|------|
| `services/api.ts` | HTTP 请求封装（fetch + JWT 注入 + 所有 API 方法） |
| `types/index.ts` | 全局 TypeScript 类型 |
| `domain/*/` | Zod 运行时校验 schema |
| `design-system/tokens.ts` | 品牌设计 token |

---

## 四、MCP Server 层

### minta_mcp.py（Stdio 传输）
- JSON-RPC 2.0 over stdin/stdout
- 5 tools: login / read_context / write_context / append_inbox / search_context
- 每个 tool 接收 username+password，内部调用 FastAPI（8772）
- 部署配置：`.mcp.json` + `enabledMcpjsonServers`

### minta_mcp_http.py（HTTP 传输）
- FastAPI 包装，端口 18721
- `POST /mcp` 端点兼容 Streamable HTTP 协议
- 适配 Cursor / Cline / 通义灵码 / TRAE / 文心快码 / 华为云码道

---

## 五、用户数据流

```
用户注册 → users 表（每用户一行，user_id 自增）
         → 登录返回 JWT → 前端存 localStorage
         → 后续请求 Header: Authorization Bearer <JWT>

用户创建 Context → POST /api/contextObjects → context_objects 表（user_id 绑定）
用户写反例 → POST /api/inbox/append → inbox_items 表（user_id 绑定）
用户评论 → POST /api/comments → comments 表（user_id 绑定）
用户生成 Key → POST /api/keys → api_keys 表（user_id 绑定）

用户用 Agent → Agent 调 MCP → MCP 调 FastAPI → 读写对应 user_id 的数据
               （username+password 认证 → 服务端查询该用户的 user_id）
```

**所有数据按 user_id 隔离**，用户只能读写自己的数据。你（admin）可以查全部。

---

## 六、设计原则

1. **Context 优先** — 所有设计围绕"让 AI 理解用户"展开，不是知识管理工具
2. **API 驱动** — 一切功能通过 API 暴露，前端和 MCP 共享同一层
3. **用户隔离** — 数据按 user_id 严格隔离，API 层 JWT 自动过滤
4. **渐进采用** — 网页版覆盖 80% 功能，MCP 覆盖 20% 的"AI 自动化"体验
5. **最小侵入** — MCP 不劫持 agent 行为，只提供工具，行为规则在 Agent Profile 里
6. **环境配置** — 所有密钥/连接串支持环境变量，不硬编码
7. **去重优先** — 反例捕获有去重+冷却，不重复写相同数据

---

## 七、当前状态

| 维度 | 完成度 |
|------|--------|
| 后端 API | 12 路由，30+ 端点，完整 CRUD |
| 前端功能 | 8 个功能模块，50+ 组件 |
| 用户系统 | 注册/登录/JWT/API Key/邮箱验证 |
| MCP 集成 | Stdio + HTTP, 10 种 Agent 配置指南 |
| 安全 | 环境变量 + 数据隔离 + 内容审核 |
| 部署 | 单进程生产模式，requirements.txt 就绪 |
| **论文数据收集** | **缺用户行为日志埋点 + 实验设计** |
