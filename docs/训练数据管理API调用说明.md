# 训练数据管理API调用说明

## 概述

训练数据管理API提供了完整的训练数据CRUD操作，支持SQL、DDL、文档和错误SQL四种数据类型的管理。所有API都采用统一的响应格式，并提供详细的错误信息。

**基础URL：** `http://localhost:8084/api/v0`

## API列表

| API端点 | 方法 | 功能描述 |
|---------|------|----------|
| `/training_data/stats` | GET | 获取训练数据统计信息 |
| `/training_data/query` | POST | 分页查询训练数据，支持筛选和搜索 |
| `/training_data/create` | POST | 创建训练数据，支持单条和批量操作 |
| `/training_data/delete` | POST | 删除训练数据，支持批量操作 |

---

## 1. 获取统计信息

### 请求信息
```http
GET /api/v0/training_data/stats
```

### 请求参数
无需参数

### 响应示例
```json
{
    "code": 200,
    "data": {
        "last_updated": "2025-06-30T16:03:42.112380",
        "response": "统计信息获取成功",
        "total_count": 228,
        "type_breakdown": {
            "ddl": 9,
            "documentation": 9,
            "error_sql": 1,
            "sql": 209
        },
        "type_percentages": {
            "ddl": 3.95,
            "documentation": 3.95,
            "error_sql": 0.44,
            "sql": 91.67
        }
    },
    "message": "操作成功",
    "success": true
}
```

### 响应字段说明
- `total_count`: 训练数据总数
- `type_breakdown`: 各类型数据的具体数量
- `type_percentages`: 各类型数据的百分比（保留2位小数）
- `last_updated`: 最后更新时间

---

## 2. 查询训练数据

### 请求信息
```http
POST /api/v0/training_data/query
```

### 请求参数
```json
{
  "page": 1,                    // 页码，必须大于0，默认1
  "page_size": 20,              // 每页大小，1-100之间，默认20
  "training_data_type": "sql",  // 可选，筛选类型："sql"|"ddl"|"documentation"|"error_sql"
  "search_keyword": "用户",     // 可选，搜索关键词，最大100字符
  "sort_by": "id",              // 可选，排序字段："id"|"training_data_type"，默认"id"
  "sort_order": "desc"          // 可选，排序方向："asc"|"desc"，默认"desc"
}
```

### 响应示例
```json
{
    "code": 200,
    "data": {
        "filters_applied": {
            "search_keyword": "用户",
            "training_data_type": "sql"
        },
        "pagination": {
            "has_next": false,
            "has_prev": false,
            "page": 1,
            "page_size": 20,
            "total": 2,
            "total_pages": 1
        },
        "records": [
            {
                "content": "SELECT user_id, user_name, last_login FROM users WHERE last_login >= CURRENT_DATE - INTERVAL '30 days';",
                "id": "fb113c5e-6cde-4653-ac5f-7558f6e634db-sql",
                "question": "查看活跃用户列表",
                "training_data_type": "sql"
            },
            {
                "content": "SELECT * FROM users WHERE delete_ts IS NULL;",
                "id": "06885f86-9d52-46f3-ad77-62ac455f6ea9-sql",
                "question": "查询所有用户信息",
                "training_data_type": "sql"
            }
        ],
        "response": "查询成功，共找到 2 条记录"
    },
    "message": "操作成功",
    "success": true
}
```

### 错误响应示例
```json
{
  "code": 400,
  "success": false,
  "message": "请求参数错误",
  "data": {
    "error_type": "missing_required_params",
    "missing_params": ["page"],
    "response": "页码必须大于0",
    "timestamp": "2025-06-24T17:41:47.486749"
  }
}
```

---

## 3. 创建训练数据

### 请求信息
```http
POST /api/v0/training_data/create
```

### 请求参数

#### 单条创建
```json
{
  "data": {
    "training_data_type": "sql",
    "question": "查询所有用户",
    "sql": "SELECT * FROM users WHERE delete_ts IS NULL"
  }
}
```

