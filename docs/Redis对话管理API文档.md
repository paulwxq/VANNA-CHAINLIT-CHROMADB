# Redis 对话管理 API 文档

## 概述

辞图智能数据问答平台提供了完整的基于 Redis 的对话管理功能，支持多用户、多会话的智能问答场景。本文档详细介绍了所有与 Redis 对话管理相关的 API 接口。

## API 基础信息

- **基础URL**: `http://localhost:8084`
- **Content-Type**: `application/json`
- **响应格式**: 标准化的JSON响应格式

## API 列表

### 1. 获取用户对话列表

#### 接口信息
- **URL**: `/api/v0/user/{user_id}/conversations`
- **方法**: `GET`
- **功能**: 获取指定用户的对话列表，按时间倒序排列

#### 请求参数

| 参数名 | 类型 | 位置 | 必填 | 说明 |
|--------|------|------|------|------|
| user_id | string | 路径参数 | 是 | 用户ID |
| limit | integer | 查询参数 | 否 | 最大返回数量，默认为 USER_MAX_CONVERSATIONS |

#### 请求示例
```http
GET /api/v0/user/guest/conversations?limit=10
```

#### 响应示例
```json
{
    "success": true,
    "code": 200,
    "message": "获取用户对话列表成功",
    "data": {
        "user_id": "john_doe",
        "conversations": [
            {
                "conversation_id": "conv_20241201_001",
                "user_id": "john_doe",
                "created_at": "2024-12-01T10:00:00",
                "updated_at": "2024-12-01T10:30:00",
                "message_count": "6",
                "conversation_title": "查询销售数据"
            }
        ],
        "total_count": 1
    }
}
```

---

### 2. 获取对话消息历史

#### 接口信息
- **URL**: `/api/v0/conversation/{conversation_id}/messages`
- **方法**: `GET`
- **功能**: 获取特定对话的所有消息历史

#### 请求参数

| 参数名 | 类型 | 位置 | 必填 | 说明 |
|--------|------|------|------|------|
| conversation_id | string | 路径参数 | 是 | 对话ID |
| limit | integer | 查询参数 | 否 | 最大返回消息数量 |

#### 请求示例
```http
GET /api/v0/conversation/conv_20241201_001/messages?limit=50
```

#### 响应示例
```json
{
    "success": true,
    "code": 200,
    "message": "获取对话消息成功",
    "data": {
        "conversation_id": "conv_20241201_001",
        "conversation_meta": {
            "conversation_id": "conv_20241201_001",
            "user_id": "john_doe",
            "created_at": "2024-12-01T10:00:00",
            "updated_at": "2024-12-01T10:30:00",
            "message_count": "6"
        },
        "messages": [
            {
                "message_id": "msg_uuid_1",
                "role": "user",
                "content": "查询销售数据",
                "timestamp": "2024-12-01T10:00:00",
                "metadata": {}
            },
            {
                "message_id": "msg_uuid_2",
                "role": "assistant",
                "content": "好的，我来帮您查询销售数据...",
                "timestamp": "2024-12-01T10:00:05",
                "metadata": {
                    "type": "DATABASE",
                    "sql": "SELECT * FROM sales",
                    "execution_path": ["start", "classify", "agent_database", "format_response"]
                }
            }
        ],
        "message_count": 2
    }
}
```

---

### 3. 获取对话上下文

#### 接口信息
- **URL**: `/api/v0/conversation/{conversation_id}/context`
- **方法**: `GET`
- **功能**: 获取对话上下文，格式化用于 LLM 处理

#### 请求参数

| 参数名 | 类型 | 位置 | 必填 | 说明 |
|--------|------|------|------|------|
| conversation_id | string | 路径参数 | 是 | 对话ID |
| count | integer | 查询参数 | 否 | 上下文消息数量，默认为 CONVERSATION_CONTEXT_COUNT |

#### 请求示例
```http
GET /api/v0/conversation/conv_20241201_001/context?count=5
```

#### 响应示例
```json
{
    "success": true,
    "code": 200,
    "message": "获取对话上下文成功",
    "data": {
        "conversation_id": "conv_20241201_001",
        "context": "User: 查询销售数据\nAssistant: 好的，我来帮您查询销售数据...\nUser: 能否按月份分组？",
        "context_message_count": 5
    }
}
```

---

### 4. 获取用户完整对话数据 🆕

#### 接口信息
- **URL**: `/api/v0/user/{user_id}/conversations/full`
- **方法**: `GET`
- **功能**: 一次性获取用户的所有对话和每个对话下的消息历史

#### 请求参数

| 参数名 | 类型 | 位置 | 必填 | 说明 |
|--------|------|------|------|------|
| user_id | string | 路径参数 | 是 | 用户ID |
| conversation_limit | integer | 查询参数 | 否 | 对话数量限制，不传则返回所有对话 |
| message_limit | integer | 查询参数 | 否 | 每个对话的消息数限制，不传则返回所有消息 |

