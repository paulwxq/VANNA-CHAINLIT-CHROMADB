data_pipeline_api_auto_workflow_guide



下面是完整执行步骤和API调用及返回说明

### 1.创建训练任务

POST `/api/v0/data_pipeline/tasks`

POST http://localhost:8084/api/v0/data_pipeline/tasks 

#### 1.1.参数示意：

参数样例1：

```JSON
{
    "task_name": "服务区初始化数据加载",
    "db_name": "highway_db",
    "business_context": "高速公路服务区管理系统"
}
```

参数样例2：

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

#### 1.2.参数说明：

##### 基础参数

- table_list_file (string): 表清单文件路径，如未提供则进入文件上传模式，目前这种方式已经废弃。
- business_context (string): 业务上下文描述，默认为"数据库管理系统"，，使用默认值会严重LLM对数据表业务主题判断的准确性。
- db_name (string): 数据库名称，如果不提供，从连接字符串中提取。
- db_connection (string): 完整的PostgreSQL连接字符串

##### 控制参数

注意：目前所有的控制参数都不在WEB UI暴露给用户，它们的默认值都是true.

- enable_sql_validation (boolean, 默认true): 是否启用SQL验证
- enable_llm_repair (boolean, 默认true): 是否启用LLM修复
- modify_original_file (boolean, 默认true): 是否修改原始文件
- enable_training_data_load (boolean, 默认true): 是否启用训练数据加载

```markdown
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

**对于前端UI**，主要提供四个参数 business_context 、db_name 、db_connection、task_name，如果db_connection连接串中填写了数据库的名字，那么db_name可以忽略。

#### 1.3.预期返回结果

POST http://localhost:8084/api/v0/data_pipeline/tasks

```json
{
    "task_name": "服务区初始化数据加载",
    "db_name": "highway_db",
    "business_context": "高速公路服务区管理系统"
}
```

下面是创建成功的返回结果，注意"task_id"，后续的操作都需要使用这个"task_id".

```Json
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



### 2.提供表名列表

有两种方式提交表名列表，这些表是将来用NL2SQL查询的，我们需要基于这些表的定义和数据生成训练数据集。另外，要注意上个步骤中返回的task_id，在接下来的步骤中都需要用到这个task_id.

#### 2.1.直接提交表名列表

##### a.) 通过下面的API获取当前数据库中的表名(可选步骤)

**API**: `POST /api/v0/database/tables`

支持下面两个参数，都是可选参数：
如果要查询的数据库没有在app_config.py中配置，或者不是查询业务数据的表，那么需要提供db_connection字符串。

```json
{
    "db_connection": "postgresql://postgres:postgres@192.168.67.1:5432/highway_db",
    "schema": "public,ods,dw"
}
```

POST: http://localhost:8084/api/v0/database/tables

直接使用空参数{}，会返回app_config.py中配置的业务数据库中所有public.* schema的表

预期返回结果：

```json
{
    "code": 200,
    "data": {
        "db_connection_info": {
            "database": "highway_db"
        },
        "response": "获取表列表成功",
        "schemas": [
            "public"
        ],
        "tables": [
            "public.bss_branch",
            "public.bss_business_day_data",
            "public.bss_car_day_count",
            "public.bss_company",
            "public.bss_section_route",
            "public.bss_section_route_area_link",
            "public.bss_service_area",
            "public.bss_service_area_mapper",
            "public.highway_metadata",
            "public.qa_feedback"
        ],
        "total": 10
    },
    "message": "操作成功",
    "success": true
}
```



##### b.) 在线提交表名字符串列表

API: POST /api/v0/data_pipeline/tasks/{task_id}/table-list

POST  http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_144901/table-list

只有一个必选参数 tables，后面的表名使用逗号分隔，支持 schema.table 的格式。

```json
{
  "tables": "bss_car_day_count,bss_business_day_data,bss_company,bss_section_route,bss_section_route_area_link,bss_service_area,bss_service_area_mapper"
}
```

预期返回结果：

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



#### 2.2.上传表名清单文件(*.txt)

API: `POST /api/v0/data_pipeline/tasks/{task_id}/upload-table-list`

预期返回结果：

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

#### 2.3.验证表名（可选）

主要用来排查问题的，目前前端UI不用关注这个API.

**API**: `GET /api/v0/data_pipeline/tasks/{task_id}/table-list-info`

GET http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_174000/table-list-info

预期返回结果：

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



### 3.自动产生训练数据并加载的全过程 (完整工作流)

API: POST:  /api/v0/data_pipeline/tasks/{task_id}/execute



完整执行的参数：

```json
{
    "execution_mode": "complete"
}
```

