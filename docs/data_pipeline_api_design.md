# Data Pipeline API 概要设计

## 项目背景

为了让Web UI能够调用Data Pipeline生成训练数据的功能，并实现任务的后台执行、进度追踪和日志查看，我们需要设计一套API系统来支持这些需求。

## 设计目标

1. **后台执行**：支持长时间运行的训练数据生成任务，不阻塞HTTP请求
2. **进度追踪**：提供实时的任务执行进度和状态查询
3. **日志管理**：集中管理任务日志，支持详细日志查看
4. **文件管理**：统一管理生成的训练数据文件
5. **并发控制**：确保同时只有一个任务在执行
6. **持久化**：任务状态持久化存储，支持服务重启后的状态恢复

## 核心设计原则

### 1. 任务与API解耦
- **API服务器**：仅负责任务调度和状态查询
- **独立脚本**：实际执行数据处理工作，完全独立运行
- **数据库桥梁**：作为两者之间的通信媒介

### 2. 任务ID即时间戳约定
- **任务ID生成规则**：`task_YYYYMMDD_HHMMSS` 格式
  - 示例：`task_20250627_143052` 表示 2025年6月27日 14:30:52 创建的任务
  - 使用本地时间，确保在同一秒内不会创建多个任务
  - 任务ID同时作为：
    - 数据库主键
    - 文件系统目录名
    - API查询参数
- **优势**：
  - 自然排序，方便查找最新任务
  - 无需额外的ID生成器
  - 时间信息直观可见

### 3. 时间戳目录管理
每个任务在`./data_pipeline/training_data/`下创建独立的时间戳目录：
```
./data_pipeline/training_data/
├── task_20250627_143052/                   # 时间戳作为任务ID
│   ├── data_pipeline.log                   # 所有data_pipeline模块的统一日志
│   ├── task_config.json                    # 任务配置参数
│   ├── task_result.json                    # 最终执行结果
│   ├── bss_*.ddl                          # 生成的DDL文件
│   ├── bss_*_detail.md                    # 生成的MD文档
│   ├── qs_*.json                          # Question-SQL对
│   ├── metadata.txt                        # 元数据文件
│   ├── sql_validation_*_summary.log       # SQL验证摘要报告
│   ├── sql_validation_*_report.json       # SQL验证详细报告（可选）
│   └── file_modifications_*.log           # 文件修改日志（如果启用修改功能）
└── task_20250627_150123/
    └── ...
```

**目录创建细节**：
- **创建时机**：在API返回之前创建，确保任务开始执行时目录已存在
- **创建位置**：相对于项目根目录的`./data_pipeline/training_data/`
- **权限设置**：确保当前用户和子进程都有读写权限（755）
- **失败处理**：如果目录创建失败，取消任务创建，返回错误信息
- **文件组织**：
  - 所有SchemaWorkflowOrchestrator的输出都重定向到此目录
  - 日志文件使用独立的FileHandler写入此目录
  - 配置文件在任务创建时立即写入

### 4. 粗粒度进度追踪
采用步骤级进度追踪，不追踪表级别的细节：
- DDL/MD生成：0% → 40%
- Question-SQL生成：40% → 70%
- SQL验证：70% → 90%
- 训练数据加载：90% → 100%

## 数据库设计

### 任务表 (data_pipeline_tasks)
```sql
CREATE TABLE data_pipeline_tasks (
    id VARCHAR(32) PRIMARY KEY,                    -- 任务ID (时间戳格式)
    task_type VARCHAR(50) NOT NULL,                -- 任务类型
    status VARCHAR(20) NOT NULL,                   -- 任务状态: pending/in_progress/partial_completed/completed/failed
    parameters JSONB NOT NULL,                     -- 任务参数
    result JSONB,                                  -- 任务结果
    error_message TEXT,                            -- 错误信息
    step_status JSONB DEFAULT '{                   -- 各步骤状态跟踪
        "ddl_generation": "pending",
        "qa_generation": "pending", 
        "sql_validation": "pending",
        "training_load": "pending"
    }',
    output_directory TEXT,                         -- 任务输出目录
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_by VARCHAR(50),
    db_name VARCHAR(100),                          -- 数据库名称
    business_context TEXT                          -- 业务上下文
);
```

### 任务执行记录表 (data_pipeline_task_executions)
```sql
CREATE TABLE data_pipeline_task_executions (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(32) REFERENCES data_pipeline_tasks(id) ON DELETE CASCADE,
    execution_step VARCHAR(50) NOT NULL,          -- 'ddl_generation', 'qa_generation', 'sql_validation', 'training_load'
    status VARCHAR(20) NOT NULL,                  -- 'running', 'completed', 'failed'
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    execution_result JSONB,                       -- 步骤执行结果
    execution_id VARCHAR(100) UNIQUE,             -- {task_id}_step_{step_name}_exec_{timestamp}
    force_executed BOOLEAN DEFAULT FALSE,         -- 是否强制执行
    files_cleaned BOOLEAN DEFAULT FALSE           -- 是否清理了旧文件
);
```