#### 请求示例
```http
# 获取所有对话和消息
GET /api/v0/user/john_doe/conversations/full

# 限制返回数据量
GET /api/v0/user/john_doe/conversations/full?conversation_limit=50&message_limit=100

# 只限制对话数量
GET /api/v0/user/john_doe/conversations/full?conversation_limit=20
```

#### 响应示例
```json
{
    "success": true,
    "code": 200,
    "message": "获取用户完整对话数据成功",
    "data": {
        "user_id": "john_doe",
        "conversations": [
            {
                "conversation_id": "conv_20241201_001",
                "user_id": "john_doe",
                "created_at": "2024-12-01T10:00:00",
                "updated_at": "2024-12-01T10:30:00",
                "meta": {
                    "conversation_id": "conv_20241201_001",
                    "user_id": "john_doe",
                    "created_at": "2024-12-01T10:00:00",
                    "updated_at": "2024-12-01T10:30:00",
                    "message_count": "6"
                },
                "messages": [
                    {
                        "message_id": "msg_uuid_1",
                        "role": "user",
                        "content": "查询销售数据",
                        "timestamp": "2024-12-01T10:00:00",
                        "metadata": {}
                    },
                    {
                        "message_id": "msg_uuid_2",
                        "role": "assistant",
                        "content": "好的，我来帮您查询销售数据...",
                        "timestamp": "2024-12-01T10:00:05",
                        "metadata": {
                            "type": "DATABASE",
                            "sql": "SELECT * FROM sales"
                        }
                    }
                ],
                "message_count": 2
            }
        ],
        "total_conversations": 1,
        "total_messages": 2,
        "conversation_limit_applied": null,
        "message_limit_applied": null,
        "query_time": "2024-12-01T15:30:00"
    }
}
```

---

### 5. 获取对话系统统计信息

#### 接口信息
- **URL**: `/api/v0/conversation_stats`
- **方法**: `GET`
- **功能**: 获取 Redis 对话系统的统计信息

#### 请求参数
无

#### 请求示例
```http
GET /api/v0/conversation_stats
```

#### 响应示例
```json
{
    "success": true,
    "code": 200,
    "message": "获取统计信息成功",
    "data": {
        "available": true,
        "total_users": 125,
        "total_conversations": 1250,
        "cached_qa_count": 500,
        "redis_info": {
            "memory_usage_mb": 120.5,
            "connected_clients": 10
        }
    }
}
```

---

### 6. 清理过期对话

#### 接口信息
- **URL**: `/api/v0/conversation_cleanup`
- **方法**: `POST`
- **功能**: 手动清理 Redis 中的过期对话数据

#### 请求参数
无

#### 请求示例
```http
POST /api/v0/conversation_cleanup
```

#### 响应示例
```json
{
    "success": true,
    "code": 200,
    "message": "对话清理完成",
    "data": null
}
```

---

### 7. 智能问答（支持对话上下文）

#### 接口信息
- **URL**: `/api/v0/ask_agent`
- **方法**: `POST`
- **功能**: 支持对话上下文的智能问答接口，集成 Redis 对话管理

#### 请求参数

| 参数名 | 类型 | 位置 | 必填 | 说明 |
|--------|------|------|------|------|
| question | string | 请求体 | 是 | 用户问题 |
| session_id | string | 请求体 | 否 | 浏览器会话ID |
| user_id | string | 请求体 | 否 | 用户ID |
| conversation_id | string | 请求体 | 否 | 对话ID |
| continue_conversation | boolean | 请求体 | 否 | 是否继续现有对话 |
| routing_mode | string | 请求体 | 否 | 路由模式（database_direct, chat_direct, hybrid, llm_only） |

#### 请求示例
```http
POST /api/v0/ask_agent
Content-Type: application/json

{
    "question": "查询最近一个月的销售数据",
    "session_id": "session_12345",
    "user_id": "john_doe",
    "continue_conversation": true,
    "routing_mode": "hybrid"
}
```

#### 响应示例
```json
{
    "success": true,
    "code": 200,
    "message": "操作成功",
    "data": {
        "type": "DATABASE",
        "response": "查询到最近一个月的销售数据，共包含150条记录...",
        "sql": "SELECT * FROM sales WHERE date >= DATE_SUB(NOW(), INTERVAL 1 MONTH)",
        "records": {
            "rows": [...],
            "columns": ["date", "amount", "product"],
            "row_count": 150,
            "total_row_count": 150,
            "is_limited": false
        },
        "summary": "查询到最近一个月的销售数据共150条记录...",
        "session_id": "session_12345",
        "execution_path": ["start", "classify", "agent_database", "format_response"],
        "classification_info": {
            "confidence": 0.95,
            "reason": "用户询问销售数据统计",
            "method": "rule_based_database_keywords"
        },
        "conversation_id": "conv_20241201_002",
        "user_id": "john_doe",
        "is_guest_user": false,
        "context_used": true,
        "from_cache": false,
        "conversation_status": "continued",
        "conversation_message": "继续现有对话",
        "requested_conversation_id": null,
        "routing_mode_used": "hybrid",
        "routing_mode_source": "api",
        "agent_version": "langgraph_v1",
        "timestamp": "2024-12-01T15:30:00"
    }
}
```