预期返回结果：该作业属于异步执行，提交后调度成功就可以返回。

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



### 4.监控与日志

#### 4.1. 任务状态监控

**API**: `GET /api/v0/data_pipeline/tasks`

GET: http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_174000

下面的返回结果：

a.) 正在执行第一步

"ddl_generation": "running"

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

b.) 四个步骤全部完成：
        "status": "completed",
        "step_status": {
            "ddl_generation": "completed",
            "qa_generation": "completed",
            "sql_validation": "completed",
            "training_load": "completed"
        },

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





#### 4.2.查看任务日志

**API**: `GET /api/v0/data_pipeline/tasks/{task_id}/logs`

这个API 

GET http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_174000/logs

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
                "level": "INFO",
                "logger": "data_pipeline.SchemaWorkflowOrchestrator",
                "message": "============================================================",
                "timestamp": "2025-07-02 19:04:10"
            },
            {
                "level": "INFO",
                "logger": "[data_pipeline.SchemaWorkflowOrchestrator] schema_workflow.py:168 - 📝 步骤1",
                "message": "开始生成DDL和MD文件",
                "timestamp": "2025-07-02 19:04:10"
            },
            {
                "level": "INFO",
                "logger": "data_pipeline.SchemaWorkflowOrchestrator",
                "message": "📝 步骤1: 开始生成DDL和MD文件\n2025-07-02 19:04:10 [INFO] [data_pipeline.SchemaWorkflowOrchestrator] schema_workflow.py:169 - ============================================================",
                "timestamp": "2025-07-02 19:04:10"
            },
            {
                "level": "INFO",
                "logger": "data_pipeline.SchemaWorkflowOrchestrator",
                "message": "============================================================\n2025-07-02 19:04:10 [INFO] [data_pipeline.SchemaTrainingDataAgent] training_data_agent.py:68 - 🚀 开始生成Schema训练数据",
                "timestamp": "2025-07-02 19:04:10"
            },
            {
                "level": "INFO",
                "logger": "[data_pipeline.SchemaTrainingDataAgent] training_data_agent.py:115 - 初始化完成，输出目录",
                "message": "C:\\Projects\\cursor_projects\\Vanna-Chainlit-Chromadb\\data_pipeline\\training_data\\task_20250702_174000",
                "timestamp": "2025-07-02 19:04:10"
            },
            {
                "level": "INFO",
                "logger": "[data_pipeline.SchemaTrainingDataAgent] training_data_agent.py:136 - 数据库权限检查完成",
                "message": "{'connect': True, 'select_metadata': True, 'select_data': True, 'is_readonly': False}\n2025-07-02 19:04:10 [INFO] [data_pipeline.SchemaTrainingDataAgent] training_data_agent.py:142 - 📋 从清单文件读取到 7 个表",
                "timestamp": "2025-07-02 19:04:10"
            },
            {
                "level": "INFO",
                "logger": "[data_pipeline.SchemaTrainingDataAgent] training_data_agent.py:164 - 🔄 开始并发处理 7 个表 (最大并发",
                "message": "1)",
                "timestamp": "2025-07-02 19:04:10"
            },
            {
                "level": "INFO",
                "logger": "[data_pipeline.SchemaTrainingDataAgent] training_data_agent.py:203 - 🔍 开始处理表",
                "message": "public.bss_car_day_count",
                "timestamp": "2025-07-02 19:04:10"
            },
            {
                "level": "ERROR",
                "logger": "[data_pipeline.SchemaTrainingDataAgent] training_data_agent.py:234 - ❌ 表 public.bss_car_day_count 处理失败，耗时",
                "message": "55.71秒",
                "timestamp": "2025-07-02 19:05:06"
            },
			... ...
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



#### 4.3.查看和下载文件

##### a.) 查看生成的训练数据文件

**API**: `GET /api/v0/data_pipeline/tasks/{task_id}/files`

GET: http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_174000/files

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
			... ...
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

GET http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_174000/files/bss_company.ddl

返回文件的内容：