### 任务日志表 (data_pipeline_task_logs)
```sql
CREATE TABLE data_pipeline_task_logs (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(32) REFERENCES data_pipeline_tasks(id) ON DELETE CASCADE,
    execution_id VARCHAR(100) REFERENCES data_pipeline_task_executions(execution_id),
    log_level VARCHAR(10) NOT NULL,               -- 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    message TEXT NOT NULL,
    step_name VARCHAR(50),                        -- 执行步骤名称
    module_name VARCHAR(100),                     -- 模块名称
    function_name VARCHAR(100),                   -- 函数名称
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    extra_data JSONB DEFAULT '{}'                 -- 额外的结构化信息
);
```

### 任务文件输出表 (data_pipeline_task_outputs)
```sql
CREATE TABLE data_pipeline_task_outputs (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(32) REFERENCES data_pipeline_tasks(id) ON DELETE CASCADE,
    execution_id VARCHAR(100) REFERENCES data_pipeline_task_executions(execution_id),
    file_type VARCHAR(50) NOT NULL,               -- 'ddl', 'md', 'json', 'log', 'report'
    file_name VARCHAR(255) NOT NULL,              -- 文件名
    file_path TEXT NOT NULL,                      -- 相对路径
    file_size BIGINT DEFAULT 0,                   -- 文件大小（字节）
    content_hash VARCHAR(64),                     -- 文件内容hash
    description TEXT,                             -- 文件描述
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_primary BOOLEAN DEFAULT FALSE,             -- 是否为主要输出文件
    is_downloadable BOOLEAN DEFAULT TRUE          -- 是否可下载
);
```

### 索引设计
```sql
-- 任务表索引
CREATE INDEX idx_tasks_status ON data_pipeline_tasks(status);
CREATE INDEX idx_tasks_created_at ON data_pipeline_tasks(created_at DESC);
CREATE INDEX idx_tasks_db_name ON data_pipeline_tasks(db_name);
CREATE INDEX idx_tasks_created_by ON data_pipeline_tasks(created_by);

-- 执行记录表索引
CREATE INDEX idx_executions_task_id ON data_pipeline_task_executions(task_id);
CREATE INDEX idx_executions_step ON data_pipeline_task_executions(execution_step);
CREATE INDEX idx_executions_status ON data_pipeline_task_executions(status);
CREATE INDEX idx_executions_started_at ON data_pipeline_task_executions(started_at DESC);

-- 日志表索引
CREATE INDEX idx_logs_task_id ON data_pipeline_task_logs(task_id);
CREATE INDEX idx_logs_execution_id ON data_pipeline_task_logs(execution_id);
CREATE INDEX idx_logs_timestamp ON data_pipeline_task_logs(timestamp DESC);
CREATE INDEX idx_logs_level ON data_pipeline_task_logs(log_level);
CREATE INDEX idx_logs_step ON data_pipeline_task_logs(step_name);

-- 文件输出表索引
CREATE INDEX idx_outputs_task_id ON data_pipeline_task_outputs(task_id);
CREATE INDEX idx_outputs_execution_id ON data_pipeline_task_outputs(execution_id);
CREATE INDEX idx_outputs_file_type ON data_pipeline_task_outputs(file_type);
CREATE INDEX idx_outputs_primary ON data_pipeline_task_outputs(is_primary) WHERE is_primary = TRUE;
```

## API设计

**实现位置**：所有API端点都在`citu_app.py`中实现，作为现有Flask应用的扩展。

### 1. 创建任务（不执行）
```
POST /api/v0/data_pipeline/tasks
```

**请求参数**：
```json
{
  "task_type": "data_workflow",
  "table_list_file": "tables.txt",
  "business_context": "高速公路服务区管理系统",
  "db_name": "highway_db",
  "enable_sql_validation": true,
  "enable_llm_repair": true,
  "modify_original_file": true,
  "enable_training_data_load": true
}
```

**注意：** 数据库连接信息自动从 `app_config.py` 获取：
- 业务数据库连接：使用 `APP_DB_CONFIG`
- 任务管理表存储：使用 `PGVECTOR_CONFIG`（向量数据库）

**响应**：
```json
{
  "success": true,
  "message": "任务创建成功",
  "data": {
    "task_id": "task_20250627_143052",
    "status": "pending",
    "output_directory": "./data_pipeline/training_data/task_20250627_143052",
    "step_status": {
      "ddl_generation": "pending",
      "qa_generation": "pending", 
      "sql_validation": "pending",
      "training_load": "pending"
    },
    "created_at": "2025-06-27T14:30:52"
  }
}
```

### 1.1. 执行任务步骤
```
POST /api/v0/data_pipeline/tasks/{task_id}/execute
```

**请求参数**：
```json
{
  "step": "ddl_generation",
  "force_execute": false,
  "clean_previous": true
}
```

**响应**：
```json
{
  "success": true,
  "message": "步骤执行已启动",
  "data": {
    "execution_id": "task_20250627_143052_step_ddl_generation_exec_20250627143055",
    "task_id": "task_20250627_143052",
    "step": "ddl_generation",
    "status": "running",
    "started_at": "2025-06-27T14:30:55"
  }
}
```

