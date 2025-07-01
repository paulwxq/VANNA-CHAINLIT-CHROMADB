# Data Pipeline API 详细设计文档

## 项目概述

本文档是基于概要设计文档和现有代码结构，对Data Pipeline API系统的详细技术实现设计。该系统将为Web UI提供完整的数据管道调度、执行监控和日志管理功能。

## 核心需求分析

### 1. 业务需求
- **API调度执行**：通过REST API调度执行 `./data_pipeline/schema_workflow.py`
- **执行监控**：实时查看任务执行状态和进度
- **日志集中管理**：所有日志写入任务特定的子目录
- **步骤控制**：支持通过参数控制执行特定步骤
- **数据库日志记录**：关键步骤信息写入PostgreSQL数据库

### 2. 技术约束
- 复用现有的 `SchemaWorkflowOrchestrator` 架构
- 集成现有的日志系统 (`core.logging`)
- 使用现有的Flask应用 (`citu_app.py`) 作为API承载
- 保持与现有数据库配置的兼容性

## 系统架构设计

### 1. 整体架构

```
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   Web Frontend      │    │   Flask API         │    │  Schema Workflow    │
│                     │ ─→ │   (citu_app.py)     │ ─→ │  (subprocess)       │
│ - 任务创建表单      │    │ - 任务调度          │    │ - DDL生成           │
│ - 进度监控界面      │    │ - 状态查询          │    │ - Q&A生成           │
│ - 日志查看器        │    │ - 日志API           │    │ - SQL验证           │
│ - 文件管理器        │    │ - 文件管理          │    │ - 训练数据加载      │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
                                    │                           │
                                    ▼                           ▼
                           ┌─────────────────────┐    ┌─────────────────────┐
                           │  PostgreSQL DB      │    │  File System        │
                           │ - 任务状态表        │    │ - 任务目录          │
                           │ - 日志记录表        │    │ - 输出文件          │
                           │ - 文件输出表        │    │ - 日志文件          │
                           └─────────────────────┘    └─────────────────────┘
```

### 2. 进程分离设计

```
HTTP Request ──┐
               │
               ▼
        ┌─────────────┐    subprocess.Popen    ┌──────────────────┐
        │ Flask API   │ ──────────────────────→ │ task_executor.py │
        │ Process     │                        │ Process          │
        │             │    Database Bridge     │                  │
        │ - 任务调度  │ ←─────────────────────→ │ - SimpleWorkflow │
        │ - 状态查询  │                        │ - 进度更新       │
        │ - 文件管理  │                        │ - 双日志记录     │
        └─────────────┘                        └──────────────────┘
               │                                        │
               ▼                                        ▼
        立即返回task_id                     独立执行工作流+日志到任务目录
```

## 数据库设计详细说明

### 1. 表结构设计

#### 任务主表 (data_pipeline_tasks)
```sql
CREATE TABLE data_pipeline_tasks (
    -- 主键：时间戳格式的任务ID
    id VARCHAR(32) PRIMARY KEY,                    -- 'task_20250627_143052'
    
    -- 任务基本信息
    task_type VARCHAR(50) NOT NULL DEFAULT 'data_workflow',
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending/in_progress/partial_completed/completed/failed
    
    -- 配置和结果（JSON格式）
    parameters JSONB NOT NULL,                     -- 任务配置参数
    result JSONB,                                  -- 最终执行结果
    
    -- 错误处理
    error_message TEXT,                            -- 错误详细信息
    
    -- 步骤状态跟踪
    step_status JSONB DEFAULT '{                   -- 各步骤状态
        "ddl_generation": "pending",
        "qa_generation": "pending", 
        "sql_validation": "pending",
        "training_load": "pending"
    }',
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- 创建者信息
    created_by VARCHAR(50) DEFAULT 'api',          -- 'api', 'manual', 'system'
    
    -- 输出目录
    output_directory TEXT,                         -- 任务输出目录路径
    
    -- 索引字段
    db_name VARCHAR(100),                          -- 数据库名称（便于筛选）
    business_context TEXT                          -- 业务上下文（便于搜索）
);

-- 创建索引
CREATE INDEX idx_tasks_status ON data_pipeline_tasks(status);
CREATE INDEX idx_tasks_created_at ON data_pipeline_tasks(created_at DESC);
CREATE INDEX idx_tasks_db_name ON data_pipeline_tasks(db_name);
CREATE INDEX idx_tasks_created_by ON data_pipeline_tasks(created_by);
```

