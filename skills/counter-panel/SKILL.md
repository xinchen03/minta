---
name: counter-panel
description: 反例收集管理面板 — 启动本地服务器，在知识库 HTML 中打开反例收集 Tab，支持勾选、编辑、一键处理、置信度调整。
type: skill
---

# 反例收集管理面板

## 触发方式

- `/反例开启` — 仅启动服务器，不弹浏览器
- `/反例面板` — 启动服务器 + 打开管理面板
- `/反例关闭` — 关闭服务器
- `/反例整理` — 纯命令行归档（不用面板时）

## `/反例面板` 执行流程

1. 检查 `counter_server.py` 服务器是否已在运行（端口 18720）
2. 若未运行，启动服务器：
   ```bash
   python "C:\Users\Lenovo\.claude\projects\C--Users-Lenovo\memory\counter_server.py"
   ```
   在后台运行
3. 若已运行，直接在浏览器打开 `http://127.0.0.1:18720/`
4. 告知用户面板已打开

> 服务器会读取 counter-inbox.md 并将数据注入知识库 HTML，
> 面板中的编辑操作通过 API 写回文件。

## `/反例整理` 执行流程（命令行版）

1. Read `memory/.remember/counter-inbox.md`
2. 逐条解析未归档条目
3. 按模板格式化，追加到 `memory/feedback_counter-examples.md` 的反例列表区域
4. 从收件箱中删除已归档条目（或标记为 archived）
5. 汇报整理结果：条数、标签分布
6. 更新 feedback_counter-examples.md frontmatter 中的统计信息

## 面板功能

| 功能 | 说明 |
|------|------|
| 分栏视图 | 全部 / 待处理 / 低置信 / 已跳过 / 已归档 |
| 勾选 + 批量操作 | 一键处理 / 跳过 / 删除 |
| 置信度滑块 | 0.0-1.0，低于 0.6 归入低置信 |
| 过期高亮 | 超过 14 天未处理橙色标记 |
| 矛盾检测 | 逻辑互斥条目标红 [!contradiction] |
| 编辑 | 点击条目修改文字、置信度、标签、状态 |
| 只读模式 | 无服务器时仍可查看和复制格式化输出 |
