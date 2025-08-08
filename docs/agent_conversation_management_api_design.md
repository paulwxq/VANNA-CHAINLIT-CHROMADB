# Agent对话管理API设计文档

## 概述

本文档设计两个API来增强agent模块中Redis对话历史记录的管理能力：

1. **新增API**: `/api/v0/conversation_limit_enforcement` - 对话限额执行API
2. **增强API**: `/api/v0/conversation_cleanup` - 对话清理API增强版

这两个API专门操作agent模块写入Redis的三种Key：
- `conversation:{conversation_id}:meta` (对话元数据)
- `conversation:{conversation_id}:messages` (对话消息列表)
- `user:{user_id}:conversations` (用户对话索引)

## API 1: 对话限额执行API

### 基本信息

- **路由**: `POST /api/v0/conversation_limit_enforcement`
- **功能**: 执行对话数量和消息数量的限制策略，确保数据量符合配置要求
- **作用**: 对现有数据进行"补救性"的限额执行，补充自动 `LTRIM` 策略可能遗漏的情况

### 请求参数 (JSON Body)

| 参数                        | 类型    | 必填 | 描述                                                     |
| --------------------------- | ------- | ---- | -------------------------------------------------------- |
| `user_id`                   | String  | 否   | 指定用户ID，如果提供则只处理该用户的数据                 |
| `user_max_conversations`    | Integer | 否   | 每个用户保留的最大对话数，默认从 `app_config.py` 获取   |
| `conversation_max_length`   | Integer | 否   | 每个对话保留的最大消息数，默认从 `app_config.py` 获取   |
| `dry_run`                   | Boolean | 否   | 是否为试运行模式，默认 `false`。为 `true` 时只返回分析结果，不执行实际操作 |

### 处理逻辑

#### 全局模式 (未提供 `user_id`)
1. 扫描所有 `user:*:conversations` Key
2. 对每个用户执行限额检查和执行
3. 返回全局统计信息

#### 指定用户模式 (提供了 `user_id`)
1. 只处理指定用户的 `user:{user_id}:conversations`
2. 执行该用户的限额检查和执行
3. 返回该用户的处理结果

#### 限额执行步骤
1. **用户对话数限制**:
   - 获取用户的对话列表 `user:{user_id}:conversations`
   - 如果对话数超过 `user_max_conversations`
   - 按时间排序，保留最新的N个对话
   - 删除多余对话的所有相关数据 (`:meta`, `:messages`)
   - 更新用户对话列表

2. **单对话消息数限制**:
   - 对每个保留的对话，检查消息数量
   - 如果消息数超过 `conversation_max_length`
   - 使用 `LTRIM` 只保留最新的N条消息

### 返回结果 (JSON)

```json
{
  "success": true,
  "message": "限额执行完成",
  "data": {
    "mode": "global|user_specific",
    "dry_run": false,
    "parameters": {
      "user_max_conversations": 5,
      "conversation_max_length": 10
    },
    "processed_users": 15,
    "total_conversations_processed": 45,
    "total_conversations_deleted": 8,
    "total_messages_trimmed": 120,
    "execution_summary": [
      {
        "user_id": "guest",
        "original_conversations": 7,
        "kept_conversations": 5,
        "deleted_conversations": 2,
        "messages_trimmed": 15
      }
    ],
    "execution_time_ms": 1250
  }
}
```

## API 2: 对话清理API增强版

### 基本信息

- **路由**: `POST /api/v0/conversation_cleanup`
- **功能**: 增强的对话清理功能，支持精确删除和批量清理
- **兼容性**: 保持原有无参数调用的功能

### 请求参数 (JSON Body)