#### 任务执行记录表 (data_pipeline_task_executions)
```sql
CREATE TABLE data_pipeline_task_executions (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(32) REFERENCES data_pipeline_tasks(id) ON DELETE CASCADE,
    execution_step VARCHAR(50) NOT NULL,          -- 'ddl_generation', 'qa_generation', 'sql_validation', 'training_load', 'complete'
    status VARCHAR(20) NOT NULL,                  -- 'running', 'completed', 'failed'
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    execution_result JSONB,                       -- 步骤执行结果
    execution_id VARCHAR(100) UNIQUE,             -- {task_id}_step_{step_name}_exec_{timestamp}
    force_executed BOOLEAN DEFAULT FALSE,         -- 是否强制执行
    files_cleaned BOOLEAN DEFAULT FALSE,          -- 是否清理了旧文件
    duration_seconds INTEGER                      -- 执行时长（秒）
);

-- 创建索引
CREATE INDEX idx_executions_task_id ON data_pipeline_task_executions(task_id);
CREATE INDEX idx_executions_step ON data_pipeline_task_executions(execution_step);
CREATE INDEX idx_executions_status ON data_pipeline_task_executions(status);
CREATE INDEX idx_executions_started_at ON data_pipeline_task_executions(started_at DESC);
```

#### 任务日志表 (data_pipeline_task_logs)
```sql
CREATE TABLE data_pipeline_task_logs (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(32) REFERENCES data_pipeline_tasks(id) ON DELETE CASCADE,
    execution_id VARCHAR(100) REFERENCES data_pipeline_task_executions(execution_id),
    
    -- 日志内容
    log_level VARCHAR(10) NOT NULL,               -- 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    message TEXT NOT NULL,                        -- 日志消息内容
    
    -- 上下文信息
    step_name VARCHAR(50),                        -- 执行步骤名称
    module_name VARCHAR(100),                     -- 模块名称
    function_name VARCHAR(100),                   -- 函数名称
    
    -- 时间戳
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 额外信息（JSON格式）
    extra_data JSONB DEFAULT '{}'                 -- 额外的结构化信息
);

-- 创建索引
CREATE INDEX idx_logs_task_id ON data_pipeline_task_logs(task_id);
CREATE INDEX idx_logs_execution_id ON data_pipeline_task_logs(execution_id);
CREATE INDEX idx_logs_timestamp ON data_pipeline_task_logs(timestamp DESC);
CREATE INDEX idx_logs_level ON data_pipeline_task_logs(log_level);
CREATE INDEX idx_logs_step ON data_pipeline_task_logs(step_name);
```

#### 任务输出文件表 (data_pipeline_task_outputs)
```sql
CREATE TABLE data_pipeline_task_outputs (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(32) REFERENCES data_pipeline_tasks(id) ON DELETE CASCADE,
    execution_id VARCHAR(100) REFERENCES data_pipeline_task_executions(execution_id),
    
    -- 文件信息
    file_type VARCHAR(50) NOT NULL,               -- 'ddl', 'md', 'json', 'log', 'report'
    file_name VARCHAR(255) NOT NULL,              -- 文件名
    file_path TEXT NOT NULL,                      -- 相对路径
    file_size BIGINT DEFAULT 0,                   -- 文件大小（字节）
    
    -- 文件内容摘要
    content_hash VARCHAR(64),                     -- 文件内容hash
    description TEXT,                             -- 文件描述
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 状态
    is_primary BOOLEAN DEFAULT FALSE,             -- 是否为主要输出文件
    is_downloadable BOOLEAN DEFAULT TRUE          -- 是否可下载
);

-- 创建索引
CREATE INDEX idx_outputs_task_id ON data_pipeline_task_outputs(task_id);
CREATE INDEX idx_outputs_execution_id ON data_pipeline_task_outputs(execution_id);
CREATE INDEX idx_outputs_file_type ON data_pipeline_task_outputs(file_type);
CREATE INDEX idx_outputs_primary ON data_pipeline_task_outputs(is_primary) WHERE is_primary = TRUE;
```

### 2. 数据库操作类设计

```python
# data_pipeline/api/simple_db_manager.py
class SimpleTaskManager:
    """简化的数据管道任务数据库管理器"""
    
    def __init__(self):
        self.logger = get_data_pipeline_logger("SimpleTaskManager")
        self._connection = None
        self._connect_to_pgvector()
    
    def create_task(self, db_connection: str, table_list_file: str, 
                   business_context: str, **kwargs) -> str:
        """创建新任务记录，返回task_id"""
        
    def update_task_status(self, task_id: str, status: str, 
                          error_message: str = None) -> bool:
        """更新任务状态"""
        
    def update_step_status(self, task_id: str, step_name: str, 
                          status: str) -> bool:
        """更新步骤状态"""
        
    def get_task(self, task_id: str) -> dict:
        """获取任务详情"""
        
    def get_tasks_list(self, limit: int = 50, status: str = None) -> list:
        """获取任务列表"""
        
    def create_execution(self, task_id: str, step_name: str) -> str:
        """创建执行记录，返回execution_id"""
        
    def complete_execution(self, execution_id: str, status: str, 
                          error_message: str = None) -> bool:
        """完成执行记录"""
        
    def record_log(self, task_id: str, level: str, message: str, 
                  execution_id: str = None, step_name: str = None) -> bool:
        """记录任务日志"""
        
    def get_task_logs(self, task_id: str, limit: int = 100) -> list:
        """获取任务日志"""
        
    def get_task_outputs(self, task_id: str) -> list:
        """获取任务输出文件列表"""
```

