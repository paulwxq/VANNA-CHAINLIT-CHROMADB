# Data Training API 训练数据集产生与加载过程的概要说明

## 概述

Data Training API 提供了通过REST API创建训练数据集和加载训练数据集的完整解决方案。整个过程分为四个主要步骤，支持全自动执行和分步手动执行两种模式。

## 核心处理流程

训练数据集的创建和加载包含以下四个步骤：

1. **DDL/MD生成** (`ddl_generation`) - 根据表名生成带有注释的DDL文件和Markdown文档
2. **Question-SQL生成** (`qa_generation`) - 基于DDL和MD文件生成问答对JSON文件
3. **SQL验证和修复** (`sql_validation`) - 验证生成的SQL语句并使用LLM纠正错误
4. **训练数据加载** (`training_load`) - 将生成的文件加载到训练数据库中

## 执行模式

### 全自动模式 (`complete`)
- 一次性执行完整的四步流程
- 执行后将训练数据直接加载到训练数据库中

### 分步执行模式 (`step`)
- 逐步执行各个阶段，每步完成后可人工检查结果
- 可在任一步骤暂停并修改训练数据

## API工作流程

### 阶段一：任务准备

#### 1.1 创建任务
**API**: `POST /api/v0/data_pipeline/tasks`

创建一个新的数据管道任务，获取唯一的task_id用于后续操作。

**两种创建方式**：
- **在线提交表名列表**：直接提供表名列表，逗号分隔。
- **文件上传模式**：不提供table_list_file，后续通过上传接口提供

#### 1.2 提供表名清单（二选一）

如果创建任务时选择了文件上传模式，需要通过以下两种方式之一提供表清单：

**方式一：上传表清单文件**
**API**: `POST /api/v0/data_pipeline/tasks/{task_id}/upload-table-list`

上传包含目标表名列表的文本文件。

**方式二：在线提交表名**

a.) 获取目标表的表名：
**API**: `POST /api/v0/database/tables`

b.) 直接提交表名列表：
**API**: `POST /api/v0/data_pipeline/tasks/{task_id}/table-list`

支持数组格式或逗号分隔格式提交表名列表，系统会自动在task目录下创建table_list.txt文件。

#### 1.3 获取表清单信息（可选）
**API**: `GET /api/v0/data_pipeline/tasks/{task_id}/table-list-info`

验证表清单文件是否正确上传，查看包含的表数量等信息。

### 阶段二：任务执行

#### 2.1 选择执行模式
根据业务需求选择执行模式：

**全自动执行**：
```json
POST /api/v0/data_pipeline/tasks/{task_id}/execute
{
  "execution_mode": "complete"
}
```

**分步执行**：

```json
POST /api/v0/data_pipeline/tasks/{task_id}/execute
{
  "execution_mode": "step",
  "step_name": "ddl_generation"
}
```

这里的step_name只能写一个，它可以是：ddl_generation/qa_generation/sql_validation/training_load

#### 2.2 步骤详细说明

**步骤1: DDL/MD生成** (`ddl_generation`)
- 连接业务数据库读取表结构
- 使用LLM生成中文注释
- 输出DDL文件和详细的Markdown文档
- 生成文件：`{table_name}.ddl`, `{table_name}_detail.md`

**步骤2: Question-SQL生成** (`qa_generation`)

- 分析MD文档提取业务主题
- 为每个主题生成多个问答对
- 输出JSON格式的问答数据
- 生成文件：`qs_{db_name}_{timestamp}_pair.json`, `metadata.txt`, `metadata_detail.md`

**步骤3: SQL验证和修复** (`sql_validation`)
- 使用PostgreSQL EXPLAIN验证SQL语法
- 对无效SQL调用LLM进行修复
- 生成验证报告和修复统计
- 可选择是否修改原始JSON文件

**步骤4: 训练数据加载** (`training_load`)
- 将DDL、文档和问答对加载到向量数据库
- 建立训练数据索引
- 验证加载结果

### 阶段三：监控和管理

#### 3.1 任务状态监控
**API**: `GET /api/v0/data_pipeline/tasks/{task_id}`

实时查看任务整体状态和各步骤的执行进度。

**状态值说明**：
- `pending` - 等待执行
- `in_progress` - 正在执行
- `completed` - 执行完成
- `failed` - 执行失败
- `partial_completed` - 部分完成

#### 3.2 查看任务日志
**API**: `GET /api/v0/data_pipeline/tasks/{task_id}/logs`

