---
name: counter-close
description: 关闭反例收集服务器 — 杀掉端口 18720 的 counter_server.py 进程。触发词：/反例关闭
type: skill
---

# 反例收集服务器关闭

## 触发方式

- `/反例关闭` — 关闭 counter_server.py 进程

## 执行流程

1. 查找占用端口 18720 的进程
2. 杀掉该进程
3. 确认端口已释放
4. 告知用户服务器已关闭

```bash
# Windows
netstat -ano | findstr 18720
for /f "tokens=5" %a in ('netstat -ano ^| findstr 18720 ^| findstr LISTENING') do taskkill /F /PID %a

# Unix
lsof -ti:18720 | xargs kill -9 2>/dev/null
```

## 注意

- 关闭后知识库面板的「反例收集」Tab 将回到只读模式
- 下次 `/反例面板` 会自动重启服务器