## API接口详细设计

### 1. API路由设计

所有API都在 `citu_app.py` 中实现，路由前缀为 `/api/v0/data_pipeline/`

```python
# citu_app.py 中添加的路由
@app.flask_app.route('/api/v0/data_pipeline/tasks', methods=['POST'])
def create_data_pipeline_task():
    """创建数据管道任务"""

@app.flask_app.route('/api/v0/data_pipeline/tasks', methods=['GET'])
def get_data_pipeline_tasks():
    """获取任务列表"""

@app.flask_app.route('/api/v0/data_pipeline/tasks/<task_id>', methods=['GET'])
def get_data_pipeline_task(task_id):
    """获取单个任务详情"""

@app.flask_app.route('/api/v0/data_pipeline/tasks/active', methods=['GET'])
def get_active_data_pipeline_task():
    """获取当前活跃任务"""

@app.flask_app.route('/api/v0/data_pipeline/tasks/<task_id>/logs', methods=['GET'])
def get_data_pipeline_task_logs(task_id):
    """获取任务日志"""

@app.flask_app.route('/api/v0/data_pipeline/tasks/<task_id>/files', methods=['GET'])
def get_data_pipeline_task_files(task_id):
    """获取任务输出文件列表"""

@app.flask_app.route('/api/v0/data_pipeline/tasks/<task_id>/files/download/<filename>', methods=['GET'])
def download_data_pipeline_task_file(task_id, filename):
    """下载任务输出文件"""

@app.flask_app.route('/api/v0/data_pipeline/tasks/<task_id>', methods=['DELETE'])
def delete_data_pipeline_task(task_id):
    """删除任务（清理）"""
```

### 2. API接口实现详情

#### 2.1 创建任务接口

```python
@app.flask_app.route('/api/v0/data_pipeline/tasks', methods=['POST'])
def create_data_pipeline_task():
    """
    创建数据管道任务
    
    Request Body:
    {
        "task_type": "complete_workflow",
        "parameters": {
            "db_connection": "postgresql://...",
            "table_list_file": "tables.txt", 
            "business_context": "业务描述",
            "output_dir": "./data_pipeline/training_data/",
            "execution_mode": "complete",
            "single_step": null
        }
    }
    """
    try:
        # 1. 参数验证
        req_data = request.get_json()
        if not req_data:
            return jsonify(bad_request_response("请求体不能为空")), 400
            
        task_type = req_data.get('task_type', 'complete_workflow')
        parameters = req_data.get('parameters', {})
        
        # 验证必需参数
        required_params = ['db_connection', 'table_list_file', 'business_context']
        missing_params = [p for p in required_params if not parameters.get(p)]
        if missing_params:
            return jsonify(bad_request_response(
                f"缺少必需参数: {', '.join(missing_params)}",
                missing_params=missing_params
            )), 400
        
        # 验证执行模式参数
        execution_mode = parameters.get('execution_mode', 'complete')
        single_step = parameters.get('single_step')
        
        if execution_mode not in ['complete', 'single']:
            return jsonify(bad_request_response("execution_mode必须是complete或single")), 400
            
        if execution_mode == 'single':
            if not single_step or single_step not in [1, 2, 3, 4]:
                return jsonify(bad_request_response("单步模式下single_step必须是1、2、3、4中的一个")), 400
        elif execution_mode == 'complete' and single_step:
            return jsonify(bad_request_response("完整模式下不应提供single_step参数")), 400
        
        # 2. 并发检查 - 简化版本（依赖SimpleWorkflowManager）
        workflow_manager = SimpleWorkflowManager()
        
        # 3. 创建任务记录（返回task_id）
        task_id = workflow_manager.create_task(
            db_connection=parameters['db_connection'],
            table_list_file=parameters['table_list_file'],
            business_context=parameters['business_context'],
            **{k: v for k, v in parameters.items() 
               if k not in ['db_connection', 'table_list_file', 'business_context']}
        )
        
        # 4. 启动后台进程
        import subprocess
        import sys
        from pathlib import Path
        
        # 构建任务执行器命令
        cmd_args = [
            sys.executable, 
            str(Path(__file__).parent / "data_pipeline" / "task_executor.py"),
            '--task-id', task_id,
            '--execution-mode', 'complete'
        ]
        
        # 如果是单步执行，添加步骤参数
        if execution_mode == 'step' and single_step:
            cmd_args.extend(['--step-name', f'step_{single_step}'])
        
        # 启动后台进程
        try:
            process = subprocess.Popen(
                cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=Path(__file__).parent
            )
            logger.info(f"启动任务进程: PID={process.pid}, task_id={task_id}")
        except Exception as e:
            # 清理任务记录
            workflow_manager.cleanup()
            return jsonify(internal_error_response(f"启动后台进程失败: {str(e)}")), 500
        
        # 5. 返回成功响应
        
        # 启动进程
        try:
            log_file_path = os.path.join(task_dir, 'data_pipeline.log')
            process = subprocess.Popen(
                cmd_args,
                stdout=open(log_file_path, 'w', encoding='utf-8'),
                stderr=subprocess.STDOUT,
                cwd=os.getcwd(),
                start_new_session=True
            )
            
            logger.info(f"启动后台任务: {task_id}, PID: {process.pid}")
            
        except Exception as e:
            # 清理资源
            task_manager.update_task_status(task_id, 'failed', error_message=f"启动进程失败: {str(e)}")
            shutil.rmtree(task_dir, ignore_errors=True)
            return jsonify(internal_error_response(f"启动任务失败: {str(e)}")), 500
        
        # 9. 返回成功响应
        return jsonify(success_response(
            message="任务创建成功",
            data={
                "task_id": task_id,
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "output_directory": task_dir
            }
        )), 201
        
    except Exception as e:
        logger.exception(f"创建任务失败: {str(e)}")
        return jsonify(internal_error_response("创建任务失败")), 500
```

