# React Agent Checkpoint管理API设计文档

## 概述

本文档描述了React Agent Checkpoint管理API的设计方案，提供checkpoint清理和统计功能，通过直接操作Redis实现，不依赖LangGraph工作流。

## 设计目标

- **简洁设计**：只需2个API，通过参数控制不同功能
- **直接操作**：直接连接Redis，不通过Agent实例
- **灵活控制**：支持全局、用户级、线程级的操作范围
- **手工调用**：通过API手工触发，不自动执行

## API设计

### API 1: Checkpoint清理

**路由：** `POST /api/v0/checkpoint/direct/cleanup`

**功能：** 清理checkpoint，保留最近N个

**请求参数：**
```json
{
  "keep_count": 10,           // 可选，保留数量，默认使用配置值
  "user_id": "wang1",         // 可选，指定用户ID
  "thread_id": "wang1:20250729235038043"  // 可选，指定线程ID
}
```

**参数逻辑：**
- 无任何参数：清理所有thread_id的checkpoint
- 只有`user_id`：清理指定用户的所有thread
- 只有`thread_id`：清理指定的thread
- `user_id`和`thread_id`同时存在：以`thread_id`为准

**响应格式：**
```json
{
  "code": 200,
  "success": true,
  "message": "Checkpoint清理完成",
  "data": {
    "operation_type": "cleanup_all|cleanup_user|cleanup_thread",
    "target": "all|wang1|wang1:20250729235038043",
    "keep_count": 10,
    "total_processed": 15,
    "total_deleted": 45,
    "details": {
      "wang1:20250729235038043": {
        "original_count": 36,
        "deleted_count": 26,
        "remaining_count": 10,
        "status": "success"
      },
      "wang1:20250731141657916": {
        "original_count": 16,
        "deleted_count": 6,
        "remaining_count": 10,
        "status": "success"
      }
    },
    "timestamp": "2025-01-31T10:30:00"
  }
}
```

### API 2: Checkpoint统计

**路由：** `GET /api/v0/checkpoint/direct/stats`

**功能：** 获取checkpoint统计信息

**查询参数：**
- `user_id`: 可选，指定用户ID

**调用方式：**
```bash
# 获取全部统计信息
GET /api/v0/checkpoint/direct/stats

# 获取指定用户统计信息  
GET /api/v0/checkpoint/direct/stats?user_id=wang1
```

**响应格式：**

**全部统计信息：**
```json
{
  "code": 200,
  "success": true,
  "message": "获取系统checkpoint统计成功",
  "data": {
    "operation_type": "system_stats",
    "total_users": 2,
    "total_threads": 4,
    "total_checkpoints": 132,
    "users": [
      {
        "user_id": "wang1",
        "thread_count": 3,
        "total_checkpoints": 116,
        "threads": [
          {
            "thread_id": "wang1:20250729235038043",
            "checkpoint_count": 36
          },
          {
            "thread_id": "wang1:20250731141657916", 
            "checkpoint_count": 16
          },
          {
            "thread_id": "wang1:20250801171843665",
            "checkpoint_count": 64
          }
        ]
      },
      {
        "user_id": "wang2",
        "thread_count": 1,
        "total_checkpoints": 16,
        "threads": [
          {
            "thread_id": "wang2:20250731141659949",
            "checkpoint_count": 16
          }
        ]
      }
    ],
    "timestamp": "2025-01-31T10:30:00"
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
    "user_id": "wang1",
    "thread_count": 3,
    "total_checkpoints": 116,
    "threads": [
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

## 技术实现

### 返回格式标准化

使用`common/result.py`的标准化响应格式：

```python
from common.result import success_response, error_response, internal_error_response

# 成功响应
return jsonify(success_response(
    response_text="Checkpoint清理完成",
    data={
        "operation_type": "cleanup_all",
        "total_deleted": 45,
        # ... 其他数据
    }
))

# 错误响应  
return jsonify(internal_error_response(
    response_text="Redis连接失败"
))
```

### Redis连接方式

参考`react_agent/enhanced_redis_api.py`的模式：

```python
# 直接创建Redis连接
redis_client = redis.Redis(
    host=config.REDIS_HOST,
    port=config.REDIS_PORT, 
    db=config.REDIS_DB,
    password=config.REDIS_PASSWORD,
    decode_responses=True
)
```

### Checkpoint Key格式

基于现有系统，checkpoint key格式：
```
checkpoint:user_id:timestamp:checkpoint_id
```

示例：
```
checkpoint:wang1:20250729235038043:01936451-dd24-641c-8005-c07e5896ad38
checkpoint:wang1:20250729235038043:01936451-dd29-624b-8006-fc1f3a83e4f5
checkpoint:wang2:20250731141659949:01936462-72a1-6e5c-8009-378fd98058aa
```

### 核心操作逻辑

**扫描Keys：**
```python
# 扫描所有checkpoint
pattern = "checkpoint:*"
# 扫描指定用户
pattern = f"checkpoint:{user_id}:*"  
# 扫描指定thread
pattern = f"checkpoint:{thread_id}:*"

