# Training Data  API 手工分步执行指南

## 概述

本文档说明如何使用 Training Data  API 进行手工分步执行训练数据生成流程。与 5.1 文档不同，本文档专注于四个步骤的独立执行和控制。

## API 接口列表

### 分步执行核心 API

| 方法 | 端点 | 描述 |
|------|------|------|
| `POST` | `/api/v0/data_pipeline/tasks/{task_id}/execute` | 执行单个步骤（分步模式） |

### 监控和状态查询 API

| 方法 | 端点 | 描述 |
|------|------|------|
| `GET` | `/api/v0/data_pipeline/tasks/{task_id}` | 获取任务和步骤状态 |
| `GET` | `/api/v0/data_pipeline/tasks/{task_id}/logs` | 获取任务执行日志 |
| `GET` | `/api/v0/data_pipeline/tasks/{task_id}/files` | 查看步骤生成文件 |
| `GET` | `/api/v0/data_pipeline/tasks/{task_id}/files/{file_name}` | 下载步骤生成文件 |

### 文件管理 API

| 方法 | 端点 | 描述 |
|------|------|------|
| `POST` | `/api/v0/data_pipeline/tasks/{task_id}/files` | 上传修改后的文件 |

### 前置条件 API

> 注意：以下API的详细用法请参考5.1.Training数据集自动生成和加载过程API

| 方法 | 端点 | 描述 |
|------|------|------|
| `POST` | `/api/v0/data_pipeline/tasks` | 创建训练任务 |
| `POST` | `/api/v0/database/tables` | 查询业务数据库表名列表 |
| `POST` | `/api/v0/data_pipeline/tasks/{task_id}/table-list` | 在线提交表名列表 |
| `POST` | `/api/v0/data_pipeline/tasks/{task_id}/upload-table-list` | 上传表清单文件 |

## 前置条件

在开始分步执行前，需要完成以下准备工作：

1. **创建任务** 
2. **提供表名列表**

这部分内容可以参考 5.1.Training 数据集自动生成和加载过程的API

## 分步执行 API

### 核心执行接口

**API**: `POST /api/v0/data_pipeline/tasks/{task_id}/execute`

**请求参数**：
```json
{
    "execution_mode": "step",
    "step_name": "{step_name}"
}
```

**参数说明**：

- `execution_mode` (string, 必需): 执行模式，分步执行时必须为 `"step"`
- `step_name` (string, 必需): 步骤名称，支持以下四个值：
  - `"ddl_generation"` - DDL/MD文档生成
  - `"qa_generation"` - Question-SQL对生成  
  - `"sql_validation"` - SQL验证和修复
  - `"training_load"` - 训练数据加载

**预期返回结果**：
```json
{
    "code": 200,
    "data": {
        "execution_mode": "step",
        "message": "任务正在后台执行，请通过状态接口查询进度",
        "response": "任务执行已启动",
        "step_name": "ddl_generation",
        "task_id": "task_20250703_000820"
    },
    "message": "操作成功",
    "success": true
}
```

## 四个步骤详细说明

### 步骤1: DDL/MD文档生成 (`ddl_generation`)

#### 功能描述
- 连接业务数据库读取表结构和样本数据
- 使用LLM生成中文字段注释和表说明
- 输出带注释的DDL文件和详细Markdown文档

#### 执行请求
```json
POST /api/v0/data_pipeline/tasks/{task_id}/execute
{
    "execution_mode": "step",
    "step_name": "ddl_generation"
}
```

参数实例：
POST:  `http://localhost:8084/api/v0/data_pipeline/tasks/task_20250703_000820/execute`

```JSON
{
    "execution_mode": "step",
    "step_name": "ddl_generation"
}
```

预期返回结果：

```json
{
    "code": 200,
    "data": {
        "execution_mode": "step",
        "message": "任务正在后台执行，请通过状态接口查询进度",
        "response": "任务执行已启动",
        "step_name": "ddl_generation",
        "task_id": "task_20250703_000820"
    },
    "message": "操作成功",
    "success": true
}
```

#### 生成文件

- `{table_name}.ddl` - 带中文注释的建表语句
- `{table_name}_detail.md` - 详细的表结构说明文档
- `metadata.txt` - 表结构元数据摘要

#### 依赖关系
- **前置条件**: 任务已创建，表清单文件已上传
- **后续步骤**: 为 `qa_generation` 提供基础数据

### 步骤2: Question-SQL对生成 (`qa_generation`)

#### 功能描述
- 分析DDL和MD文档，提取业务主题
- 为每个业务主题生成多个自然语言问题和对应SQL查询
- 输出JSON格式的问答训练数据

#### 执行请求
```json
POST /api/v0/data_pipeline/tasks/{task_id}/execute
{
    "execution_mode": "step",
    "step_name": "qa_generation"
}
```

POST  `http://localhost:8084/api/v0/data_pipeline/tasks/task_20250703_000820/execute`

```json
{
    "execution_mode": "step",
    "step_name": "qa_generation"
}
```

预期返回结果