#### 2.2 获取任务详情接口

```python
@app.flask_app.route('/api/v0/data_pipeline/tasks/<task_id>', methods=['GET'])
def get_data_pipeline_task(task_id):
    """
    获取单个任务详情
    
    Response:
    {
        "success": true,
        "data": {
            "task_id": "task_20250627_143052",
            "task_type": "complete_workflow",
            "status": "running",
            "progress": 45,
            "current_step": "question_sql_generation",
            "parameters": {...},
            "result": {...},
            "error_message": null,
            "step_details": [...],
            "created_at": "2025-06-27T14:30:52",
            "started_at": "2025-06-27T14:30:53",
            "completed_at": null,
            "duration": 125.5,
            "output_directory": "./data_pipeline/training_data/task_20250627_143052"
        }
    }
    """
    try:
        # 参数验证
        if not task_id or not task_id.startswith('task_'):
            return jsonify(bad_request_response("无效的任务ID格式")), 400
        
        workflow_manager = SimpleWorkflowManager()
        task_data = workflow_manager.get_task_status(task_id)
        
        if not task_data:
            return jsonify(not_found_response(f"任务不存在: {task_id}")), 404
        
        # 计算执行时长
        duration = None
        if task_data.get('started_at'):
            end_time = task_data.get('completed_at') or datetime.now()
            start_time = task_data['started_at']
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time)
            if isinstance(end_time, str):
                end_time = datetime.fromisoformat(end_time)
            duration = (end_time - start_time).total_seconds()
        
        # 获取步骤详情
        step_details = []
        step_stats = task_data.get('step_stats', {})
        
        for step_name in ['ddl_md_generation', 'question_sql_generation', 'sql_validation', 'training_data_load']:
            step_info = step_stats.get(step_name, {})
            step_details.append({
                "step": step_name,
                "status": step_info.get('status', 'pending'),
                "started_at": step_info.get('started_at'),
                "completed_at": step_info.get('completed_at'),
                "duration": step_info.get('duration'),
                "error_message": step_info.get('error_message')
            })
        
        response_data = {
            **task_data,
            "duration": duration,
            "step_details": step_details
        }
        
        return jsonify(success_response("获取任务详情成功", data=response_data))
        
    except Exception as e:
        logger.exception(f"获取任务详情失败: {str(e)}")
        return jsonify(internal_error_response("获取任务详情失败")), 500
```

## Schema Workflow 集成设计

### 1. 命令行参数扩展

在现有的 `setup_argument_parser()` 函数中添加新参数：

```python
def setup_argument_parser():
    """设置命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="Schema工作流编排器 - 端到端的Schema处理流程",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # ... 现有参数 ...
    
    # 新增API集成参数
    parser.add_argument(
        "--task-id",
        required=False,
        help="任务ID（API调用时提供，手动执行时自动生成）"
    )
    
    parser.add_argument(
        "--no-db-tracking",
        action="store_true",
        help="禁用数据库任务追踪（不记录到任务表）"
    )
    
    # 新增执行模式参数
    parser.add_argument(
        "--execution-mode",
        choices=['complete', 'single'],
        default='complete',
        help="执行模式：complete=完整工作流，single=单步执行"
    )
    
    parser.add_argument(
        "--single-step",
        type=int,
        choices=[1, 2, 3, 4],
        help="单步执行时指定步骤号（1=DDL生成，2=Q&A生成，3=SQL验证，4=训练数据加载）"
    )
    
    return parser
```