#### 批量创建
```json
{
  "data": [
    {
      "training_data_type": "sql",
      "question": "查询活跃用户",
      "sql": "SELECT * FROM users WHERE status = 'active'"
    },
    {
      "training_data_type": "documentation",
      "content": "用户表用于存储系统用户的基本信息和状态。"
    },
    {
      "training_data_type": "ddl",
      "ddl": "CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(100));"
    },
    {
      "training_data_type": "error_sql",
      "question": "错误的查询示例",
      "sql": "SELCT * FROM users"
    }
  ]
}
```

### 数据类型字段要求

| 类型 | 必需字段 | 可选字段 | 说明 |
|------|----------|----------|------|
| `sql` | `training_data_type`, `question`, `sql` | - | SQL查询训练数据 |
| `documentation` | `training_data_type`, `content` | - | 文档说明训练数据 |
| `ddl` | `training_data_type`, `ddl` | - | DDL语句训练数据 |
| `error_sql` | `training_data_type`, `question`, `sql` | - | 错误SQL示例数据 |

### 响应示例
```json
{
    "code": 200,
    "data": {
        "current_total_count": 229,
        "failed_count": 0,
        "response": "训练数据创建完成",
        "results": [
            {
                "index": 0,
                "message": "sql训练数据创建成功",
                "success": true,
                "training_id": "f4903d4c-7c37-4140-bfde-930f0f50fbf3-sql",
                "type": "sql"
            }
        ],
        "successfully_created": 1,
        "summary": {
            "ddl": 0,
            "documentation": 0,
            "error_sql": 0,
            "sql": 1
        },
        "total_requested": 1
    },
    "message": "操作成功",
    "success": true
}
```



```json
{
    "code": 200,
    "data": {
        "current_total_count": 231,
        "failed_count": 0,
        "response": "训练数据创建完成",
        "results": [
            {
                "index": 0,
                "message": "sql训练数据创建成功",
                "success": true,
                "training_id": "0d3dd858-b3a3-4eca-863a-a41c552862a2-sql",
                "type": "sql"
            },
            {
                "index": 1,
                "message": "documentation训练数据创建成功",
                "success": true,
                "training_id": "59b802fd-e0f7-48b4-b207-afd170d41c37-doc",
                "type": "documentation"
            }
        ],
        "successfully_created": 2,
        "summary": {
            "ddl": 0,
            "documentation": 1,
            "error_sql": 0,
            "sql": 1
        },
        "total_requested": 2
    },
    "message": "操作成功",
    "success": true
}
```



### SQL安全检查

系统会自动检查SQL语句，禁止以下危险操作：
- `UPDATE`：数据更新操作
- `DELETE`：数据删除操作
- `DROP`：表删除操作
- `ALERT`：表结构修改操作

如果检测到危险操作，会返回错误：
```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "total_requested": 1,
    "successfully_created": 0,
    "failed_count": 1,
    "results": [
      {
        "index": 0,
        "success": false,
        "type": "sql",
        "error": "在训练集中禁止使用\"UPDATE,DELETE,ALERT,DROP\"",
        "message": "创建失败"
      }
    ]
  }
}
```

### 批量操作限制
- 单次批量操作最多支持50条记录。
- 超出限制会返回400错误

---

## 4. 删除训练数据

### 请求信息
```http
POST /api/v0/training_data/delete
```

### 请求参数
```json
{
  "ids": [
    "e1afe1c2-6956-4133-9cb6-0f83c5e1b12d-sql",
    "0db3b76a-6fa5-4c8e-9115-3ec7cc6159fe-doc"
  ],
  "confirm": true  // 必须为true，安全确认机制
}
```

### 参数说明
- `ids`: 要删除的训练数据ID数组，必需
- `confirm`: 删除确认，必须为`true`，否则返回400错误

