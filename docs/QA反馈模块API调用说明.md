
# QA反馈模块API调用说明

## 📋 概述

QA反馈模块提供了完整的用户反馈管理功能，支持用户对问答结果进行点赞/点踩反馈，并将反馈数据转化为训练数据。本模块包含6个主要API端点，支持反馈记录的创建、查询、修改、删除以及训练数据集成。

### 🔧 基础信息
- **基础URL**: `http://localhost:5000`
- **API前缀**: `/api/v0/qa_feedback/`
- **数据格式**: JSON
- **字符编码**: UTF-8

---

## 🔍 API端点一览

| API端点 | 方法 | 功能描述 |
|---------|------|----------|
| `/api/v0/qa_feedback/query` | POST | 查询反馈记录（支持分页、筛选、排序） |
| `/api/v0/qa_feedback/delete/{id}` | DELETE | 删除指定反馈记录 |
| `/api/v0/qa_feedback/update/{id}` | PUT | 修改指定反馈记录 |
| `/api/v0/qa_feedback/add_to_training` | POST | **核心功能**：批量添加到训练集 |
| `/api/v0/qa_feedback/add` | POST | 创建新的反馈记录 |
| `/api/v0/qa_feedback/stats` | GET | 获取反馈统计信息 |

---

## 📖 详细API说明

### 1. 查询反馈记录 API

**端点**: `POST /api/v0/qa_feedback/query`

**功能**: 查询反馈记录，支持分页、筛选和排序功能，主要用于审核页面展示反馈数据。

#### 📝 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `page` | int | 否 | 1 | 页码（从1开始） |
| `page_size` | int | 否 | 20 | 每页记录数（范围：1-100） |
| `is_thumb_up` | boolean | 否 | null | 筛选点赞状态（true=点赞，false=点踩） |
| `create_time_start` | string | 否 | null | 创建时间开始（格式：YYYY-MM-DD） |
| `create_time_end` | string | 否 | null | 创建时间结束（格式：YYYY-MM-DD） |
| `is_in_training_data` | boolean | 否 | null | 是否已加入训练数据 |
| `sort_by` | string | 否 | "create_time" | 排序字段（id/create_time/update_time/user_id） |
| `sort_order` | string | 否 | "desc" | 排序方向（asc/desc） |

#### 🌰 请求示例

**基础查询**：
```json
{
  "page": 1,
  "page_size": 10
}
```

**完整筛选查询**：
```json
{
  "page": 1,
  "page_size": 20,
  "is_thumb_up": true,
  "create_time_start": "2024-01-01",
  "create_time_end": "2024-12-31",
  "is_in_training_data": false,
  "sort_by": "create_time",
  "sort_order": "desc"
}
```

**查询未训练的负向反馈**：
```json
{
  "is_thumb_up": false,
  "is_in_training_data": false,
  "sort_by": "create_time",
  "sort_order": "asc"
}
```