### 2. SchemaWorkflowOrchestrator 类修改

```python
class SchemaWorkflowOrchestrator:
    """端到端的Schema处理编排器 - 完整工作流程"""
    
    def __init__(self, 
                 db_connection: str,
                 table_list_file: str, 
                 business_context: str,
                 output_dir: str = None,
                 enable_sql_validation: bool = True,
                 enable_llm_repair: bool = True,
                 modify_original_file: bool = True,
                 enable_training_data_load: bool = True,
                 # 新增参数
                 task_id: str = None,
                 db_logger: 'DatabaseProgressLogger' = None,
                 execution_mode: str = 'complete',
                 single_step: int = None):
        """
        初始化Schema工作流编排器
        
        Args:
            # ... 现有参数 ...
            task_id: 任务ID（可选）
            db_logger: 数据库进度记录器（可选）
            execution_mode: 执行模式 ('complete' 或 'single')
            single_step: 单步执行时的步骤号 (1-4)
        """
        # ... 现有初始化代码 ...
        
        # 新增属性
        self.task_id = task_id
        self.db_logger = db_logger
        self.execution_mode = execution_mode
        self.single_step = single_step
        
        # 如果提供了task_id但没有db_logger，尝试创建一个
        if self.task_id and not self.db_logger:
            try:
                self.db_logger = self._create_db_logger()
            except Exception as e:
                self.logger.warning(f"无法创建数据库记录器: {e}")
    
    def _create_db_logger(self):
        """创建数据库进度记录器"""
        from data_pipeline.api.database_logger import DatabaseProgressLogger
        return DatabaseProgressLogger(self.task_id, self.db_connection)
    
    def _should_execute_step(self, step_number: int) -> bool:
        """判断是否应该执行指定步骤"""
        if self.execution_mode == 'complete':
            # 完整模式：执行所有步骤
            return True
        elif self.execution_mode == 'single':
            # 单步模式：只执行指定的步骤
            return step_number == self.single_step
        else:
            return False
    
    async def execute_complete_workflow(self) -> Dict[str, Any]:
        """执行完整的Schema处理工作流程"""
        self.workflow_state["start_time"] = time.time()
        
        # 更新数据库状态为running
        if self.db_logger:
            self.db_logger.update_task_status('running')
            self.db_logger.add_log('INFO', f'开始执行Schema工作流编排', 'workflow_start')
        
        self.logger.info("🚀 开始执行Schema工作流编排")
        # ... 现有日志 ...
        
        try:
            # 步骤1: 生成DDL和MD文件
            if self._should_execute_step(1):
                await self._execute_step_1_ddl_md_generation()
            
            # 步骤2: 生成Question-SQL对
            if self._should_execute_step(2):
                await self._execute_step_2_question_sql_generation()
            
            # 步骤3: 验证和修正SQL
            if self._should_execute_step(3):
                await self._execute_step_3_sql_validation()
            
            # 步骤4: 训练数据加载
            if self._should_execute_step(4):
                await self._execute_step_4_training_data_load()
            
            # 设置结束时间
            self.workflow_state["end_time"] = time.time()
            
            # 生成最终报告
            final_report = await self._generate_final_report()
            
            # 更新数据库状态为completed
            if self.db_logger:
                self.db_logger.update_task_status('completed', result=final_report)
                self.db_logger.add_log('INFO', '工作流执行完成', 'workflow_complete')
            
            self.logger.info("✅ Schema工作流编排完成")
            return final_report
            
        except Exception as e:
            self.workflow_state["end_time"] = time.time()
            
            # 更新数据库状态为failed
            if self.db_logger:
                self.db_logger.update_task_status('failed', error_message=str(e))
                self.db_logger.add_log('ERROR', f'工作流执行失败: {str(e)}', 'workflow_error')
            
            self.logger.exception(f"❌ 工作流程执行失败: {str(e)}")
            error_report = await self._generate_error_report(e)
            return error_report
    
    async def _execute_step_1_ddl_md_generation(self):
        """步骤1: 生成DDL和MD文件"""
        self.workflow_state["current_step"] = "ddl_md_generation"
        
        # 更新数据库进度
        if self.db_logger:
            self.db_logger.update_progress(10, 'ddl_md_generation')
            self.db_logger.add_log('INFO', 'DDL/MD生成开始', 'ddl_md_generation')
        
        # ... 现有执行代码 ...
        
        try:
            # ... DDL/MD生成逻辑 ...
            
            # 更新进度
            if self.db_logger:
                self.db_logger.update_progress(40, 'ddl_md_generation')
                self.db_logger.add_log('INFO', f'DDL/MD生成完成: 成功处理 {processed_tables} 个表', 'ddl_md_generation')
            
        except Exception as e:
            if self.db_logger:
                self.db_logger.add_log('ERROR', f'DDL/MD生成失败: {str(e)}', 'ddl_md_generation')
            raise
    
    # 类似地修改其他步骤方法...
```

