# 训练数据管理API概要设计文档

## 📋 概述

本文档描述了训练数据管理系统的API设计方案，提供完整的CRUD操作接口，支持分页查询、类型筛选、批量操作等功能。该系统旨在为AI训练数据提供统一的管理入口。

### 🎯 设计目标
- **统一管理**：提供训练数据的统一管理接口
- **类型支持**：支持SQL、文档、DDL、错误SQL四种训练数据类型
- **批量操作**：支持批量创建和删除操作
- **性能优化**：支持分页查询和类型筛选
- **数据统计**：提供详细的数据统计信息

### 🔧 基础信息
- **基础URL**: `http://localhost:5000`
- **API前缀**: `/api/v0/training_data/`
- **数据格式**: JSON
- **字符编码**: UTF-8
- **命名规范**: 统一使用动词命名（query/create/delete/stats）

---

## 🚀 API端点一览

| API端点 | 方法 | 功能描述 |
|---------|------|----------|
| `/api/v0/training_data/query` | POST | 分页查询训练数据（支持类型筛选和搜索） |
| `/api/v0/training_data/create` | POST | 创建训练数据（支持单条和批量） |
| `/api/v0/training_data/delete` | POST | 删除训练数据（支持批量删除） |
| `/api/v0/training_data/stats` | GET | 获取训练数据统计信息 |

---

## 📖 详细API设计

### 1. 分页查询API

**端点**: `POST /api/v0/training_data/query`

**功能**: 分页查询训练数据，支持类型筛选、搜索和排序功能。

#### 📝 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `page` | int | 否 | 1 | 页码（从1开始） |
| `page_size` | int | 否 | 20 | 每页记录数（范围：1-100） |
| `training_data_type` | string | 否 | null | 筛选类型：sql/documentation/ddl/error_sql |
| `sort_by` | string | 否 | "id" | 排序字段：id/training_data_type |
| `sort_order` | string | 否 | "desc" | 排序方向：asc/desc |
| `search_keyword` | string | 否 | null | 搜索关键词（在question/content中搜索） |

#### 🌰 请求示例

**基础查询**：
```json
{
  "page": 1,
  "page_size": 20
}
```

**筛选查询**：
```json
{
  "page": 1,
  "page_size": 20,
  "training_data_type": "sql",
  "search_keyword": "用户",
  "sort_by": "id",
  "sort_order": "desc"
}
```