### 1.2. 创建任务并立即执行完整工作流
```
POST /api/v0/data_pipeline/tasks/execute-complete
```

**请求参数**：
```json
{
  "task_type": "complete_workflow",
  "table_list_file": "tables.txt",
  "business_context": "高速公路服务区管理系统",
  "db_name": "highway_db"
}
```

**响应**：
```json
{
  "success": true,
  "message": "完整工作流执行已启动",
  "data": {
    "task_id": "task_20250627_143052",
    "execution_id": "task_20250627_143052_step_complete_exec_20250627143055",
    "status": "running",
    "started_at": "2025-06-27T14:30:55"
  }
}
```

### 2. 获取任务列表
```
GET /api/v0/data_pipeline/tasks
```

**响应**：
```json
{
  "success": true,
  "data": {
    "tasks": [
      {
        "task_id": "task_20250627_143052",
        "task_type": "complete_workflow",
        "status": "running",
        "progress": 45,
        "created_at": "2025-06-27T14:30:52"
      }
    ]
  }
}
```

### 3. 获取任务详情
```
GET /api/v0/data_pipeline/tasks/{task_id}
```

**响应**：
```json
{
  "success": true,
  "data": {
    "task_id": "task_20250627_143052",
    "task_type": "data_workflow",
    "status": "in_progress",
    "parameters": { ... },
    "step_status": {
      "ddl_generation": "completed",
      "qa_generation": "running", 
      "sql_validation": "pending",
      "training_load": "pending"
    },
    "output_directory": "./data_pipeline/training_data/task_20250627_143052",
    "created_at": "2025-06-27T14:30:52",
    "started_at": "2025-06-27T14:30:53",
    "completed_at": null,
    "current_execution": {
      "execution_id": "task_20250627_143052_step_qa_generation_exec_20250627143521",
      "step": "qa_generation",
      "status": "running",
      "started_at": "2025-06-27T14:35:21"
    }
  }
}
```

### 3.1. 获取任务执行历史
```
GET /api/v0/data_pipeline/tasks/{task_id}/executions
```

**响应**：
```json
{
  "success": true,
  "data": {
    "executions": [
      {
        "execution_id": "task_20250627_143052_step_ddl_generation_exec_20250627143053",
        "step": "ddl_generation",
        "status": "completed",
        "started_at": "2025-06-27T14:30:53",
        "completed_at": "2025-06-27T14:35:20",
        "duration": 267,
        "force_executed": false,
        "files_cleaned": true
      },
      {
        "execution_id": "task_20250627_143052_step_qa_generation_exec_20250627143521",
        "step": "qa_generation",
        "status": "running",
        "started_at": "2025-06-27T14:35:21",
        "completed_at": null,
        "force_executed": false,
        "files_cleaned": false
      }
    ]
  }
}
```

### 4. 获取当前活跃任务
```
GET /api/v0/data_pipeline/tasks/active
```

**响应**：返回最近的运行中任务，如无则返回最近完成的任务

### 5. 获取任务日志
```
GET /api/v0/data_pipeline/tasks/{task_id}/logs?limit=100&level=INFO
```

**响应**：
```json
{
  "success": true,
  "data": {
    "logs": [
      {
        "timestamp": "2025-06-27T14:30:53",
        "level": "INFO",
        "step_name": "ddl_md_generation",
        "message": "开始处理表: bss_business_day_data"
      }
    ]
  }
}
```

### 6. 获取任务输出文件
```
GET /api/v0/data_pipeline/tasks/{task_id}/files
```

**响应**：
```json
{
  "success": true,
  "data": {
    "files": [
      {
        "file_name": "qs_highway_db_20250627_143052_pair.json",
        "file_type": "json",
        "file_size": 102400,
        "download_url": "/api/v0/data_pipeline/tasks/task_20250627_143052/files/download/qs_highway_db_20250627_143052_pair.json"
      }
    ]
  }
}
```

### 7. 下载文件
```
GET /api/v0/data_pipeline/tasks/{task_id}/files/download/{filename}
```

## 任务与执行模型设计

### 1. 核心概念

**任务（Task）**：一个完整的数据处理工作单元，包含4个步骤，有唯一的任务ID和输出目录
**执行（Execution）**：在某个任务中执行特定步骤的一次操作，支持重复执行和分步执行

### 2. 步骤定义

**步骤标识使用描述性名称**：
- **ddl_generation**：DDL生成 - 生成DDL文件和MD文档
- **qa_generation**：Q&A生成 - 生成Question-SQL对
- **sql_validation**：SQL验证 - 验证和修正SQL语句  
- **training_load**：训练数据加载 - 加载训练数据到Vanna

### 3. 支持的执行模式

**完整工作流模式**：
- 一次性执行所有4个步骤：ddl_generation → qa_generation → sql_validation → training_load
- 传统的端到端执行方式

