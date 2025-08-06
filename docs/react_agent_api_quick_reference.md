# React Agent API 快速参考指南

## API端点总览

| API端点 | 方法 | 适用场景 | 状态 |
|---------|------|----------|------|
| `/api/v0/ask_react_agent` | POST | 同步调用，JSON响应 | ✅ 正常使用 |
| `/api/v0/ask_react_agent_stream` | GET | 异步流式，简单查询 | ✅ 正常使用 |
| `/api/v0/ask_react_agent_stream_sync` | GET | 同步流式，复杂数据库查询 | ✅ **推荐** |

## 使用建议

### 🚀 复杂数据库查询 (推荐)
```bash
GET /api/v0/ask_react_agent_stream_sync?question=请问当前系统中哪个服务区档口最多?&user_id=your_user_id
```
- ✅ 解决Vector搜索异步冲突
- ✅ 适用于需要数据库查询的问题
- ✅ 稳定可靠，无异步错误

### 💬 简单对话查询
```bash
GET /api/v0/ask_react_agent_stream?question=你好&user_id=your_user_id
```
- ✅ 适用于不涉及数据库的简单问题
- ✅ 异步流式响应

### 📊 标准同步调用
```bash
POST /api/v0/ask_react_agent
Content-Type: application/json

{
  "question": "你的问题",
  "user_id": "your_user_id"
}
```
- ✅ 标准JSON响应
- ✅ 适用于集成已有的同步调用代码

## 参数说明

所有API支持相同的核心参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | string | ✅ | 用户问题 |
| `user_id` | string | ✅ | 用户ID |
| `thread_id` | string | ❌ | 对话线程ID，不传则自动生成 |
| `routing_mode` | string | ❌ | 路由模式，默认'agent' |
| `continue_conversation` | boolean | ❌ | 是否继续对话，默认false |

## 技术架构对比

| 特性 | 原异步API | 新同步API |
|------|-----------|-----------|
| LangGraph执行 | `ainvoke()` 异步 | `invoke()` 同步 |
| LLM配置 | `streaming=True` | `streaming=False` |
| Vector搜索 | 异步冲突 ❌ | 同步执行 ✅ |
| 复杂查询 | 可能出错 ⚠️ | 稳定可靠 ✅ |
| Checkpointer | AsyncRedisSaver | 无 (避免异步依赖) |

## 问题排查

### Vector搜索异步冲突错误
```
RuntimeError: Task <Task pending...> got Future <Future pending> attached to a different loop
```
**解决方案**: 使用 `/api/v0/ask_react_agent_stream_sync`

### LLM配置错误
```
parameter.enable_thinking must be set to false for non-streaming calls
```
**解决方案**: 已在同步API中修复，设置 `enable_thinking=False`

## 示例代码

### JavaScript (前端)
```javascript
// 同步流式API (推荐)
const eventSource = new EventSource(
  `/api/v0/ask_react_agent_stream_sync?question=${encodeURIComponent(question)}&user_id=${userId}`
);

eventSource.onmessage = function(event) {
  const data = JSON.parse(event.data);
  console.log('收到数据:', data);
  
  if (data.type === 'completed') {
    eventSource.close();
  }
};
```

### Python (后端调用)
```python
import requests

# 同步API调用
response = requests.get(
    'http://localhost:8084/api/v0/ask_react_agent_stream_sync',
    params={
        'question': '请问当前系统中哪个服务区档口最多?',
        'user_id': 'test_user'
    },
    headers={'Accept': 'text/event-stream'},
    stream=True
)

for line in response.iter_lines():
    if line.startswith(b'data: '):
        data = json.loads(line[6:].decode())
        print(f"收到: {data}")
```

---

**更新时间**: 2025-08-06  
**版本**: v1.0  
**问题解决**: React Agent Vector搜索异步冲突问题