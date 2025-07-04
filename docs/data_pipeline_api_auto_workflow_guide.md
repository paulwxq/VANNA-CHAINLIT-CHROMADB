# Training 数据集自动生成加载的过程和API

## 概述

本文档详细说明了 Data Pipeline 自动化训练数据生成的完整工作流程和 API 调用方法。通过这些 API，可以自动化生成数据库表的 DDL 文档、Markdown 说明、Question-SQL 训练对，并自动加载到训练数据库中。

## API 接口列表

### 核心工作流 API

| 方法 | 端点 | 描述 |
|------|------|------|
| `POST` | `/api/v0/data_pipeline/tasks` | 创建数据管道任务 |
| `POST` | `/api/v0/data_pipeline/tasks/{task_id}/execute` | 执行数据管道任务 |
| `GET` | `/api/v0/data_pipeline/tasks/{task_id}` | 获取任务状态 |
| `GET` | `/api/v0/data_pipeline/tasks` | 获取任务列表 |
| `DELETE` | `/api/v0/data_pipeline/tasks` | 删除任务（批量） |

### 表名管理 API

| 方法 | 端点 | 描述 |
|------|------|------|
| `POST` | `/api/v0/database/tables` | 查询数据库表列表 |
| `POST` | `/api/v0/data_pipeline/tasks/{task_id}/table-list` | 在线提交表名列表 |
| `POST` | `/api/v0/data_pipeline/tasks/{task_id}/upload-table-list` | 上传表清单文件 |
| `GET` | `/api/v0/data_pipeline/tasks/{task_id}/table-list-info` | 获取表清单文件信息 |

### 文件管理 API

| 方法 | 端点 | 描述 |
|------|------|------|
| `GET` | `/api/v0/data_pipeline/tasks/{task_id}/files` | 查看任务文件列表 |
| `GET` | `/api/v0/data_pipeline/tasks/{task_id}/files/{file_name}` | 下载任务文件 |
| `POST` | `/api/v0/data_pipeline/tasks/{task_id}/files` | 上传文件到任务目录 |

### 监控和日志 API

| 方法 | 端点 | 描述 |
|------|------|------|
| `GET` | `/api/v0/data_pipeline/tasks/{task_id}/logs` | 获取任务日志 |

## 执行流程

下面是完整的执行流程和API调用说明：

### 1. 创建训练任务

**API**: `POST /api/v0/data_pipeline/tasks`

**请求地址**: `http://localhost:8084/api/v0/data_pipeline/tasks`

#### 1.1 参数示例

**参数样例1**：

```json
{
    "task_name": "服务区初始化数据加载",
    "db_name": "highway_db",
    "business_context": "高速公路服务区管理系统"
}
```

**参数样例2**：
```json
{
    "db_name": "highway_db",
    "business_context": "高速公路服务区管理系统",
    "enable_sql_validation": true,
    "enable_llm_repair": true,
    "modify_original_file": true,
    "enable_training_data_load": true
}
```

#### 1.2 参数说明

##### 基础参数

- `table_list_file` (string): 表清单文件路径，如未提供则进入文件上传模式，目前这种方式已经废弃
- `business_context` (string): 业务上下文描述，默认为"数据库管理系统"，使用默认值会严重影响LLM对数据表业务主题判断的准确性
- `db_name` (string): 数据库名称，如果不提供，从连接字符串中提取
- `db_connection` (string): 完整的PostgreSQL连接字符串

##### 控制参数

> **注意**：目前所有的控制参数都不在WEB UI暴露给用户，它们的默认值都是true。

- `enable_sql_validation` (boolean, 默认true): 是否启用SQL验证
- `enable_llm_repair` (boolean, 默认true): 是否启用LLM修复
- `modify_original_file` (boolean, 默认true): 是否修改原始文件
- `enable_training_data_load` (boolean, 默认true): 是否启用训练数据加载

**执行步骤流程**：
```
1. DDL/MD生成 (必需)
   ↓
2. Question-SQL生成 (必需)
   ↓
3. SQL验证 (受enable_sql_validation控制)
   ├─ SQL验证失败 → LLM修复 (受enable_llm_repair控制)
   └─ 文件修改 (受modify_original_file控制)
   ↓
4. 训练数据加载 (受enable_training_data_load控制)
```