**分步执行模式**：
- 在同一个任务中分多次执行不同步骤
- 支持检查每个步骤的结果后再决定是否执行下一步
- 支持重复执行同一步骤（比如步骤失败后重新执行）
- 所有步骤的日志和输出文件都在同一个任务目录中

### 4. 步骤依赖关系

- **ddl_generation**：无依赖，可直接执行
- **qa_generation**：依赖 ddl_generation 成功完成
- **sql_validation**：依赖 qa_generation 成功完成
- **training_load**：依赖 sql_validation 成功完成

### 5. 文件管理策略

**同一任务目录原则**：
- 所有步骤的输出都在 `./data_pipeline/training_data/{task_id}/` 目录
- 重复执行步骤时清理该步骤的旧输出文件
- 保持其他步骤的文件不受影响

**步骤文件映射**：
- ddl_generation: `*.ddl`, `*_detail.md`, `metadata.txt`
- qa_generation: `qs_*.json`, `qs_*.json.backup`
- sql_validation: `sql_validation_*_summary.log`, `sql_validation_*_report.json`
- training_load: `training_load_*.log`

### 6. 并发控制

**单任务内串行执行**：
- 同一任务内不允许并发执行多个步骤
- 全局可以有多个不同任务并发执行
- 执行前检查是否有正在运行的步骤

## 执行流程设计

### 1. 任务创建流程
```
1. 前端发送POST请求创建任务
2. API生成task_id (格式: task_YYYYMMDD_HHMMSS)
3. 在数据库中创建任务记录，状态为'pending'
4. 创建对应的时间戳目录
5. 初始化步骤状态为全部'pending'
6. 立即返回task_id给前端
7. 任务创建完成，等待步骤执行请求
```

### 2. 步骤执行流程  
```
1. 前端发送POST请求执行特定步骤
2. 检查任务是否存在
3. 检查步骤依赖关系（除非force_execute=true）
4. 检查是否有正在运行的步骤（并发控制）
5. 生成execution_id
6. 创建执行记录，状态为'running'
7. 如果clean_previous=true，清理该步骤的旧输出文件
8. 启动独立任务执行器进程: subprocess.Popen([
     sys.executable, 
     './data_pipeline/task_executor.py',
     '--task-id', task_id,
     '--execution-mode', execution_mode,  # 'complete' 或 'step'
     '--step-name', step_name if execution_mode == 'step' else None
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    cwd=project_root
)
9. 立即返回execution_id给前端
10. API请求结束，task_executor.py脚本继续后台运行
```

**详细实现步骤**：

#### 2.1 任务ID生成
```python
from datetime import datetime
task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
```

#### 2.2 并发检查
```sql
SELECT COUNT(*) FROM data_pipeline_tasks WHERE status = 'running';
-- 如果结果 > 0，返回错误："已有任务正在执行，请稍后再试"
```

#### 2.3 任务记录创建
```sql
INSERT INTO data_pipeline_tasks (id, task_type, status, parameters, created_by)
VALUES (?, ?, 'pending', ?::jsonb, ?);
```

#### 2.4 目录创建
```python
task_dir = os.path.join('./data_pipeline/training_data/', task_id)
os.makedirs(task_dir, mode=0o755, exist_ok=False)  # exist_ok=False 确保目录唯一
```

#### 2.5 配置文件写入
```python
config_path = os.path.join(task_dir, 'task_config.json')
with open(config_path, 'w', encoding='utf-8') as f:
    json.dump({
        'task_id': task_id,
        'task_type': task_type,
        'parameters': parameters,
        'created_at': datetime.now().isoformat()
    }, f, indent=2, ensure_ascii=False)
```

#### 2.6 启动后台进程
```python
# 使用subprocess.Popen启动独立任务执行器进程
process = subprocess.Popen(
    [sys.executable, 
     './data_pipeline/task_executor.py',
     '--task-id', task_id,
     '--execution-mode', execution_mode,  # 'complete' 或 'step'
     '--step-name', step_name if execution_mode == 'step' else None
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    cwd=project_root  # 项目根目录
)
```

### 2. 后台执行流程
```
1. task_executor.py启动，接收task_id和执行模式参数
2. 初始化日志系统，创建SimpleWorkflowExecutor实例
3. 确保任务目录存在，设置任务目录日志记录器
4. 更新数据库状态为'running'，started_at时间戳
5. 创建SchemaWorkflowOrchestrator并重定向其日志到任务目录
6. 执行工作流（完整或单步），记录详细日志到data_pipeline.log
7. 生成的文件都保存在对应的时间戳目录
8. 完成后更新数据库状态为'completed'或'failed'
9. 清理资源，脚本退出
```

**任务执行架构** (基于独立的task_executor.py):

#### 2.1 任务执行器参数
```python
# data_pipeline/task_executor.py 命令行参数
parser.add_argument('--task-id', required=True, help='任务ID')
parser.add_argument('--execution-mode', default='complete', 
                   choices=['complete', 'step'], help='执行模式')
parser.add_argument('--step-name', help='步骤名称（当execution-mode=step时必需）')
```

