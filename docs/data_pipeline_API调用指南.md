# Data Pipeline API调用指南

## 概述

本文档详细介绍data_pipeline模块的API调用方式、支持的参数列表以及API调用时的日志配置方式。data_pipeline API系统基于Flask框架构建，提供RESTful接口支持后台任务执行、进度追踪和结果管理。

## 目录

1. [API架构概览](#1-api架构概览)
2. [核心API端点](#2-核心api端点)
3. [任务管理API](#3-任务管理api)
4. [文件管理API](#4-文件管理api)
5. [日志管理API](#5-日志管理api)
6. [数据库工具API](#6-数据库工具api)
7. [日志配置](#7-日志配置)
8. [使用示例](#8-使用示例)
9. [错误处理](#9-错误处理)
10. [最佳实践](#10-最佳实践)

## 1. API架构概览

### 1.1 系统架构

```
unified_api.py (Flask应用)
├── 任务管理API
│   ├── POST /api/v0/data_pipeline/tasks                    # 创建任务
│   ├── POST /api/v0/data_pipeline/tasks/{task_id}/execute  # 执行任务
│   ├── GET  /api/v0/data_pipeline/tasks/{task_id}          # 获取任务状态
│   └── GET  /api/v0/data_pipeline/tasks                    # 获取任务列表
├── 文件管理API
│   ├── GET  /api/v0/data_pipeline/tasks/{task_id}/files    # 获取文件列表
│   ├── GET  /api/v0/data_pipeline/tasks/{task_id}/files/{filename} # 下载文件
│   └── POST /api/v0/data_pipeline/tasks/{task_id}/upload-table-list # 上传表清单
├── 日志管理API
│   ├── GET  /api/v0/data_pipeline/tasks/{task_id}/logs     # 获取任务日志
│   └── POST /api/v0/data_pipeline/tasks/{task_id}/logs/query # 高级日志查询
└── 数据库工具API
    ├── POST /api/v0/database/tables                        # 获取数据库表列表
    └── POST /api/v0/database/table/ddl                     # 获取表DDL/MD文档
```

### 1.2 核心组件

| 组件 | 功能 | 实现位置 |
|------|------|----------|
| **SimpleWorkflowManager** | 任务管理器 | `data_pipeline.api.simple_workflow` |
| **SimpleFileManager** | 文件管理器 | `data_pipeline.api.simple_file_manager` |
| **SimpleTaskManager** | 数据库管理器 | `data_pipeline.api.simple_db_manager` |
| **TableInspectorAPI** | 数据库检查器 | `data_pipeline.api.table_inspector_api` |
| **task_executor.py** | 独立任务执行器 | `data_pipeline.task_executor` |

### 1.3 任务执行模式

| 模式 | 描述 | 使用场景 |
|------|------|----------|
| **完整工作流** | 一次性执行4个步骤 | 生产环境，自动化处理 |
| **分步执行** | 逐步执行各个步骤 | 调试，质量控制 |
| **后台执行** | 使用subprocess独立进程 | 长时间任务，不阻塞API |
| **Vector表管理** | 备份和清空vector表数据 | 重新训练前清理旧数据 |

## 2. 核心API端点

### 2.1 基础信息

- **基础URL**: `http://localhost:8084`
- **API版本**: `v0`
- **内容类型**: `application/json`
- **字符编码**: `UTF-8`

### 2.2 通用响应格式

#### 成功响应
```json
{
    "success": true,
    "code": 200,
    "message": "操作成功",
    "data": {
        // 具体数据
    }
}
```

#### 错误响应
```json
{
    "success": false,
    "code": 400,
    "message": "请求参数错误",
    "error": {
        "type": "ValidationError",
        "details": "缺少必需参数: table_list_file"
    }
}
```

### 2.3 HTTP状态码

| 状态码 | 说明 | 使用场景 |
|--------|------|----------|
| `200` | 成功 | 获取数据成功 |
| `201` | 创建成功 | 任务创建成功 |
| `202` | 已接受 | 任务执行已启动 |
| `400` | 请求错误 | 参数验证失败 |
| `404` | 未找到 | 任务不存在 |
| `409` | 冲突 | 任务已在执行 |
| `500` | 服务器错误 | 内部错误 |

### 2.4 Vector表管理功能

data_pipeline API现在支持Vector表管理功能，用于备份和清空向量数据：

#### 关键参数
- `backup_vector_tables`: 备份vector表数据到任务目录
- `truncate_vector_tables`: 清空vector表数据（自动启用备份）

#### 参数依赖关系
- ✅ 可以单独使用 `backup_vector_tables`
- ❌ 不能单独使用 `truncate_vector_tables`  
- 🔄 使用 `truncate_vector_tables` 时自动启用 `backup_vector_tables`

#### 影响的表
- `langchain_pg_collection`: 只备份，不清空
- `langchain_pg_embedding`: 备份并清空

#### 应用场景
- **重新训练**: 在加载新训练数据前清空旧的embedding数据
- **数据迁移**: 备份vector数据用于环境迁移
- **版本管理**: 保留不同版本的vector数据备份

## 3. 任务管理API

### 3.1 创建任务

**端点**: `POST /api/v0/data_pipeline/tasks`

#### 请求参数

| 参数 | 必需 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `table_list_file` | ❌ | string | - | 表清单文件路径，不提供则需要后续上传 |
| `business_context` | ❌ | string | - | 业务上下文描述 |
| `db_name` | ❌ | string | - | 数据库名称 |
| `db_connection` | ❌ | string | - | 数据库连接字符串，不提供则使用默认配置 |
| `task_name` | ❌ | string | - | 任务名称 |
| `enable_sql_validation` | ❌ | boolean | `true` | 是否启用SQL验证 |
| `enable_llm_repair` | ❌ | boolean | `true` | 是否启用LLM修复 |
| `modify_original_file` | ❌ | boolean | `true` | 是否修改原始文件 |
| `enable_training_data_load` | ❌ | boolean | `true` | 是否启用训练数据加载 |
| `backup_vector_tables` | ❌ | boolean | `false` | 是否备份vector表数据 |
| `truncate_vector_tables` | ❌ | boolean | `false` | 是否清空vector表数据（自动启用备份） |

#### 请求示例

```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "table_list_file": "tables.txt",
    "business_context": "高速公路服务区管理系统",
    "db_name": "highway_db",
    "task_name": "高速公路数据处理",
    "enable_sql_validation": true,
    "enable_llm_repair": true,
    "modify_original_file": true,
    "enable_training_data_load": true,
    "backup_vector_tables": false,
    "truncate_vector_tables": false
  }'
```

#### 响应示例

```json
{
    "success": true,
    "code": 201,
    "message": "任务创建成功",
    "data": {
        "task_id": "task_20250627_143052",
        "task_name": "高速公路数据处理",
        "status": "pending",
        "created_at": "2025-06-27T14:30:52"
    }
}
```

### 3.2 执行任务

**端点**: `POST /api/v0/data_pipeline/tasks/{task_id}/execute`

#### 请求参数

| 参数 | 必需 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `execution_mode` | ❌ | enum | `complete` | 执行模式：`complete`/`step` |
| `step_name` | ❌ | string | - | 步骤名称，步骤模式时必需 |
| `backup_vector_tables` | ❌ | boolean | `false` | 是否备份vector表数据 |
| `truncate_vector_tables` | ❌ | boolean | `false` | 是否清空vector表数据（自动启用备份） |

#### 有效步骤名称

- `ddl_generation` - DDL/MD文档生成
- `qa_generation` - Question-SQL对生成
- `sql_validation` - SQL验证和修复
- `training_load` - 训练数据加载

#### 请求示例

```bash
# 执行完整工作流
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/execute \
  -H "Content-Type: application/json" \
  -d '{
    "execution_mode": "complete",
    "backup_vector_tables": false,
    "truncate_vector_tables": false
  }'

# 执行完整工作流并清空vector表
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/execute \
  -H "Content-Type: application/json" \
  -d '{
    "execution_mode": "complete",
    "truncate_vector_tables": true
  }'

# 执行单个步骤
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/execute \
  -H "Content-Type: application/json" \
  -d '{
    "execution_mode": "step",
    "step_name": "ddl_generation",
    "backup_vector_tables": false,
    "truncate_vector_tables": false
  }'
```

#### 响应示例

```json
{
    "success": true,
    "code": 202,
    "message": "任务执行已启动",
    "data": {
        "task_id": "task_20250627_143052",
        "execution_mode": "complete",
        "step_name": null,
        "message": "任务正在后台执行，请通过状态接口查询进度"
    }
}
```

### 3.3 获取任务状态

**端点**: `GET /api/v0/data_pipeline/tasks/{task_id}`

#### 响应示例

```json
{
    "success": true,
    "code": 200,
    "message": "获取任务状态成功",
    "data": {
        "task_id": "task_20250627_143052",
        "task_name": "高速公路数据处理",
        "status": "in_progress",
        "step_status": {
            "ddl_generation": "completed",
            "qa_generation": "running",
            "sql_validation": "pending",
            "training_load": "pending"
        },
        "created_at": "2025-06-27T14:30:52",
        "started_at": "2025-06-27T14:31:00",
        "completed_at": null,
        "parameters": {
            "business_context": "高速公路服务区管理系统",
            "enable_sql_validation": true,
            "backup_vector_tables": false,
            "truncate_vector_tables": false
        },
        "current_step": {
            "execution_id": "task_20250627_143052_step_qa_generation_exec_20250627143521",
            "step": "qa_generation",
            "status": "running",
            "started_at": "2025-06-27T14:35:21"
        },
        "total_steps": 4,
        "steps": [
            {
                "step_name": "ddl_generation",
                "step_status": "completed",
                "started_at": "2025-06-27T14:30:53",
                "completed_at": "2025-06-27T14:35:20",
                "error_message": null
            }
        ]
    }
}
```

#### 任务状态说明

| 状态 | 说明 |
|------|------|
| `pending` | 待执行 |
| `in_progress` | 执行中 |
| `completed` | 已完成 |
| `failed` | 执行失败 |
| `cancelled` | 已取消 |

### 3.4 获取任务列表

**端点**: `GET /api/v0/data_pipeline/tasks`

#### 查询参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | int | `50` | 返回数量限制 |
| `offset` | int | `0` | 偏移量 |
| `status` | string | - | 状态过滤 |

#### 请求示例

```bash
curl "http://localhost:8084/api/v0/data_pipeline/tasks?limit=20&status=completed"
```

#### 响应示例

```json
{
    "success": true,
    "code": 200,
    "message": "获取任务列表成功",
    "data": {
        "tasks": [
            {
                "task_id": "task_20250627_143052",
                "task_name": "高速公路数据处理",
                "status": "completed",
                "step_status": {
                    "ddl_generation": "completed",
                    "qa_generation": "completed",
                    "sql_validation": "completed",
                    "training_load": "completed"
                },
                "created_at": "2025-06-27T14:30:52",
                "started_at": "2025-06-27T14:31:00",
                "completed_at": "2025-06-27T14:45:30",
                "created_by": "user123",
                "db_name": "highway_db",
                "business_context": "高速公路服务区管理系统",
                "directory_exists": true,
                "updated_at": "2025-06-27T14:45:30"
            }
        ],
        "total": 1,
        "limit": 20,
        "offset": 0
    }
}
```

### 3.5 高级任务查询

**端点**: `POST /api/v0/data_pipeline/tasks/query`

#### 请求参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `page` | int | 页码，默认1 |
| `page_size` | int | 每页大小，默认20 |
| `status` | string | 任务状态筛选 |
| `task_name` | string | 任务名称模糊搜索 |
| `created_by` | string | 创建者精确匹配 |
| `db_name` | string | 数据库名称精确匹配 |
| `created_time_start` | string | 创建时间范围开始 |
| `created_time_end` | string | 创建时间范围结束 |

#### 请求示例

```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/query \
  -H "Content-Type: application/json" \
  -d '{
    "page": 1,
    "page_size": 10,
    "status": "completed",
    "task_name": "highway",
    "created_time_start": "2025-06-01T00:00:00",
    "created_time_end": "2025-06-30T23:59:59"
  }'
```

## 4. 文件管理API

### 4.1 获取任务文件列表

**端点**: `GET /api/v0/data_pipeline/tasks/{task_id}/files`

#### 响应示例

```json
{
    "success": true,
    "code": 200,
    "message": "获取文件列表成功",
    "data": {
        "task_id": "task_20250627_143052",
        "files": [
            {
                "file_name": "qs_highway_db_20250627_143052_pair.json",
                "file_type": "json",
                "file_size": 102400,
                "file_size_human": "100.0 KB",
                "created_at": "2025-06-27T14:40:30",
                "is_primary": true,
                "description": "Question-SQL训练数据对",
                "download_url": "/api/v0/data_pipeline/tasks/task_20250627_143052/files/qs_highway_db_20250627_143052_pair.json"
            },
            {
                "file_name": "data_pipeline.log",
                "file_type": "log",
                "file_size": 51200,
                "file_size_human": "50.0 KB",
                "created_at": "2025-06-27T14:30:52",
                "is_primary": false,
                "description": "任务执行日志",
                "download_url": "/api/v0/data_pipeline/tasks/task_20250627_143052/files/data_pipeline.log"
            }
        ],
        "total_files": 2,
        "total_size": 153600,
        "total_size_human": "150.0 KB"
    }
}
```

### 4.2 下载文件

**端点**: `GET /api/v0/data_pipeline/tasks/{task_id}/files/{filename}`

#### 请求示例

```bash
curl -O http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/files/qs_highway_db_20250627_143052_pair.json
```

#### 响应
- 成功时返回文件内容，设置适当的Content-Type
- 失败时返回JSON错误信息

### 4.3 上传表清单文件

**端点**: `POST /api/v0/data_pipeline/tasks/{task_id}/upload-table-list`

#### 请求参数
- 使用multipart/form-data格式
- 文件字段名: `file`
- 支持的文件类型: `.txt`

#### 请求示例

```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/upload-table-list \
  -F "file=@tables.txt"
```

#### 响应示例

```json
{
    "success": true,
    "code": 200,
    "message": "表清单文件上传成功",
    "data": {
        "task_id": "task_20250627_143052",
        "file_name": "table_list.txt",
        "file_size": 1024,
        "file_path": "./data_pipeline/training_data/task_20250627_143052/table_list.txt",
        "table_count": 8,
        "tables": [
            "bss_business_day_data",
            "bss_car_day_count",
            "bss_company"
        ]
    }
}
```

### 4.4 获取表清单信息

**端点**: `GET /api/v0/data_pipeline/tasks/{task_id}/table-list-info`

#### 响应示例

```json
{
    "success": true,
    "code": 200,
    "message": "获取表清单信息成功",
    "data": {
        "task_id": "task_20250627_143052",
        "has_table_list": true,
        "file_name": "table_list.txt",
        "file_size": 1024,
        "file_path": "./data_pipeline/training_data/task_20250627_143052/table_list.txt",
        "table_count": 8,
        "tables": [
            "bss_business_day_data",
            "bss_car_day_count"
        ],
        "uploaded_at": "2025-06-27T14:32:15"
    }
}
```

### 4.5 直接创建表清单

**端点**: `POST /api/v0/data_pipeline/tasks/{task_id}/table-list`

#### 请求参数

| 参数 | 必需 | 类型 | 说明 |
|------|------|------|------|
| `table_names` | ✅ | array | 表名列表 |
| `business_context` | ❌ | string | 业务上下文描述 |

#### 请求示例

```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/table-list \
  -H "Content-Type: application/json" \
  -d '{
    "table_names": [
      "bss_business_day_data",
      "bss_car_day_count",
      "bss_company"
    ],
    "business_context": "高速公路服务区管理系统"
  }'
```

## 5. 日志管理API

### 5.1 获取任务日志

**端点**: `GET /api/v0/data_pipeline/tasks/{task_id}/logs`

#### 查询参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | int | `100` | 日志行数限制 |
| `level` | string | - | 日志级别过滤 |

#### 请求示例

```bash
curl "http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/logs?limit=50&level=ERROR"
```

#### 响应示例

```json
{
    "success": true,
    "code": 200,
    "message": "获取任务日志成功",
    "data": {
        "task_id": "task_20250627_143052",
        "logs": [
            {
                "timestamp": "2025-06-27 14:30:52",
                "level": "INFO",
                "logger": "SchemaWorkflowOrchestrator",
                "message": "🚀 开始执行Schema工作流编排"
            },
            {
                "timestamp": "2025-06-27 14:30:53",
                "level": "INFO",
                "logger": "DDLMDGenerator",
                "message": "开始处理表: bss_business_day_data"
            },
            {
                "timestamp": "2025-06-27 14:31:25",
                "level": "ERROR",
                "logger": "SQLValidator",
                "message": "SQL验证失败，尝试LLM修复"
            }
        ],
        "total": 3,
        "source": "file",
        "log_file": "/path/to/data_pipeline/training_data/task_20250627_143052/data_pipeline.log"
    }
}
```

### 5.2 高级日志查询

**端点**: `POST /api/v0/data_pipeline/tasks/{task_id}/logs/query`

#### 请求参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | `1` | 页码 |
| `page_size` | int | `50` | 每页大小 |
| `level` | string | - | 日志级别过滤 |
| `start_time` | string | - | 开始时间 |
| `end_time` | string | - | 结束时间 |
| `keyword` | string | - | 关键词搜索 |
| `logger_name` | string | - | 记录器名称过滤 |
| `step_name` | string | - | 步骤名称过滤 |
| `sort_by` | string | `timestamp` | 排序字段 |
| `sort_order` | string | `desc` | 排序顺序 |

#### 请求示例

```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/logs/query \
  -H "Content-Type: application/json" \
  -d '{
    "page": 1,
    "page_size": 20,
    "level": "ERROR",
    "keyword": "SQL验证",
    "start_time": "2025-06-27T14:30:00",
    "end_time": "2025-06-27T14:45:00"
  }'
```

#### 响应示例

```json
{
    "success": true,
    "code": 200,
    "message": "高级日志查询成功",
    "data": {
        "logs": [
            {
                "timestamp": "2025-06-27 14:31:25",
                "level": "ERROR",
                "logger": "SQLValidator",
                "step": "sql_validation",
                "message": "SQL验证失败，尝试LLM修复",
                "line_number": 125
            }
        ],
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total": 1,
            "total_pages": 1,
            "has_next": false,
            "has_prev": false
        },
        "log_file_info": {
            "exists": true,
            "file_path": "/path/to/data_pipeline/training_data/task_20250627_143052/data_pipeline.log",
            "file_size": 51200,
            "last_modified": "2025-06-27T14:45:30"
        },
        "query_time": "0.023s"
    }
}
```

## 6. 数据库工具API

### 6.1 获取数据库表列表

**端点**: `POST /api/v0/database/tables`

#### 请求参数

| 参数 | 必需 | 类型 | 说明 |
|------|------|------|------|
| `db_connection` | ❌ | string | 数据库连接字符串，不传则使用默认配置 |
| `schema` | ❌ | string | Schema名称，支持多个用逗号分隔 |
| `table_name_pattern` | ❌ | string | 表名模式匹配，支持通配符 |

#### 请求示例

```bash
curl -X POST http://localhost:8084/api/v0/database/tables \
  -H "Content-Type: application/json" \
  -d '{
    "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
    "schema": "public,ods",
    "table_name_pattern": "bss_*"
  }'
```

#### 响应示例

```json
{
    "success": true,
    "code": 200,
    "message": "获取表列表成功",
    "data": {
        "tables": [
            "public.bss_business_day_data",
            "public.bss_car_day_count",
            "ods.bss_company"
        ],
        "total": 3,
        "schemas": ["public", "ods"],
        "table_name_pattern": "bss_*",
        "db_connection_info": {
            "database": "highway_db"
        }
    }
}
```

### 6.2 获取表DDL/MD文档

**端点**: `POST /api/v0/database/table/ddl`

#### 请求参数

| 参数 | 必需 | 类型 | 说明 |
|------|------|------|------|
| `table` | ✅ | string | 表名（可包含schema） |
| `db_connection` | ❌ | string | 数据库连接字符串 |
| `business_context` | ❌ | string | 业务上下文描述 |
| `type` | ❌ | enum | 输出类型：`ddl`/`md`/`both` |

#### 请求示例

```bash
curl -X POST http://localhost:8084/api/v0/database/table/ddl \
  -H "Content-Type: application/json" \
  -d '{
    "table": "public.bss_company",
    "business_context": "高速公路服务区管理系统",
    "type": "both"
  }'
```

#### 响应示例

```json
{
    "success": true,
    "code": 200,
    "message": "获取表DDL成功",
    "data": {
        "ddl": "-- 中文名: 存储高速公路管理公司信息\ncreate table public.bss_company (\n  id varchar(32) not null,\n  company_name varchar(255)\n);",
        "md": "## bss_company（存储高速公路管理公司信息）\n\n字段列表：\n- id (varchar(32)) - 主键ID\n- company_name (varchar(255)) - 公司名称",
        "table_info": {
            "table_name": "bss_company",
            "schema_name": "public",
            "full_name": "public.bss_company",
            "comment": "存储高速公路管理公司信息",
            "field_count": 2,
            "row_count": 15
        },
        "fields": [
            {
                "column_name": "id",
                "data_type": "varchar",
                "max_length": 32,
                "is_nullable": false,
                "is_primary_key": true,
                "comment": "主键ID"
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

## 7. 日志配置

### 7.1 API日志架构

API模式下的日志系统采用双日志架构：

1. **任务目录日志**: 每个任务在独立目录下生成详细日志
2. **API系统日志**: 记录API调用和系统事件

### 7.2 日志文件位置

#### 任务日志
```
data_pipeline/training_data/task_20250627_143052/
└── data_pipeline.log                    # 任务详细执行日志
```

#### API系统日志
```
logs/
├── app.log                              # Flask应用日志
├── agent.log                            # Agent相关日志
├── vanna.log                            # Vanna系统日志
└── data_pipeline.log                    # data_pipeline模块日志（已弃用）
```

### 7.3 日志级别配置

#### 7.3.1 环境变量配置

```bash
# 设置日志级别
export DATA_PIPELINE_LOG_LEVEL=DEBUG
export FLASK_LOG_LEVEL=INFO

# 设置日志目录
export DATA_PIPELINE_LOG_DIR=./logs/data_pipeline/
```

#### 7.3.2 任务日志配置

任务执行时自动配置：

```python
# 在SimpleWorkflowExecutor中自动设置
def _setup_task_directory_logger(self):
    task_dir = self.file_manager.get_task_directory(self.task_id)
    log_file = task_dir / "data_pipeline.log"
    
    # 创建任务专用logger
    self.task_dir_logger = logging.getLogger(f"TaskDir_{self.task_id}")
    # ... 配置详细格式和处理器
```

### 7.4 日志格式

#### 任务日志格式
```
2025-07-01 14:30:52 [INFO] TaskDir_task_20250627_143052: 任务目录日志初始化完成
2025-07-01 14:30:53 [INFO] SchemaWorkflowOrchestrator: 🚀 开始执行Schema工作流编排
2025-07-01 14:30:54 [INFO] DDLMDGenerator: 开始处理表: bss_business_day_data
```

#### API日志格式
```
2025-07-01 14:30:50 [INFO] unified_api: POST /api/v0/data_pipeline/tasks - 任务创建成功
2025-07-01 14:30:51 [INFO] SimpleWorkflowManager: 创建任务: task_20250627_143052
2025-07-01 14:30:52 [INFO] unified_api: POST /api/v0/data_pipeline/tasks/task_20250627_143052/execute - 任务执行启动
```

### 7.5 日志监控和查询

#### 通过API查询日志
```bash
# 获取最新日志
curl "http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/logs?limit=100"

# 查询错误日志
curl "http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/logs?level=ERROR"

# 高级日志查询
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/logs/query \
  -H "Content-Type: application/json" \
  -d '{
    "page": 1,
    "page_size": 50,
    "level": "ERROR",
    "keyword": "SQL验证"
  }'
```

#### 直接查看日志文件
```bash
# 查看最新任务日志
tail -f data_pipeline/training_data/task_*/data_pipeline.log

# 搜索错误日志
grep -i "error" data_pipeline/training_data/task_*/data_pipeline.log
```

## 8. 使用示例

### 8.1 完整工作流示例

#### 步骤1: 创建任务
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "table_list_file": "tables.txt",
    "business_context": "高速公路服务区管理系统",
    "db_name": "highway_db",
    "task_name": "高速公路数据处理",
    "backup_vector_tables": false,
    "truncate_vector_tables": false
  }'
```

#### 步骤2: 执行完整工作流
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/execute \
  -H "Content-Type: application/json" \
  -d '{
    "execution_mode": "complete",
    "backup_vector_tables": false,
    "truncate_vector_tables": false
  }'
```

#### 步骤3: 轮询任务状态
```bash
#!/bin/bash
TASK_ID="task_20250627_143052"

while true; do
    STATUS=$(curl -s "http://localhost:8084/api/v0/data_pipeline/tasks/$TASK_ID" | jq -r '.data.status')
    echo "任务状态: $STATUS"
    
    if [[ "$STATUS" == "completed" || "$STATUS" == "failed" ]]; then
        break
    fi
    
    sleep 10
done
```

#### 步骤4: 获取结果文件
```bash
# 获取文件列表
curl "http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/files"

# 下载主要输出文件
curl -O "http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/files/qs_highway_db_20250627_143052_pair.json"
```

### 8.2 Vector表管理示例

#### 带Vector表管理的完整工作流
```bash
# 创建任务并启用vector表清空
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "table_list_file": "tables.txt",
    "business_context": "高速公路服务区管理系统",
    "db_name": "highway_db",
    "task_name": "高速公路数据处理_清空vector",
    "truncate_vector_tables": true
  }'

# 执行工作流（truncate_vector_tables会自动启用backup_vector_tables）
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/execute \
  -H "Content-Type: application/json" \
  -d '{
    "execution_mode": "complete",
    "truncate_vector_tables": true
  }'

# 检查vector表管理结果
curl "http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052"

# 下载备份文件（如果有）
curl "http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/files" | \
  jq -r '.data.files[] | select(.file_name | contains("langchain_")) | .download_url'
```

#### 仅备份Vector表
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/execute \
  -H "Content-Type: application/json" \
  -d '{
    "execution_mode": "complete",
    "backup_vector_tables": true,
    "truncate_vector_tables": false
  }'
```

### 8.3 分步执行示例

#### 步骤1: 创建任务（无表清单）
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "business_context": "测试系统",
    "db_name": "test_db",
    "task_name": "测试任务"
  }'
```

#### 步骤2: 上传表清单
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/upload-table-list \
  -F "file=@tables.txt"
```

#### 步骤3: 分步执行
```bash
# 执行DDL生成
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/execute \
  -H "Content-Type: application/json" \
  -d '{
    "execution_mode": "step",
    "step_name": "ddl_generation"
  }'

# 等待完成后执行Q&A生成
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/execute \
  -H "Content-Type: application/json" \
  -d '{
    "execution_mode": "step",
    "step_name": "qa_generation"
  }'
```

### 8.4 数据库工具使用示例

#### 获取数据库表列表
```bash
curl -X POST http://localhost:8084/api/v0/database/tables \
  -H "Content-Type: application/json" \
  -d '{
    "schema": "public",
    "table_name_pattern": "bss_*"
  }'
```

#### 获取单表DDL
```bash
curl -X POST http://localhost:8084/api/v0/database/table/ddl \
  -H "Content-Type: application/json" \
  -d '{
    "table": "public.bss_company",
    "business_context": "高速公路管理系统",
    "type": "ddl"
  }'
```

### 8.5 JavaScript客户端示例

```javascript
class DataPipelineAPI {
    constructor(baseUrl = 'http://localhost:8084') {
        this.baseUrl = baseUrl;
    }

    async createTask(params) {
        const response = await fetch(`${this.baseUrl}/api/v0/data_pipeline/tasks`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(params)
        });
        return await response.json();
    }

    async executeTask(taskId, executionMode = 'complete', stepName = null) {
        const params = { execution_mode: executionMode };
        if (stepName) params.step_name = stepName;

        const response = await fetch(`${this.baseUrl}/api/v0/data_pipeline/tasks/${taskId}/execute`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(params)
        });
        return await response.json();
    }

    async getTaskStatus(taskId) {
        const response = await fetch(`${this.baseUrl}/api/v0/data_pipeline/tasks/${taskId}`);
        return await response.json();
    }

    async pollTaskStatus(taskId, interval = 5000) {
        return new Promise((resolve, reject) => {
            const poll = async () => {
                try {
                    const result = await this.getTaskStatus(taskId);
                    const status = result.data?.status;
                    
                    console.log(`任务状态: ${status}`);
                    
                    if (status === 'completed') {
                        resolve(result);
                    } else if (status === 'failed') {
                        reject(new Error('任务执行失败'));
                    } else {
                        setTimeout(poll, interval);
                    }
                } catch (error) {
                    reject(error);
                }
            };
            poll();
        });
    }

    async getTaskFiles(taskId) {
        const response = await fetch(`${this.baseUrl}/api/v0/data_pipeline/tasks/${taskId}/files`);
        return await response.json();
    }

    async getTaskLogs(taskId, limit = 100, level = null) {
        const params = new URLSearchParams({ limit });
        if (level) params.append('level', level);
        
        const response = await fetch(`${this.baseUrl}/api/v0/data_pipeline/tasks/${taskId}/logs?${params}`);
        return await response.json();
    }
}

// 使用示例
async function runDataPipelineWorkflow() {
    const api = new DataPipelineAPI();
    
    try {
        // 1. 创建任务
        const createResult = await api.createTask({
            table_list_file: 'tables.txt',
            business_context: '高速公路服务区管理系统',
            db_name: 'highway_db',
            task_name: '高速公路数据处理',
            backup_vector_tables: false,
            truncate_vector_tables: false
        });
        
        const taskId = createResult.data.task_id;
        console.log(`任务创建成功: ${taskId}`);
        
        // 2. 执行任务
        await api.executeTask(taskId, 'complete');
        console.log('任务执行已启动');
        
        // 3. 轮询状态
        const finalResult = await api.pollTaskStatus(taskId);
        console.log('任务执行完成:', finalResult);
        
        // 4. 获取结果文件
        const files = await api.getTaskFiles(taskId);
        console.log('生成的文件:', files.data.files);
        
    } catch (error) {
        console.error('工作流执行失败:', error);
    }
}
```

### 8.6 Python客户端示例

```python
import requests
import time
import json

class DataPipelineAPI:
    def __init__(self, base_url='http://localhost:8084'):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json'
        })

    def create_task(self, **params):
        """创建任务"""
        response = self.session.post(
            f'{self.base_url}/api/v0/data_pipeline/tasks',
            json=params
        )
        response.raise_for_status()
        return response.json()

    def execute_task(self, task_id, execution_mode='complete', step_name=None):
        """执行任务"""
        params = {'execution_mode': execution_mode}
        if step_name:
            params['step_name'] = step_name
        
        response = self.session.post(
            f'{self.base_url}/api/v0/data_pipeline/tasks/{task_id}/execute',
            json=params
        )
        response.raise_for_status()
        return response.json()

    def get_task_status(self, task_id):
        """获取任务状态"""
        response = self.session.get(
            f'{self.base_url}/api/v0/data_pipeline/tasks/{task_id}'
        )
        response.raise_for_status()
        return response.json()

    def poll_task_status(self, task_id, interval=5):
        """轮询任务状态直到完成"""
        while True:
            result = self.get_task_status(task_id)
            status = result['data']['status']
            
            print(f"任务状态: {status}")
            
            if status == 'completed':
                return result
            elif status == 'failed':
                raise Exception(f"任务执行失败: {result['data'].get('error_message', '未知错误')}")
            
            time.sleep(interval)

    def get_task_files(self, task_id):
        """获取任务文件列表"""
        response = self.session.get(
            f'{self.base_url}/api/v0/data_pipeline/tasks/{task_id}/files'
        )
        response.raise_for_status()
        return response.json()

    def download_file(self, task_id, filename, save_path=None):
        """下载文件"""
        response = self.session.get(
            f'{self.base_url}/api/v0/data_pipeline/tasks/{task_id}/files/{filename}'
        )
        response.raise_for_status()
        
        if save_path is None:
            save_path = filename
        
        with open(save_path, 'wb') as f:
            f.write(response.content)
        
        return save_path

    def get_task_logs(self, task_id, limit=100, level=None):
        """获取任务日志"""
        params = {'limit': limit}
        if level:
            params['level'] = level
        
        response = self.session.get(
            f'{self.base_url}/api/v0/data_pipeline/tasks/{task_id}/logs',
            params=params
        )
        response.raise_for_status()
        return response.json()

# 使用示例
def run_data_pipeline_workflow():
    api = DataPipelineAPI()
    
    try:
        # 1. 创建任务
        create_result = api.create_task(
            table_list_file='tables.txt',
            business_context='高速公路服务区管理系统',
            db_name='highway_db',
            task_name='高速公路数据处理',
            backup_vector_tables=False,
            truncate_vector_tables=False
        )
        
        task_id = create_result['data']['task_id']
        print(f"任务创建成功: {task_id}")
        
        # 2. 执行任务
        api.execute_task(task_id, 'complete')
        print("任务执行已启动")
        
        # 3. 轮询状态
        final_result = api.poll_task_status(task_id)
        print("任务执行完成:", json.dumps(final_result, indent=2, ensure_ascii=False))
        
        # 4. 获取结果文件
        files = api.get_task_files(task_id)
        print("生成的文件:")
        for file_info in files['data']['files']:
            print(f"  - {file_info['file_name']} ({file_info['file_size_human']})")
        
        # 5. 下载主要输出文件
        primary_files = [f for f in files['data']['files'] if f.get('is_primary')]
        if primary_files:
            filename = primary_files[0]['file_name']
            save_path = api.download_file(task_id, filename)
            print(f"主要输出文件已下载: {save_path}")
        
    except Exception as error:
        print(f"工作流执行失败: {error}")

if __name__ == '__main__':
    run_data_pipeline_workflow()
```

## 9. 错误处理

### 9.1 常见错误码

| 错误码 | HTTP状态 | 说明 | 解决方案 |
|--------|----------|------|----------|
| `TASK_NOT_FOUND` | 404 | 任务不存在 | 检查task_id是否正确 |
| `TASK_ALREADY_RUNNING` | 409 | 任务已在执行 | 等待当前任务完成 |
| `INVALID_EXECUTION_MODE` | 400 | 无效的执行模式 | 使用`complete`或`step` |
| `MISSING_STEP_NAME` | 400 | 缺少步骤名称 | 步骤模式需要指定step_name |
| `INVALID_STEP_NAME` | 400 | 无效的步骤名称 | 使用有效的步骤名称 |
| `FILE_NOT_FOUND` | 404 | 文件不存在 | 检查文件名是否正确 |
| `DATABASE_CONNECTION_ERROR` | 500 | 数据库连接失败 | 检查数据库配置 |
| `VECTOR_BACKUP_FAILED` | 500 | Vector表备份失败 | 检查数据库连接和磁盘空间 |
| `VECTOR_TRUNCATE_FAILED` | 500 | Vector表清空失败 | 检查数据库权限 |

### 9.2 错误响应格式

```json
{
    "success": false,
    "code": 400,
    "message": "请求参数错误",
    "error": {
        "type": "ValidationError",
        "details": "无效的执行模式，必须是 'complete' 或 'step'",
        "invalid_params": ["execution_mode"],
        "timestamp": "2025-06-27T14:30:52"
    }
}
```

### 9.3 错误处理最佳实践

#### 客户端错误处理
```javascript
async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(`API错误: ${data.message} (${data.code})`);
        }
        
        return data;
        
    } catch (error) {
        if (error instanceof TypeError && error.message.includes('fetch')) {
            throw new Error('网络连接失败，请检查服务器是否正常运行');
        }
        throw error;
    }
}

// 使用示例
try {
    const result = await apiRequest('/api/v0/data_pipeline/tasks/invalid_id');
} catch (error) {
    if (error.message.includes('404')) {
        console.log('任务不存在，请检查任务ID');
    } else {
        console.error('API调用失败:', error.message);
    }
}
```

#### 重试机制
```python
import time
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

def create_session_with_retry():
    session = requests.Session()
    
    # 配置重试策略
    retry_strategy = Retry(
        total=3,
        status_forcelist=[429, 500, 502, 503, 504],
        method_whitelist=["HEAD", "GET", "OPTIONS"],
        backoff_factor=1
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session

# 使用示例
session = create_session_with_retry()
response = session.get('http://localhost:8084/api/v0/data_pipeline/tasks/task_id')
```

### 9.4 日志错误排查

#### 查看任务错误日志
```bash
# 获取任务错误日志
curl "http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/logs?level=ERROR"

# 搜索特定错误
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/logs/query \
  -H "Content-Type: application/json" \
  -d '{
    "keyword": "连接失败",
    "level": "ERROR"
  }'
```

#### 分析错误模式
```python
def analyze_error_logs(api, task_id):
    """分析任务错误日志"""
    logs_result = api.get_task_logs(task_id, level='ERROR')
    error_logs = logs_result['data']['logs']
    
    # 统计错误类型
    error_types = {}
    for log in error_logs:
        message = log['message']
        if 'SQL验证失败' in message:
            error_types['SQL_VALIDATION'] = error_types.get('SQL_VALIDATION', 0) + 1
        elif '数据库连接' in message:
            error_types['DATABASE_CONNECTION'] = error_types.get('DATABASE_CONNECTION', 0) + 1
        elif 'LLM调用' in message:
            error_types['LLM_CALL'] = error_types.get('LLM_CALL', 0) + 1
        else:
            error_types['OTHER'] = error_types.get('OTHER', 0) + 1
    
    return error_types

# 使用示例
error_analysis = analyze_error_logs(api, 'task_20250627_143052')
print("错误类型统计:", error_analysis)
```

## 10. 最佳实践

### 10.1 任务管理最佳实践

#### 1. 任务命名规范
```python
# 推荐的任务命名格式
task_name_patterns = {
    "环境_数据库_用途_时间": "prod_highway_training_20250627",
    "项目_模块_版本": "crm_customer_v1.2",
    "业务_场景_批次": "ecommerce_recommendation_batch01"
}
```

#### 2. 参数配置建议
```json
{
    "推荐配置": {
        "enable_sql_validation": true,
        "enable_llm_repair": true,
        "modify_original_file": true,
        "enable_training_data_load": true,
        "backup_vector_tables": false,
        "truncate_vector_tables": false
    },
    "调试配置": {
        "enable_sql_validation": false,
        "enable_llm_repair": false,
        "modify_original_file": false,
        "enable_training_data_load": false,
        "backup_vector_tables": false,
        "truncate_vector_tables": false
    },
    "快速配置": {
        "enable_sql_validation": true,
        "enable_llm_repair": false,
        "modify_original_file": false,
        "enable_training_data_load": true,
        "backup_vector_tables": false,
        "truncate_vector_tables": false
    },
    "Vector清理配置": {
        "enable_sql_validation": true,
        "enable_llm_repair": true,
        "modify_original_file": true,
        "enable_training_data_load": true,
        "backup_vector_tables": true,
        "truncate_vector_tables": true
    }
}
```

#### 3. 任务监控策略
```javascript
class TaskMonitor {
    constructor(api, taskId) {
        this.api = api;
        this.taskId = taskId;
        this.callbacks = {};
    }

    on(event, callback) {
        this.callbacks[event] = callback;
    }

    async start(interval = 5000) {
        while (true) {
            try {
                const result = await this.api.getTaskStatus(this.taskId);
                const status = result.data.status;
                
                // 触发状态变化回调
                if (this.callbacks.statusChange) {
                    this.callbacks.statusChange(status, result.data);
                }
                
                // 检查是否完成
                if (status === 'completed') {
                    if (this.callbacks.completed) {
                        this.callbacks.completed(result.data);
                    }
                    break;
                } else if (status === 'failed') {
                    if (this.callbacks.failed) {
                        this.callbacks.failed(result.data);
                    }
                    break;
                }
                
                await new Promise(resolve => setTimeout(resolve, interval));
                
            } catch (error) {
                if (this.callbacks.error) {
                    this.callbacks.error(error);
                }
                break;
            }
        }
    }
}

// 使用示例
const monitor = new TaskMonitor(api, taskId);
monitor.on('statusChange', (status, data) => {
    console.log(`任务状态更新: ${status}`);
    updateProgressBar(data.step_status);
});
monitor.on('completed', (data) => {
    console.log('任务完成，开始下载结果文件');
    downloadResultFiles(data);
});
monitor.on('failed', (data) => {
    console.error('任务失败:', data.error_message);
    showErrorDialog(data.error_message);
});
monitor.start();
```

### 10.2 性能优化建议

#### 1. 并发控制
```python
import asyncio
import aiohttp

class AsyncDataPipelineAPI:
    def __init__(self, base_url='http://localhost:8084'):
        self.base_url = base_url
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def create_multiple_tasks(self, task_configs, max_concurrent=3):
        """并发创建多个任务"""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def create_single_task(config):
            async with semaphore:
                async with self.session.post(
                    f'{self.base_url}/api/v0/data_pipeline/tasks',
                    json=config
                ) as response:
                    return await response.json()
        
        tasks = [create_single_task(config) for config in task_configs]
        return await asyncio.gather(*tasks)

# 使用示例
async def batch_create_tasks():
    task_configs = [
        {
            'table_list_file': f'tables_{i}.txt',
            'business_context': f'业务系统{i}',
            'db_name': f'db_{i}'
        }
        for i in range(1, 6)
    ]
    
    async with AsyncDataPipelineAPI() as api:
        results = await api.create_multiple_tasks(task_configs)
        print(f"创建了 {len(results)} 个任务")
```

#### 2. 缓存策略
```python
import functools
import time

def cache_with_ttl(ttl_seconds=300):
    """带TTL的缓存装饰器"""
    def decorator(func):
        cache = {}
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = str(args) + str(sorted(kwargs.items()))
            current_time = time.time()
            
            if key in cache:
                result, timestamp = cache[key]
                if current_time - timestamp < ttl_seconds:
                    return result
            
            result = func(*args, **kwargs)
            cache[key] = (result, current_time)
            return result
        
        return wrapper
    return decorator

class CachedDataPipelineAPI(DataPipelineAPI):
    @cache_with_ttl(60)  # 缓存1分钟
    def get_task_status(self, task_id):
        return super().get_task_status(task_id)
    
    @cache_with_ttl(300)  # 缓存5分钟
    def get_task_files(self, task_id):
        return super().get_task_files(task_id)
```

### 10.3 安全最佳实践

#### 1. API认证
```python
class SecureDataPipelineAPI(DataPipelineAPI):
    def __init__(self, base_url, api_key=None):
        super().__init__(base_url)
        if api_key:
            self.session.headers.update({
                'Authorization': f'Bearer {api_key}'
            })

    def set_api_key(self, api_key):
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}'
        })
```

#### 2. 参数验证
```python
def validate_task_params(params):
    """验证任务参数"""
    required_fields = ['business_context', 'db_name']
    
    for field in required_fields:
        if field not in params or not params[field]:
            raise ValueError(f"缺少必需参数: {field}")
    
    # 验证数据库连接字符串格式
    if 'db_connection' in params:
        db_conn = params['db_connection']
        if not db_conn.startswith('postgresql://'):
            raise ValueError("数据库连接字符串必须以postgresql://开头")
    
    # 验证任务名称长度
    if 'task_name' in params and len(params['task_name']) > 100:
        raise ValueError("任务名称不能超过100个字符")
    
    return True

# 使用示例
try:
    validate_task_params({
        'business_context': '高速公路管理系统',
        'db_name': 'highway_db'
    })
except ValueError as e:
    print(f"参数验证失败: {e}")
```

### 10.4 监控和告警

#### 1. 任务状态监控
```python
import logging
from datetime import datetime, timedelta

class TaskStatusMonitor:
    def __init__(self, api, alert_callback=None):
        self.api = api
        self.alert_callback = alert_callback
        self.logger = logging.getLogger(__name__)

    async def monitor_all_tasks(self):
        """监控所有活跃任务"""
        tasks_result = self.api.get_tasks_list(status_filter='in_progress')
        active_tasks = tasks_result['data']['tasks']
        
        for task in active_tasks:
            await self.check_task_health(task)

    async def check_task_health(self, task):
        """检查单个任务健康状态"""
        task_id = task['task_id']
        started_at = datetime.fromisoformat(task['started_at'])
        current_time = datetime.now()
        
        # 检查任务是否超时（超过2小时）
        if current_time - started_at > timedelta(hours=2):
            self.logger.warning(f"任务 {task_id} 可能超时")
            if self.alert_callback:
                self.alert_callback('TASK_TIMEOUT', task)
        
        # 检查任务日志是否有错误
        logs_result = self.api.get_task_logs(task_id, level='ERROR')
        if logs_result['data']['total'] > 0:
            self.logger.error(f"任务 {task_id} 发现错误日志")
            if self.alert_callback:
                self.alert_callback('TASK_ERROR', task)

def alert_handler(alert_type, task):
    """告警处理函数"""
    if alert_type == 'TASK_TIMEOUT':
        print(f"⚠️ 任务超时告警: {task['task_id']}")
        # 可以集成邮件、钉钉、微信等通知方式
    elif alert_type == 'TASK_ERROR':
        print(f"❌ 任务错误告警: {task['task_id']}")

# 使用示例
monitor = TaskStatusMonitor(api, alert_handler)
asyncio.run(monitor.monitor_all_tasks())
```

#### 2. 性能指标收集
```python
class PerformanceMetrics:
    def __init__(self):
        self.metrics = {}

    def record_api_call(self, endpoint, duration, status_code):
        """记录API调用指标"""
        key = f"{endpoint}_{status_code}"
        if key not in self.metrics:
            self.metrics[key] = {
                'count': 0,
                'total_duration': 0,
                'avg_duration': 0,
                'max_duration': 0,
                'min_duration': float('inf')
            }
        
        metric = self.metrics[key]
        metric['count'] += 1
        metric['total_duration'] += duration
        metric['avg_duration'] = metric['total_duration'] / metric['count']
        metric['max_duration'] = max(metric['max_duration'], duration)
        metric['min_duration'] = min(metric['min_duration'], duration)

    def get_report(self):
        """获取性能报告"""
        return {
            'api_metrics': self.metrics,
            'summary': {
                'total_calls': sum(m['count'] for m in self.metrics.values()),
                'avg_response_time': sum(m['avg_duration'] for m in self.metrics.values()) / len(self.metrics) if self.metrics else 0
            }
        }

# 集成到API客户端
class InstrumentedDataPipelineAPI(DataPipelineAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.metrics = PerformanceMetrics()

    def _make_request(self, method, url, **kwargs):
        """带性能监控的请求方法"""
        start_time = time.time()
        try:
            response = getattr(self.session, method)(url, **kwargs)
            duration = time.time() - start_time
            self.metrics.record_api_call(url, duration, response.status_code)
            return response
        except Exception as e:
            duration = time.time() - start_time
            self.metrics.record_api_call(url, duration, 0)
            raise
```

## 总结

data_pipeline API系统提供了完整的RESTful接口支持，能够满足各种数据处理需求。通过合理使用任务管理、文件管理、日志管理和数据库工具API，可以构建高效的数据处理工作流。建议在生产环境中实施适当的监控、告警和性能优化措施，确保系统的稳定性和可靠性。 