#### ✅ 成功响应格式

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功，共找到 156 条记录",
  "data": {
    "records": [
      {
        "id": "uuid-123-sql",
        "training_data_type": "sql",
        "question": "查询所有用户信息",
        "content": "SELECT * FROM users",
        "created_at": "2024-06-24T10:30:00"
      },
      {
        "id": "uuid-456-doc",
        "training_data_type": "documentation", 
        "question": null,
        "content": "用户表包含用户的基本信息...",
        "created_at": "2024-06-24T11:00:00"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 156,
      "total_pages": 8,
      "has_next": true,
      "has_prev": false
    },
    "filters_applied": {
      "training_data_type": "sql",
      "search_keyword": "用户"
    }
  }
}
```

---

### 2. 创建训练数据API

**端点**: `POST /api/v0/training_data/create`

**功能**: 创建训练数据，支持单条和批量创建，支持四种数据类型。

#### 📝 请求参数

**单条记录**：
```json
{
  "data": {
    "training_data_type": "sql",
    "question": "查询所有用户信息",
    "sql": "SELECT * FROM users"
  }
}
```

**批量记录**：
```json
{
  "data": [
    {
      "training_data_type": "sql",
      "question": "查询所有用户信息", 
      "sql": "SELECT * FROM users"
    },
    {
      "training_data_type": "documentation",
      "content": "用户表包含用户的基本信息..."
    },
    {
      "training_data_type": "ddl",
      "ddl": "CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(100));"
    },
    {
      "training_data_type": "error_sql",
      "question": "查询用户",
      "sql": "SELECT * FROM user"
    }
  ]
}
```

#### 📋 各类型字段要求

| 类型 | 必填字段 | 可选字段 | 说明 |
|------|----------|----------|------|
| `sql` | `sql` | `question` | 如果不提供question会自动生成，SQL会进行语法检查 |
| `error_sql` | `question`, `sql` | 无 | 错误的SQL示例，不进行语法检查 |
| `documentation` | `content` | 无 | 文档内容，不进行格式检查 |
| `ddl` | `ddl` | 无 | DDL语句，不进行语法检查 |

#### ✅ 成功响应格式

```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "response": "训练数据创建完成",
    "total_requested": 4,
    "successfully_created": 3,
    "failed_count": 1,
    "results": [
      {
        "index": 0,
        "success": true,
        "training_id": "uuid-123-sql",
        "type": "sql",
        "message": "SQL训练数据创建成功"
      },
      {
        "index": 1,
        "success": true,
        "training_id": "uuid-456-doc",
        "type": "documentation", 
        "message": "文档训练数据创建成功"
      },
      {
        "index": 2,
        "success": true,
        "training_id": "uuid-789-ddl",
        "type": "ddl",
        "message": "DDL训练数据创建成功"
      },
      {
        "index": 3,
        "success": false,
        "type": "error_sql",
        "error": "创建失败：缺少必填字段question",
        "message": "创建失败"
      }
    ],
    "summary": {
      "sql": 1,
      "documentation": 1,
      "ddl": 1,
      "error_sql": 0
    },
    "current_total_count": 159
  }
}
```

---

### 3. 删除训练数据API

**端点**: `POST /api/v0/training_data/delete`

**功能**: 删除指定的训练数据记录，支持批量删除。

#### 📝 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `ids` | array[string] | 是 | 要删除的训练数据ID列表 |
| `confirm` | boolean | 是 | 确认删除标志，必须为true |

#### 🌰 请求示例

```json
{
  "ids": ["uuid-123-sql", "uuid-456-doc", "uuid-789-ddl"],
  "confirm": true
}
```

#### ✅ 成功响应格式

```json
{
  "code": 200,
  "success": true,
  "message": "删除操作完成",
  "data": {
    "response": "训练数据删除完成",
    "total_requested": 3,
    "successfully_deleted": 2,
    "failed_count": 1,
    "deleted_ids": ["uuid-123-sql", "uuid-456-doc"],
    "failed_ids": ["uuid-789-ddl"],
    "failed_details": [
      {
        "id": "uuid-789-ddl",
        "error": "记录不存在"
      }
    ],
    "current_total_count": 157
  }
}
```

---

### 4. 统计信息API

**端点**: `GET /api/v0/training_data/stats`

**功能**: 获取训练数据的统计信息，用于监控和分析。

#### 🌰 请求示例

```
GET /api/v0/training_data/stats
```

#### ✅ 成功响应格式

```json
{
  "code": 200,
  "success": true,
  "message": "统计信息获取成功",
  "data": {
    "response": "统计信息获取成功",
    "total_count": 156,
    "type_breakdown": {
      "sql": 45,
      "documentation": 38,
      "ddl": 52,
      "error_sql": 21
    },
    "type_percentages": {
      "sql": 28.85,
      "documentation": 24.36,
      "ddl": 33.33,
      "error_sql": 13.46
    },
    "last_updated": "2024-06-24T15:30:00"
  }
}
```

---

## 🔧 技术实现要点

### 1. 数据源集成

#### 1.1 查询数据源
- 使用现有的 `vn.get_training_data()` 方法获取训练数据
- 基于返回的DataFrame进行分页和筛选处理
- 根据ID后缀判断训练数据类型：
  - `-sql` → sql类型
  - `-doc` → documentation类型
  - `-ddl` → ddl类型
  - `-error_sql` → error_sql类型

#### 1.2 创建数据源
- **SQL类型**：调用 `vn.train(question=question, sql=sql)` 或 `vn.train(sql=sql)`
- **错误SQL类型**：调用 `vn.train_error_sql(question=question, sql=sql)`
- **文档类型**：调用 `vn.train(documentation=content)`
- **DDL类型**：调用 `vn.train(ddl=ddl)`

#### 1.3 删除数据源
- 使用 `custompgvector/pgvector.py` 中的 `remove_training_data(id)` 方法

### 2. 核心算法设计

#### 2.1 分页算法
```python
def paginate_data(data_list: list, page: int, page_size: int):
    """分页处理算法"""
    total = len(data_list)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_data = data_list[start_idx:end_idx]
    
    return {
        "data": page_data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": end_idx < total,
            "has_prev": page > 1
        }
    }