#### 2.2 任务执行主函数
```python
async def execute_task(task_id: str, execution_mode: str, step_name: str = None):
    """执行任务的异步函数"""
    executor = None
    try:
        # 创建SimpleWorkflowExecutor实例
        executor = SimpleWorkflowExecutor(task_id)
        
        if execution_mode == "complete":
            # 执行完整工作流
            return await executor.execute_complete_workflow()
        elif execution_mode == "step":
            # 执行单个步骤
            return await executor.execute_single_step(step_name)
        else:
            raise ValueError(f"不支持的执行模式: {execution_mode}")
            
    finally:
        if executor:
            executor.cleanup()
```

#### 2.3 SimpleWorkflowExecutor核心功能
```python
class SimpleWorkflowExecutor:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.task_manager = SimpleTaskManager()  # 数据库管理
        self.file_manager = SimpleFileManager()  # 文件管理
        self.task_dir_logger = None              # 任务目录日志记录器
        self._load_task_info()                   # 加载任务信息
    
    def _setup_task_directory_logger(self):
        """设置任务目录日志记录器"""
        task_dir = self.file_manager.get_task_directory(self.task_id)
        log_file = task_dir / "data_pipeline.log"
        
        # 创建专门的任务目录日志记录器
        self.task_dir_logger = logging.getLogger(f"TaskDir_{self.task_id}")
        self.task_dir_logger.setLevel(logging.DEBUG)
        self.task_dir_logger.handlers.clear()
        self.task_dir_logger.propagate = False
        
        # 创建文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        self.task_dir_logger.addHandler(file_handler)
    
    def _redirect_orchestrator_logs(self, orchestrator):
        """重定向SchemaWorkflowOrchestrator的日志到任务目录"""
        if self.task_dir_logger and hasattr(orchestrator, 'logger'):
            for handler in self.task_dir_logger.handlers:
                if isinstance(handler, logging.FileHandler):
                    orchestrator.logger.addHandler(handler)
                    break
```

#### 2.4 双日志系统设计

##### 日志文件位置
- **任务目录日志**：`./data_pipeline/training_data/{task_id}/data_pipeline.log` - 详细执行日志
- **数据库日志**：存储在 `data_pipeline_task_logs` 表 - 结构化查询和展示
- **系统日志**：`./logs/` 目录保留系统级日志（app.log、agent.log、vanna.log）

##### 日志记录机制
1. **任务目录日志记录器**：
   - 每个任务创建独立的 `TaskDir_{task_id}` 日志记录器
   - 直接写入任务目录的 `data_pipeline.log` 文件
   - 捕获所有详细的执行过程信息

2. **数据库日志记录器**：
   - 通过 `SimpleTaskManager.record_log()` 记录关键事件
   - 支持按级别、步骤、时间等条件查询
   - 用于API返回和Web UI展示

3. **SchemaWorkflowOrchestrator日志重定向**：
   - 将orchestrator的日志同时输出到任务目录文件
   - 确保所有子模块的日志都集中记录
   - 保持现有日志系统不变的同时增强功能

##### 日志内容示例
```
# 任务目录日志文件内容示例
2025-07-01 14:30:52 [INFO] TaskDir_task_20250701_143052: 任务目录日志初始化完成 - 任务ID: task_20250701_143052
2025-07-01 14:30:52 [INFO] TaskDir_task_20250701_143052: 任务参数: {"db_connection": "...", "business_context": "..."}
2025-07-01 14:30:53 [INFO] TaskDir_task_20250701_143052: [complete] 开始执行步骤: complete
2025-07-01 14:30:53 [INFO] DataPipelineOrchestrator: 开始执行完整工作流
2025-07-01 14:30:54 [INFO] DDLMDGenerator: 开始处理表: bss_business_day_data
```

#### 2.5 执行示例

```bash
# 1. API调用（完整工作流）
python data_pipeline/task_executor.py \
    --task-id "task_20250627_143052" \
    --execution-mode complete

# 2. API调用（单步执行DDL生成）
python data_pipeline/task_executor.py \
    --task-id "task_20250627_143052" \
    --execution-mode step \
    --step-name ddl_generation

# 3. API调用（单步执行Q&A生成）
python data_pipeline/task_executor.py \
    --task-id "task_20250627_143052" \
    --execution-mode step \
    --step-name qa_generation

# 4. API调用（单步执行SQL验证）
python data_pipeline/task_executor.py \
    --task-id "task_20250627_143052" \
    --execution-mode step \
    --step-name sql_validation

# 5. API调用（单步执行训练数据加载）
python data_pipeline/task_executor.py \
    --task-id "task_20250627_143052" \
    --execution-mode step \
    --step-name training_load
```

### 3. 分步执行使用流程