```json
{
    "code": 200,
    "data": {
        "execution_mode": "step",
        "message": "任务正在后台执行，请通过状态接口查询进度",
        "response": "任务执行已启动",
        "step_name": "qa_generation",
        "task_id": "task_20250703_000820"
    },
    "message": "操作成功",
    "success": true
}
```

#### 生成文件

- `qs_{db_name}_{timestamp}_pair.json` - 问答对数据文件
- `qs_{db_name}_{timestamp}_pair.json.backup` - 自动备份文件(如果有LLM自动纠正的动作)
- `metadata_detail.md` - 业务主题分析详情

#### 依赖关系
- **前置条件**: `ddl_generation` 步骤必须成功完成

- **后续步骤**: 为 `sql_validation` 提供待验证的SQL

  

### 步骤3: SQL验证和修复 (`sql_validation`)

#### 功能描述
- 使用PostgreSQL EXPLAIN验证生成的SQL语法正确性
- 对无效SQL调用LLM进行自动修复
- 生成详细的验证报告和统计信息
- 可选择修改原始JSON文件或仅生成报告

#### 执行请求
```json
POST /api/v0/data_pipeline/tasks/{task_id}/execute
{
    "execution_mode": "step",
    "step_name": "sql_validation"
}
```

执行示例：

POST `http://localhost:8084/api/v0/data_pipeline/tasks/task_20250703_000820/execute`

```json
{
    "execution_mode": "step",
    "step_name": "sql_validation"
}
```

```json
{
    "code": 200,
    "data": {
        "execution_mode": "step",
        "message": "任务正在后台执行，请通过状态接口查询进度",
        "response": "任务执行已启动",
        "step_name": "sql_validation",
        "task_id": "task_20250703_000820"
    },
    "message": "操作成功",
    "success": true
}
```

#### 生成文件

- `sql_validation_{timestamp}_summary.log` - 验证结果摘要
- `file_modifications_{timestamp}.log` - 文件修改记录（如果启用修改）

#### 控制参数
> 注意：这些参数在任务创建时设置，分步执行时会使用创建时的配置，目前这些参数不暴露给前端UI，均使用默认值。

- `enable_sql_validation` (boolean): 是否启用SQL验证
- `enable_llm_repair` (boolean): 是否启用LLM修复
- `modify_original_file` (boolean): 是否修改原始JSON文件

#### 依赖关系
- **前置条件**: `qa_generation` 步骤必须成功完成
- **后续步骤**: 为 `training_load` 提供验证过的训练数据

### 步骤4: 训练数据加载 (`training_load`)

#### 功能描述
- 将DDL文档、Markdown说明和问答对加载到向量数据库
- 建立训练数据索引用于后续的NL2SQL查询
- 验证加载结果并生成统计报告

#### 执行请求
```json
POST /api/v0/data_pipeline/tasks/{task_id}/execute
{
    "execution_mode": "step",
    "step_name": "training_load"
}
```

执行示例

POST `http://localhost:8084/api/v0/data_pipeline/tasks/task_20250703_000820/execute`

```JSON
{
    "execution_mode": "step",
    "step_name": "training_load"
}
```

返回结果

```json
{
    "code": 200,
    "data": {
        "execution_mode": "step",
        "message": "任务正在后台执行，请通过状态接口查询进度",
        "response": "任务执行已启动",
        "step_name": "training_load",
        "task_id": "task_20250703_000820"
    },
    "message": "操作成功",
    "success": true
}
```



#### 加载内容

- DDL文件 (`*.ddl`)
- Markdown文档 (`*_detail.md`)
- 问答对数据 (`qs_*.json`)
- 错误SQL记录（如果存在）

#### 依赖关系
- **前置条件**: 前三个步骤都必须成功完成
- **后续步骤**: 无，这是最后一个步骤

## 监控和状态查询

### 查看步骤执行状态

**API**: `GET /api/v0/data_pipeline/tasks/{task_id}`

**关键字段说明**：

```json
{
    "step_status": {
        "ddl_generation": "completed",
        "qa_generation": "running", 
        "sql_validation": "pending",
        "training_load": "pending"
    },
    "current_step": {
        "execution_id": "task_20250702_174000_step_qa_generation_exec_20250702_190410",
        "step": "qa_generation",
        "status": "running",
        "started_at": "2025-07-02T19:04:09.933108"
    }
}
```

**状态值说明**

- `pending` - 等待执行
- `running` - 正在执行
- `completed` - 执行完成
- `failed` - 执行失败

**执行示例**

GET `http://localhost:8084/api/v0/data_pipeline/tasks/task_20250703_000820`

