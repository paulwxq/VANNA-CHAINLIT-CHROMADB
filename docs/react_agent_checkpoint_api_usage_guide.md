# React Agent Checkpoint API管理使用说明

## API端点列表

| 方法 | URI | 功能说明 |
|------|-----|----------|
| GET | `/api/v0/checkpoint/direct/stats` | 获取Checkpoint统计信息 |
| GET | `/api/v0/checkpoint/direct/stats?user_id={user_id}` | 获取指定用户的Checkpoint统计信息 |
| POST | `/api/v0/checkpoint/direct/cleanup` | 清理Checkpoint数据 |

## 概述

React Agent Checkpoint管理API提供了对LangGraph Agent运行过程中产生的checkpoint数据进行管理和监控的功能。这些API通过直接操作Redis数据库，实现对checkpoint的统计查询和清理操作，不依赖Agent实例运行。

## API列表

| API名称 | 路由 | 方法 | 使用目的 |
|---------|------|------|----------|
| 获取Checkpoint统计 | `/api/v0/checkpoint/direct/stats` | GET | 查看系统中checkpoint的统计信息，包括用户数量、线程数量、checkpoint总数等 |
| 清理Checkpoint | `/api/v0/checkpoint/direct/cleanup` | POST | 清理过期的checkpoint数据，支持全局、用户级、线程级的清理操作 |

## API详细说明

### 1. 获取Checkpoint统计

**API路由：** `GET /api/v0/checkpoint/direct/stats`

**使用目的：** 获取系统或指定用户的checkpoint统计信息，用于监控数据量和存储状态。

#### 参数说明

- **查询参数（可选）：**
  - `user_id`: 指定用户ID，获取特定用户的统计信息

#### 使用示例

```bash
# 获取系统全部统计信息
curl http://localhost:8084/api/v0/checkpoint/direct/stats

# 获取指定用户统计信息
curl "http://localhost:8084/api/v0/checkpoint/direct/stats?user_id=wang1"
```

#### 返回结果说明

**系统全部统计信息：**
```json
{
  "code": 200,
  "success": true,
  "message": "获取系统checkpoint统计成功",
  "data": {
    "operation_type": "system_stats",
    "total_users": 2,                    // 系统总用户数
    "total_threads": 4,                  // 系统总线程数
    "total_checkpoints": 132,            // 系统总checkpoint数
    "users": [                           // 用户详细信息列表
      {
        "user_id": "wang1",              // 用户ID
        "thread_count": 3,               // 用户线程数
        "total_checkpoints": 116,        // 用户checkpoint总数
        "threads": [                     // 线程详细信息
          {
            "thread_id": "wang1:20250729235038043",
            "checkpoint_count": 36       // 线程checkpoint数量
          }
          // ... 更多线程
        ]
      }
      // ... 更多用户
    ],
    "timestamp": "2025-01-31T10:30:00"   // 统计时间戳
  }
}
```

**指定用户统计信息：**
```json
{
  "code": 200,
  "success": true,
  "message": "获取用户wang1统计成功",
  "data": {
    "operation_type": "user_stats",
    "user_id": "wang1",                  // 目标用户ID
    "thread_count": 3,                   // 用户线程数
    "total_checkpoints": 116,            // 用户checkpoint总数
    "threads": [                         // 按checkpoint数量降序排列
      {
        "thread_id": "wang1:20250801171843665",
        "checkpoint_count": 64
      },
      {
        "thread_id": "wang1:20250729235038043",
        "checkpoint_count": 36
      },
      {
        "thread_id": "wang1:20250731141657916",
        "checkpoint_count": 16
      }
    ],
    "timestamp": "2025-01-31T10:30:00"
  }
}
```

### 2. 清理Checkpoint

**API路由：** `POST /api/v0/checkpoint/direct/cleanup`

**使用目的：** 清理过期的checkpoint数据，释放Redis存储空间，每个线程保留最近N个checkpoint。

#### 参数说明

**请求体参数（JSON格式）：**

| 参数名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `keep_count` | int | 否 | 10 | 每个线程保留的checkpoint数量 |
| `user_id` | string | 否 | - | 指定要清理的用户ID |
| `thread_id` | string | 否 | - | 指定要清理的线程ID |

**参数逻辑：**
- 无任何参数：清理所有线程的checkpoint
- 只有`user_id`：清理指定用户的所有线程
- 只有`thread_id`：清理指定的线程
- `user_id`和`thread_id`同时存在：以`thread_id`为准

#### 使用示例