#### 场景1：分步执行，检查每步结果
```bash
# 1. 创建任务
curl -X POST /api/v0/data_pipeline/tasks \
  -d '{"task_type": "data_workflow", "parameters": {...}}'
# 返回: {"task_id": "task_20250627_143052"}

# 2. 执行DDL生成
curl -X POST /api/v0/data_pipeline/tasks/task_20250627_143052/execute \
  -d '{"step": "ddl_generation"}'
# 等待完成，检查结果

# 3. 检查DDL生成结果满意后，执行Q&A生成
curl -X POST /api/v0/data_pipeline/tasks/task_20250627_143052/execute \
  -d '{"step": "qa_generation"}'

# 4. 如果Q&A结果不满意，重新执行
curl -X POST /api/v0/data_pipeline/tasks/task_20250627_143052/execute \
  -d '{"step": "qa_generation", "clean_previous": true}'

# 5. 继续后续步骤
curl -X POST /api/v0/data_pipeline/tasks/task_20250627_143052/execute \
  -d '{"step": "sql_validation"}'

curl -X POST /api/v0/data_pipeline/tasks/task_20250627_143052/execute \
  -d '{"step": "training_load"}'
```

#### 场景2：一次性执行完整工作流
```bash
# 创建任务并立即执行完整工作流
curl -X POST /api/v0/data_pipeline/tasks/execute-complete \
  -d '{"task_type": "complete_workflow", "parameters": {...}}'
```

### 4. 前端轮询实现
```javascript
// 分步执行时的轮询
async function pollExecutionStatus(taskId, executionId) {
    const pollInterval = setInterval(async () => {
        const response = await fetch(`/api/v0/data_pipeline/tasks/${taskId}/executions`);
        const data = await response.json();
        
        const currentExecution = data.data.executions.find(e => e.execution_id === executionId);
        
        // 更新UI
        updateStepStatus(currentExecution.step, currentExecution.status);
        
        // 检查是否完成
        if (currentExecution.status === 'completed' || currentExecution.status === 'failed') {
            clearInterval(pollInterval);
            handleStepComplete(currentExecution);
        }
    }, 5000);
}

// 任务整体状态轮询
async function pollTaskStatus(taskId) {
    const pollInterval = setInterval(async () => {
        const response = await fetch(`/api/v0/data_pipeline/tasks/${taskId}`);
        const data = await response.json();
        
        // 更新各步骤状态
        updateAllStepsStatus(data.data.step_status);
        
        // 更新当前执行信息
        if (data.data.current_execution) {
            updateCurrentExecution(data.data.current_execution);
        }
        
        // 检查任务是否全部完成
        if (data.data.status === 'completed' || data.data.status === 'failed') {
            clearInterval(pollInterval);
            handleTaskComplete(data.data);
        }
    }, 5000);
}
```

## 任务配置文件格式

### task_config.json 示例
```json
{
  "task_id": "task_20250627_143052",
  "task_type": "complete_workflow",
  "created_at": "2025-06-27T14:30:52",
  "parameters": {
    "db_connection": {
      "host": "localhost",
      "port": 5432,
      "database": "highway_db",
      "user": "postgres",
      "password": "******"
    },
    "table_list": ["bss_business_day_data", "bss_car_day_count", ...],
    "business_context": "高速公路服务区管理系统",
    "output_dir": "./data_pipeline/training_data/task_20250627_143052",
    "execution_mode": "complete",
    "single_step": null,
    "llm_config": {
      "model": "qianwen",
      "temperature": 0.7
    }
  }
}
```

## 错误处理机制

### 1. API层错误处理
```python
try:
    task_id = create_task(request_data)
    return {"success": True, "task_id": task_id}
except ConcurrentTaskError:
    return {"success": False, "error": "已有任务正在执行"}, 409
except Exception as e:
    logger.error(f"任务创建失败: {str(e)}")
    return {"success": False, "error": "任务创建失败"}, 500
```

### 2. 执行流程中的错误处理
```python
try:
    # 执行任务
    report = await orchestrator.execute_complete_workflow()
    if self.db_logger:
        self.db_logger.update_status('completed')
except Exception as e:
    # 记录错误到日志和数据库
    self.logger.error(f"任务执行失败: {str(e)}", exc_info=True)
    if self.db_logger:
        self.db_logger.log('ERROR', str(e))
        self.db_logger.update_status('failed', error_message=str(e))
    raise
```

### 3. 僵尸任务检测
```python
# 在API启动时检查
def check_zombie_tasks():
    # 查找超过2小时仍在运行的任务
    query = """
    UPDATE data_pipeline_tasks 
    SET status = 'failed', 
        error_message = '任务超时，可能已停止运行'
    WHERE status = 'running' 
    AND started_at < NOW() - INTERVAL '2 hours'
    """
```

## 并发控制策略

### 单任务执行原则
- 同时只允许一个任务处于'running'状态
- 新任务提交时检查数据库，如有运行中任务则拒绝
- 前端显示当前运行任务信息，提示用户等待

### 任务锁实现
```python
# 使用数据库事务确保原子性
def acquire_task_lock(task_id):
    with db.transaction():
        # 检查是否有运行中的任务
        running_count = db.query(
            "SELECT COUNT(*) FROM data_pipeline_tasks WHERE status = 'running'"
        ).scalar()
        
        if running_count > 0:
            raise ConcurrentTaskError("已有任务正在执行")
            
        # 获取锁：更新状态为running
        db.execute(
            "UPDATE data_pipeline_tasks SET status = 'running', started_at = NOW() WHERE id = %s",
            [task_id]
        )
```