**对于前端UI**，主要提供四个参数 `business_context`、`db_name`、`db_connection`、`task_name`，如果`db_connection`连接串中填写了数据库的名字，那么`db_name`可以忽略。

#### 1.3 预期返回结果

**请求**：
```json
{
    "task_name": "服务区初始化数据加载",
    "db_name": "highway_db",
    "business_context": "高速公路服务区管理系统"
}
```

**响应**（创建成功）：
> **注意**：请记录返回的 `task_id`，后续的操作都需要使用这个 `task_id`。

```json
{
    "code": 200,
    "data": {
        "created_at": "2025-07-02T17:40:00.268100",
        "file_upload_mode": true,
        "next_step": "POST /api/v0/data_pipeline/tasks/task_20250702_174000/upload-table-list",
        "response": "任务创建成功，请上传表清单文件后再执行任务",
        "status": "pending",
        "task_id": "task_20250702_174000",
        "task_name": "服务区初始化数据加载"
    },
    "message": "操作成功",
    "success": true
}
```

### 2. 提供表名列表

有两种方式提交表名列表，这些表是将来用NL2SQL查询的，我们需要基于这些表的定义和数据生成训练数据集。

> **重要**：请注意上个步骤中返回的`task_id`，在接下来的步骤中都需要用到这个`task_id`。

#### 2.1 直接提交表名列表

##### a.) 通过API获取当前数据库中的表名（可选步骤）

**API**: `POST /api/v0/database/tables`

**请求地址**: `http://localhost:8084/api/v0/database/tables`

**参数**（都是可选参数）：`db_connection / schema / table_name_pattern` 

> 如果要查询的数据库没有在app_config.py中配置，或者不是查询业务数据的表，那么需要提供db_connection字符串。

```json
{
    "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
    "schema": "public,ods,dw",
    "table_name_pattern": "*_area*"
}
```

**请求示例**：
直接使用空参数`{}`，会返回app_config.py中配置的业务数据库中所有public.*schema的表

**预期返回结果**：
```json
{
    "code": 200,
    "data": {
        "db_connection_info": {
            "database": "highway_db"
        },
        "response": "获取表列表成功",
        "schemas": [
            "public",
            "ods",
            "dw"
        ],
        "table_name_pattern": "*_area*",
        "tables": [
            "public.bss_section_route_area_link",
            "public.bss_service_area",
            "public.bss_service_area_mapper"
        ],
        "total": 3
    },
    "message": "操作成功",
    "success": true
}
```

##### b.) 在线提交表名字符串列表

**API**: `POST /api/v0/data_pipeline/tasks/{task_id}/table-list`

**请求地址**: `http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_144901/table-list`

**参数**：
只有一个必选参数 `tables`，后面的表名使用逗号分隔，支持 `schema.table` 的格式。

```json
{
  "tables": "bss_car_day_count,bss_business_day_data,bss_company,bss_section_route,bss_section_route_area_link,bss_service_area,bss_service_area_mapper"
}
```

**预期返回结果**：
```json
{
    "code": 200,
    "data": {
        "created_time": "2025-07-02T18:07:15.596971",
        "file_size": 220,
        "file_size_formatted": "220.0 B",
        "filename": "table_list.txt",
        "original_count": 7,
        "response": "表清单已成功创建，包含 7 个表",
        "table_count": 7,
        "task_id": "task_20250702_174000",
        "unique_table_count": 7
    },
    "message": "操作成功",
    "success": true
}
```

#### 2.2 上传表名清单文件(*.txt)

**API**: `POST /api/v0/data_pipeline/tasks/{task_id}/upload-table-list`

**预期返回结果**：
```json
{
    "code": 200,
    "data": {
        "file_size": 284,
        "file_size_formatted": "284.0 B",
        "filename": "table_list.txt",
        "response": "表清单文件上传成功",
        "task_id": "task_20250702_144901",
        "upload_time": "2025-07-02T14:59:37.143754"
    },
    "message": "操作成功",
    "success": true
}
```

#### 2.3 验证表名（可选）

主要用来排查问题的，目前前端UI不用关注这个API。

