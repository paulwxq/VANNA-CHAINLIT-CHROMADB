# Data Pipeline API 使用指南

## 概述

Data Pipeline API 是一个简化的数据管道调度和管理系统，支持通过 REST API 调度执行数据管道任务，提供任务管理、进度监控、双日志系统和文件管理等功能。

## 系统架构

### 核心组件

1. **简化任务管理器** (`SimpleTaskManager`) - 管理任务生命周期和数据库操作
2. **简化工作流执行器** (`SimpleWorkflowExecutor`) - 执行具体的数据管道任务
3. **任务执行器** (`task_executor.py`) - 独立进程执行任务
4. **文件管理器** (`SimpleFileManager`) - 管理任务输出文件和下载
5. **双日志系统** - 数据库日志 + 任务目录详细日志

### 数据库结构

系统使用 4 个主要数据库表（部署在 pgvector 数据库中）：

- `data_pipeline_tasks` - 任务主表
- `data_pipeline_task_executions` - 任务执行记录表
- `data_pipeline_task_logs` - 任务日志表
- `data_pipeline_task_outputs` - 任务输出文件表

### 执行架构

```
API请求 → citu_app.py → subprocess → task_executor.py → SimpleWorkflowExecutor → SchemaWorkflowOrchestrator
```

- **进程隔离**：使用 subprocess 启动独立进程执行任务
- **双日志记录**：数据库结构化日志 + 任务目录详细文件日志
- **任务目录管理**：每个任务在 `./data_pipeline/training_data/{task_id}/` 目录中独立存储

## 部署说明

### 1. 数据库初始化

首先运行 SQL 初始化脚本创建必要的数据库表：

```bash
psql -h host -p port -U username -d database_name -f data_pipeline/sql/init_tables.sql
```

### 2. 启动应用

启动 Flask 应用（包含 Data Pipeline API）：

```bash
python citu_app.py
```

应用将在 `http://localhost:8084` 启动，Data Pipeline API 端点前缀为 `/api/v0/data_pipeline/`。

## API 使用指南

### 基础任务管理

#### 1. 创建任务

```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks \\
  -H "Content-Type: application/json" \\
  -d '{
    "table_list_file": "tables.txt",
    "business_context": "高速公路服务区管理系统",
    "db_name": "highway_db",
    "enable_sql_validation": true,
    "enable_llm_repair": true,
    "modify_original_file": true,
    "enable_training_data_load": true
  }'
```

响应示例：
```json
{
  "success": true,
  "code": 201,
  "message": "任务创建成功",
  "data": {
    "task_id": "task_20250627_143052",
    "status": "pending",
    "created_at": "2025-06-27T14:30:52"
  }
}
```

#### 2. 执行任务

**完整工作流执行：**
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/execute \\
  -H "Content-Type: application/json" \\
  -d '{
    "execution_mode": "complete",
    "force_execution": false,
    "clean_existing_files": true
  }'
```

**单步执行：**
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/execute \\
  -H "Content-Type: application/json" \\
  -d '{
    "execution_mode": "step", 
    "step_name": "ddl_generation"
  }'
```

**可用的步骤名称：**
- `ddl_generation` - DDL生成和MD文档生成
- `qa_generation` - Q&A问答对生成
- `sql_validation` - SQL验证和修复
- `training_load` - 训练数据加载到Vanna