## Redis 对话管理特性

### 1. 用户身份管理
- 支持登录用户和访客用户
- 基于 session_id 和 IP 地址的访客识别
- 智能用户ID解析和会话管理

### 2. 对话生命周期管理
- 自动创建和管理对话
- 支持对话继续和新建
- 对话元数据维护和更新

### 3. 上下文管理
- 维护对话历史和上下文
- 支持上下文感知的问答
- 灵活的上下文长度控制

### 4. 缓存机制
- 智能答案缓存和检索
- 只缓存无上下文的问答，避免上下文污染
- 缓存命中率统计和性能优化

### 5. 数据持久化
- Redis 数据持久化存储
- 自动过期和清理机制
- 数据备份和恢复支持

## 错误处理

所有 API 都遵循统一的错误响应格式：

```json
{
    "success": false,
    "code": 500,
    "message": "处理失败",
    "data": {
        "response": "具体错误信息",
        "error_type": "error_type_code",
        "can_retry": true,
        "timestamp": "2024-12-01T15:30:00"
    }
}
```

### 常见错误码

| 错误码 | 说明 |
|--------|------|
| 400 | 请求参数错误 |
| 422 | 参数验证失败 |
| 500 | 系统内部错误 |
| 503 | 服务暂时不可用 |

## 使用建议

### 1. 性能优化
- 合理使用分页参数控制返回数据量
- 使用缓存机制减少重复查询
- 定期清理过期对话数据

### 2. 安全考虑
- 验证用户权限和会话有效性
- 避免暴露敏感的对话内容
- 实施适当的访问频率限制

### 3. 最佳实践
- 使用 `/conversations/full` API 获取完整数据
- 根据业务需求设置合理的上下文长度
- 监控 Redis 内存使用情况

## 配置参数

相关配置参数在 `app_config.py` 中定义：

```python
# Redis 对话管理配置
USER_MAX_CONVERSATIONS = 50        # 用户最大对话数
CONVERSATION_CONTEXT_COUNT = 10    # 默认上下文消息数量
REDIS_CONVERSATION_TTL = 86400 * 7 # 对话过期时间（7天）
```

## 缓存策略说明

### 智能缓存机制

系统采用**上下文感知的缓存策略**：

#### 缓存规则
- ✅ **缓存存储条件**: 只有**无上下文**的问答会被缓存（严控质量）
- ✅ **缓存使用条件**: **无论是否有上下文**都可以查找缓存（提高利用率）

#### 缓存逻辑
```
第1次问答（无上下文）→ 缓存存储 ✅
第2次相同问题（有上下文）→ 缓存命中 ✅（优化后）
第3次相同问题（新对话，无上下文）→ 缓存命中 ✅
```

#### 优势
- 🎯 **缓存质量保障**: 严控存储条件，确保缓存都是明确的问答
- ⚡ **性能全面提升**: 新用户和多轮对话都能享受缓存加速
- 🧠 **平衡设计**: 存储严格，使用灵活，错误概率低
- 🔄 **高利用率**: 最大化缓存的使用价值

#### 配置控制
```python
# 在 app_config.py 中控制缓存行为
ENABLE_QUESTION_ANSWER_CACHE = True  # 全局缓存开关
QUESTION_ANSWER_TTL = 24 * 3600      # 缓存过期时间（24小时）
```

## 更新日志

### v1.2.1 (2024-12-22)
- 🚀 **平衡缓存策略**: 严控存储条件，放宽使用条件
- ⚡ **性能提升**: 多轮对话中的重复问题也能使用缓存
- 🎯 **智能平衡**: 既保证缓存质量，又最大化利用率

### v1.2.0 (2024-12-22)
- 🔧 **优化缓存策略**: 只缓存无上下文的问答，避免上下文污染
- ✨ **简化缓存键**: 基于问题本身生成缓存键，提高缓存命中率
- 🎯 **逻辑优化**: 解决同一对话中重复问题无法使用缓存的问题

### v1.1.0 (2024-12-01)
- 🆕 新增 `/api/v0/user/{user_id}/conversations/full` API
- ✨ 支持一次性获取用户完整对话数据
- 🔧 优化参数处理，支持不传递限制参数时返回所有记录
- 🔄 **字段更新**: ask_agent API 响应中 query_result 改为 records
- 📝 **新增字段**: conversation_title、routing_mode_used、routing_mode_source

### v1.0.0 (2024-11-01)
- 🎉 首次发布 Redis 对话管理功能
- 📝 完整的 API 文档和使用指南 