**API**: `GET /api/v0/data_pipeline/tasks/{task_id}/table-list-info`

**请求地址**: `http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_174000/table-list-info`

**预期返回结果**：
```json
{
    "code": 200,
    "data": {
        "created_at": "2025-07-02T18:07:15.596353",
        "exists": true,
        "file_name": "table_list.txt",
        "file_path": "C:\\Projects\\cursor_projects\\Vanna-Chainlit-Chromadb\\data_pipeline\\training_data\\task_20250702_174000\\table_list.txt",
        "file_size": 220,
        "file_size_formatted": "220.0 B",
        "has_file": true,
        "is_readable": true,
        "response": "获取表清单文件信息成功",
        "table_count": 7,
        "task_id": "task_20250702_174000",
        "uploaded_at": "2025-07-02T18:07:15.596971"
    },
    "message": "操作成功",
    "success": true
}
```

### 3. 自动产生训练数据并加载的全过程（完整工作流）

**API**: `POST /api/v0/data_pipeline/tasks/{task_id}/execute`

**完整执行的参数**：
```json
{
    "execution_mode": "complete"
}
```

**预期返回结果**：
> 该作业属于异步执行，提交后调度成功就可以返回。

```json
{
    "code": 200,
    "data": {
        "execution_mode": "complete",
        "message": "任务正在后台执行，请通过状态接口查询进度",
        "response": "任务执行已启动",
        "step_name": null,
        "task_id": "task_20250702_174000"
    },
    "message": "操作成功",
    "success": true
}
```

### 4. 监控与日志

#### 4.1 任务状态监控

**API**: `GET /api/v0/data_pipeline/tasks/{task_id}`

**请求地址**: `http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_174000`

##### 执行中状态示例

正在执行第一步：`"ddl_generation": "running"`

```json
{
    "code": 200,
    "data": {
        "completed_at": null,
        "created_at": "2025-07-02T17:40:00.268100",
        "current_step": {
            "execution_id": "task_20250702_174000_step_ddl_generation_exec_20250702_190410",
            "started_at": "2025-07-02T19:04:09.933108",
            "status": "running",
            "step": "ddl_generation"
        },
        "error_message": null,
        "parameters": {
            "business_context": "高速公路服务区管理系统",
            "db_connection": "postgresql://postgres:postgres@192.168.67.1:6432/highway_db",
            "enable_llm_repair": true,
            "enable_sql_validation": true,
            "enable_training_data_load": true,
            "file_upload_mode": true,
            "modify_original_file": true,
            "table_list_file": "{task_directory}/table_list.txt"
        },
        "response": "获取任务状态成功",
        "result": null,
        "started_at": "2025-07-02T19:04:09.925931",
        "status": "in_progress",
        "step_status": {
            "ddl_generation": "running",
            "qa_generation": "pending",
            "sql_validation": "pending",
            "training_load": "pending"
        },
        "steps": [
            {
                "completed_at": null,
                "error_message": null,
                "started_at": "2025-07-02T19:04:09.933108",
                "step_name": "ddl_generation",
                "step_status": "running"
            },
            {
                "completed_at": null,
                "error_message": null,
                "started_at": null,
                "step_name": "qa_generation",
                "step_status": "pending"
            },
            {
                "completed_at": null,
                "error_message": null,
                "started_at": null,
                "step_name": "sql_validation",
                "step_status": "pending"
            },
            {
                "completed_at": null,
                "error_message": null,
                "started_at": null,
                "step_name": "training_load",
                "step_status": "pending"
            }
        ],
        "task_id": "task_20250702_174000",
        "task_name": "服务区初始化数据加载",
        "total_steps": 4
    },
    "message": "操作成功",
    "success": true
}
```

##### 完成状态示例

四个步骤全部完成：
- `"status": "completed"`
- `"step_status": { "ddl_generation": "completed", "qa_generation": "completed", "sql_validation": "completed", "training_load": "completed" }`