| 参数                     | 类型    | 必填 | 描述                                           |
| ------------------------ | ------- | ---- | ---------------------------------------------- |
| `user_id`                | String  | 否   | 删除指定用户的所有对话数据                     |
| `conversation_id`        | String  | 否   | 删除指定的对话 (支持 `conversation_id` 格式)   |
| `thread_id`              | String  | 否   | 删除指定的对话 (支持 `thread_id` 格式，与 `conversation_id` 等效) |
| `clear_all_agent_data`   | Boolean | 否   | 是否清空所有agent对话数据，默认 `false`        |
| `cleanup_invalid_refs`   | Boolean | 否   | 是否只清理无效引用，默认 `false`               |

**注意**: 所有操作模式参数互斥，一次请求只能执行一种操作：
- `user_id` (模式1)
- `conversation_id` 或 `thread_id` (模式2)
- `clear_all_agent_data: true` (模式3)
- `cleanup_invalid_refs: true` (模式4)

如果同时提供多个操作参数，API将返回参数冲突错误。

### 处理逻辑

#### 模式1: 删除指定用户 (提供 `user_id`)
1. 获取用户的所有对话 `user:{user_id}:conversations`
2. 逐个删除每个对话的 `:meta` 和 `:messages`
3. 删除用户对话索引 `user:{user_id}:conversations`
4. 返回删除统计

#### 模式2: 删除指定对话 (提供 `conversation_id` 或 `thread_id`)
1. 验证对话是否存在
2. 获取对话所属用户
3. 删除 `conversation:{id}:meta`
4. 删除 `conversation:{id}:messages`
5. 从 `user:{user_id}:conversations` 中移除该对话ID
6. 返回删除结果

#### 模式3: 清空所有agent对话数据 (提供 `clear_all_agent_data: true`)
**⚠️ 危险操作**: 此模式将完全清空所有agent对话历史数据，不可恢复！

**参数冲突处理**: 如果同时提供了其他操作模式参数（如 `user_id`、`conversation_id`、`thread_id`、`cleanup_invalid_refs`），API将立即返回参数冲突错误，**不会执行任何删除操作**。

**执行步骤**:
1. 扫描并删除所有 `conversation:*:meta` Key
2. 扫描并删除所有 `conversation:*:messages` Key  
3. 扫描并删除所有 `user:*:conversations` Key
4. 返回删除统计

#### 模式4: 清理无效引用 (提供 `cleanup_invalid_refs: true`)
1. 扫描所有 `user:*:conversations` 列表
2. 对每个用户对话列表中的conversation_id，检查对应的 `conversation:{id}:meta` 是否存在
3. 如果元数据不存在，从用户对话列表中移除该conversation_id
4. 重建清理后的用户对话列表
5. 返回清理统计

#### 无参数请求处理
如果请求中没有提供任何参数，API将返回错误，要求明确指定操作模式。

### 返回结果 (JSON)

#### 参数冲突错误
```json
{
  "success": false,
  "message": "参数冲突：不能同时提供多个操作模式参数",
  "error": "检测到冲突参数: user_id 和 clear_all_agent_data",
  "valid_modes": [
    "user_id (删除指定用户)",
    "conversation_id 或 thread_id (删除指定对话，两参数等同)",
    "clear_all_agent_data (清空所有数据)",
    "cleanup_invalid_refs (清理无效引用)"
  ]
}
```

#### 删除用户模式
```json
{
  "success": true,
  "message": "用户对话数据删除完成",
  "data": {
    "operation_mode": "delete_user",
    "user_id": "guest",
    "deleted_conversations": 5,
    "deleted_messages": 47,
    "execution_time_ms": 150
  }
}
```

#### 删除对话模式
```json
{
  "success": true,
  "message": "对话删除完成",
  "data": {
    "operation_mode": "delete_conversation",
    "conversation_id": "guest:20250125143022155",
    "user_id": "guest",
    "deleted_messages": 8,
    "execution_time_ms": 45
  }
}
```

#### 清空所有数据模式
```json
{
  "success": true,
  "message": "所有agent对话数据清空完成",
  "data": {
    "operation_mode": "clear_all_agent_data",
    "deleted_conversation_metas": 150,
    "deleted_conversation_messages": 150,
    "deleted_user_conversations": 25,
    "total_keys_deleted": 325,
    "execution_time_ms": 2500
  }
}
```