响应示例：
```json
{
  "success": true,
  "code": 202,
  "message": "任务执行已启动",
  "data": {
    "task_id": "task_20250627_143052",
    "execution_mode": "step",
    "step_name": "ddl_generation",
    "status": "running"
  }
}

#### 3. 查询任务状态

```bash
curl -X GET http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052
```

响应示例：
```json
{
  "success": true,
  "data": {
    "task_id": "task_20250627_143052",
    "status": "in_progress",
    "step_status": {
      "ddl_generation": "completed",
      "qa_generation": "running",
      "sql_validation": "pending",
      "training_load": "pending"
    },
    "current_execution": {
      "execution_id": "task_20250627_143052_step_qa_generation_exec_20250627_143100",
      "step": "qa_generation",
      "status": "running",
      "started_at": "2025-06-27T14:31:00"
    }
  }
}
```

#### 4. 获取任务列表

```bash
curl -X GET "http://localhost:8084/api/v0/data_pipeline/tasks?limit=10&status=completed"
```

### 日志管理

#### 查看任务日志（数据库日志）

```bash
curl -X GET "http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/logs?limit=50&level=ERROR"
```

### 文件管理

#### 1. 获取任务文件列表

#### 查看任务目录详细日志

任务执行过程中的详细日志会写入任务目录的 `data_pipeline.log` 文件：

**文件位置：** `./data_pipeline/training_data/{task_id}/data_pipeline.log`

**日志内容示例：**
```
2025-07-01 14:30:52 [INFO] TaskDir_task_20250701_143052: 任务目录日志初始化完成 - 任务ID: task_20250701_143052
2025-07-01 14:30:53 [INFO] TaskDir_task_20250701_143052: [complete] 开始执行步骤: complete
2025-07-01 14:30:53 [INFO] DataPipelineOrchestrator: 开始执行完整工作流
2025-07-01 14:30:54 [INFO] DDLMDGenerator: 开始处理表: bss_business_day_data
```

### 文件管理

#### 1. 获取输出文件列表

```bash
curl -X GET http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/files
```

#### 2. 下载任务文件

```bash
curl -X GET http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/files/qs_highway_db_20250627_143052_pair.json \\
  -o downloaded_file.json
```

#### 3. 创建任务压缩包

```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/files/archive \\
  -H "Content-Type: application/json" \\
  -d '{"archive_format": "zip"}'
```

#### 4. 验证文件完整性

```bash
curl -X GET http://localhost:8084/api/v0/data_pipeline/tasks/task_20250627_143052/files/integrity
```

#### 5. 清理旧文件

```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/files/cleanup \\
  -H "Content-Type: application/json" \\
  -d '{"days_to_keep": 30}'
```

### 监控功能

#### 1. 获取系统状态

```bash
curl -X GET http://localhost:8084/api/v0/data_pipeline/monitor/status
```

响应包含：
- 系统性能指标（CPU、内存、磁盘使用率）
- 任务统计信息
- 磁盘使用情况
- 异常检测结果
- 系统健康状态

#### 2. 获取任务详细监控

```bash
curl -X GET http://localhost:8084/api/v0/data_pipeline/monitor/tasks/task_20250627_143052
```

#### 3. 获取历史性能数据

```bash
curl -X GET "http://localhost:8084/api/v0/data_pipeline/monitor/metrics/history?minutes=120"
```

#### 4. 获取异常记录

```bash
curl -X GET "http://localhost:8084/api/v0/data_pipeline/monitor/anomalies?hours=24"
```

### 统计信息

#### 获取整体统计

```bash
curl -X GET http://localhost:8084/api/v0/data_pipeline/stats
```

## 工作流说明

### 完整工作流步骤

1. **DDL生成** (`ddl_generation`)
   - 连接数据库分析表结构
   - 生成 `.ddl` 文件和 `_detail.md` 文档
   - 生成 `metadata.txt` 和 `filename_mapping.txt`

2. **Question-SQL生成** (`qa_generation`)
   - 基于DDL和文档生成问答对
   - 输出 `qs_*_pair.json` 文件

3. **SQL验证** (`sql_validation`) - 可选
   - 验证生成的SQL语句
   - 修复无效SQL（如果启用LLM修复）
   - 生成验证报告

4. **训练数据加载** (`training_load`) - 可选
   - 将生成的数据加载到 Vanna.ai 训练数据库

### 任务状态说明

- `pending` - 任务已创建，等待执行
- `in_progress` - 任务正在执行中
- `partial_completed` - 部分步骤完成
- `completed` - 任务完全完成
- `failed` - 任务执行失败

### 步骤状态说明

- `pending` - 步骤等待执行
- `running` - 步骤正在执行
- `completed` - 步骤执行完成
- `failed` - 步骤执行失败

## 文件组织结构

每个任务在 `./data_pipeline/training_data/` 下创建独立目录：

```
./data_pipeline/training_data/
├── task_20250627_143052/                   # 任务ID作为目录名
│   ├── task_config.json                    # 任务配置参数
│   ├── task_result.json                    # 最终执行结果
│   ├── ddl_generation_result.json          # DDL生成步骤结果
│   ├── qa_generation_result.json           # QA生成步骤结果
│   ├── sql_validation_result.json          # SQL验证步骤结果
│   ├── training_load_result.json           # 训练加载步骤结果
│   ├── bss_*.ddl                          # 生成的DDL文件
│   ├── bss_*_detail.md                    # 生成的MD文档
│   ├── qs_*.json                          # Question-SQL对
│   ├── metadata.txt                        # 元数据文件
│   ├── filename_mapping.txt               # 文件映射
│   ├── sql_validation_*_summary.log       # SQL验证摘要
│   └── sql_validation_*_report.json       # SQL验证详细报告
└── task_20250627_150123/
    └── ...