```json
{
    "code": 200,
    "data": {
        "completed_at": "2025-07-02T19:21:03.007862",
        "created_at": "2025-07-02T17:40:00.268100",
        "current_step": null,
        "error_message": null,
        "parameters": {
            "business_context": "高速公路服务区管理系统",
            "db_connection": "postgresql://postgres:postgres@192.168.67.1:6432/highway_db",
            "enable_llm_repair": true,
            "enable_sql_validation": true,
            "enable_training_data_load": true,
            "file_upload_mode": true,
            "modify_original_file": true,
            "table_list_file": "{task_directory}/table_list.txt"
        },
        "response": "获取任务状态成功",
        "result": null,
        "started_at": "2025-07-02T19:04:09.925931",
        "status": "completed",
        "step_status": {
            "ddl_generation": "completed",
            "qa_generation": "completed",
            "sql_validation": "completed",
            "training_load": "completed"
        },
        "steps": [
            {
                "completed_at": "2025-07-02T19:10:18.599375",
                "error_message": null,
                "started_at": "2025-07-02T19:04:09.933108",
                "step_name": "ddl_generation",
                "step_status": "completed"
            },
            {
                "completed_at": "2025-07-02T19:17:23.449415",
                "error_message": null,
                "started_at": "2025-07-02T19:10:18.602632",
                "step_name": "qa_generation",
                "step_status": "completed"
            },
            {
                "completed_at": "2025-07-02T19:19:48.712247",
                "error_message": null,
                "started_at": "2025-07-02T19:17:23.453558",
                "step_name": "sql_validation",
                "step_status": "completed"
            },
            {
                "completed_at": "2025-07-02T19:21:03.002708",
                "error_message": null,
                "started_at": "2025-07-02T19:19:48.715083",
                "step_name": "training_load",
                "step_status": "completed"
            }
        ],
        "task_id": "task_20250702_174000",
        "task_name": "服务区初始化数据加载",
        "total_steps": 4
    },
    "message": "操作成功",
    "success": true
}
```

#### 4.2 查看任务日志

**API**: `GET /api/v0/data_pipeline/tasks/{task_id}/logs`

**请求地址**: `http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_174000/logs`

**预期返回结果**：
```json
{
    "code": 200,
    "data": {
        "log_file": "C:\\Projects\\cursor_projects\\Vanna-Chainlit-Chromadb\\data_pipeline\\training_data\\task_20250702_174000\\data_pipeline.log",
        "logs": [
            {
                "level": "INFO",
                "logger": "TaskDir_task_20250702_174000",
                "message": "任务目录日志初始化完成 - 任务ID: task_20250702_174000",
                "timestamp": "2025-07-02 19:04:10"
            },
            {
                "level": "INFO",
                "logger": "TaskDir_task_20250702_174000",
                "message": "任务参数: {\"db_connection\": \"postgresql://postgres:postgres@192.168.67.1:6432/highway_db\", \"table_list_file\": \"{task_directory}/table_list.txt\", \"business_context\": \"高速公路服务区管理系统\", \"file_upload_mode\": true, \"enable_llm_repair\": true, \"modify_original_file\": true, \"enable_sql_validation\": true, \"enable_training_data_load\": true}",
                "timestamp": "2025-07-02 19:04:10"
            },
            {
                "level": "INFO",
                "logger": "TaskDir_task_20250702_174000",
                "message": "完整工作流任务开始执行",
                "timestamp": "2025-07-02 19:04:10"
            },
            {
                "level": "INFO",
                "logger": "TaskDir_task_20250702_174000",
                "message": "[ddl_generation] 开始执行步骤: ddl_generation",
                "timestamp": "2025-07-02 19:04:10"
            },
            {
                "level": "INFO",
                "logger": "TaskDir_task_20250702_174000",
                "message": "[ddl_generation] 开始执行DDL/MD生成步骤\n2025-07-02 19:04:10 [INFO] [data_pipeline.SchemaWorkflowOrchestrator] schema_workflow.py:167 - ============================================================",
                "timestamp": "2025-07-02 19:04:10"
            },
            {
                "level": "ERROR",
                "logger": "[data_pipeline.SchemaTrainingDataAgent] training_data_agent.py:234 - ❌ 表 public.bss_car_day_count 处理失败，耗时",
                "message": "55.71秒",
                "timestamp": "2025-07-02 19:05:06"
            }
        ],
        "response": "获取任务日志成功",
        "source": "file",
        "task_id": "task_20250702_174000",
        "total": 23
    },
    "message": "操作成功",
    "success": true
}
```