```
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



#### 4.4.查看历史任务列表(管理员)

**API**: `GET /api/v0/data_pipeline/tasks`

GET: http://localhost:8084/api/v0/data_pipeline/tasks

预期返回：

```json
{
    "code": 200,
    "data": {
        "limit": 50,
        "offset": 0,
        "response": "获取任务列表成功",
        "tasks": [
            {
                "business_context": "高速公路服务区管理系统",
                "completed_at": "2025-07-02T19:21:03.007862",
                "created_at": "2025-07-02T17:40:00.268100",
                "created_by": "guest",
                "db_name": "highway_db",
                "started_at": "2025-07-02T19:04:09.925931",
                "status": "completed",
                "step_status": "all_completed",
                "task_id": "task_20250702_174000",
                "task_name": "服务区初始化数据加载"
            },
            {
                "business_context": "测试向后兼容性",
                "completed_at": null,
                "created_at": "2025-07-02T17:39:31.751256",
                "created_by": "guest",
                "db_name": "test_db",
                "started_at": null,
                "status": "pending",
                "step_status": "pending",
                "task_id": "task_20250702_173932",
                "task_name": null
            },
            {
                "business_context": "高速公路服务区管理系统",
                "completed_at": null,
                "created_at": "2025-07-02T17:39:30.680619",
                "created_by": "guest",
                "db_name": "highway_db",
                "started_at": null,
                "status": "pending",
                "step_status": "pending",
                "task_id": "task_20250702_173931",
                "task_name": "测试任务_高速公路数据分析"
            },
            {
                "business_context": "高速公路服务区管理系统",
                "completed_at": null,
                "created_at": "2025-07-02T17:38:53.251452",
                "created_by": "guest",
                "db_name": "highway_db",
                "started_at": null,
                "status": "pending",
                "step_status": "pending",
                "task_id": "task_20250702_173852",
                "task_name": "测试任务_高速公路数据分析"
            },
            {
                "business_context": "高速公路服务区管理系统",
                "completed_at": null,
                "created_at": "2025-07-02T17:06:35.438861",
                "created_by": "guest",
                "db_name": "highway_db",
                "started_at": null,
                "status": "pending",
                "step_status": "pending",
                "task_id": "task_20250702_170635",
                "task_name": null
            },
            {
                "business_context": "高速公路服务区管理系统",
                "completed_at": null,
                "created_at": "2025-07-02T14:49:02.267179",
                "created_by": "guest",
                "db_name": "highway_db",
                "started_at": null,
                "status": "pending",
                "step_status": "pending",
                "task_id": "task_20250702_144901",
                "task_name": null
            },
            {
                "business_context": "高速公路服务区管理系统",
                "completed_at": null,
                "created_at": "2025-07-02T01:09:52.930419",
                "created_by": "guest",
                "db_name": "highway_db",
                "started_at": "2025-07-02T01:22:14.539878",
                "status": "in_progress",
                "step_status": "partial_completed",
                "task_id": "task_20250702_010952",
                "task_name": null
            },
            {
                "business_context": "高速公路服务区管理系统",
                "completed_at": "2025-07-02T01:19:57.163044",
                "created_at": "2025-07-01T23:18:50.085424",
                "created_by": "guest",
                "db_name": "highway_db",
                "started_at": "2025-07-01T23:36:53.411362",
                "status": "failed",
                "step_status": "failed",
                "task_id": "task_20250701_231850",
                "task_name": null
            },
            {
                "business_context": "高速公路服务区管理系统",
                "completed_at": null,
                "created_at": "2025-07-01T22:40:37.182904",
                "created_by": "guest",
                "db_name": "highway_db",
                "started_at": null,
                "status": "pending",
                "step_status": "pending",
                "task_id": "task_20250701_224036",
                "task_name": null
            },
            {
                "business_context": "高速公路服务区管理系统",
                "completed_at": null,
                "created_at": "2025-07-01T14:38:33.755737",
                "created_by": "guest",
                "db_name": "highway_db",
                "started_at": null,
                "status": "pending",
                "step_status": "pending",
                "task_id": "task_20250701_223833",
                "task_name": null
            },
            {
                "business_context": "高速公路服务区管理系统",
                "completed_at": null,
                "created_at": "2025-07-01T14:20:42.631833",
                "created_by": "guest",
                "db_name": "highway_db",
                "started_at": null,
                "status": "pending",
                "step_status": "pending",
                "task_id": "task_20250701_222042",
                "task_name": null
            },
            {
                "business_context": "高速公路服务区管理系统",
                "completed_at": "2025-07-01T14:05:04.194755",
                "created_at": "2025-07-01T13:34:35.478473",
                "created_by": "guest",
                "db_name": "highway_db",
                "started_at": "2025-07-01T13:35:06.200488",
                "status": "completed",
                "step_status": "all_completed",
                "task_id": "task_20250701_213434",
                "task_name": null
            },
            {
                "business_context": "高速公路服务区管理系统",
                "completed_at": null,
                "created_at": "2025-07-01T13:24:25.700551",
                "created_by": "guest",
                "db_name": "highway_db",
                "started_at": "2025-07-01T13:25:59.712938",
                "status": "in_progress",
                "step_status": "pending",
                "task_id": "task_20250701_212426",
                "task_name": null
            }
        ],
        "total": 13
    },
    "message": "操作成功",
    "success": true
}
```