### 响应示例
```json
{
    "code": 200,
    "data": {
        "current_total_count": 229,
        "deleted_ids": [
            "0d3dd858-b3a3-4eca-863a-a41c552862a2-sql",
            "59b802fd-e0f7-48b4-b207-afd170d41c37-doc"
        ],
        "failed_count": 0,
        "failed_details": [],
        "failed_ids": [],
        "response": "训练数据删除完成",
        "successfully_deleted": 2,
        "total_requested": 2
    },
    "message": "操作成功",
    "success": true
}
```

### 确认机制错误
```json
{
  "code": 400,
  "success": false,
  "message": "请求参数错误",
  "data": {
    "error_type": "missing_required_params",
    "response": "删除操作需要确认，请设置confirm为true",
    "timestamp": "2025-06-24T17:39:58.501962"
  }
}
```

### 批量操作限制
- 单次批量删除最多支持50条记录
- 超出限制会返回400错误

---

## 通用响应格式

### 成功响应
```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    // 具体的响应数据
  }
}
```

### 错误响应
```json
{
  "code": 400|500|503,
  "success": false,
  "message": "错误类型描述",
  "data": {
    "error_type": "错误类型标识",
    "response": "用户友好的错误信息",
    "timestamp": "错误发生时间",
    // 其他错误相关字段
  }
}
```

## 错误码说明

| 状态码 | 含义 | 常见场景 |
|--------|------|----------|
| 200 | 成功 | 请求正常处理 |
| 400 | 请求参数错误 | 参数验证失败、缺少必需参数 |
| 500 | 系统内部错误 | 数据库错误、系统异常 |
| 503 | 服务不可用 | 系统维护、组件异常 |

## 使用示例

### Python调用示例
```python
import requests
import json

BASE_URL = "http://localhost:8084/api/v0"

# 1. 获取统计信息
def get_stats():
    response = requests.get(f"{BASE_URL}/training_data/stats")
    return response.json()

# 2. 查询数据
def query_data(page=1, page_size=20, keyword=None, data_type=None):
    data = {"page": page, "page_size": page_size}
    if keyword:
        data["search_keyword"] = keyword
    if data_type:
        data["training_data_type"] = data_type
    
    response = requests.post(f"{BASE_URL}/training_data/query", json=data)
    return response.json()

# 3. 创建数据
def create_data(training_data):
    response = requests.post(f"{BASE_URL}/training_data/create", 
                           json={"data": training_data})
    return response.json()

# 4. 删除数据
def delete_data(ids):
    response = requests.post(f"{BASE_URL}/training_data/delete",
                           json={"ids": ids, "confirm": True})
    return response.json()

# 使用示例
if __name__ == "__main__":
    # 获取统计
    stats = get_stats()
    print(f"总数据量: {stats['data']['total_count']}")
    
    # 查询SQL类型数据
    results = query_data(data_type="sql", keyword="用户")
    print(f"找到 {results['data']['pagination']['total']} 条记录")
    
    # 创建新数据
    new_data = {
        "training_data_type": "sql",
        "question": "查询测试用户",
        "sql": "SELECT * FROM users WHERE status = 'test'"
    }
    create_result = create_data(new_data)
    if create_result['data']['successfully_created'] > 0:
        created_id = create_result['data']['results'][0]['training_id']
        print(f"创建成功，ID: {created_id}")
        
        # 删除刚创建的数据
        delete_result = delete_data([created_id])
        print(f"删除成功: {delete_result['data']['successfully_deleted']} 条")
```

## 注意事项

1. **安全性**：
   - SQL类型数据会进行语法检查和安全检查
   - 禁止UPDATE、DELETE、DROP、ALERT等危险操作
   - 删除操作需要明确确认（confirm=true）

2. **性能考虑**：
   - 查询API支持分页，建议合理设置page_size
   - 批量操作限制在50条以内
   - 搜索关键词限制100字符以内

3. **数据类型**：
   - 确保为不同类型的训练数据提供正确的字段
   - SQL和error_sql类型需要question和sql字段
   - documentation类型需要content字段
   - ddl类型需要ddl字段

4. **错误处理**：
   - 始终检查响应的success字段
   - 批量操作可能部分成功，需要检查具体结果
   - 关注failed_count和failed_details获取失败详情 