## Web UI模块设计

### 1. 任务管理页面
- **任务创建表单**：配置任务参数并提交
- **任务列表**：显示历史任务和状态
- **任务筛选**：按状态、时间等筛选任务

### 2. 任务详情页面
- **实时进度条**：显示当前执行进度
- **步骤状态**：各步骤的执行状态和耗时
- **实时日志**：滚动显示任务日志
- **文件管理**：列出生成的文件并提供下载

### 3. 日志查看器
- **日志级别筛选**：INFO/WARNING/ERROR
- **关键词搜索**：在日志中搜索特定内容
- **自动滚动**：新日志自动滚动到底部
- **日志导出**：下载完整日志文件

### 4. 文件管理器
- **文件列表**：显示所有生成的文件
- **批量下载**：打包下载所有文件
- **文件预览**：在线查看文本文件内容
- **文件统计**：显示文件大小和生成时间

## 技术实现要点

### 1. 数据库连接管理
- 复用现有的PostgreSQL连接配置
- 在独立脚本中建立独立的数据库连接
- 确保连接池的正确释放

### 2. 日志系统集成
- 复用现有的core.logging系统
- 在SchemaWorkflowOrchestrator中添加数据库日志写入
- 保持原有的文件日志不变

### 3. 文件路径管理
- 统一使用绝对路径避免路径混乱
- 确保时间戳目录的正确创建和权限
- 提供文件清理机制避免磁盘空间耗尽

### 4. 错误处理
- 完善的异常捕获和错误信息记录
- 优雅的错误恢复机制
- 清晰的错误信息展示给用户

## SchemaWorkflowOrchestrator集成细节

### 1. 主要修改点

由于直接调用schema_workflow.py，不需要额外的worker.py，主要修改集中在：

1. **命令行参数扩展**：添加`--task-id`和`--no-db-tracking`参数
2. **数据库记录器集成**：在SchemaWorkflowOrchestrator中集成进度记录功能
3. **各步骤进度更新**：在现有的执行步骤中添加进度更新调用

### 2. 进度更新实现

在每个执行步骤方法中添加进度更新：

```python
# _execute_step_1_ddl_md_generation
if self.db_logger:
    self.db_logger.update_progress(10, 'ddl_md_generation')
    self.db_logger.log('INFO', 'DDL/MD生成开始', 'ddl_md_generation')
    # ... 执行实际工作
    self.db_logger.update_progress(40, 'ddl_md_generation')
    
# _execute_step_2_question_sql_generation  
if self.db_logger:
    self.db_logger.update_progress(40, 'question_sql_generation')
    # ... 执行实际工作
    self.db_logger.update_progress(70, 'question_sql_generation')
    
# _execute_step_3_sql_validation
if self.db_logger:
    self.db_logger.update_progress(70, 'sql_validation')
    # ... 执行实际工作
    self.db_logger.update_progress(90, 'sql_validation')
    
# _execute_step_4_training_data_load
if self.db_logger:
    self.db_logger.update_progress(90, 'training_data_load')
    # ... 执行实际工作
    self.db_logger.update_progress(100, 'training_data_load')
```

### 3. 任务状态管理

在主执行流程中管理任务状态：

```python
async def execute_complete_workflow(self):
    # 开始时更新状态
    if self.db_logger:
        self.db_logger.update_status('running')
    
    try:
        # 执行各步骤...
        report = await self._generate_final_report()
        
        # 成功完成
        if self.db_logger:
            self.db_logger.update_status('completed')
            
    except Exception as e:
        # 失败处理
        if self.db_logger:
            self.db_logger.update_status('failed', str(e))
        raise
```

### 4. 输出目录管理

当通过API调用时，output_dir会被设置为任务特定的时间戳目录，确保所有输出文件都集中存储。

## API安全性考虑

### 1. 认证和授权
- 使用现有的API认证机制（如JWT）
- 检查用户权限，确保有执行数据生成的权限
- 记录操作者信息到created_by字段

### 2. 输入验证
```python
def validate_task_request(request_data):
    # 验证必填字段
    required_fields = ['task_type', 'parameters']
    for field in required_fields:
        if field not in request_data:
            raise ValueError(f"缺少必填字段: {field}")
    
    # 验证数据库连接参数
    db_params = request_data['parameters'].get('db_connection', {})
    if not all(k in db_params for k in ['host', 'port', 'database']):
        raise ValueError("数据库连接参数不完整")
        
    # 验证表列表
    table_list = request_data['parameters'].get('table_list', [])
    if not table_list:
        raise ValueError("表列表不能为空")
```

### 3. 路径安全
- 禁止路径遍历攻击
- 确保所有文件操作都在指定的任务目录内
- 使用os.path.normpath和验证路径前缀

## 性能优化建议

### 1. 数据库查询优化
- 使用批量插入日志，而非逐条插入
- 建立适当的索引加速查询
- 定期清理旧日志数据

