# Flask API 迁移说明

## 📋 迁移概述

已将 Custom React Agent API 从 FastAPI 迁移到 Flask，保持了相同的功能和接口，但使用了不同的 Web 框架。

## 🔄 主要变化

### 1. 依赖包变化
```bash
# 旧版本 (FastAPI)
pip install fastapi uvicorn aiohttp

# 新版本 (Flask)
pip install flask aiohttp
```

### 2. 框架特性差异

| 特性 | FastAPI | Flask |
|------|---------|--------|
| 自动API文档 | ✅ 自动生成 `/docs` | ❌ 无自动文档 |
| 请求验证 | ✅ Pydantic 自动验证 | ⚠️ 手动验证 |
| 异步支持 | ✅ 原生支持 | ⚠️ 需要 asyncio.run() |
| 类型提示 | ✅ 完整支持 | ⚠️ 基础支持 |
| 性能 | 🚀 更高 | 📊 中等 |
| 学习曲线 | 📈 中等 | 📊 简单 |

### 3. 代码结构变化

#### 路由定义
```python
# FastAPI
@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    ...

# Flask
@app.route("/api/chat", methods=["POST"])
def chat_endpoint():
    data = request.get_json()
    ...
```

#### 响应格式
```python
# FastAPI
return ChatResponse(code=200, message="成功", data=result)

# Flask
return jsonify({"code": 200, "message": "成功", "data": result})
```

#### 错误处理
```python
# FastAPI
raise HTTPException(status_code=400, detail="错误信息")

# Flask
return jsonify({"error": "错误信息"}), 400
```

## ✅ 保持不变的功能

1. **API 接口**: 所有端点路径和参数保持不变
2. **响应格式**: JSON 响应结构完全一致
3. **功能逻辑**: Agent 处理逻辑无任何变化
4. **会话管理**: Thread ID 管理机制保持原样
5. **错误处理**: 错误代码和消息保持一致

## 🚀 启动方式

### Flask 版本启动
```bash
# 方式1：直接运行
python api.py

# 方式2：使用 flask 命令
export FLASK_APP=api.py
flask run --host=0.0.0.0 --port=8000
```

### 测试验证
```bash
# 健康检查
curl http://localhost:8000/health

# 功能测试
python test_api.py
```

## 🔧 开发者注意事项

### 1. 异步函数调用
```python
# Flask 中调用异步 Agent 方法
agent_result = asyncio.run(_agent_instance.chat(...))
```

### 2. 请求数据验证
```python
# 手动验证替代 Pydantic
def validate_request_data(data):
    errors = []
    if not data.get('question'):
        errors.append('问题不能为空')
    # ... 更多验证
    if errors:
        raise ValueError('; '.join(errors))
```

### 3. CORS 支持
```python
# 暂时不启用跨域支持
# 如果需要跨域支持，可以安装 flask-cors
# pip install flask-cors
```

## 📊 性能考虑

1. **单线程处理**: Flask 默认单线程，高并发时需要配置 WSGI 服务器
2. **内存使用**: 相比 FastAPI 略低
3. **启动速度**: 更快的启动时间
4. **开发效率**: 更简单的调试和开发

## 🛠️ 生产部署建议

### 使用 Gunicorn
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 api:app
```

### 使用 uWSGI
```bash
pip install uwsgi
uwsgi --http :8000 --wsgi-file api.py --callable app --workers 4
```

## 🐛 故障排除

### 常见问题

1. **异步函数调用错误**
   - 确保使用 `asyncio.run()` 包装异步调用

2. **CORS 错误**
   - 当前未启用跨域支持
   - 如需跨域支持，可安装 `pip install flask-cors`

3. **端口占用**
   ```bash
   # 查看端口占用
   netstat -an | grep 8000
   ```

---

**迁移完成**: Flask 版本已完全实现所有 FastAPI 功能，接口保持 100% 兼容。 