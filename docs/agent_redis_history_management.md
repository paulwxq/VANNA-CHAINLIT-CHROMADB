# Agent模块对话历史记录管理说明 (Redis)

本文档旨在详细说明 `agent` 模块（及其依赖的通用模块）如何管理存储在 Redis 中的对话历史记录，包括数据结构、自动保留策略、过期机制以及手动清理功能。

## 核心架构

`agent` 模块本身不直接执行 Redis 操作。实际的 Redis 交互由一个通用的核心模块 `common/redis_conversation_manager.py` 负责。API 层（如 `unified_api.py`）在接收到请求后，会调用这个通用模块来创建、更新或获取对话数据。

## Redis 中的数据结构

系统使用以下三种类型的 Redis Key 来存储和管理对话历史：

1.  **对话元数据 (Hash)**: `conversation:{conversation_id}:meta`
    - **用途**: 存储对话的基本信息，如创建时间、最后更新时间、所属用户ID和消息总数。
    - **类型**: `Hash`

2.  **对话消息列表 (List)**: `conversation:{conversation_id}:messages`
    - **用途**: 存储一个对话中所有的消息内容。每条消息是一个 JSON 字符串，包含 `role`, `content`, `timestamp` 等字段。
    - **类型**: `List`

3.  **用户对话索引 (List)**: `user:{user_id}:conversations`
    - **用途**: 存储一个用户所有对话的 `conversation_id`。此列表按时间倒序排列，最新的对话ID在列表的最前面。
    - **类型**: `List`

## 数据保留与上限策略（自动）

系统采用一种“主动限制”（Proactive Capping）的机制，在数据写入时就自动维护数据的数量上限，无需额外的清理脚本。

### 用户对话数上限

-   **机制**: 当一个新对话被创建时，系统会将新的 `conversation_id` 通过 `LPUSH` 命令添加到该用户对话列表的头部。紧接着，系统会立即使用 `LTRIM` 命令修剪这个列表，只保留最新的 N 个对话。
-   **配置**: 保留的对话数量由 `app_config.py` 中的 `USER_MAX_CONVERSATIONS` 参数控制。
    ```python
    # app_config.py
    USER_MAX_CONVERSATIONS = 5  # 每个用户最多保留的对话数
    ```

### 单对话消息数上限

-   **机制**: 当一条新消息被保存时，它会被 `LPUSH` 到对应对话消息列表的头部。同样，系统会立即使用 `LTRIM` 命令修剪该列表，只保留最新的 N 条消息。
-   **配置**: 保留的消息数量由 `app_config.py` 中的 `CONVERSATION_MAX_LENGTH` 参数控制。
    ```python
    # app_config.py
    CONVERSATION_MAX_LENGTH = 10  # 单个对话最大消息数
    ```

## 数据过期策略 (TTL)

系统支持为对话数据设置自动过期时间。

-   **机制**: 当一个新对话被创建或有新消息加入时，系统会为该对话的 `:meta` 和 `:messages` 这两个 Key 设置或续期 TTL（Time-To-Live）。
-   **配置**: TTL 的值由 `app_config.py` 中的 `CONVERSATION_TTL` 参数（单位为秒）控制。
    ```python
    # app_config.py
    CONVERSATION_TTL = 7 * 24 * 3600  # 默认为7天
    ```
-   **如何禁用 TTL**: 将 `CONVERSATION_TTL` 的值设置为 `None` 即可禁用 TTL。`redis-py` 客户端在接收到 `None` 作为过期时间时，会忽略该命令，从而使 Key 永久存储。
    ```python
    # app_config.py - 禁用TTL的示例
    CONVERSATION_TTL = None
    ```

## 对话历史管理 API

系统提供了一套完整的API来管理和操作存储在Redis中的agent对话历史记录。

### 1. 对话查询API

**`GET /api/v0/user/<user_id>/conversations`**
- **功能**: 获取指定用户的对话列表
- **操作的Redis Key**: `user:{user_id}:conversations` 和 `conversation:{conversation_id}:meta`
- **参数**: 
  - `user_id` (路径参数): 用户ID
  - `limit` (查询参数, 可选): 返回对话数量限制，默认为 `USER_MAX_CONVERSATIONS`
- **返回**: 用户的对话列表，包含对话ID、创建时间、更新时间、对话标题等信息

