# API响应格式标准化文档

## 目录
- [概述](#概述)
- [标准化原则](#标准化原则)
- [HTTP状态码规范](#http状态码规范)
- [Message字段标准值](#message字段标准值)
- [JSON响应格式规范](#json响应格式规范)
- [完整示例](#完整示例)
- [修改实施计划](#修改实施计划)
- [前端集成指南](#前端集成指南)

## 概述

本文档定义了项目中所有API接口的统一响应格式规范，旨在：
- 统一所有API的响应结构
- 简化前端开发和维护
- 提供清晰的错误处理机制
- 确保向后兼容性

## 标准化原则

### 核心设计原则

1. **统一结构**：所有API响应使用相同的基础结构
2. **职责分离**：`message`用于高层级描述，`data.response`用于具体内容
3. **前端友好**：通过关键字段快速判断如何处理响应
4. **扁平化设计**：避免过深的嵌套结构
5. **向后兼容**：保持现有字段，逐步迁移

### 字段职责划分

- **`code`**：HTTP状态码
- **`success`**：操作成功/失败的布尔值
- **`message`**：高层级分类描述，不包含具体业务细节
- **`data.response`**：用户最终看到的具体内容
- **`data.*`**：其他业务数据和元信息

## HTTP状态码规范

| 状态码 | 使用场景 | 说明 |
|--------|----------|------|
| 200 | 成功响应 | 包括业务成功和业务失败但HTTP通信成功的情况 |
| 400 | 请求参数错误 | 缺少必需参数、参数格式错误 |
| 422 | 参数验证失败 | 参数格式正确但业务逻辑验证失败 |
| 500 | 服务器内部错误 | 数据库错误、系统异常等 |
| 503 | 服务不可用 | Agent初始化失败、健康检查失败等 |

## Message字段标准值

### 成功场景
- `"操作成功"`

### 客户端错误场景 (4xx)
- `"请求参数错误"`
- `"参数验证失败"`

### 服务端错误场景 (5xx)
- `"系统内部错误"`
- `"服务暂时不可用"`

### 业务处理场景
- `"查询失败"`
- `"生成失败"`
- `"处理失败"`

## JSON响应格式规范

### 基础结构

```json
{
  "code": "HTTP状态码 (必须)",
  "success": "布尔值，操作是否成功 (必须)",
  "message": "高层级描述信息 (必须)",
  "data": "数据载体，所有具体信息都在这里 (必须，可为null)"
}
```

### 必须字段
- `code`：HTTP状态码
- `success`：操作是否成功
- `message`：高层级描述
- `data`：数据载体

### data中的通用字段
- `response`：用户看到的具体内容（推荐）
- `timestamp`：响应时间戳（推荐）
- `error_type`：错误类型标识（仅失败时）
- `can_retry`：是否可以重试（仅失败时）

### Ask Agent API专用字段
- `type`：响应类型（DATABASE/CHAT）
- `sql`：生成的SQL语句（DATABASE类型）
- `summary`：LLM对查询结果的总结（DATABASE类型，可选）
- `query_result`：查询结果数据（DATABASE类型）
- `session_id`：会话ID
- `execution_path`：执行路径
- `classification_info`：分类信息
- `agent_version`：Agent版本

## 完整示例

### 1. 数据库查询成功（有摘要）

```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "type": "DATABASE",
    "response": "共有120个服务区。",
    "sql": "SELECT COUNT(*) AS 服务区总数 FROM bss_service_area WHERE delete_ts IS NULL;",
    "summary": "共有120个服务区。",
    "query_result": {
      "columns": ["服务区总数"],
      "rows": [{"服务区总数": 120}],
      "row_count": 1,
      "is_limited": false,
      "total_row_count": 1
    },
    "session_id": "test_session_001",
    "execution_path": ["classify", "agent_database", "format_response"],
    "classification_info": {
      "confidence": 0.95,
      "method": "enhanced_llm",
      "reason": "用户询问服务区数量统计"
    },
    "agent_version": "langgraph_v1",
    "timestamp": "2025-06-21T19:31:19.948772"
  }
}
```

### 2. 数据库查询成功（无摘要，仅数据）

```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "type": "DATABASE",
    "sql": "SELECT service_area_name, company_id FROM bss_service_area LIMIT 10;",
    "query_result": {
      "columns": ["service_area_name", "company_id"],
      "rows": [
        {"service_area_name": "阳澄湖服务区", "company_id": "001"},
        {"service_area_name": "梅村服务区", "company_id": "002"}
      ],
      "row_count": 2,
      "is_limited": true,
      "total_row_count": 120
    },
    "session_id": "test_session_001",
    "execution_path": ["classify", "agent_database", "format_response"],
    "classification_info": {
      "confidence": 0.95,
      "method": "enhanced_llm",
      "reason": "用户询问服务区列表"
    },
    "agent_version": "langgraph_v1",
    "timestamp": "2025-06-21T19:31:19.948772"
  }
}
```

### 3. SQL生成失败

```json
{
  "code": 422,
  "success": false,
  "message": "查询失败",
  "data": {
    "type": "DATABASE",
    "response": "无法生成该查询，因为提供的上下文中缺少存储\"服务区经理名字\"的相关字段信息。",
    "error_type": "sql_generation_failed",
    "session_id": "test_session_001",
    "execution_path": ["classify", "agent_database_error", "format_response"],
    "classification_info": {
      "confidence": 0.95,
      "method": "enhanced_llm",
      "reason": "用户询问服务区经理信息"
    },
    "agent_version": "langgraph_v1",
    "timestamp": "2025-06-21T19:31:19.948772"
  }
}
```

### 4. SQL执行失败

```json
{
  "code": 500,
  "success": false,
  "message": "查询失败",
  "data": {
    "type": "DATABASE",
    "response": "查询执行失败，请稍后重试。",
    "error_type": "sql_execution_failed",
    "sql": "SELECT * FROM non_existent_table;",
    "sql_error_category": "table_not_found",
    "can_retry": false,
    "session_id": "test_session_001",
    "execution_path": ["classify", "agent_database", "sql_execution_error"],
    "classification_info": {
      "confidence": 0.95,
      "method": "enhanced_llm",
      "reason": "用户询问数据统计"
    },
    "agent_version": "langgraph_v1",
    "timestamp": "2025-06-21T19:31:19.948772"
  }
}
```

### 5. 聊天回复成功

```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "type": "CHAT",
    "response": "根据我的知识库，中国荔枝的主要产地集中在南方地区，包括广东、广西、福建、海南等省份。",
    "session_id": "test_session_001",
    "execution_path": ["start", "classify", "agent_chat", "format_response"],
    "classification_info": {
      "confidence": 0.85,
      "method": "rule_based_non_business",
      "reason": "包含非业务实体词: ['荔枝']"
    },
    "agent_version": "langgraph_v1",
    "timestamp": "2025-06-21T22:53:37.723684"
  }
}
```

### 6. Agent初始化失败

```json
{
  "code": 503,
  "success": false,
  "message": "服务暂时不可用",
  "data": {
    "response": "AI服务暂时不可用，请稍后重试。",
    "error_type": "agent_initialization_failed",
    "can_retry": true,
    "session_id": "test_session_001",
    "execution_path": ["agent_init_error"],
    "agent_version": "langgraph_v1",
    "timestamp": "2025-06-21T19:31:19.948772"
  }
}
```

### 7. 请求参数错误

```json
{
  "code": 400,
  "success": false,
  "message": "请求参数错误",
  "data": {
    "response": "缺少必需参数：question",
    "error_type": "missing_required_params",
    "missing_params": ["question"],
    "timestamp": "2025-06-21T19:31:19.948772"
  }
}
```

### 8. 系统内部错误

```json
{
  "code": 500,
  "success": false,
  "message": "系统内部错误",
  "data": {
    "response": "请求处理异常，请稍后重试。",
    "error_type": "request_processing_failed",
    "can_retry": true,
    "session_id": "test_session_001",
    "execution_path": ["general_error"],
    "agent_version": "langgraph_v1",
    "timestamp": "2025-06-21T19:31:19.948772"
  }
}
```

### 9. 健康检查成功

```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "status": "healthy",
    "test_result": true,
    "workflow_compiled": true,
    "tools_count": 4,
    "response": "Agent健康检查完成",
    "checks": {
      "agent_creation": true,
      "tools_import": true,
      "llm_connection": true,
      "classifier_ready": true
    },
    "timestamp": "2025-06-21T19:31:19.948772"
  }
}
```

### 10. 健康检查失败

```json
{
  "code": 503,
  "success": false,
  "message": "服务暂时不可用",
  "data": {
    "status": "degraded",
    "test_result": false,
    "workflow_compiled": false,
    "tools_count": 0,
    "response": "部分组件异常",
    "checks": {
      "agent_creation": false,
      "tools_import": true,
      "llm_connection": true,
      "classifier_ready": true
    },
    "timestamp": "2025-06-21T19:31:19.948772"
  }
}
```

## 修改实施计划

### 第一阶段：核心基础设施修改

#### 1.1 `common/result.py`
**修改重点：**
- 更新默认 message 值
- 新增便捷方法处理常见场景
- 确保所有具体信息通过 `data` 字段传递

**新增功能：**
- 标准化错误响应方法
- Ask Agent API 专用响应方法

#### 1.2 新建 `common/messages.py`
**内容：**
```python
class MessageTemplate:
    SUCCESS = "操作成功"
    BAD_REQUEST = "请求参数错误"
    VALIDATION_FAILED = "参数验证失败"
    INTERNAL_ERROR = "系统内部错误"
    SERVICE_UNAVAILABLE = "服务暂时不可用"
    QUERY_FAILED = "查询失败"
    GENERATION_FAILED = "生成失败"
    PROCESSING_FAILED = "处理失败"
```

### 第二阶段：主要API接口修改

#### 2.1 `citu_app.py`
**需要修改的API接口：**

1. **`/api/v0/ask_agent`**
   - 字段重命名：`data_result` → `query_result`
   - 错误信息迁移：从 `message` 到 `data.response`
   - 统一 message 值

2. **`/api/v0/ask` 和 `/api/v0/ask_cached`**
   - 返回格式统一：`rows`, `columns` → `query_result`
   - LLM解释性文本处理
   - 错误响应标准化

3. **`/api/v0/agent_health`**
   - 关键修改：`data.message` → `data.response`
   - 统一健康状态描述

4. **其他管理API**
   - `/api/v0/cache_overview`
   - `/api/v0/cache_cleanup`
   - `/api/v0/training_error_question_sql`
   - `/api/v0/citu_run_sql`

#### 2.2 `flask_app.py`
**修改内容：**
- 统一错误返回格式
- 使用标准化的 result 方法

### 第三阶段：Agent和工具层修改

#### 3.1 `agent/citu_agent.py`
**主要修改点：**
- `_format_response_node()` 方法：
  - 字段重命名：`data_result` → `query_result`
  - 错误处理：`error` → `data.response`
  - 统一 `response` 字段使用

- `process_question()` 方法：
  - 确保返回格式符合新规范

#### 3.2 `agent/state.py`
**修改内容：**
- 更新 `final_response` 结构定义
- 确保状态管理符合新字段命名

#### 3.3 工具层修改
**文件：** `agent/tools/sql_execution.py`, `agent/tools/summary_generation.py`, `agent/tools/general_chat.py`
**修改内容：**
- 统一返回结果字段命名
- 确保 response 格式一致

### 第四阶段：文档和测试更新

#### 4.1 `docs/agent api 说明.md`
**更新内容：**
- 所有API示例格式更新
- 字段命名统一
- Message 值标准化

#### 4.2 其他文档
- 更新包含API响应示例的所有文档
- 前端集成指南更新

### 修改优先级

| 优先级 | 阶段 | 文件/模块 | 依赖关系 |
|--------|------|-----------|----------|
| P0 | 第一阶段 | `common/result.py` | 无依赖，基础组件 |
| P0 | 第一阶段 | `common/messages.py` | 无依赖，新建文件 |
| P1 | 第二阶段 | `citu_app.py` | 依赖第一阶段完成 |
| P1 | 第二阶段 | `agent/citu_agent.py` | 依赖第一阶段完成 |
| P2 | 第三阶段 | `agent/state.py`, `agent/tools/*` | 依赖前两阶段 |
| P2 | 第三阶段 | `flask_app.py` | 依赖第一阶段 |
| P3 | 第四阶段 | 文档更新 | 依赖前三阶段 |

### 关键变更总结

1. **字段重命名**
   - `data_result` → `query_result`
   - `data.message` → `data.response`（健康检查API）

2. **内容迁移**
   - 具体错误信息：`message` → `data.response`
   - LLM解释性文本：统一放入 `data.response`

3. **格式统一**
   - 所有API使用相同的基础JSON结构
   - 错误处理格式标准化

4. **Message标准化**
   - 使用预定义的message常量
   - 移除message中的具体业务细节

## 前端集成指南

### 响应处理逻辑

```javascript
function handleApiResponse(response) {
  const { code, success, message, data } = response;
  
  if (success) {
    // 成功情况处理
    if (data.type === "DATABASE") {
      // 数据库查询成功
      if (data.summary || data.response) {
        displaySummary(data.summary || data.response);
      }
      if (data.query_result) {
        displayTable(data.query_result);
      }
      if (data.sql) {
        displaySQL(data.sql);
      }
    } else if (data.type === "CHAT") {
      // 聊天回复
      displayChatMessage(data.response);
    } else {
      // 其他成功情况
      displayMessage(data.response || message);
    }
  } else {
    // 失败情况处理
    const errorMessage = data.response || message;
    displayError(errorMessage);
    
    // 根据错误类型提供特殊处理
    if (data.error_type === "sql_generation_failed") {
      showSuggestion("请尝试重新描述您的问题");
    } else if (data.can_retry) {
      showRetryButton();
    }
  }
}
```

### 关键判断字段

1. **`success`** - 主要成功/失败判断
2. **`data.type`** - 响应类型判断（DATABASE/CHAT）
3. **`data.response`** - 用户展示内容
4. **`data.error_type`** - 错误类型特殊处理
5. **`data.can_retry`** - 重试机制判断

### 数据展示优先级

1. **摘要文本**：`data.summary` 或 `data.response`
2. **表格数据**：`data.query_result`
3. **SQL语句**：`data.sql`（可选显示）

这样的设计确保前端能够以统一、简洁的方式处理所有API响应，提高开发效率和用户体验。