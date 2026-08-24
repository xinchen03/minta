# DSH × Minta 接入指南(已验证)

> 2026-08-23 全链路验证通过: Minta MCP(18721, streamable-http) → DSH `mcp-client` → 会话 19 工具(`mcp__minta__*`)

## 前置条件

1. 本机 Minta 引擎运行: `python minta_cli.py start`
   - 确认健康: `minta_cli.py status` → Data API :8772 / Autopilot :18730 / MCP HTTP :18721 全 RUNNING
2. DeepSeek Harness 已安装: `npx @deepseek-ai/dsh web`(配好 DeepSeek API Key)

## 接入(2 分钟, 推荐)

安装插件包, MCP 行由 bundle patch 自动合成, 无需手改配置:

```bash
dsh plugin --profile web add @xxinchen/dsh-plugin
```

重启 web: `Ctrl+C` 后重新 `npx @deepseek-ai/dsh web`。

验证: 新会话问一句 "列出所有名字带 minta 的工具"。
预期: 19 个 `mcp__minta__*` 工具(login / read/write/search_context / get_pack / get_slot / update_slot / append/list/confirm/discard_inbox / autopilot_preflight / autopilot_postflight / chat / expert_list / infer / consult / trust / feedback)。

> 插件包只做一件事: 把下面的 mcp-client 行合入 profile。引擎(单独部署)提供全部能力。
> 想检查合成结果: `npx @deepseek-ai/dsh --profile web --dump-config | grep mcp-client-minta`
>
> **迁移用户注意**: 若你之前按旧教程手动在 `cordis.patch.yml` 里加过 `mcp-client-minta` 块, 装插件前必须先删掉它——bundle patch 与手动块插入同一 loader entry id, 并存时 boot 直接失败(`duplicate loader entry id: mcp-client-minta`)。检查: `grep -A6 mcp-client-minta ~/.dsh/profiles/web/cordis.patch.yml`(无输出即干净)。

## 手动接入(不装 npm 包时的备选)

在 `~/.dsh/profiles/web/cordis.patch.yml` 追加(或新建):

```yaml
# Minta context layer — MCP server (streamable HTTP at 127.0.0.1:18721)
- insert:
    - id: mcp-client-minta
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        transport: streamable-http
        serverName: minta
        url: http://127.0.0.1:18721/mcp
        failOnStartupError: false
```

重启 web 后同上验证。

## 字段说明(mcp-client Config, 来自官方 schema)

- `transport`: `stdio`(spawn 子进程) 或 `streamable-http`(连 URL, Minta 用这个)
- `serverName`: 唯一命名空间(mcp 工具前缀 `mcp__<serverName>__`)
- stdio 分支字段: `command` / `args` / `env` / `cwd`; http 分支: `url` / `headers`
- `failOnStartupError`: false 时引擎没起也不会拖垮 DSH 会话
- `reconnect`: {enabled, initialDelayMs, maxDelayMs, maxAttempts}

## 注意(避坑记录)

- **错误的写法**: package.json 里 `dsh.mcpServers` 字段目前不被 DSH 消费(无效果), 不要用它
- 插件 bundle(`dsh.bundle.patch`)把 patch 层合入 profile 配置树; MCP 连接本身走 `mcp-client` 插件行
- profile 是隔离的: 插件/配置按 `--profile web / headless` 各自独立, 改 web 要重启 web
- 无密钥时 web 可开但模型不可用; Minta 工具与模型无关, 登录用 `minta_login` 即可

## 未来演进

- v2 插件目标: DSH 生命周期插件(agent/pre-step 时 `autopilot_preflight`, turn/end 时 `autopilot_postflight`)—— 把记忆治理做成"自动"而不是"工具"
- 领域技能包(数模 CUMCM 10 阶段 / 科研论文)以 `dsh.skills` 形式发布