开始执行："step_status": { "ddl_generation": "running", ...

结束执行："step_status": { "ddl_generation": "completed", ...

**成功执行返回结果**

```json
{
    "code": 200,
    "data": {
        "completed_at": null,
        "created_at": "2025-07-03T00:08:20.129529",
        "current_step": {
            "execution_id": "task_20250703_000820_step_ddl_generation_exec_20250703_001027",
            "started_at": "2025-07-03T00:10:27.281031",
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
        "started_at": "2025-07-03T00:10:27.273943",
        "status": "in_progress",
        "step_status": {
            "ddl_generation": "running",
            "qa_generation": "pending",
            "sql_validation": "pending",
            "training_load": "pending"
        }, ... ...
```

**执行失败返回结果**

```json
{
    "code": 200,
    "data": {
        "completed_at": "2025-07-03T00:28:22.923340",
        "created_at": "2025-07-03T00:08:20.129529",
        "current_step": null,
        "error_message": "文件验证失败: DDL文件数量(14)与表数量(7)不一致",
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
        "started_at": "2025-07-03T00:10:27.273943",
        "status": "failed",
        "step_status": {
            "ddl_generation": "completed",
            "qa_generation": "failed",
            "sql_validation": "pending",
            "training_load": "pending"
        },
        "steps": [
            {
                "completed_at": "2025-07-03T00:27:35.026604",
                "error_message": null,
                "started_at": "2025-07-03T00:20:14.120309",
                "step_name": "ddl_generation",
                "step_status": "completed"
            },
            {
                "completed_at": "2025-07-03T00:28:22.920372",
                "error_message": "文件验证失败: DDL文件数量(14)与表数量(7)不一致",
                "started_at": "2025-07-03T00:28:22.908887",
                "step_name": "qa_generation",
                "step_status": "failed"
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
        "task_id": "task_20250703_000820",
        "task_name": "服务区初始化数据加载",
        "total_steps": 4
    },
    "message": "操作成功",
    "success": true
}
```



### 查看步骤执行日志

**API**: `GET /api/v0/data_pipeline/tasks/{task_id}/logs`

支持按日志级别过滤和行数限制，详细用法参考[自动化工作流指南 - 4.2 查看任务日志](./data_pipeline_api_auto_workflow_guide.md#42-查看任务日志)。

### 查看步骤生成文件

**API**: `GET /api/v0/data_pipeline/tasks/{task_id}/files`

查看当前任务目录下的所有文件，详细用法参考[自动化工作流指南 - 4.3 查看和下载文件](./data_pipeline_api_auto_workflow_guide.md#43-查看和下载文件)。

## 典型手工执行流程

### 场景1: 逐步检查每个步骤结果

```bash
# 1. 执行DDL生成
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_174000/execute \
  -H "Content-Type: application/json" \
  -d '{
    "execution_mode": "step",
    "step_name": "ddl_generation"
  }'

# 2. 监控执行状态
curl -X GET http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_174000

# 3. 检查生成的DDL文件是否满意
curl -X GET http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_174000/files

# 4. 如果满意，继续执行Q&A生成
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_174000/execute \
  -H "Content-Type: application/json" \
  -d '{
    "execution_mode": "step", 
    "step_name": "qa_generation"
  }'

# 5. 重复监控和检查过程...
```

### 场景2: 重新执行特定步骤

```bash
# 如果某个步骤结果不满意，可以重新执行
# 注意：重新执行会覆盖该步骤的输出文件

curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_174000/execute \
  -H "Content-Type: application/json" \
  -d '{
    "execution_mode": "step",
    "step_name": "qa_generation"
  }'
```

### 场景3: 跳过某些步骤

如果任务创建时禁用了某些步骤（如 `enable_sql_validation: false`），系统会自动跳过这些步骤。

## 错误处理和故障排除

### 常见错误类型

1. **步骤依赖错误**: 尝试执行未满足前置条件的步骤
2. **数据库连接错误**: 业务数据库连接失败
3. **LLM调用错误**: AI服务不可用或配额不足
4. **文件权限错误**: 任务目录写入权限不足

### 错误信息查看

通过以下方式获取详细错误信息：

1. **任务状态API**: 查看 `error_message` 字段
2. **任务日志API**: 查看 `ERROR` 级别的日志
3. **步骤状态**: 查看 `steps` 数组中各步骤的 `error_message`

### 故障恢复

1. **修复错误后重新执行**: 解决根本问题后重新执行失败的步骤
2. **强制执行**: 某些情况下可能需要忽略依赖关系强制执行
3. **手工干预**: 下载生成文件，手工修改后重新上传

## 性能优化建议

### 1. 合理的表数量
- 建议单次处理表数量：5-20个
- 大量表可以分批处理

### 2. 数据库连接优化
- 使用连接池减少连接开销
- 确保数据库性能良好

### 3. 监控执行时间
- DDL生成：通常每表1-3分钟
- Q&A生成：通常总计5-15分钟
- SQL验证：通常1-5分钟
- 训练加载：通常1-3分钟

### 4. 资源管理
- 避免同时执行多个大型任务
- 监控磁盘空间使用情况

## 文件管理

### 步骤输出文件清理

每个步骤重新执行时会自动清理该步骤的旧输出文件，但保留其他步骤的文件。

### 手工文件管理

可以通过文件上传API手工替换生成的文件：
- 参考[自动化工作流指南 - 4.4 上传训练数据](./data_pipeline_api_auto_workflow_guide.md#44-上传训练数据)

### 备份策略

系统会自动创建关键文件的备份：
- `qs_*.json.backup` - 问答对数据备份
- 支持多版本备份机制 