```

## 错误处理

### 常见错误和解决方案

1. **任务创建失败**
   - 检查数据库连接配置
   - 确认表清单文件存在
   - 验证PostgreSQL连接权限

2. **执行超时**
   - 系统自动检测2小时以上的僵尸任务
   - 可通过监控API查看系统资源使用情况

3. **文件访问错误**
   - 检查目录权限
   - 确认磁盘空间充足

4. **依赖检查失败**
   - 按顺序执行步骤：ddl_generation → qa_generation → sql_validation → training_load
   - 或使用 `force_execution: true` 跳过依赖检查

## 最佳实践

### 1. 任务管理
- 使用描述性的业务上下文
- 定期清理旧任务文件释放磁盘空间
- 监控长时间运行的任务

### 2. 性能优化
- 大型数据库建议分批处理表清单
- 监控系统资源使用情况
- 及时处理异常告警

### 3. 安全考虑
- 不要在日志中记录敏感数据库连接信息
- 定期备份重要的训练数据
- 控制API访问权限

## 故障排除

### 查看日志
```bash
# 查看任务错误日志
curl -X GET "http://localhost:8084/api/v0/data_pipeline/tasks/TASK_ID/logs?level=ERROR"

# 查看系统异常
curl -X GET "http://localhost:8084/api/v0/data_pipeline/monitor/anomalies"
```

### 检查系统状态
```bash
# 获取完整系统状态
curl -X GET http://localhost:8084/api/v0/data_pipeline/monitor/status
```

### 手动清理
```bash
# 清理僵尸任务（通过数据库管理器）
# 清理旧文件
curl -X POST http://localhost:8084/api/v0/data_pipeline/files/cleanup \\
  -H "Content-Type: application/json" \\
  -d '{"days_to_keep": 7}'
```

## 扩展功能

### 自定义告警
系统支持异常检测和告警，可以通过修改 `TaskAnomalyDetector` 类添加自定义告警逻辑。

### 性能监控
系统自动收集性能指标，支持查看历史数据和趋势分析。

### 文件管理
支持文件完整性验证、压缩包创建、批量下载等功能。

## 完整 API 接口说明

### 1. 任务管理接口

#### 创建任务
```bash
POST /api/v0/data_pipeline/tasks
Content-Type: application/json

{
  "table_list_file": "tables.txt",
  "business_context": "业务描述",
  "db_name": "highway_db",
  "enable_sql_validation": true,
  "enable_llm_repair": true,
  "modify_original_file": true,
  "enable_training_data_load": true
}
```

**参数说明：**
- `table_list_file` (必填): 表清单文件路径
- `business_context` (必填): 业务上下文描述
- `db_name` (可选): 指定业务数据库名称，如不提供则使用app_config中的默认配置
- 其他参数为可选的功能开关

**注意：** 数据库连接信息自动从 `app_config.py` 的 `APP_DB_CONFIG` 获取，无需在API请求中提供

**预期返回：**
```json
{
  "success": true,
  "code": 201,
  "message": "任务创建成功",
  "data": {
    "task_id": "task_20250701_143052",
    "status": "pending",
    "created_at": "2025-07-01T14:30:52"
  }
}
```

#### 执行任务
```bash
POST /api/v0/data_pipeline/tasks/{task_id}/execute
Content-Type: application/json