**`GET /api/v0/conversation/<conversation_id>/messages`**
- **功能**: 获取特定对话的消息历史和元数据
- **操作的Redis Key**: `conversation:{conversation_id}:messages` 和 `conversation:{conversation_id}:meta`
- **参数**: 
  - `conversation_id` (路径参数): 对话ID
  - `limit` (查询参数, 可选): 返回消息数量限制
- **返回**: 对话的消息列表、对话元数据、消息总数等信息

### 2. 统计信息API

**`GET /api/v0/conversation_stats`**
- **功能**: 获取对话系统的统计信息
- **操作的Redis Key**: 统计 `user:*:conversations`、`conversation:*:meta`、`qa_cache:*` 等Key
- **参数**: 无
- **返回**: Redis中对话数据的统计信息，包括：
  - 总用户数
  - 总对话数
  - 问答缓存数量
  - Redis内存使用情况

### 3. 对话限额执行API

**`POST /api/v0/conversation_limit_enforcement`**
- **功能**: 执行对话限额策略，对用户对话数量和消息数量进行"补救性"控制
- **操作的Redis Key**: `user:*:conversations`, `conversation:*:meta`, `conversation:*:messages`
- **使用场景**: 
  - 系统配置变更后需要追溯应用新的限额策略
  - 定期清理以释放Redis内存空间
  - 数据迁移或维护时的批量整理
- **参数**: 
  - `user_id` (可选): 指定用户ID，如果不提供则处理所有用户
  - `user_max_conversations` (可选): 每用户最大对话数，默认使用 `USER_MAX_CONVERSATIONS` 配置
  - `conversation_max_length` (可选): 每对话最大消息数，默认使用 `CONVERSATION_MAX_LENGTH` 配置
  - `dry_run` (可选): 试运行模式，默认为 `false`。设为 `true` 时只模拟执行，不实际删除数据
- **返回**: 详细的执行统计信息，包括：
  - `mode`: 执行模式（"global"或"user_specific"）
  - `dry_run`: 是否为试运行模式
  - `processed_users`: 处理的用户数
  - `total_conversations_processed`: 处理的对话总数
  - `total_conversations_deleted`: 删除的对话总数
  - `total_messages_trimmed`: 裁剪的消息总数
  - `execution_summary`: 每个用户的详细处理结果
  - `execution_time_ms`: 执行时间（毫秒）

### 4. 手动数据清理API

**`POST /api/v0/conversation_cleanup`**
- **功能**: 多模式对话清理API，支持精确的数据清理操作
- **操作的Redis Key**: `user:*:conversations`, `conversation:*:meta`, `conversation:*:messages`
- **使用场景**:
  - 清理数据不一致问题（无效引用）
  - 删除特定用户或对话的数据
  - 系统维护和数据重置
- **参数** (四种互斥的操作模式，必须且只能选择一种):
  
  **模式1: 删除指定用户**
  ```json
  {"user_id": "guest"}
  ```
  - 删除指定用户的所有对话数据，包括元数据、消息和用户对话索引
  
  **模式2: 删除指定对话**
  ```json
  {"conversation_id": "guest:20250125143022155"}
  // 或
  {"thread_id": "guest:20250125143022155"}
  ```
  - 删除指定的单个对话（conversation_id和thread_id等效）
  - 同时从所属用户的对话列表中移除引用
  
  **模式3: 清空所有agent对话数据** ⚠️ **危险操作**
  ```json
  {"clear_all_agent_data": true}
  ```
  - 完全清空所有agent模块的对话数据
  - 删除所有 `conversation:*:meta`、`conversation:*:messages`、`user:*:conversations` Key
  - **注意**: 此操作不可恢复，仅限于系统重置或测试环境使用
  
  **模式4: 清理无效引用**
  ```json
  {"cleanup_invalid_refs": true}
  ```
  - 清理用户对话列表中指向已不存在对话的无效引用
  - 维护数据一致性，不删除实际对话数据

- **返回**: 根据操作模式返回相应的统计信息，包括删除的对话数、消息数、处理时间等

### 使用示例

1.  **获取用户对话列表**:
    ```bash
    curl -X GET http://127.0.0.1:8084/api/v0/user/guest/conversations
    ```

2.  **获取特定对话的消息**:
    ```bash
    curl -X GET http://127.0.0.1:8084/api/v0/conversation/guest:20250125143022155/messages
    ```