### 3. 数据库进度记录器

```python
# data_pipeline/api/database_logger.py
class DatabaseProgressLogger:
    """数据库进度记录器"""
    
    def __init__(self, task_id: str, db_connection_string: str):
        self.task_id = task_id
        self.task_manager = DataPipelineTaskManager(db_connection_string)
        self.logger = get_data_pipeline_logger("DatabaseLogger")
    
    def update_task_status(self, status: str, current_step: str = None, 
                          error_message: str = None, result: dict = None):
        """更新任务状态"""
        try:
            success = self.task_manager.update_task_status(
                self.task_id, status, current_step, error_message
            )
            if result and status == 'completed':
                self.task_manager.update_task_result(self.task_id, result)
            return success
        except Exception as e:
            self.logger.warning(f"更新任务状态失败: {e}")
            return False
    
    def update_progress(self, progress: int, current_step: str = None):
        """更新任务进度"""
        try:
            return self.task_manager.update_task_progress(
                self.task_id, progress, current_step
            )
        except Exception as e:
            self.logger.warning(f"更新任务进度失败: {e}")
            return False
    
    def add_log(self, level: str, message: str, step_name: str = None, 
               extra_data: dict = None):
        """添加任务日志"""
        try:
            return self.task_manager.add_task_log(
                self.task_id, level, message, step_name, extra_data
            )
        except Exception as e:
            self.logger.warning(f"添加任务日志失败: {e}")
            return False
```

## 日志系统集成设计

### 1. 日志路径管理

修改 `core/logging/log_manager.py` 以支持任务特定的日志目录：

```python
def _create_file_handler(self, file_config: dict, module: str) -> logging.Handler:
    """创建文件处理器"""
    
    # 对于data_pipeline模块，检查是否有任务特定的日志目录
    if module == 'data_pipeline' and 'DATA_PIPELINE_LOG_DIR' in os.environ:
        log_file = Path(os.environ['DATA_PIPELINE_LOG_DIR']) / 'data_pipeline.log'
        # 禁用轮转，因为每个任务的日志是独立的
        file_config = file_config.copy()
        file_config['enable_rotation'] = False
    else:
        log_file = self.base_log_dir / file_config.get('filename', f'{module}.log')
    
    # 确保日志目录存在
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # ... 其余代码保持不变 ...
```

### 2. 任务日志初始化

在 `schema_workflow.py` 的 `main()` 函数中：

```python
async def main():
    """命令行入口点"""
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # 初始化变量
    task_id = None
    db_logger = None
    
    # 如果不禁用数据库追踪
    if not args.no_db_tracking:
        # 如果没有task_id，自动生成
        if not args.task_id:
            from datetime import datetime
            args.task_id = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.info(f"📝 自动生成任务ID: {args.task_id}")
        
        task_id = args.task_id
        
        # 确定任务目录
        if task_id.startswith('task_'):
            # API调用的任务，输出目录已经是任务特定的
            task_dir = args.output_dir
        else:
            # 手动执行的任务，创建任务特定目录
            task_dir = os.path.join(args.output_dir, task_id)
            os.makedirs(task_dir, exist_ok=True)
            args.output_dir = task_dir
        
        # 设置环境变量，让日志系统知道当前的任务目录
        os.environ['DATA_PIPELINE_LOG_DIR'] = task_dir
        
        # 重新初始化日志系统
        from core.logging import initialize_logging
        initialize_logging()
        
        try:
            # 创建任务记录（如果是手动执行）
            if task_id.startswith('manual_'):
                task_manager = DataPipelineTaskManager(args.db_connection)
                task_manager.create_task(
                    task_id=task_id,
                    task_type='complete_workflow',
                    parameters={
                        'db_connection': args.db_connection,
                        'table_list': args.table_list,
                        'business_context': args.business_context,
                        'output_dir': args.output_dir,
                        # ... 其他参数
                    },
                    created_by='manual'
                )
            
            # 初始化数据库记录器
            db_logger = DatabaseProgressLogger(task_id, args.db_connection)
            logger.info(f"✅ 已启用数据库任务追踪: {task_id}")
            
        except Exception as e:
            logger.warning(f"⚠️ 无法初始化任务追踪: {e}")
            db_logger = None
    else:
        logger.info("ℹ️ 已禁用数据库任务追踪")
    
    # 参数验证：单步模式必须提供步骤号
    if args.execution_mode == 'single' and not args.single_step:
        logger.error("单步模式下必须提供 --single-step 参数")
        sys.exit(1)
    
    # 创建编排器，传入新参数
    orchestrator = SchemaWorkflowOrchestrator(
        db_connection=args.db_connection,
        table_list_file=args.table_list,
        business_context=args.business_context,
        output_dir=args.output_dir,
        enable_sql_validation=not args.skip_validation,
        enable_llm_repair=not args.disable_llm_repair,
        modify_original_file=not args.no_modify_file,
        enable_training_data_load=not args.skip_training_load,
        task_id=task_id,
        db_logger=db_logger,
        execution_mode=args.execution_mode,
        single_step=args.single_step
    )
    
    # 执行工作流
    report = await orchestrator.execute_complete_workflow()
    
    # ... 其余代码保持不变 ...
```