keys = []
cursor = 0
while True:
    cursor, batch = redis_client.scan(cursor=cursor, match=pattern, count=1000)
    keys.extend(batch)
    if cursor == 0:
        break
```

**数据分组：**
```python
# 按thread_id分组
thread_groups = {}
for key in keys:
    parts = key.split(':')
    if len(parts) >= 3:
        user_id = parts[1]
        timestamp = parts[2] 
        thread_id = f"{user_id}:{timestamp}"
        
        if thread_id not in thread_groups:
            thread_groups[thread_id] = []
        thread_groups[thread_id].append(key)
```

**批量清理操作：**
```python
# 保留最近N个checkpoint，使用Redis批量删除
for thread_id, keys in thread_groups.items():
    if len(keys) > keep_count:
        # 按key排序（key包含timestamp，天然有序）
        keys.sort()
        # 删除旧的keys
        keys_to_delete = keys[:-keep_count]
        
        # 使用Redis Pipeline批量删除，提升性能
        if keys_to_delete:
            pipeline = redis_client.pipeline()
            for key in keys_to_delete:
                pipeline.delete(key)
            pipeline.execute()  # 批量执行删除命令
```

## 配置参数

在`react_agent/config.py`中添加：

```python
# --- Checkpoint管理配置 ---
CHECKPOINT_KEEP_COUNT = 10         # 每个thread保留的checkpoint数量（API默认值）
```

## API集成位置

- **文件位置：** `unified_api.py`
- **路由前缀：** `/api/v0/checkpoint/direct/`
- **依赖模块：** `react_agent.config`、`redis`、`common.result`

## 错误处理

### 常见错误情况：

1. **Redis连接失败**
2. **thread_id格式错误**
3. **用户不存在**
4. **删除checkpoint失败**

### 错误响应格式：

使用`common/result.py`的标准化错误响应：

```json
{
  "code": 500,
  "success": false,
  "message": "请求处理失败",
  "data": {
    "response": "具体错误信息",
    "error_type": "REDIS_CONNECTION_ERROR|INVALID_THREAD_ID|USER_NOT_FOUND|DELETE_FAILED",
    "timestamp": "2025-01-31T10:30:00"
  }
}
```

## 使用示例

### 清理API调用示例

```bash
# 1. 清理所有thread，每个保留10个checkpoint
curl -X POST http://localhost:8084/api/v0/checkpoint/direct/cleanup \
  -H "Content-Type: application/json" \
  -d '{"keep_count": 10}'

# 2. 清理用户wang1的所有thread，每个保留5个
curl -X POST http://localhost:8084/api/v0/checkpoint/direct/cleanup \
  -H "Content-Type: application/json" \
  -d '{"user_id": "wang1", "keep_count": 5}'

# 3. 清理指定thread，保留8个
curl -X POST http://localhost:8084/api/v0/checkpoint/direct/cleanup \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "wang1:20250729235038043", "keep_count": 8}'
```

### 统计API调用示例

```bash
# 4. 获取全部统计信息
curl http://localhost:8084/api/v0/checkpoint/direct/stats

# 5. 获取用户wang1的统计信息
curl "http://localhost:8084/api/v0/checkpoint/direct/stats?user_id=wang1"
```

## 性能考虑

1. **批量扫描：** 使用`scan`命令避免阻塞Redis
2. **批量删除：** 使用Redis Pipeline批量删除keys，提升性能
3. **连接管理：** 操作完成后及时关闭Redis连接
4. **日志记录：** 记录操作过程便于调试和监控
5. **单线程处理：** 当前使用单线程顺序处理，避免并发复杂性

## 安全考虑

1. **参数验证：** 验证user_id和thread_id格式
2. **权限控制：** 可考虑添加用户身份验证
3. **操作日志：** 记录谁在什么时候执行了清理操作
4. **回滚机制：** 重要操作前可考虑备份

---

*本文档描述了checkpoint管理API的完整设计方案，为实际开发提供详细的技术规范。*