3.  **获取系统统计信息**:
    ```bash
    curl -X GET http://127.0.0.1:8084/api/v0/conversation_stats
    ```

4.  **对话限额执行示例**:

    **试运行模式 - 查看会删除什么**:
    ```bash
    curl -X POST -H "Content-Type: application/json" \
         -d '{"dry_run": true}' \
         http://127.0.0.1:8084/api/v0/conversation_limit_enforcement
    ```

    **为特定用户执行限额策略**:
    ```bash
    curl -X POST -H "Content-Type: application/json" \
         -d '{"user_id": "guest", "user_max_conversations": 3}' \
         http://127.0.0.1:8084/api/v0/conversation_limit_enforcement
    ```

    **全局执行自定义限额策略**:
    ```bash
    curl -X POST -H "Content-Type: application/json" \
         -d '{"user_max_conversations": 5, "conversation_max_length": 20}' \
         http://127.0.0.1:8084/api/v0/conversation_limit_enforcement
    ```

5.  **对话清理示例**:

    **清理无效引用**:
    ```bash
    curl -X POST -H "Content-Type: application/json" \
         -d '{"cleanup_invalid_refs": true}' \
         http://127.0.0.1:8084/api/v0/conversation_cleanup
    ```

    **删除特定用户的所有对话**:
    ```bash
    curl -X POST -H "Content-Type: application/json" \
         -d '{"user_id": "test_user"}' \
         http://127.0.0.1:8084/api/v0/conversation_cleanup
    ```

    **删除特定对话**:
    ```bash
    curl -X POST -H "Content-Type: application/json" \
         -d '{"conversation_id": "guest:20250125143022155"}' \
         http://127.0.0.1:8084/api/v0/conversation_cleanup
    ```

    **清空所有agent对话数据** ⚠️ **危险操作**:
    ```bash
    curl -X POST -H "Content-Type: application/json" \
         -d '{"clear_all_agent_data": true}' \
         http://127.0.0.1:8084/api/v0/conversation_cleanup
    ```

### API响应示例

#### 对话限额执行API响应示例

**试运行模式响应**:
```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "mode": "global",
    "dry_run": true,
    "parameters": {
      "user_max_conversations": 5,
      "conversation_max_length": 10
    },
    "processed_users": 2,
    "total_conversations_processed": 6,
    "total_conversations_deleted": 2,
    "total_messages_trimmed": 0,
    "execution_summary": [
      {
        "user_id": "test_user",
        "original_conversations": 1,
        "kept_conversations": 1,
        "deleted_conversations": 0,
        "messages_trimmed": 0
      },
      {
        "user_id": "wang11",
        "original_conversations": 5,
        "kept_conversations": 3,
        "deleted_conversations": 2,
        "messages_trimmed": 0
      }
    ],
    "execution_time_ms": 15,
    "timestamp": "2025-08-07T22:54:27.941807",
    "response": "限额执行完成"
  }
}
```

#### 对话清理API响应示例

**清理无效引用响应**:
```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "operation_mode": "cleanup_invalid_refs",
    "processed_users": 2,
    "cleaned_references": 0,
    "response": "无效引用清理完成",
    "timestamp": "2025-08-07T22:54:27.975516"
  }
}
```

**删除指定对话响应**:
```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "operation_mode": "delete_conversation",
    "conversation_id": "guest:20250125143022155",
    "user_id": "guest",
    "deleted_messages": 8,
    "execution_time_ms": 2,
    "existed": true,
    "response": "对话删除完成",
    "timestamp": "2025-08-07T22:54:27.990033"
  }
}
```

**参数错误响应示例**:
```json
{
  "code": 400,
  "success": false,
  "message": "请求参数错误",
  "data": {
    "error_type": "missing_required_params",
    "response": "参数错误：必须指定操作模式",
    "error": "请提供以下参数组合之一: user_id | conversation_id/thread_id | clear_all_agent_data | cleanup_invalid_refs",
    "timestamp": "2025-08-07T22:54:28.002030"
  }
}
```

## 自动与手动策略的关系

系统的对话管理由三层策略共同保障：自动化的实时保留策略、补救性的限额执行API和精确的数据清理API。这三者是互补关系，各司其职。

### 1. 自动保留策略 (`LTRIM` 操作)