## 错误处理和监控

### 1. 僵尸任务检测

```python
# data_pipeline/api/task_monitor.py
class TaskMonitor:
    """任务监控器"""
    
    def __init__(self, db_connection_string: str):
        self.task_manager = DataPipelineTaskManager(db_connection_string)
        self.logger = get_data_pipeline_logger("TaskMonitor")
    
    def check_zombie_tasks(self, timeout_hours: int = 2):
        """检查僵尸任务"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=timeout_hours)
            
            # 查找超时的运行中任务
            zombie_tasks = self.task_manager.get_zombie_tasks(cutoff_time)
            
            for task in zombie_tasks:
                task_id = task['id']
                self.logger.warning(f"发现僵尸任务: {task_id}")
                
                # 标记为失败
                self.task_manager.update_task_status(
                    task_id, 
                    'failed', 
                    error_message=f"任务超时（超过{timeout_hours}小时），可能已停止运行"
                )
                
                # 记录日志
                self.task_manager.add_task_log(
                    task_id, 
                    'ERROR', 
                    f"任务被标记为僵尸任务，执行时间超过{timeout_hours}小时", 
                    'system_check'
                )
        
        except Exception as e:
            self.logger.error(f"检查僵尸任务失败: {e}")

# 在citu_app.py中添加定期检查
import threading
import time

def start_task_monitor():
    """启动任务监控器"""
    def monitor_loop():
        monitor = TaskMonitor(app_config.PGVECTOR_CONFIG)
        while True:
            try:
                monitor.check_zombie_tasks()
                time.sleep(300)  # 每5分钟检查一次
            except Exception as e:
                logger.error(f"任务监控异常: {e}")
                time.sleep(60)  # 出错时等待1分钟再重试
    
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()
    logger.info("任务监控器已启动")

# 在应用启动时调用
if __name__ == '__main__':
    start_task_monitor()
    app.run()
```

### 2. 文件输出管理

```python
# data_pipeline/api/file_manager.py
class TaskFileManager:
    """任务文件管理器"""
    
    def __init__(self, task_id: str, output_dir: str, db_connection_string: str):
        self.task_id = task_id
        self.output_dir = Path(output_dir)
        self.task_manager = DataPipelineTaskManager(db_connection_string)
        self.logger = get_data_pipeline_logger("FileManager")
    
    def scan_and_register_files(self):
        """扫描并注册输出文件"""
        try:
            if not self.output_dir.exists():
                return
            
            # 文件类型映射
            file_type_mapping = {
                '.ddl': 'ddl',
                '.md': 'md', 
                '.json': 'json',
                '.log': 'log',
                '.txt': 'txt'
            }
            
            for file_path in self.output_dir.iterdir():
                if file_path.is_file():
                    file_ext = file_path.suffix.lower()
                    file_type = file_type_mapping.get(file_ext, 'other')
                    file_size = file_path.stat().st_size
                    
                    # 判断是否为主要输出文件
                    is_primary = (
                        file_path.name.endswith('_pair.json') or
                        file_path.name == 'metadata.txt' or
                        file_path.name.endswith('_summary.log')
                    )
                    
                    # 注册文件
                    self.task_manager.register_output_file(
                        task_id=self.task_id,
                        file_type=file_type,
                        file_name=file_path.name,
                        file_path=str(file_path.relative_to(self.output_dir)),
                        file_size=file_size,
                        is_primary=is_primary
                    )
        
        except Exception as e:
            self.logger.error(f"扫描文件失败: {e}")
    
    def cleanup_task_files(self):
        """清理任务文件"""
        try:
            if self.output_dir.exists():
                shutil.rmtree(self.output_dir)
                self.logger.info(f"已清理任务文件: {self.output_dir}")
        except Exception as e:
            self.logger.error(f"清理任务文件失败: {e}")
```

## 部署和初始化

### 1. 数据库初始化脚本

