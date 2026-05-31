---
name: kb-audit
description: >
  审计 Minta 知识库健康度——检测陈旧条目、分类错误、断链、孤立文件、冗余内容。
  每次新增/修改知识库条目后或定期运行。输出审计报告，自动标记 stale 条目。
  灵感来自 Paperclip doc-maintenance 技能。
---

# 知识库审计技能

系统性检查 `memory/live/` 中所有知识条目的健康度，不重写内容，只报告问题。

## 触发时机

- 新增或修改 3 个以上知识库条目后
- 用户说"审计知识库""检查知识库""知识库健康度"
- 定期（每月至少一次）
- 发现 build_kb.py 报告 warnings 时

## 审计维度

### 1. 陈旧度检查
```
条件：updated > 90天 且非 canonical → 标记 stale
条件：freshness 评分 < 30 → 标记需更新
条件：引用已不存在的文件/路径 → 标记断链
```

### 2. 分类检查
- FILE_CATEGORY 中已映射的文件 → 确认映射正确
- 未映射的文件 → 报告缺失，建议分类
- type 字段与 category 不匹配 → 标记

### 3. 结构检查
- topic_id 相同的多条记忆 → 确认 canonical 标记正确
- replaces 指向的文件是否存在 → 断链检测
- 同 category 下 > 10 条 → 建议拆分

### 4. 联动性检查
- 应该互联但缺失交叉引用的条目对
- 例如：`reference_citation_standards.md` ↔ `reference_literature_databases.md` 应互相引用
- upstream/downstream 链是否完整

### 5. 内容检查
- body_html 为空或 < 100 字符 → 标记草稿
- preview/summary 缺失 → 标记
- tags 为空或 < 2 个 → 标记

## 审计流程

### Step 1 — 全量扫描
```bash
python ~/.claude/projects/C--Users-Lenovo/memory/build_kb.py --check
```
捕获 build_kb.py 内置的审计输出（陈旧度、重复 topic_id、canonical 冲突等）。

### Step 2 — 逐文件检查
对每个 `live/*.md`：
1. 读 frontmatter → 检查 type/status/canonical/replaces/topic_id
2. 读 body → 检查是否有 `[[link]]` 引用不存在的文件
3. 对照 FILE_CATEGORY → 检查分类映射
4. 计算 days_since_updated

### Step 3 — 交叉引用检查
对每条记忆：
1. 提取所有对其他 `live/*.md` 的引用
2. 检查被引用文件是否存在
3. 检查上下游链是否双向

### Step 4 — 生成审计报告
输出格式：
```
=== Minta 知识库审计报告 ===
日期: YYYY-MM-DD
总条目: N

## Critical (需立即处理)
- [file.md] 问题描述

## Warnings
- [file.md] 问题描述

## Suggestions
- [file.md] 建议

## 分类覆盖
身份档案: N | 领域知识: N | 学术写作: N | 竞赛工作流: N | 工具与方法: N | 宪章原则: N | 项目: N | 插件: N

## 联动健康
- 孤立条目（无交叉引用）: N
- 单向引用（缺少回链）: N
```

### Step 5 — 自动修复（可选）
- `--auto-fix`：自动归档 stale 条目、补写 FILE_CATEGORY 缺失映射
- 修复后自动运行 `build_kb.py` 同步

## 协同技能

- `pkb` — 五层知识模型加载/查询
- `skill-manager` — 技能注册状态检查
- `counter-capture` — 如果审计发现重复问题模式，自动登记反例