#### ✅ 成功响应格式

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功，共找到 25 条记录",
  "data": {
    "records": [
      {
        "id": 1,
        "question": "查询所有用户信息",
        "sql": "SELECT * FROM users",
        "is_thumb_up": true,
        "user_id": "user123",
        "create_time": "2024-06-24T10:30:00",
        "is_in_training_data": false,
        "update_time": null
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 25,
      "total_pages": 2,
      "has_next": true,
      "has_prev": false
    }
  }
}
```

---

### 2. 删除反馈记录 API

**端点**: `DELETE /api/v0/qa_feedback/delete/{id}`

**功能**: 根据记录ID删除指定的反馈记录。

#### 📝 路径参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `id` | int | 是 | 反馈记录的ID |

#### 🌰 请求示例

```
DELETE /api/v0/qa_feedback/delete/123
```

#### ✅ 成功响应格式

```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "response": "反馈记录删除成功",
    "deleted_id": 123
  }
}
```

#### ❌ 失败响应格式

```json
{
  "code": 404,
  "success": false,
  "message": "资源未找到",
  "data": {
    "response": "反馈记录不存在 (ID: 123)",
    "timestamp": "2024-06-24T10:30:00"
  }
}
```

---

### 3. 修改反馈记录 API

**端点**: `PUT /api/v0/qa_feedback/update/{id}`

**功能**: 修改指定反馈记录的内容。

#### 📝 路径参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `id` | int | 是 | 反馈记录的ID |

#### 📝 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `question` | string | 否 | 问题内容 |
| `sql` | string | 否 | SQL内容 |
| `is_thumb_up` | boolean | 否 | 是否点赞 |
| `user_id` | string | 否 | 用户ID |
| `is_in_training_data` | boolean | 否 | 是否已加入训练数据 |

#### 🌰 请求示例

**修改问题和SQL**：
```json
{
  "question": "查询活跃用户信息",
  "sql": "SELECT * FROM users WHERE status = 'active'"
}
```

**修改反馈状态**：
```json
{
  "is_thumb_up": false,
  "is_in_training_data": true
}
```

#### ✅ 成功响应格式

```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "response": "反馈记录更新成功",
    "updated_id": 123,
    "updated_fields": ["question", "sql"]
  }
}
```

---

### 4. 添加到训练数据集 API ⭐

**端点**: `POST /api/v0/qa_feedback/add_to_training`

**功能**: **核心功能**，将反馈记录批量添加到训练数据集。支持混合处理：正向反馈（点赞）加入SQL训练集，负向反馈（点踩）加入错误SQL训练集。

#### 📝 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `feedback_ids` | array[int] | 是 | 反馈记录ID列表 |

#### 🌰 请求示例

**批量添加训练数据**：
```json
{
  "feedback_ids": [17]
}
```

#### ✅ 成功响应格式

```json
{
    "code": 200,
    "data": {
        "response": "训练数据添加完成，成功处理 1 条记录",
        "successfully_trained_ids": [
            17
        ],
        "summary": {
            "already_trained": 0,
            "errors": 0,
            "negative_trained": 1,
            "positive_trained": 0,
            "total_processed": 1,
            "total_requested": 1
        },
        "training_details": {
            "error_sql_training_count": 1,
            "sql_training_count": 0
        }
    },
    "message": "操作成功",
    "success": true
}
```

#### 🔄 处理逻辑说明

- **正向反馈** (`is_thumb_up=true`) → 调用 `vn.train(question, sql)` 
- **负向反馈** (`is_thumb_up=false`) → 调用 `vn.train_error_sql(question, sql)`
- **已训练记录** → 跳过处理
- **训练成功** → 自动标记 `is_in_training_data=true`

---

### 5. 创建反馈记录 API

**端点**: `POST /api/v0/qa_feedback/add`

**功能**: 创建新的反馈记录，通常由前端在用户点赞/点踩时调用。

#### 📝 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `question` | string | 是 | - | 用户问题 |
| `sql` | string | 是 | - | 生成的SQL |
| `is_thumb_up` | boolean | 是 | - | 是否点赞 |
| `user_id` | string | 否 | "guest" | 用户ID |

#### 🌰 请求示例

**用户点赞示例**：
```json
{
  "question": "查询所有部门信息",
  "sql": "SELECT * FROM departments",
  "is_thumb_up": true,
  "user_id": "user123"
}
```

**用户点踩示例**：
```json
{
  "question": "统计每个部门的员工数量",
  "sql": "SELECT department, COUNT(*) FROM employees",
  "is_thumb_up": false,
  "user_id": "user456"
}
```

#### ✅ 成功响应格式

```json
{
    "code": 200,
    "data": {
        "feedback_id": 18,
        "response": "反馈记录创建成功"
    },
    "message": "操作成功",
    "success": true
}
```

---

### 6. 反馈统计信息 API

**端点**: `GET /api/v0/qa_feedback/stats`

**功能**: 获取反馈数据的统计信息，用于监控面板和数据分析。

#### 🌰 请求示例

```
GET /api/v0/qa_feedback/stats
```

#### ✅ 成功响应格式

```json
{
    "code": 200,
    "data": {
        "negative_feedback": 10,
        "positive_feedback": 8,
        "positive_rate": 44.44,
        "response": "统计信息获取成功",
        "total_feedback": 18,
        "trained_feedback": 5,
        "training_rate": 27.78,
        "untrained_feedback": 13
    },
    "message": "操作成功",
    "success": true
}
```

#### 📊 统计字段说明

| 字段名 | 说明 |
|--------|------|
| `total_feedback` | 总反馈数 |
| `positive_feedback` | 正向反馈数（点赞） |
| `negative_feedback` | 负向反馈数（点踩） |
| `trained_feedback` | 已训练反馈数 |
| `untrained_feedback` | 未训练反馈数 |
| `positive_rate` | 正向反馈率（%） |
| `training_rate` | 训练覆盖率（%） |

---

## 🔧 使用流程示例

### 典型工作流程

1. **用户反馈阶段**
   ```json
   POST /api/v0/qa_feedback/add
   {
     "question": "查询用户订单",
     "sql": "SELECT * FROM orders WHERE user_id = 123",
     "is_thumb_up": true,
     "user_id": "user123"
   }
   ```

2. **审核管理阶段**
   ```json
   POST /api/v0/qa_feedback/query
   {
     "is_in_training_data": false,
     "page": 1,
     "page_size": 50
   }
   ```

3. **批量训练阶段**
   ```json
   POST /api/v0/qa_feedback/add_to_training
   {
     "feedback_ids": [1, 2, 3, 4, 5]
   }
   ```

4. **统计监控阶段**
   ```
   GET /api/v0/qa_feedback/stats
   ```

---

## ⚠️ 错误处理

### 常见错误响应

**400 - 请求参数错误**
```json
{
  "code": 400,
  "success": false,
  "message": "请求参数错误",
  "data": {
    "response": "缺少必需参数：question",
    "missing_params": ["question"],
    "error_type": "missing_required_params",
    "timestamp": "2024-06-24T10:30:00"
  }
}
```

**404 - 资源未找到**
```json
{
  "code": 404,
  "success": false,
  "message": "资源未找到",
  "data": {
    "response": "反馈记录不存在 (ID: 999)",
    "error_type": "resource_not_found",
    "timestamp": "2024-06-24T10:30:00"
  }
}
```

**500 - 系统内部错误**
```json
{
  "code": 500,
  "success": false,
  "message": "系统内部错误",
  "data": {
    "response": "查询反馈记录失败，请稍后重试",
    "error_type": "database_error",
    "can_retry": true,
    "timestamp": "2024-06-24T10:30:00"
  }
}
```

---

## 🚀 Postman 测试集合

### 环境变量
```json
{
  "base_url": "http://localhost:5000",
  "api_prefix": "/api/v0/qa_feedback"
}
```

### 测试用例建议

1. **数据创建测试** - 先添加几条反馈记录
2. **查询功能测试** - 测试各种筛选和排序组合
3. **更新功能测试** - 修改记录内容
4. **训练集成测试** - 批量添加到训练数据
5. **统计功能测试** - 验证统计数据准确性
6. **删除功能测试** - 清理测试数据

---

## 📝 注意事项

1. **数据库自动创建**: 首次调用任何API时，系统会自动创建 `qa_feedback` 表
2. **连接复用**: 系统优先复用现有的Vanna数据库连接，提高性能
3. **事务安全**: 所有写操作都使用数据库事务，确保数据一致性
4. **分页限制**: 查询API的 `page_size` 最大值为100，避免单次返回过多数据
5. **训练幂等性**: 同一记录不会重复训练，系统会自动跟踪训练状态

---

## 🎯 总结

QA反馈模块提供了完整的反馈数据生命周期管理，从用户反馈收集到训练数据集成，支持高效的数据处理和智能的训练优化。通过合理使用这些API，可以构建强大的用户反馈系统，持续改进AI模型的表现。 