```bash
# 清理所有线程，每个保留10个checkpoint
curl -X POST http://localhost:8084/api/v0/checkpoint/direct/cleanup \
  -H "Content-Type: application/json" \
  -d '{"keep_count": 10}'

# 清理用户wang1的所有线程，每个保留5个checkpoint
curl -X POST http://localhost:8084/api/v0/checkpoint/direct/cleanup \
  -H "Content-Type: application/json" \
  -d '{"user_id": "wang1", "keep_count": 5}'

# 清理指定线程，保留8个checkpoint
curl -X POST http://localhost:8084/api/v0/checkpoint/direct/cleanup \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "wang1:20250729235038043", "keep_count": 8}'
```

#### 返回结果说明

```json
{
  "code": 200,
  "success": true,
  "message": "Checkpoint清理完成",
  "data": {
    "operation_type": "cleanup_all",        // 操作类型：cleanup_all|cleanup_user|cleanup_thread
    "target": "all",                        // 操作目标：all|用户ID|线程ID
    "keep_count": 10,                       // 保留数量
    "total_processed": 15,                  // 处理的线程总数
    "total_deleted": 45,                    // 删除的checkpoint总数
    "details": {                            // 详细处理结果
      "wang1:20250729235038043": {
        "original_count": 36,               // 原始checkpoint数量
        "deleted_count": 26,                // 删除的checkpoint数量
        "remaining_count": 10,              // 剩余checkpoint数量
        "status": "success"                 // 处理状态
      },
      "wang1:20250731141657916": {
        "original_count": 16,
        "deleted_count": 6,
        "remaining_count": 10,
        "status": "success"
      }
      // ... 更多线程处理结果
    },
    "timestamp": "2025-01-31T10:30:00"      // 操作时间戳
  }
}
```

## 错误处理

### 常见错误情况

1. **Redis连接失败**
2. **thread_id格式错误**
3. **用户不存在**
4. **删除checkpoint失败**

### 错误响应格式

```json
{
  "code": 500,
  "success": false,
  "message": "请求处理失败",
  "data": {
    "response": "具体错误信息",
    "error_type": "REDIS_CONNECTION_ERROR",  // 错误类型
    "timestamp": "2025-01-31T10:30:00"
  }
}
```

### 错误类型说明

| 错误类型 | 说明 |
|----------|------|
| `REDIS_CONNECTION_ERROR` | Redis连接失败 |
| `INVALID_THREAD_ID` | 线程ID格式错误 |
| `USER_NOT_FOUND` | 指定用户不存在 |
| `DELETE_FAILED` | 删除checkpoint操作失败 |

## 使用场景

### 1. 监控场景
```bash
# 定期检查系统checkpoint数据量
curl http://localhost:8084/api/v0/checkpoint/direct/stats

# 检查特定用户的数据量
curl "http://localhost:8084/api/v0/checkpoint/direct/stats?user_id=wang1"
```

### 2. 维护场景
```bash
# 系统维护：清理所有过期数据
curl -X POST http://localhost:8084/api/v0/checkpoint/direct/cleanup \
  -H "Content-Type: application/json" \
  -d '{"keep_count": 10}'

# 用户维护：清理特定用户数据
curl -X POST http://localhost:8084/api/v0/checkpoint/direct/cleanup \
  -H "Content-Type: application/json" \
  -d '{"user_id": "wang1", "keep_count": 5}'
```

### 3. 故障排查场景
```bash
# 检查问题线程的checkpoint数量
curl "http://localhost:8084/api/v0/checkpoint/direct/stats?user_id=problem_user"

# 清理问题线程的数据
curl -X POST http://localhost:8084/api/v0/checkpoint/direct/cleanup \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "problem_user:20250729235038043", "keep_count": 3}'
```

## 最佳实践

1. **定期监控**：建议定期调用统计API监控checkpoint数据量
2. **合理清理**：根据实际使用情况设置合适的保留数量（建议5-10个）
3. **分批处理**：对于大量数据的清理，建议按用户分批进行
4. **备份策略**：重要操作前可考虑备份关键checkpoint数据
5. **日志查看**：操作后查看相关日志确认执行结果

## 注意事项

- 清理操作不可逆，请谨慎操作
- 建议在低峰期进行大批量清理操作
- 保留数量建议不少于3个，以确保Agent正常回溯
- API直接操作Redis，不依赖Agent实例状态
- 所有时间戳均为ISO 8601格式

---

*该文档提供了React Agent Checkpoint API的完整使用指南，帮助用户有效管理和维护checkpoint数据。*