# ASGI模式启动说明

## 概述

为了解决Flask与LangGraph异步事件循环冲突问题（"Event loop is closed"错误），我们将Flask应用改为使用ASGI适配器启动。这样可以获得真正的异步支持，允许LangGraph的checkpoint保存在请求完成后继续执行。

## 问题背景

原本的错误：
```
redisvl.exceptions.RedisSearchError: Unexpected error while searching: Event loop is closed
```

这个错误发生在Flask路由处理完成后，LangGraph尝试异步保存checkpoint时事件循环已被关闭。

## 解决方案

使用ASGI适配器（`WsgiToAsgi`）将Flask WSGI应用包装为ASGI应用，然后使用uvicorn ASGI服务器运行，获得持久化事件循环支持。

## 安装依赖

```bash
# 进入项目目录
cd test/custom_react_agent

# 安装ASGI依赖
pip install uvicorn asgiref

# 或者安装所有依赖
pip install -r requirements.txt
```

## 启动方式

### 方式1：直接运行api.py（推荐）

```bash
cd test/custom_react_agent
python api.py
```

**说明**：
- 会自动尝试使用ASGI模式启动
- 如果缺少依赖，会fallback到传统Flask模式
- 支持Ctrl+C优雅关闭

**启动日志示例**：
```
🚀 使用ASGI模式启动异步Flask应用...
   这将解决事件循环冲突问题，支持LangGraph异步checkpoint保存
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 方式2：使用uvicorn命令行启动

```bash
cd test/custom_react_agent

# 启动ASGI应用
uvicorn asgi_app:asgi_app --host 0.0.0.0 --port 8000

# 开发模式（自动重载）
uvicorn asgi_app:asgi_app --host 0.0.0.0 --port 8000 --reload

# 生产模式（多worker）
uvicorn asgi_app:asgi_app --host 0.0.0.0 --port 8000 --workers 4
```

### 方式3：传统Flask模式（不推荐）

如果ASGI依赖安装失败，会自动fallback到传统Flask模式：

```
⚠️ ASGI依赖缺失，使用传统Flask模式启动
   建议安装: pip install uvicorn asgiref
   传统模式可能存在异步事件循环冲突问题
```

## 测试API

启动后，可以测试API：

```bash
# 测试健康检查
curl http://localhost:8000/health

# 测试聊天API
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "question": "请问下一届足球世界杯在哪里举行?"
  }'
```

## 预期效果

1. **完全解决"Event loop is closed"错误**
2. **LangGraph checkpoint正常保存**
3. **支持连续多次API调用**
4. **保持所有现有功能**

## 验证成功

如果修复成功，您应该看到：
- API响应正常
- 日志中没有"Event loop is closed"错误
- 对话状态正确保存
- 连续请求都能正常处理

## 故障排除

### 如果依然出现事件循环错误：

1. **确认使用ASGI模式**：检查启动日志是否显示"使用ASGI模式启动"
2. **检查依赖版本**：确保uvicorn和asgiref版本符合要求
3. **重启服务**：完全重启API服务
4. **检查Redis连接**：确保Redis服务正常运行

### 常见问题：

**Q: ImportError: No module named 'uvicorn'**
A: 运行 `pip install uvicorn asgiref`

**Q: 启动时提示权限错误**
A: 尝试更换端口：`python api.py` 或在代码中修改端口号

**Q: 仍然出现异步错误**
A: 检查是否真的使用了ASGI模式，查看启动日志确认

## 技术说明

### ASGI vs WSGI

- **WSGI（原来）**：同步协议，每个请求结束后关闭事件循环
- **ASGI（现在）**：异步协议，保持事件循环活跃，支持异步任务

### WsgiToAsgi适配器

- 无缝将Flask WSGI应用转换为ASGI兼容
- 保持所有Flask代码不变
- 获得真正的异步支持

## 文件说明

- `api.py`：主要API文件，包含自动ASGI启动逻辑
- `asgi_app.py`：独立ASGI应用文件，用于uvicorn命令行启动
- `requirements.txt`：所需依赖列表
- `ASGI_启动说明.md`：本文档

## 成功案例

修复后的API调用应该像这样工作：

```bash
# 第一次请求
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"user_id":"polo","question":"你好"}'
# ✅ 成功响应

# 第二次请求（之前会失败）
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"user_id":"polo","question":"请问下一届足球世界杯在哪里举行?"}'
# ✅ 成功响应，无事件循环错误
```

---

如有问题，请检查启动日志和错误信息。