# 完整工作流
{"execution_mode": "complete"}

# 单步执行
{"execution_mode": "step", "step_name": "ddl_generation"}
```

**预期返回：**
```json
{
  "success": true,
  "code": 202,
  "message": "任务执行已启动",
  "data": {
    "task_id": "task_20250701_143052",
    "execution_mode": "complete",
    "status": "running"
  }
}
```

#### 查询任务状态
```bash
GET /api/v0/data_pipeline/tasks/{task_id}
```

**预期返回：**
```json
{
  "success": true,
  "data": {
    "task_id": "task_20250701_143052",
    "status": "in_progress",
    "step_status": {
      "ddl_generation": "completed",
      "qa_generation": "running",
      "sql_validation": "pending",
      "training_load": "pending"
    },
    "created_at": "2025-07-01T14:30:52",
    "started_at": "2025-07-01T14:30:53"
  }
}
```

#### 获取任务列表
```bash
GET /api/v0/data_pipeline/tasks?limit=10&status=completed
```

**预期返回：**
```json
{
  "success": true,
  "data": {
    "tasks": [
      {
        "task_id": "task_20250701_143052",
        "status": "completed",
        "created_at": "2025-07-01T14:30:52"
      }
    ]
  }
}
```

### 2. 日志接口

#### 获取任务日志
```bash
GET /api/v0/data_pipeline/tasks/{task_id}/logs?limit=50&level=ERROR
```

**预期返回：**
```json
{
  "success": true,
  "data": {
    "logs": [
      {
        "id": 123,
        "timestamp": "2025-07-01T14:30:54",
        "level": "INFO",
        "message": "开始执行步骤: ddl_generation",
        "step_name": "ddl_generation"
      }
    ]
  }
}
```

### 3. 文件管理接口

#### 获取文件列表
```bash
GET /api/v0/data_pipeline/tasks/{task_id}/files
```

**预期返回：**
```json
{
  "success": true,
  "data": {
    "files": [
      {
        "file_name": "data_pipeline.log",
        "file_type": "log",
        "file_size": 1024,
        "download_url": "/api/v0/data_pipeline/tasks/{task_id}/files/download/data_pipeline.log"
      },
      {
        "file_name": "qs_highway_db_20250701_143052_pair.json",
        "file_type": "json",
        "file_size": 10240,
        "download_url": "/api/v0/data_pipeline/tasks/{task_id}/files/download/qs_highway_db_20250701_143052_pair.json"
      }
    ]
  }
}
```

#### 下载文件
```bash
GET /api/v0/data_pipeline/tasks/{task_id}/files/download/{filename}
```

**预期返回：** 文件二进制内容，Content-Type 根据文件类型设置

### 4. 执行记录接口

#### 获取任务执行记录
```bash
GET /api/v0/data_pipeline/tasks/{task_id}/executions
```

**预期返回：**
```json
{
  "success": true,
  "data": {
    "executions": [
      {
        "execution_id": "task_20250701_143052_step_ddl_generation_exec_20250701143053",
        "execution_step": "ddl_generation",
        "status": "completed",
        "started_at": "2025-07-01T14:30:53",
        "completed_at": "2025-07-01T14:35:20"
      }
    ]
  }
}
```

### 5. 错误响应格式

所有接口在出错时都返回统一的错误格式：

```json
{
  "success": false,
  "code": 400,
  "message": "错误描述",
  "error_type": "validation_error",
  "details": {}
}
```

**常见错误码：**
- `400` - 请求参数错误
- `404` - 任务不存在
- `409` - 任务冲突（已有任务在执行）
- `500` - 服务器内部错误
- `503` - 服务暂时不可用

## 技术支持

如有问题，请检查：
1. 系统日志和错误信息
2. 数据库连接状态
3. 文件系统权限
4. 系统资源使用情况
5. 任务目录详细日志文件 `./data_pipeline/training_data/{task_id}/data_pipeline.log`

通过监控API可以获取详细的系统状态和错误信息，有助于快速定位和解决问题。