#### 4.3 查看和下载文件

##### a.) 查看生成的训练数据文件

**API**: `GET /api/v0/data_pipeline/tasks/{task_id}/files`

**请求地址**: `http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_174000/files`

**预期返回结果**：
```json
{
    "code": 200,
    "data": {
        "directory_info": {
            "directory_path": "C:\\Projects\\cursor_projects\\Vanna-Chainlit-Chromadb\\data_pipeline\\training_data\\task_20250702_174000",
            "exists": true,
            "total_files": 26,
            "total_size": 104982,
            "total_size_formatted": "102.5 KB"
        },
        "files": [
            {
                "created_at": "2025-07-02T19:04:10.194958",
                "file_name": "data_pipeline.log",
                "file_size": 35951,
                "file_size_formatted": "35.1 KB",
                "file_type": "log",
                "is_readable": true,
                "modified_at": "2025-07-02T19:21:03.233582"
            },
            {
                "created_at": "2025-07-02T19:21:03.230334",
                "file_name": "task_result.json",
                "file_size": 3601,
                "file_size_formatted": "3.5 KB",
                "file_type": "json",
                "is_readable": true,
                "modified_at": "2025-07-02T19:21:03.230878"
            },
            {
                "created_at": "2025-07-02T19:19:48.483686",
                "file_name": "sql_validation_20250702_191948_summary.log",
                "file_size": 2839,
                "file_size_formatted": "2.8 KB",
                "file_type": "log",
                "is_readable": true,
                "modified_at": "2025-07-02T19:19:48.484199"
            },
            {
                "created_at": "2025-07-02T18:07:15.596353",
                "file_name": "table_list.txt",
                "file_size": 220,
                "file_size_formatted": "220.0 B",
                "file_type": "text",
                "is_readable": true,
                "modified_at": "2025-07-02T18:07:15.596971"
            }
        ],
        "response": "获取任务文件列表成功",
        "task_id": "task_20250702_174000"
    },
    "message": "操作成功",
    "success": true
}
```

##### b.) 下载生成的文件

**API**: `GET /api/v0/data_pipeline/tasks/{task_id}/files/{file_name}`

**请求地址**: `http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_174000/files/bss_company.ddl`

**返回文件的内容**：
```sql
-- 中文名: 业务支撑系统公司信息表
-- 描述: 业务支撑系统公司信息表，存储服务区关联企业的基础信息及状态变更记录
create table public.bss_company (
  id varchar(32) not null     -- 主键ID，主键,
  version integer not null    -- 版本号,
  create_ts timestamp         -- 创建时间,
  created_by varchar(50)      -- 创建人ID,
  update_ts timestamp         -- 更新时间,
  updated_by varchar(50)      -- 更新人ID,
  delete_ts timestamp         -- 删除时间,
  deleted_by varchar(50)      -- 删除人ID,
  company_name varchar(255)   -- 公司名称,
  company_no varchar(255)     -- 公司编码,
  primary key (id)
);
```

#### 4.4 上传训练数据

如果有需要，可以把自动生成的训练数据下载到本地，进行修改，然后上传。或者，直接上传本地准备好的训练数据集。

**API**: `POST /api/v0/data_pipeline/tasks/{task_id}/files`

**请求地址**: `http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_213000/files`

##### 预期返回结果

**基本上传（无同名文件）**：
```json
{
    "code": 200,
    "data": {
        "response": "文件上传成功",
        "success": true,
        "task_id": "task_20250702_213000",
        "uploaded_file": {
            "filename": "tables.txt",
            "overwrite_mode": "backup",
            "size": 284,
            "size_formatted": "284.0 B",
            "uploaded_at": "2025-07-02T21:42:13.627532"
        }
    },
    "message": "操作成功",
    "success": true
}
```

**备份模式下，有同名文件的返回结果**：
```json
{
    "code": 200,
    "data": {
        "backup_info": {
            "backup_created_at": "2025-07-02T21:43:06.048935",
            "backup_filename": "tables.txt_bak1",
            "backup_version": 1,
            "had_existing_file": true
        },
        "response": "文件上传成功",
        "success": true,
        "task_id": "task_20250702_213000",
        "uploaded_file": {
            "filename": "tables.txt",
            "overwrite_mode": "backup",
            "size": 284,
            "size_formatted": "284.0 B",
            "uploaded_at": "2025-07-02T21:43:06.050035"
        }
    },
    "message": "操作成功",
    "success": true
}
```