获取详细的执行日志，支持按级别过滤和行数限制。

#### 3.3 文件管理
**API**: `GET /api/v0/data_pipeline/tasks/{task_id}/files`

查看任务生成的所有文件列表。

**API**: `GET /api/v0/data_pipeline/tasks/{task_id}/files/{file_name}`

下载指定的输出文件。

### 阶段四：辅助功能

#### 4.1 任务列表管理（管理员）

**API**: `GET /api/v0/data_pipeline/tasks`

查看历史任务列表，支持状态过滤和分页。

#### 4.2 数据库表查询
**API**: `POST /api/v0/database/tables`

查询业务数据库中的可用表列表，用于构建表清单文件。

#### 4.3 获取数据表的ddl和字段注释信息

**API:** `POST /api/v0/database/table/ddl`

获取指定表的ddl定义和LLM生成的字段注释信息

## 典型使用场景

### 场景一：全自动创建训练数据集

```
1. POST /api/v0/data_pipeline/tasks
   (创建任务，提供table_list_file、business_context等参数)

2. 提供表清单 (二选一)：上传*.txt表名列表文件，或者在线提交逗号分隔的表名字符串
   方式A: POST /api/v0/data_pipeline/tasks/{task_id}/upload-table-list
          (上传表清单文件)
   方式B: POST /api/v0/data_pipeline/tasks/{task_id}/table-list
          (直接提交表名列表)

3. POST /api/v0/data_pipeline/tasks/{task_id}/execute
   (execution_mode: "complete")

4. GET /api/v0/data_pipeline/tasks/{task_id}
   (轮询监控执行状态)

5. GET /api/v0/data_pipeline/tasks/{task_id}/files
   (完成后查看生成的文件)
```

### 场景二：分步手动控制

```
1. POST /api/v0/data_pipeline/tasks
   (创建任务，不提供table_list_file)

2. 提供表清单 (二选一)：上传*.txt表名列表文件，或者在线提交逗号分隔的表名字符串
   方式A: POST /api/v0/data_pipeline/tasks/{task_id}/upload-table-list
          (上传表清单文件)
   方式B: POST /api/v0/data_pipeline/tasks/{task_id}/table-list
          (直接提交表名列表)

3. POST /api/v0/data_pipeline/tasks/{task_id}/execute
   (execution_mode: "step", step_name: "ddl_generation")

4. GET /api/v0/data_pipeline/tasks/{task_id}
   (检查DDL生成结果)

5. POST /api/v0/data_pipeline/tasks/{task_id}/execute
   (execution_mode: "step", step_name: "qa_generation")

6. 重复步骤4-5执行剩余步骤 (sql_validation, training_load)
```

## 依赖关系

### 步骤间依赖
- `qa_generation` 依赖 `ddl_generation` 完成
- `sql_validation` 依赖 `qa_generation` 完成
- `training_load` 依赖前三个步骤完成

### 外部依赖
- **业务数据库连接**：读取表结构和样本数据
- **LLM服务**：生成注释、主题提取、SQL修复
- **向量数据库**：存储最终的训练数据

### 配置依赖
- 数据库连接配置
- LLM模型配置
- 文件存储路径配置

## 输出文件说明

每个任务在 `./data_pipeline/training_data/{task_id}/` 目录下生成以下文件：

### ddl_generation：

- **DDL文件**: `{table_name}.ddl` - 包含注释的建表语句
- **文档文件**: `{table_name}_detail.md` - 详细的表结构说明

### qa_generation：

- **问答文件**: `qs_{db_name}_{timestamp}_pair.json` - 问答对数据
- **元数据文件**: `metadata.txt`, `metadata_detail.md` - 业务主题元数据

### sql_validation：

- **数据验证日志**：sql_validation_20250701_234912_summary.log
- **qa文件修改日志**：file_modifications_20250701_234912.log

### training_load：

- **日志文件**: `data_pipeline.log`  - training_load没有专门日志，它写入到data_pipeline.log.

**其它文件：**

- **配置文件**: `task_config.json` - 任务配置信息
- **日志文件**: `data_pipeline.log` - 详细执行日志

通过文件下载API可获取所有生成的文件用于验证和后续处理。 

## 错误处理

### 任务级错误

- 数据库连接失败
- 权限不足
- 配置错误

### 步骤级错误

- 表不存在或无权限访问
- LLM调用失败
- SQL验证失败
- 文件写入失败

所有错误信息通过任务状态API和日志API提供详细信息，支持问题诊断和故障排除。