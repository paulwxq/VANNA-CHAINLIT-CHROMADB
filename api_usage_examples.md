# 表检查API使用指南

本文档介绍新开发的数据库表检查API的使用方法。

## 📋 API概览

### 1. 获取表列表
- **路径**: `POST /api/v0/database/tables`
- **功能**: 获取数据库中的表列表，支持表名模糊搜索

### 2. 获取表DDL/文档
- **路径**: `POST /api/v0/database/table/ddl`
- **功能**: 获取表的DDL语句或MD文档

## 🔧 API 1: 获取表列表

### 请求示例

#### 基础查询
```bash
curl -X POST http://localhost:8084/api/v0/database/tables \
  -H "Content-Type: application/json" \
  -d '{
    "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
    "schema": "public,ods"
  }'
```

#### 表名模糊搜索
```bash
curl -X POST http://localhost:8084/api/v0/database/tables \
  -H "Content-Type: application/json" \
  -d '{
    "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
    "schema": "public,ods",
    "table_name_pattern": "ods_*"
  }'
```

### 参数说明

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| db_connection | string | ✅ | 完整的PostgreSQL连接字符串 |
| schema | string | ❌ | 查询的schema，支持多个用逗号分隔，默认为public |
| table_name_pattern | string | ❌ | 表名模糊搜索模式，支持通配符：`ods_*`、`*_dim`、`*fact*` |

### 响应示例

#### 基础查询响应
```json
{
  "success": true,
  "code": 200,
  "message": "获取表列表成功",
  "data": {
    "tables": [
      "public.bss_company",
      "public.bss_branch_copy",
      "ods.raw_data"
    ],
    "total": 3,
    "schemas": ["public", "ods"],
    "db_connection_info": {
      "database": "highway_db"
    }
  }
}
```

#### 模糊搜索响应
```json
{
  "success": true,
  "code": 200,
  "message": "获取表列表成功",
  "data": {
    "tables": [
      "ods.ods_user",
      "ods.ods_order",
      "ods.ods_product"
    ],
    "total": 3,
    "schemas": ["ods"],
    "table_name_pattern": "ods_*",
    "db_connection_info": {
      "database": "highway_db"
    }
  }
}
```

## 📄 API 2: 获取表DDL/文档

### 请求示例

#### DDL格式
```bash
curl -X POST http://localhost:8084/api/v0/database/table/ddl \
  -H "Content-Type: application/json" \
  -d '{
    "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
    "table": "public.bss_company",
    "business_context": "高速公路服务区管理系统",
    "type": "ddl"
  }'
```

#### MD文档格式
```bash
curl -X POST http://localhost:8084/api/v0/database/table/ddl \
  -H "Content-Type: application/json" \
  -d '{
    "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
    "table": "public.bss_company",
    "business_context": "高速公路服务区管理系统",
    "type": "md"
  }'
```

#### 同时获取DDL和MD
```bash
curl -X POST http://localhost:8084/api/v0/database/table/ddl \
  -H "Content-Type: application/json" \
  -d '{
    "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
    "table": "public.bss_company",
    "business_context": "高速公路服务区管理系统",
    "type": "both"
  }'
```

### 参数说明

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| db_connection | string | ✅ | 完整的PostgreSQL连接字符串 |
| table | string | ✅ | 表名，格式为 schema.tablename |
| business_context | string | ❌ | 业务上下文描述，用于LLM生成更准确的注释 |
| type | string | ❌ | 输出类型：ddl/md/both，默认ddl |

### 响应示例

