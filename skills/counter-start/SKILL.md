---
name: counter-start
description: 启动反例收集服务器（端口 18720），不弹浏览器。触发词：/反例开启。对话结束后用 /反例关闭 关掉。
type: skill
---

# 反例收集服务器启动

## 触发方式

- `/反例开启` — 启动 counter_server.py，不打开浏览器

## 执行流程

1. 检查端口 18720 是否已被占用
2. 若已占用：告知用户"服务器已在运行"
3. 若未占用：后台启动 `python counter_server.py --no-browser`
4. 告知用户服务器已就绪

```bash
# 检查是否已运行
python -c "import socket; s=socket.socket(); s.settimeout(1); r=s.connect_ex(('127.0.0.1',18720)); s.close(); print('running' if r==0 else 'stopped')"
```

## 注意

- 启动后知识库面板的「反例收集」Tab 进入可编辑模式
- 对话结束后用 `/反例关闭` 关闭
- 服务器路径: `C:\Users\Lenovo\.claude\projects\C--Users-Lenovo\memory\counter_server.py`