#### 清理无效引用模式
```json
{
  "success": true,
  "message": "无效引用清理完成",
  "data": {
    "operation_mode": "cleanup_invalid_refs",
    "processed_users": 12,
    "cleaned_references": 3,
    "execution_time_ms": 200
  }
}
```

## 实现要点

### 1. 数据安全
- 所有删除操作需要在事务中执行或确保原子性
- 删除前验证数据的存在性和所有权
- 提供详细的操作日志
- **特别注意**: `clear_all_agent_data` 是危险操作，建议增加二次确认机制
- 参数互斥检查：确保不同操作模式的参数不能同时提供

### 2. 性能考虑
- 大批量操作时使用管道 (Pipeline) 提高效率
- 限制单次操作的最大数据量，避免长时间阻塞
- 对于全局模式，考虑分页处理

### 3. 错误处理
- **参数互斥检查**：
  - 不能同时提供多个操作模式的参数
  - 具体互斥规则：
    - 共有四组参数组合：`user_id`/ `conversation_id`（`thread_id` ） / `clear_all_agent_data`/`cleanup_invalid_refs`
    - 这四组参数不能同时传递。
    - `conversation_id` 和 `thread_id` 完全等同
  - 无参数时必须返回错误，要求指定操作模式
- Redis连接异常处理
- 部分操作失败时的回滚策略
- 对于 `clear_all_agent_data` 操作，增加额外的安全检查

### 4. 日志记录
- 记录所有重要操作的详细日志
- 包含用户ID、对话ID、操作类型等关键信息
- 便于问题排查和审计

## 使用示例

### 限额执行API

1. **全局限额执行**:
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"user_max_conversations": 3, "conversation_max_length": 8}' \
     http://127.0.0.1:5000/api/v0/conversation_limit_enforcement
```

2. **指定用户限额执行**:
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"user_id": "guest", "user_max_conversations": 5}' \
     http://127.0.0.1:5000/api/v0/conversation_limit_enforcement
```

3. **试运行模式**:
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"dry_run": true}' \
     http://127.0.0.1:5000/api/v0/conversation_limit_enforcement
```

### 对话清理API

1. **删除指定用户**:
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"user_id": "guest"}' \
     http://127.0.0.1:5000/api/v0/conversation_cleanup
```

2. **删除指定对话**:
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"conversation_id": "guest:20250125143022155"}' \
     http://127.0.0.1:5000/api/v0/conversation_cleanup
```

3. **清空所有agent对话数据** (⚠️ 危险操作):
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"clear_all_agent_data": true}' \
     http://127.0.0.1:5000/api/v0/conversation_cleanup
```

4. **清理无效引用**:
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"cleanup_invalid_refs": true}' \
     http://127.0.0.1:5000/api/v0/conversation_cleanup
```

5. **无参数调用** (将返回错误):
```bash
curl -X POST http://127.0.0.1:5000/api/v0/conversation_cleanup

# 返回结果：
{
  "success": false,
  "message": "参数错误：必须指定操作模式",
  "error": "请提供以下参数组合之一: user_id | conversation_id/thread_id | clear_all_agent_data | cleanup_invalid_refs"
}
```

## 总结

这两个API的设计目标是：

1. **限额执行API**: 提供"补救性"的数据量控制，处理自动限制策略可能遗漏的历史数据
2. **增强清理API**: 提供多层次的数据删除能力：
   - **精确删除**: 删除指定用户或指定对话
   - **完全清空**: 清空所有agent对话历史数据 (危险操作)
   - **维护清理**: 清理无效引用，保持数据一致性
   - **明确操作**: 不支持无参数调用，必须明确指定操作模式，避免误操作

两个API相互补充，形成完整的agent对话数据管理体系，满足从日常维护到紧急清理的各种需求。
