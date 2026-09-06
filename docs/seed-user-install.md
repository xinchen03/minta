# Minta 种子用户 3 分钟安装卡

> 来源：GitHub 公开版（[xinchen03/minta](https://github.com/xinchen03/minta)）。
> 你的记忆存在**你自己电脑里**，Minta 从不把记忆内容上传任何地方。

## 你属于哪种人？走对应的路线

### 🅰 用 AI 编程工具的（Claude Code / Cursor / DSH / Codex）——推荐路径

```bash
# 1. 下载源码 ZIP（GitHub -> Code -> Download ZIP -> 解压）
# 2. Windows：解压后文件夹里双击 start_minta.bat
#    （自动装依赖 + 起引擎 8772 + 弹网页 + 菜单选你的编辑器）
#    macOS/Linux： python minta_cli.py start
# 3. 弹窗菜单里选 1/2/3/4 = 自动连接并启动对应编辑器
#    需要手动时：
#    DSH:    dsh plugin --profile web add @xxinchen/dsh-plugin
#    Claude Code: python minta_cli.py connect --claude
```

### 🅱 只想看看效果（不看代码）

```bash
# Windows 双击 start_minta.bat（会自动弹浏览器）
# 或手动：python minta_cli.py start
# 浏览器打开 http://localhost:8772 —— 记忆健康看板 + 收件箱
# 按 skills/minta-quickstart 的三步走：教它一句经验 -> 收件箱确认 -> 下次自动用
```

### 🅲 想装 Docker（不装 Python）

```bash
docker compose up -d   # 起 8772/18721；数据在 minta_data 卷
# 然后同上，打开 http://localhost:8772
```

## 3 分钟体验（所有路线通用）

1. 在 AI 对话里说一句经验，如："以后回答前先说一句你试过什么"
2. 打开 `http://127.0.0.1:8772` → 收件箱 → 点"确认"
3. 继续聊天。下次开会话它自动带着这条记忆

## 想支持项目（可选，默认关）

把下面两行存成 `.env` 文件（和 minta_cli.py 同目录）：

```
MINTA_TELEMETRY=1
MINTA_TELEMETRY_POSTHOG_KEY=phc_AY3tBursmTQMZLkGn9QKz75o6feyJCKuTWnruh9dLB5q
```

只上报安装/版本/活跃时间，**不含任何记忆内容**。不填=无任何上报。