-   **角色**: "日常门卫"，负责高频的数量控制。
-   **机制**: 在数据写入的瞬间，通过 `LTRIM` 命令实时确保每个用户的对话数和每个对话的消息数不超过预设上限 (`USER_MAX_CONVERSATIONS` 和 `CONVERSATION_MAX_LENGTH`)。
-   **特点**: 高效、实时，保证了 Redis 数据的基本健康和数量可控。但它只关心"新旧顺序"，不关心对话的实际"质量"（例如，一个仅有一两句话的废弃对话和一个有价值的长对话，它只看谁更新)。
-   **局限性**: 只在新数据写入时生效，对于已存在的历史数据无能为力。

### 2. 补救性限额执行 (`/api/v0/conversation_limit_enforcement`)

-   **角色**: "历史数据整理师"，负责对存量数据进行批量限额控制。
-   **机制**: 
    -   扫描所有用户的对话数据，按照指定的限额策略进行裁剪
    -   支持全局处理或指定用户处理
    -   可以自定义限额参数，不局限于配置文件中的值
    -   支持试运行模式，可以预览操作结果而不实际执行
-   **特点**: 
    -   **批量处理**: 一次性处理大量历史数据
    -   **灵活配置**: 可临时调整限额参数
    -   **安全预览**: 试运行模式确保操作安全
    -   **详细统计**: 提供完整的执行报告
-   **使用场景**:
    -   系统配置更改后，需要追溯应用新的限额策略
    -   定期维护，释放Redis内存空间
    -   数据迁移前的批量整理

### 3. 精确数据清理 (`/api/v0/conversation_cleanup`)

-   **角色**: "精确手术刀"，负责特定目标的数据清理和维护。
-   **机制**: 提供四种精确的操作模式：
    -   **清理无效引用**: 维护数据一致性，清理TTL过期后的孤立引用
    -   **删除指定用户**: 完全移除某个用户的所有对话数据
    -   **删除指定对话**: 精确删除单个对话及相关引用
    -   **清空所有数据**: 系统重置或测试环境的完全清理
-   **特点**: 
    -   **操作精确**: 每种模式都有明确的作用范围
    -   **参数互斥**: 严格的参数验证，避免误操作
    -   **安全保护**: 危险操作有明确标识和警告
    -   **数据完整性**: 确保删除操作的原子性和一致性
-   **使用场景**:
    -   日常维护中的数据一致性保障
    -   用户数据删除请求的处理
    -   系统故障后的数据修复
    -   开发测试环境的数据重置

### 三层策略的协同工作

1. **预防为主**: 自动保留策略在源头控制数据增长
2. **定期维护**: 限额执行API处理历史数据积累问题  
3. **精确清理**: 数据清理API处理特定的维护需求和异常情况

这种分层设计确保了系统在各种场景下都能有效管理Redis中的对话数据，既保证了性能，又提供了灵活性和安全性。

## 安全注意事项与最佳实践

### ⚠️ 危险操作警告

1. **`clear_all_agent_data` 操作**：
   - 这是一个**不可逆**的操作，会删除所有agent对话数据
   - 仅限于系统重置、测试环境清理或紧急维护使用
   - 生产环境使用前务必进行数据备份

2. **限额执行操作**：
   - 非试运行模式下会实际删除数据
   - 建议先用 `dry_run: true` 预览操作结果
   - 重要数据删除前请确保已备份

### 🔒 最佳实践建议

1. **API使用顺序**：
   ```
   查看统计 → 试运行预览 → 实际执行 → 验证结果
   ```

2. **定期维护建议**：
   - 每周运行一次 `cleanup_invalid_refs` 清理无效引用
   - 根据Redis内存使用情况，定期执行限额策略
   - 监控 `/api/v0/conversation_stats` 统计信息

3. **参数验证**：
   - 所有API都有严格的参数验证
   - 参数冲突会返回400错误和详细说明
   - 仔细阅读错误信息以正确使用API

4. **权限控制**：
   - 危险操作建议添加额外的权限验证
   - 生产环境建议限制这些API的访问权限
   - 记录所有管理操作的审计日志

### 📊 监控建议

定期检查以下指标：
- Redis内存使用量变化
- 对话数据增长趋势  
- 无效引用的数量
- API执行时间和频率

通过合理使用这些API，可以有效地管理和维护Redis中的对话历史数据，确保系统的稳定性和性能。
