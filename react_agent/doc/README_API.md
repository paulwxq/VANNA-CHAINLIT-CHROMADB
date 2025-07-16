# Custom React Agent API 文档

Flask API服务，提供与Custom React Agent进行交互的RESTful接口。

## 🚀 快速开始

### 启动服务
```bash
cd test/custom_react_agent
python api.py
```

服务将在 http://localhost:8000 启动

## 📋 API 端点

### 1. 健康检查
**GET** `/health`

检查API服务状态

**响应示例:**
```json
{
  "status": "healthy",
  "agent_initialized": true,
  "timestamp": "2025-01-15T10:30:00"
}
```

### 2. 聊天接口
**POST** `/api/chat`

与Agent进行对话

**请求参数:**
```json
{
  "question": "请问哪个高速服务区的档口数量最多？",
  "user_id": "doudou",
  "thread_id": "doudou:20250115103000001"  // 可选，不提供则自动生成
}
```

**响应示例:**
```json
{
  "success": true,
  "data": {
    "records": {...},      // SQL查询结果
    "response": "...",     // Agent回答
    "sql": "...",         // 执行的SQL
    "react_agent_meta": {...}
  },
  "thread_id": "doudou:20250115103000001",
  "timestamp": "2025-01-15T10:30:00"
}
```

### 3. 获取用户对话列表 ⭐ 新增
**GET** `/api/v0/react/users/{user_id}/conversations`

获取指定用户的最近聊天记录列表

**路径参数:**
- `user_id`: 用户ID

**查询参数:**
- `limit`: 返回数量限制 (默认10，最大50)

**请求示例:**
```bash
curl "http://localhost:8000/api/v0/react/users/doudou/conversations?limit=5"
```

**响应示例:**
```json
{
  "success": true,
  "data": {
    "user_id": "doudou",
    "conversations": [
      {
        "thread_id": "doudou:20250115103000001",
        "user_id": "doudou",
        "timestamp": "20250115103000001",
        "message_count": 4,
        "last_message": "南城服务区的档口数量最多，共有39个档口。",
        "last_updated": "2025-01-15T10:30:00",
        "conversation_preview": "请问哪个高速服务区的档口数量最多？",
        "formatted_time": "2025-01-15 10:30:00"
      },
      {
        "thread_id": "doudou:20250115102500002", 
        "user_id": "doudou",
        "timestamp": "20250115102500002",
        "message_count": 6,
        "last_message": "共有6个餐饮档口。",
        "last_updated": "2025-01-15T10:25:00",
        "conversation_preview": "南城服务区有多少个餐饮档口？",
        "formatted_time": "2025-01-15 10:25:00"
      }
    ],
    "total_count": 2,
    "limit": 5
  },
  "timestamp": "2025-01-15T10:35:00"
}
```

### 4. 获取对话详情 ⭐ 新增
**GET** `/api/v0/react/users/{user_id}/conversations/{thread_id}`

获取特定对话的详细历史记录

**路径参数:**
- `user_id`: 用户ID
- `thread_id`: 对话线程ID (必须以 `user_id:` 开头)

**请求示例:**
```bash
curl "http://localhost:8000/api/v0/react/users/doudou/conversations/doudou:20250115103000001"
```

**响应示例:**
```json
{
  "success": true,
  "data": {
    "user_id": "doudou",
    "thread_id": "doudou:20250115103000001",
    "message_count": 4,
    "messages": [
      {
        "type": "human",
        "content": "请问哪个高速服务区的档口数量最多？",
        "tool_calls": null
      },
      {
        "type": "ai", 
        "content": "我来帮您查询一下高速服务区的档口数量信息。",
        "tool_calls": [...]
      },
      {
        "type": "tool",
        "content": "[{\"service_area\": \"南城服务区\", \"booth_count\": 39}, ...]",
        "tool_calls": null
      },
      {
        "type": "ai",
        "content": "南城服务区的档口数量最多，共有39个档口。",
        "tool_calls": null
      }
    ]
  },
  "timestamp": "2025-01-15T10:35:00"
}
```

## 🔧 技术特性

### Thread ID 设计
- 格式：`{user_id}:{timestamp}`
- 示例：`doudou:20250115103000001`
- 自动按时间戳排序
- 无需额外映射表

### 数据持久化
- 使用 AsyncRedisSaver 存储对话状态
- 支持跨会话的对话历史查询
- Redis pattern匹配高效查询用户数据

### 错误处理
- 统一的JSON错误格式
- 详细的错误日志
- 优雅的异常处理

## 📊 使用场景

1. **聊天机器人界面**: 显示用户的历史对话列表
2. **对话管理**: 查看和管理特定对话的详细内容
3. **数据分析**: 分析用户的对话模式和频率
4. **客服系统**: 客服人员查看用户历史对话记录

## 🔍 测试示例

```bash
# 1. 发起对话
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "请问哪个高速服务区的档口数量最多？", "user_id": "doudou"}'

# 2. 查看对话列表  
curl "http://localhost:8000/api/v0/react/users/doudou/conversations?limit=5"

# 3. 查看特定对话详情
curl "http://localhost:8000/api/v0/react/users/doudou/conversations/doudou:20250115103000001"
```

## 📝 注意事项

- user_id 和 thread_id 的格式验证
- limit 参数范围限制 (1-50)
- 异步操作的错误处理
- Redis连接的健壮性 