##### 参数说明

- `file` (file, required): 要上传的文件
- `overwrite_mode` (string, optional): 重名处理模式，可选值：`backup`（默认）、`replace`、`skip`

##### 使用示例

```bash
# 基本上传（默认备份模式）
curl -X POST \
  http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_123456/files \
  -F "file=@test.ddl"

# 上传DDL文件（备份模式）
curl -X POST \
  http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_213000/files \
  -F "file=@test.ddl" \
  -F "overwrite_mode=backup"

# 上传文件（替换模式）
curl -X POST \
  http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_213000/files \
  -F "file=@config.json" \
  -F "overwrite_mode=replace"
```

#### 4.5 查看历史任务列表（管理员）

**API**: `GET /api/v0/data_pipeline/tasks`

**请求地址**: `http://localhost:8084/api/v0/data_pipeline/tasks`

**预期返回结果**：
```json
{
    "code": 200,
    "data": {
        "limit": 50,
        "offset": 0,
        "response": "获取任务列表成功",
        "tasks": [
            {
                "business_context": "数据库管理系统",
                "completed_at": null,
                "created_at": "2025-07-02T22:38:03.338248",
                "created_by": "guest",
                "db_name": "highway_db",
                "directory_exists": false,
                "started_at": null,
                "status": "pending",
                "step_status": "pending",
                "task_id": "task_20250702_223802",
                "task_name": "任务删除测试",
                "updated_at": "2025-07-02T22:39:25.276811"
            },
            {
                "business_context": "数据库管理系统",
                "completed_at": null,
                "created_at": "2025-07-02T22:37:51.797283",
                "created_by": "guest",
                "db_name": "highway_db",
                "directory_exists": true,
                "started_at": null,
                "status": "pending",
                "step_status": "pending",
                "task_id": "task_20250702_223751",
                "task_name": "任务删除测试",
                "updated_at": null
            }
        ],
        "total": 29
    },
    "message": "操作成功",
    "success": true
}
```

#### 4.6 删除历史任务列表（管理员）

**API**: `DELETE /api/v0/data_pipeline/tasks`

**请求地址**: `http://localhost:8084/api/v0/data_pipeline/tasks`

##### 参数说明

| 参数名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `task_ids` | Array[String] | ✅ | - | 要删除的任务ID列表，支持单个或多个 |
| `confirm` | Boolean | ✅ | - | 确认删除操作，必须为 `true` |
| `delete_database_records` | Boolean | ❌ | `false` | 是否删除数据库记录 |
| `continue_on_error` | Boolean | ❌ | `true` | 批量删除时遇到错误是否继续 |

##### 使用示例

**删除单个任务**：
```bash
curl -X DELETE \
  http://localhost:8084/api/v0/data_pipeline/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": ["task_20250702_223802"],
    "confirm": true
  }'
```

**删除多个任务**：
```bash
curl -X DELETE \
  http://localhost:8084/api/v0/data_pipeline/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": ["task_20250702_223802", "task_20250702_223751", "task_20250702_223705"],
    "confirm": true,
    "delete_database_records": false,
    "continue_on_error": true
  }'
```

**请求参数示例**：
```json
{
    "task_ids": ["manual_20250701_165444"],
    "confirm": true
}
```

**预期返回结果**：
```json
{
    "code": 200,
    "data": {
        "deleted_at": "2025-07-02T23:15:26.423971",
        "deleted_tasks": [
            {
                "database_records_deleted": false,
                "deleted_at": "2025-07-02T23:15:26.423971",
                "deleted_files_count": 1,
                "deleted_size": "281 B",
                "directory_deleted": true,
                "success": true,
                "task_id": "manual_20250701_165444"
            }
        ],
        "failed_tasks": [],
        "response": "任务目录删除成功",
        "summary": {
            "failed": 0,
            "successfully_deleted": 1,
            "total_requested": 1
        }
    },
    "message": "操作成功",
    "success": true
}
```