```

#### 2.2 类型筛选算法
```python
def filter_by_type(data_list: list, training_data_type: str):
    """按类型筛选算法"""
    if not training_data_type:
        return data_list
    
    return [
        record for record in data_list 
        if record.get('training_data_type') == training_data_type
    ]
```

#### 2.3 SQL语法检查算法
```python
def validate_sql_syntax(sql: str) -> tuple[bool, str]:
    """SQL语法检查（仅对sql类型）"""
    try:
        import sqlparse
        parsed = sqlparse.parse(sql.strip())
        
        if not parsed or not parsed[0].tokens:
            return False, "SQL语法错误：空语句"
        
        # 基本语法检查
        sql_upper = sql.strip().upper()
        if not any(sql_upper.startswith(keyword) for keyword in 
                  ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP']):
            return False, "SQL语法错误：不是有效的SQL语句"
        
        return True, ""
    except Exception as e:
        return False, f"SQL语法错误：{str(e)}"
```

### 3. 性能和安全考虑

#### 3.1 性能优化
- **分页限制**：最大页面大小限制为100条记录
- **批量限制**：批量操作最大支持50条记录
- **查询缓存**：考虑对频繁查询结果进行缓存
- **异步处理**：大批量操作考虑异步处理

#### 3.2 安全考虑
- **参数验证**：严格验证所有输入参数
- **SQL注入防护**：对SQL内容进行安全检查
- **删除确认**：删除操作必须提供确认标志
- **权限控制**：预留权限验证接口

#### 3.3 错误处理
- **统一错误格式**：使用项目标准错误响应格式
- **批量操作错误**：部分成功时提供详细的成功/失败信息
- **数据库异常**：妥善处理数据库连接和操作异常

---

## 🔄 集成方案

### 1. 代码集成
- **主要文件**：`citu_app.py` - 添加新的API路由
- **响应格式**：复用 `common/result.py` 中的标准响应格式
- **数据库连接**：复用现有的Vanna实例和数据库连接
- **错误处理**：遵循项目现有的错误处理规范

### 2. 依赖关系
```
训练数据管理API
├── vn.get_training_data()          # 查询数据源
├── vn.train()                      # 创建训练数据
├── vn.train_error_sql()            # 创建错误SQL
├── vn.remove_training_data()       # 删除数据
└── common/result.py                # 响应格式
```

### 3. 配置要求
- **数据库连接**：确保PgVector或ChromaDB连接正常
- **Vanna实例**：确保Vanna实例初始化完成
- **依赖库**：sqlparse（用于SQL语法检查）

---

## 📊 使用场景示例

### 1. 典型工作流程

**步骤1：查看统计信息**
```bash
GET /api/v0/training_data/stats
```

**步骤2：查询现有数据**
```json
POST /api/v0/training_data/query
{
  "page": 1,
  "page_size": 50,
  "training_data_type": "sql"
}
```

**步骤3：批量添加训练数据**
```json
POST /api/v0/training_data/create
{
  "data": [
    {
      "training_data_type": "sql",
      "question": "查询活跃用户",
      "sql": "SELECT * FROM users WHERE status = 'active'"
    },
    {
      "training_data_type": "documentation",
      "content": "用户状态字段说明：active表示活跃用户..."
    }
  ]
}
```

**步骤4：清理无效数据**
```json
POST /api/v0/training_data/delete
{
  "ids": ["uuid-invalid-1", "uuid-invalid-2"],
  "confirm": true
}
```

### 2. 数据迁移场景
适用于从其他系统批量导入训练数据，支持不同类型的混合导入。

### 3. 数据清理场景
适用于定期清理低质量或过时的训练数据，维护数据集质量。

---

## ⚠️ 注意事项

### 1. 限制说明
- 分页查询每页最大100条记录
- 批量操作最大50条记录
- 搜索关键词最大长度100字符
- SQL语法检查仅适用于sql类型

### 2. 兼容性
- 需要确保Vanna实例支持所有调用的方法
- 数据库版本兼容性（PgVector扩展）
- Python依赖库版本要求

### 3. 监控建议
- 记录API调用日志
- 监控批量操作性能
- 跟踪数据质量指标
- 设置异常告警机制

---

## 📝 更新记录

| 版本 | 日期 | 更新内容 | 作者 |
|------|------|----------|------|
| 1.0 | 2024-06-24 | 初始版本设计 | AI Assistant |

---

**文档状态**: 概要设计完成  
**下一步**: 详细设计和开发实现 