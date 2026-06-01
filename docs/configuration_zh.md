# Minta 配置指南

> 🌐 中文 | [English](configuration.md)

Minta 所有可配置项——环境变量、数据库、邮件、CORS 等全覆盖。

---

## 目录

1. [快速上手：.env 文件](#快速上手env-文件)
2. [全部环境变量](#全部环境变量)
3. [数据库配置](#数据库配置)
4. [邮件验证（SMTP）](#邮件验证smtp)
5. [CORS 配置](#cors-配置)
6. [API 密钥管理](#api-密钥管理)
7. [Autopilot 设置](#autopilot-设置)
8. [专家系统设置](#专家系统设置)
9. [生产环境检查清单](#生产环境检查清单)

---

## 快速上手：.env 文件

Minta 从项目根目录的 `.env` 文件加载配置。复制示例文件并编辑：

```bash
cp .env.example .env
```

### 最小生产环境 .env

```bash
# 必填
MINTA_DATABASE_URL=sqlite:///./minta.db
MINTA_JWT_SECRET=<生成随机字符串>
MINTA_API_KEY=<生成随机字符串>
MINTA_ENV=production

# 可选（邮箱验证）
MINTA_SMTP_HOST=smtp.qq.com
MINTA_SMTP_PORT=465
MINTA_SMTP_USER=你的邮箱@qq.com
MINTA_SMTP_PASS=你的SMTP授权码
```

### 生成安全密钥

```bash
# 生成 JWT 密钥
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 生成 API 密钥
python -c "import secrets; print('minta_' + secrets.token_urlsafe(32))"
```

> ⚠️ **重要：** 生产环境中如果未设置 `MINTA_JWT_SECRET`，Minta 会**拒绝启动**并抛出 `RuntimeError`。这是有意为之——自动生成的 fallback 仅用于开发环境。

---

## 全部环境变量

### 核心设置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MINTA_ENV` | `production` | `production` 或 `development`。开发模式启用 `/docs`（Swagger UI）、宽松 CORS、更详细日志 |
| `MINTA_DATABASE_URL` | `sqlite:///./minta.db` | 数据库连接字符串。支持 SQLite、MySQL、PostgreSQL |
| `MINTA_JWT_SECRET` | 自动生成（仅开发） | JWT token 签名密钥。**生产环境必须设置** |
| `MINTA_API_KEY` | 自动生成 | 程序化访问和 MCP 工具的 API 密钥。首次运行自动生成 |

### 邮件（SMTP）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MINTA_SMTP_HOST` | `smtp.qq.com` | SMTP 服务器地址 |
| `MINTA_SMTP_PORT` | `465` | SMTP 端口（465 为 SSL，587 为 TLS） |
| `MINTA_SMTP_USER` | `""`（空） | SMTP 用户名/邮箱地址 |
| `MINTA_SMTP_PASS` | `""`（空） | SMTP 密码或授权码 |

> 💡 **说明：** 未配置 SMTP 时，开发环境中的邮箱验证自动通过。启动时会打印警告。

### CORS

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MINTA_CORS_ORIGINS` | `http://localhost:8772` | 逗号分隔的允许来源列表。仅 `production` 模式生效。开发模式允许所有来源（`*`） |

### 功能开关

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MINTA_EXPERT_ENABLED` | `true` | 启用/关闭专家推理系统 |
| `MINTA_AUTOPILOT_ENABLED` | `true` | 启用/关闭 Autopilot 记忆管理 |

### 高级选项

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MINTA_API_URL` | `http://127.0.0.1:8772` | Minta 服务地址（MCP HTTP 服务内部使用） |
| `MCP_HTTP_PORT` | `18721` | MCP HTTP 服务端口 |
| `MINTA_JWT_EXPIRE_MINUTES` | `1440`（24 小时） | JWT token 过期时间 |

---

## 数据库配置

### SQLite（默认——零配置）

```bash
# .env
MINTA_DATABASE_URL=sqlite:///./minta.db
```

无需额外配置。首次运行时自动在项目根目录创建数据库文件。

> ⚠️ SQLite 适合个人使用。多用户或高并发场景请使用 MySQL 或 PostgreSQL。

### MySQL

```bash
# .env
MINTA_DATABASE_URL=mysql+pymysql://用户名:密码@localhost:3306/minta
```

**安装依赖：**
```bash
pip install pymysql
```

**初始化数据库：**
```sql
CREATE DATABASE minta CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'minta'@'localhost' IDENTIFIED BY '你的密码';
GRANT ALL PRIVILEGES ON minta.* TO 'minta'@'localhost';
FLUSH PRIVILEGES;
```

表结构在首次启动时自动创建（`Base.metadata.create_all()`）。

### PostgreSQL

```bash
# .env
MINTA_DATABASE_URL=postgresql://用户名:密码@localhost:5432/minta
```

**安装依赖：**
```bash
pip install psycopg2-binary
```

**初始化数据库：**
```sql
CREATE DATABASE minta;
CREATE USER minta WITH PASSWORD '你的密码';
GRANT ALL PRIVILEGES ON DATABASE minta TO minta;
```

---

## 邮件验证（SMTP）

Minta 可以在注册时发送邮件验证码，需要 SMTP 配置。

### QQ 邮箱配置（推荐国内用户）

1. 登录 QQ 邮箱 → 设置 → 账户
2. 开启 **POP3/SMTP 服务**
3. 复制**授权码**（不是登录密码）
4. 在 `.env` 中配置：

```bash
MINTA_SMTP_HOST=smtp.qq.com
MINTA_SMTP_PORT=465
MINTA_SMTP_USER=你的邮箱@qq.com
MINTA_SMTP_PASS=你的授权码
```

### Gmail 配置

1. 在 Google 账户中开启**两步验证**
2. 生成**应用专用密码**（Google 账户 → 安全 → 应用密码）
3. 在 `.env` 中配置：

```bash
MINTA_SMTP_HOST=smtp.gmail.com
MINTA_SMTP_PORT=587
MINTA_SMTP_USER=你的邮箱@gmail.com
MINTA_SMTP_PASS=你的应用密码
```

### 测试邮件

```bash
# 配置好 SMTP 后，注册一个新用户，检查是否收到验证邮件
minta start
# 然后 POST 到 /api/auth/register
```

如果 SMTP 未配置，Minta 会打印警告，开发环境中自动通过验证。

---

## CORS 配置

### 开发环境（宽松）

```bash
MINTA_ENV=development
# CORS：允许所有来源 (*)
# /docs：启用
```

### 生产环境（严格）

```bash
MINTA_ENV=production
MINTA_CORS_ORIGINS=http://localhost:8772,https://你的域名.com
# CORS：仅允许列出的来源
# /docs：隐藏
```

### 常见 CORS 场景

**仅本地开发：**
```bash
MINTA_CORS_ORIGINS=http://localhost:8772
```

**配合反向代理（Nginx）：**
```bash
MINTA_CORS_ORIGINS=https://minta.你的域名.com
```

**多来源：**
```bash
MINTA_CORS_ORIGINS=http://localhost:8772,http://localhost:3000,https://minta.example.com
```

> ⚠️ 生产环境绝不能用 `MINTA_CORS_ORIGINS=*`。有安全风险。如需临时放宽，用 `MINTA_ENV=development`。

---

## API 密钥管理

### 内置 API 密钥

首次运行时，Minta 自动生成 API 密钥并保存到 `.minta_api_key`（文件权限 `0600`）。可以覆盖：

```bash
MINTA_API_KEY=minta_你的自定义密钥
```

### 创建额外 API 密钥

1. 登录仪表盘
2. 进入**设置 → API 密钥**
3. 点击**创建新密钥**
4. 立即复制密钥——只显示一次

### 使用 API 密钥

```bash
# HTTP 请求中
curl -H "X-API-Key: minta_……" http://localhost:8772/api/contextObjects/stats

# MCP 工具（自动）
# MCP 服务从环境变量读取 MINTA_API_KEY
```

### 吊销密钥

```bash
# 通过 API
curl -X DELETE -H "X-API-Key: minta_……" http://localhost:8772/api/keys/{密钥ID}

# 或在仪表盘 → 设置 → API 密钥 → 吊销
```

---

## Autopilot 设置

**Autopilot** 是 Minta 的记忆管理 agent。在 AI 对话前自动读取上下文，对话后自动建议记忆更新。

### 启用/关闭

```bash
# .env 中
MINTA_AUTOPILOT_ENABLED=true   # 启用（默认）
MINTA_AUTOPILOT_ENABLED=false  # 关闭
```

### 工作原理

1. **Preflight**（`/api/autopilot/preflight`）：分析你的消息，检索相关记忆
2. **Postflight**（`/api/autopilot/postflight`）：分析对话，决定是否：
   - 写入新记忆
   - 捕获反例（纠正）
   - 更新已有记忆

### 决策日志

Autopilot 决策可追溯：
- `GET /api/autopilot/logs` — 查看最近决策
- `GET /api/autopilot/status` — 检查 Autopilot 健康状态

---

## 专家系统设置

专家系统将临床决策规则编译为生产规则。

### 启用/关闭

```bash
MINTA_EXPERT_ENABLED=true   # 启用（默认）
MINTA_EXPERT_ENABLED=false  # 关闭
```

### 默认专家领域

首次启动且无已有规则时，Minta 自动编译三个领域：
- **Ottawa 踝关节规则**（Stiell 1992, JAMA）
- **Ottawa 膝关节规则**（Stiell 1996, JAMA）
- **加拿大颈椎规则**（Stiell 2001, JAMA）

### 生命周期自动扫描

自动扫描器按计划检查记忆健康：

```bash
# 查看当前设置
curl http://localhost:8772/api/lifecycle/auto-scan/status

# 修改间隔（1 小时到 7 天）
curl -X POST "http://localhost:8772/api/lifecycle/auto-scan/interval?hours=12"

# 开关
curl -X POST "http://localhost:8772/api/lifecycle/auto-scan/toggle?enabled=true"
```

设置持久化到 `data/auto_scan_config.json`。

---

## 生产环境检查清单

部署 Minta 到生产环境前：

- [ ] 设置 `MINTA_ENV=production`
- [ ] 生成强 `MINTA_JWT_SECRET`（≥32 字节随机）
- [ ] 生成强 `MINTA_API_KEY`
- [ ] 配置 `MINTA_CORS_ORIGINS` 为实际域名
- [ ] 使用正式数据库（MySQL 或 PostgreSQL，不用 SQLite）
- [ ] 配置 SMTP 用于邮箱验证
- [ ] 用反向代理（Nginx/Caddy）+ HTTPS
- [ ] 检查安全头（HSTS、X-Frame-Options 等默认已开启）
- [ ] 阅读 [SECURITY.md](../../SECURITY.md) 了解漏洞报告流程

### Nginx 反向代理示例

```nginx
server {
    listen 443 ssl;
    server_name minta.example.com;

    ssl_certificate /etc/ssl/certs/minta.pem;
    ssl_certificate_key /etc/ssl/private/minta.key;

    location / {
        proxy_pass http://127.0.0.1:8772;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> 💡 Minta 默认绑定 `127.0.0.1`，放在反向代理后面无需额外的防火墙规则就能安全运行。