```json
{
  "success": true,
  "code": 200,
  "message": "获取表DDL成功",
  "data": {
    "ddl": "-- 中文名: 服务区档口基础信息表\n-- 描述: 服务区档口基础信息表...\ncreate table public.bss_company (\n  id varchar(32) not null     -- 主键ID,\n  ...\n);",
    "md": "## bss_company（服务区档口基础信息表）\n...",
    "table_info": {
      "table_name": "bss_company",
      "schema_name": "public",
      "full_name": "public.bss_company",
      "comment": "服务区档口基础信息表",
      "field_count": 15,
      "row_count": 1000,
      "table_size": "256 kB"
    },
    "fields": [
      {
        "name": "id",
        "type": "varchar",
        "nullable": false,
        "comment": "主键ID",
        "is_primary_key": true,
        "is_foreign_key": false,
        "default_value": null,
        "is_enum": false,
        "enum_values": []
      }
    ],
    "generation_info": {
      "business_context": "高速公路服务区管理系统",
      "output_type": "both",
      "has_llm_comments": true,
      "database": "highway_db"
    }
  }
}
```

## 🚀 特性说明

### 表名模糊搜索（新增功能）
- 支持通配符模式：`ods_*`、`*_dim`、`*fact*`
- 支持SQL LIKE语法：`ods_%`、`%_dim`
- 数据库层面高效过滤，适用于大量表的场景
- 自动转换通配符为SQL LIKE语法

### 智能注释生成
- 当提供`business_context`时，系统会调用LLM生成智能注释
- LLM会结合表结构、样例数据和业务上下文生成准确的中文注释
- 自动识别枚举字段并提供可能的取值

### 多格式输出
- **DDL**: 标准的CREATE TABLE语句，包含注释
- **MD**: Markdown格式的表文档，适合文档系统
- **Both**: 同时提供DDL和MD格式

### 高性能设计
- 复用现有的`data_pipeline`模块，90%+代码复用率
- 异步处理，支持并发请求
- 智能缓存，避免重复计算

## 🧪 测试方法

运行测试脚本：
```bash
python test_table_inspector_api.py
```

测试脚本包含：
- 表列表API的各种参数组合测试
- 表名模糊搜索功能测试
- DDL/MD生成API的功能测试
- 错误处理测试
- 性能基准测试

## ⚠️ 注意事项

1. **连接字符串**: 必须包含完整的数据库信息
2. **LLM调用**: 当提供`business_context`时会调用LLM，响应时间较长
3. **权限要求**: 需要数据库的读取权限
4. **超时设置**: DDL生成包含LLM调用，建议设置60秒以上超时
5. **表名模糊搜索**: 支持 `*` 通配符和 `%` SQL语法，区分大小写

## 🔗 集成示例

### JavaScript/前端集成
```javascript
// 获取表列表
const tables = await fetch('/api/v0/database/tables', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    db_connection: 'postgresql://user:pass@host:5432/db',
    schema: 'public'
  })
}).then(r => r.json());

// 获取表列表（使用模糊搜索）
const filteredTables = await fetch('/api/v0/database/tables', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    db_connection: 'postgresql://user:pass@host:5432/db',
    schema: 'public,ods',
    table_name_pattern: 'ods_*'
  })
}).then(r => r.json());

// 获取表DDL
const ddl = await fetch('/api/v0/database/table/ddl', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    db_connection: 'postgresql://user:pass@host:5432/db',
    table: 'public.users',
    business_context: '用户管理系统',
    type: 'both'
  })
}).then(r => r.json());
```

### Python集成
```python
import requests

# 获取表列表
response = requests.post('http://localhost:8084/api/v0/database/tables', 
  json={
    'db_connection': 'postgresql://user:pass@host:5432/db',
    'schema': 'public'
  })
tables = response.json()

# 获取表列表（使用模糊搜索）
response = requests.post('http://localhost:8084/api/v0/database/tables', 
  json={
    'db_connection': 'postgresql://user:pass@host:5432/db',
    'schema': 'public,ods',
    'table_name_pattern': 'ods_*'
  })
ods_tables = response.json()

# 获取表DDL  
response = requests.post('http://localhost:8084/api/v0/database/table/ddl',
  json={
    'db_connection': 'postgresql://user:pass@host:5432/db', 
    'table': 'public.users',
    'business_context': '用户管理系统',
    'type': 'ddl'
  })
ddl = response.json()
``` 