### 2. 文件处理优化
- 大文件使用流式读写
- 压缩旧任务的输出文件
- 实现文件分片下载

### 3. 内存管理
- 在worker中及时释放大对象
- 使用生成器处理大数据集
- 监控内存使用情况

## 任务清理策略

### 1. 自动清理
```python
# 定期任务清理旧数据
def cleanup_old_tasks():
    # 清理30天前的任务
    cutoff_date = datetime.now() - timedelta(days=30)
    
    # 查询要清理的任务
    old_tasks = db.query("""
        SELECT id FROM data_pipeline_tasks 
        WHERE created_at < %s AND status IN ('completed', 'failed')
    """, [cutoff_date])
    
    for task in old_tasks:
        # 删除文件目录
        task_dir = os.path.join('./data_pipeline/training_data/', task.id)
        if os.path.exists(task_dir):
            shutil.rmtree(task_dir)
            
        # 删除数据库记录
        db.execute("DELETE FROM data_pipeline_tasks WHERE id = %s", [task.id])
```

### 2. 手动清理API
```
DELETE /api/v0/data_pipeline/tasks/{task_id}
```

## 监控指标

### 1. 任务指标
- 任务执行时间统计
- 任务成功率
- 各步骤平均耗时

### 2. 系统指标
- CPU和内存使用率
- 磁盘空间占用
- 数据库连接池状态

### 3. 告警规则
- 任务执行超时告警
- 磁盘空间不足告警
- 连续失败任务告警

## 部署和运维

### 1. 依赖要求
- 现有的Data Pipeline依赖不变
- 确保subprocess能够正确启动Python脚本
- 数据库表的创建和权限配置
- Windows系统需要注意Python路径和脚本执行权限

### 2. 初始化脚本
```sql
-- 创建必要的数据库表
CREATE TABLE IF NOT EXISTS data_pipeline_tasks (...);
CREATE TABLE IF NOT EXISTS data_pipeline_task_logs (...);
CREATE TABLE IF NOT EXISTS data_pipeline_task_outputs (...);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_tasks_status ON data_pipeline_tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON data_pipeline_tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_logs_task_id ON data_pipeline_task_logs(task_id);

-- 创建清理函数
CREATE OR REPLACE FUNCTION cleanup_old_tasks()...
```

### 3. 运维检查清单
- [ ] 确保training_data目录有足够的磁盘空间
- [ ] 定期检查是否有僵尸任务
- [ ] 监控任务执行时间趋势
- [ ] 备份重要的训练数据
- [ ] 定期执行任务清理

### 4. 故障排查指南
1. **任务卡住**：检查数据库中任务状态，查看任务目录下的日志文件
2. **任务失败**：
   - 查看数据库中的 error_message 字段
   - 在 data_pipeline.log 中搜索 [ERROR] 级别日志
   - 检查数据库连接和LLM服务状态
3. **磁盘满**：执行清理脚本，调整保留策略
4. **性能下降**：检查数据库索引，清理历史日志

## 总结

本设计采用了任务与API解耦的架构，通过数据库作为通信桥梁，实现了长时间任务的后台执行和实时进度追踪。设计简洁实用，充分复用了现有的代码和基础设施，能够满足Web UI调用Data Pipeline的各种需求。

本概要设计文档详细描述了Data Pipeline API的完整实现方案：

1. **核心设计特点**：
   - 任务ID即时间戳的简洁设计，无需额外的ID生成器
   - API与执行脚本完全解耦，支持服务重启后任务继续执行
   - 基于数据库的状态管理和进度追踪，替代复杂的消息队列
   - 时间戳目录的统一文件管理，所有输出集中存储

2. **技术实现亮点**：
   - 使用subprocess实现真正的后台执行，不阻塞HTTP请求
   - 粗粒度进度追踪（步骤级），避免过度复杂
   - 完善的错误处理和恢复机制，包括僵尸任务检测
   - 单任务执行保证系统稳定性，避免资源竞争

3. **实用性考虑**：
   - 充分复用现有的SchemaWorkflowOrchestrator代码
   - 支持服务重启后的状态恢复，任务不会丢失
   - 提供完整的文件管理和下载功能
   - 包含监控、清理和运维策略，便于长期维护

4. **Web UI友好设计**：
   - 清晰的RESTful API设计，易于前端集成
   - 实时进度查询，支持轮询机制
   - 完整的日志查看和文件下载功能
   - 直观的任务状态展示

5. **关键实现变更**：
   - 直接调用schema_workflow.py，无需额外的worker.py
   - 手工执行时自动生成manual_前缀的task_id
   - 支持--no-db-tracking参数禁用数据库追踪
   - 只需修改schema_workflow.py一个文件即可实现所有功能
   - 使用环境变量方案统一管理data_pipeline模块的日志路径
   - 所有任务日志都写入各自的任务目录，不再使用./logs/data_pipeline.log
   - 禁用日志轮转（rotation），因为每个任务的日志是独立的

本方案在保持简单实用的同时，提供了完整的功能支持，能够很好地满足Data Pipeline Web UI集成的需求。