```sql
-- data_pipeline/sql/init_tables.sql

-- 创建任务表
CREATE TABLE IF NOT EXISTS data_pipeline_tasks (
    id VARCHAR(32) PRIMARY KEY,
    task_type VARCHAR(50) NOT NULL DEFAULT 'complete_workflow',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    parameters JSONB NOT NULL,
    result JSONB,
    error_message TEXT,
    error_step VARCHAR(100),
    progress INTEGER DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
    current_step VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_by VARCHAR(50) DEFAULT 'api',
    step_stats JSONB DEFAULT '{}',
    output_directory TEXT,
    db_name VARCHAR(100),
    business_context TEXT
);

-- 创建日志表
CREATE TABLE IF NOT EXISTS data_pipeline_task_logs (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(32) REFERENCES data_pipeline_tasks(id) ON DELETE CASCADE,
    log_level VARCHAR(10) NOT NULL,
    message TEXT NOT NULL,
    step_name VARCHAR(100),
    module_name VARCHAR(100),
    function_name VARCHAR(100),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    extra_data JSONB DEFAULT '{}'
);

-- 创建输出文件表
CREATE TABLE IF NOT EXISTS data_pipeline_task_outputs (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(32) REFERENCES data_pipeline_tasks(id) ON DELETE CASCADE,
    file_type VARCHAR(50) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_size BIGINT DEFAULT 0,
    content_hash VARCHAR(64),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_primary BOOLEAN DEFAULT FALSE,
    is_downloadable BOOLEAN DEFAULT TRUE
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_tasks_status ON data_pipeline_tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON data_pipeline_tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_db_name ON data_pipeline_tasks(db_name);
CREATE INDEX IF NOT EXISTS idx_tasks_created_by ON data_pipeline_tasks(created_by);

CREATE INDEX IF NOT EXISTS idx_logs_task_id ON data_pipeline_task_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON data_pipeline_task_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_logs_level ON data_pipeline_task_logs(log_level);
CREATE INDEX IF NOT EXISTS idx_logs_step ON data_pipeline_task_logs(step_name);

CREATE INDEX IF NOT EXISTS idx_outputs_task_id ON data_pipeline_task_outputs(task_id);
CREATE INDEX IF NOT EXISTS idx_outputs_file_type ON data_pipeline_task_outputs(file_type);
CREATE INDEX IF NOT EXISTS idx_outputs_primary ON data_pipeline_task_outputs(is_primary) WHERE is_primary = TRUE;

-- 创建清理函数
CREATE OR REPLACE FUNCTION cleanup_old_data_pipeline_tasks(days_to_keep INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
    cutoff_date TIMESTAMP;
BEGIN
    cutoff_date := NOW() - INTERVAL '1 day' * days_to_keep;
    
    -- 删除旧任务（级联删除相关日志和文件记录）
    DELETE FROM data_pipeline_tasks 
    WHERE created_at < cutoff_date 
    AND status IN ('completed', 'failed');
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;
```

### 2. 配置文件更新

需要在 `app_config.py` 中添加Data Pipeline相关配置：

```python
# Data Pipeline API配置
DATA_PIPELINE_CONFIG = {
    "max_concurrent_tasks": 1,           # 最大并发任务数
    "task_timeout_hours": 2,             # 任务超时时间（小时）
    "log_retention_days": 30,            # 日志保留天数
    "file_retention_days": 30,           # 文件保留天数
    "monitor_interval_seconds": 300,     # 监控检查间隔（秒）
    "enable_file_download": True,        # 是否允许文件下载
    "max_download_file_size": 100 * 1024 * 1024,  # 最大下载文件大小（字节）
}
```

## 总结

本详细设计文档提供了Data Pipeline API系统的完整技术实现方案：

### 主要特点

1. **API与执行分离**：使用subprocess实现真正的后台执行，API不阻塞
2. **数据库驱动的状态管理**：所有任务状态、进度、日志都记录在PostgreSQL中
3. **灵活的步骤控制**：支持从指定步骤开始、结束，以及跳过特定步骤
4. **统一的日志管理**：每个任务的日志都写入独立的任务目录
5. **完整的文件管理**：自动扫描、注册和管理任务输出文件
6. **健壮的错误处理**：包括僵尸任务检测、超时处理等

### 实现要点

1. **最小化代码修改**：主要修改集中在 `schema_workflow.py` 和 `citu_app.py`
2. **向后兼容**：手动执行方式仍然完全支持
3. **扩展性好**：易于添加新的任务类型和执行步骤
4. **监控友好**：提供完整的任务监控和清理机制

### 关键文件

1. `citu_app.py` - 添加API路由实现
2. `data_pipeline/schema_workflow.py` - 修改以支持API集成
3. `data_pipeline/api/database_manager.py` - 数据库操作封装（新建）
4. `data_pipeline/api/database_logger.py` - 进度记录器（新建）
5. `data_pipeline/sql/init_tables.sql` - 数据库初始化脚本（新建）

这个设计充分考虑了现有代码结构，提供了完整的API功能，同时保持了系统的简洁性和可维护性。