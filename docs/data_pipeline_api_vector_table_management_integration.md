# Data Pipeline API Vector表管理功能集成方案

## 概述

为 Data Pipeline API 集成 Vector 表管理功能，支持在执行训练数据加载时进行 Vector 表的备份和清空操作。本方案基于已实现的命令行功能（详见 `vector_table_management_design.md`），最大程度复用现有代码，确保 API 与命令行功能保持一致。

## 需求回顾

### 1. API 参数支持
- **完整执行模式**：`POST /api/v0/data_pipeline/tasks/{task_id}/execute`
  ```json
  {
      "execution_mode": "complete",
      "backup_vector_tables": false,
      "truncate_vector_tables": false
  }
  ```

- **单步执行模式**：仅在 `step_name` 为 `"training_load"` 时支持
  ```json
  {
      "execution_mode": "step", 
      "step_name": "training_load",
      "backup_vector_tables": false,
      "truncate_vector_tables": false
  }
  ```

### 2. 参数逻辑
- `backup_vector_tables`：可单独使用
- `truncate_vector_tables`：自动启用 `backup_vector_tables`
- 非 `training_load` 步骤传递这些参数时：忽略并记录 WARNING 日志
- 默认值：均为 `false`

### 3. 复用原则
- 最大程度复用命令行实现的 `VectorTableManager` 类
- 保持与命令行功能的一致性
- 不影响现有命令行执行逻辑

## 修改方案

### 1. API 请求参数扩展

#### 1.1 unified_api.py 修改

**位置**：`@app.route('/api/v0/data_pipeline/tasks/<task_id>/execute', methods=['POST'])`

```python
@app.route('/api/v0/data_pipeline/tasks/<task_id>/execute', methods=['POST'])
def execute_data_pipeline_task(task_id):
    """执行数据管道任务"""
    try:
        req = request.get_json(force=True) if request.is_json else {}
        execution_mode = req.get('execution_mode', 'complete')
        step_name = req.get('step_name')
        
        # 新增：Vector表管理参数
        backup_vector_tables = req.get('backup_vector_tables', False)
        truncate_vector_tables = req.get('truncate_vector_tables', False)
        
        # 现有验证逻辑...
        
        # 新增：Vector表管理参数验证和警告
        if execution_mode == 'step' and step_name != 'training_load':
            if backup_vector_tables or truncate_vector_tables:
                logger.warning(
                    f"⚠️ Vector表管理参数仅在training_load步骤有效，当前步骤: {step_name}，忽略参数"
                )
                backup_vector_tables = False
                truncate_vector_tables = False
        
        # 构建执行命令时添加新参数
        cmd = [
            python_executable,
            str(script_path),
            "--task-id", task_id,
            "--execution-mode", execution_mode
        ]
        
        if step_name:
            cmd.extend(["--step-name", step_name])
            
        # 新增：Vector表管理参数传递
        if backup_vector_tables:
            cmd.append("--backup-vector-tables")
        if truncate_vector_tables:
            cmd.append("--truncate-vector-tables")
        
        # 其余逻辑保持不变...
```

#### 1.2 task_executor.py 修改

**新增命令行参数解析**：

```python
def main():
    """主执行函数"""
    parser = argparse.ArgumentParser(description='Data Pipeline 任务执行器')
    parser.add_argument('--task-id', required=True, help='任务ID')
    parser.add_argument('--execution-mode', default='complete', choices=['complete', 'step'], help='执行模式')
    parser.add_argument('--step-name', help='步骤名称（当execution-mode=step时必需）')
    
    # 新增：Vector表管理参数
    parser.add_argument('--backup-vector-tables', action='store_true', help='备份vector表数据')
    parser.add_argument('--truncate-vector-tables', action='store_true', help='清空vector表数据（自动启用备份）')
    
    args = parser.parse_args()
    
    # 现有验证逻辑...
    
    try:
        # 传递新参数到execute_task
        result = asyncio.run(execute_task(
            args.task_id, 
            args.execution_mode, 
            args.step_name,
            args.backup_vector_tables,
            args.truncate_vector_tables
        ))
```

**修改execute_task函数签名**：

```python
async def execute_task(task_id: str, execution_mode: str, step_name: str = None, 
                      backup_vector_tables: bool = False, truncate_vector_tables: bool = False):
    """执行任务的异步函数"""
    executor = None
    try:
        executor = SimpleWorkflowExecutor(task_id, backup_vector_tables, truncate_vector_tables)
        
        if execution_mode == "complete":
            return await executor.execute_complete_workflow()
        elif execution_mode == "step":
            return await executor.execute_single_step(step_name)
        else:
            raise ValueError(f"不支持的执行模式: {execution_mode}")
            
    finally:
        if executor:
            executor.cleanup()
```

### 2. SimpleWorkflowExecutor 扩展

#### 2.1 构造函数修改

**位置**：`data_pipeline/api/simple_workflow.py`

```python
class SimpleWorkflowExecutor:
    """简化的任务工作流执行器"""
    
    def __init__(self, task_id: str, backup_vector_tables: bool = False, truncate_vector_tables: bool = False):
        """
        初始化工作流执行器
        
        Args:
            task_id: 任务ID
            backup_vector_tables: 是否备份vector表数据
            truncate_vector_tables: 是否清空vector表数据（自动启用备份）
        """
        self.task_id = task_id
        self.backup_vector_tables = backup_vector_tables
        self.truncate_vector_tables = truncate_vector_tables
        
        # 参数逻辑：truncate自动启用backup
        if self.truncate_vector_tables:
            self.backup_vector_tables = True
        
        self.logger = get_logger("SimpleWorkflowExecutor", task_id)
        
        # 记录Vector表管理参数状态
        if self.backup_vector_tables or self.truncate_vector_tables:
            self.logger.info(f"🗂️ Vector表管理已启用: backup={self.backup_vector_tables}, truncate={self.truncate_vector_tables}")
        
        # 现有初始化逻辑...
```

#### 2.2 _create_orchestrator 方法修改

```python
def _create_orchestrator(self):
    """创建工作流编排器"""
    # 现有参数获取逻辑...
    
    # 创建SchemaWorkflowOrchestrator时传递Vector表管理参数
    orchestrator = SchemaWorkflowOrchestrator(
        db_connection=db_connection,
        table_list_file=table_list_file,
        business_context=business_context,
        output_dir=self.task_output_dir,
        task_id=self.task_id,
        enable_question_sql_generation=enable_qa_generation,
        enable_sql_validation=enable_sql_validation,
        enable_training_data_load=enable_training_load,
        # 新增：Vector表管理参数
        backup_vector_tables=self.backup_vector_tables,
        truncate_vector_tables=self.truncate_vector_tables
    )
    
    return orchestrator
```

#### 2.3 execute_single_step 方法修改

```python
async def execute_single_step(self, step_name: str) -> Dict[str, Any]:
    """执行单个步骤"""
    try:
        # 新增：非training_load步骤的Vector表管理参数警告
        if step_name != 'training_load' and (self.backup_vector_tables or self.truncate_vector_tables):
            self.logger.warning(
                f"⚠️ Vector表管理参数仅在training_load步骤有效，当前步骤: {step_name}，忽略参数"
            )
            # 临时禁用Vector表管理参数
            temp_backup = self.backup_vector_tables
            temp_truncate = self.truncate_vector_tables
            self.backup_vector_tables = False
            self.truncate_vector_tables = False
        
        # 现有步骤执行逻辑...
        
        # 创建工作流编排器（会根据当前参数状态创建）
        orchestrator = self._create_orchestrator()
        
        # 执行指定步骤...
        
        # 恢复原始参数状态（如果被临时修改）
        if step_name != 'training_load' and ('temp_backup' in locals()):
            self.backup_vector_tables = temp_backup
            self.truncate_vector_tables = temp_truncate
        
        # 现有返回逻辑...
```

### 3. SchemaWorkflowOrchestrator 参数扩展

#### 3.1 构造函数修改

**位置**：`data_pipeline/schema_workflow.py`

```python
class SchemaWorkflowOrchestrator:
    def __init__(self, 
                 # 现有参数...
                 backup_vector_tables: bool = False,
                 truncate_vector_tables: bool = False):
        """
        初始化工作流编排器
        
        Args:
            # 现有参数说明...
            backup_vector_tables: 是否备份vector表数据
            truncate_vector_tables: 是否清空vector表数据（自动启用备份）
        """
        # 现有初始化逻辑...
        
        # 新增：Vector表管理参数
        self.backup_vector_tables = backup_vector_tables
        self.truncate_vector_tables = truncate_vector_tables
        
        # 参数逻辑：truncate自动启用backup
        if self.truncate_vector_tables:
            self.backup_vector_tables = True
            self.logger.info("🔄 启用truncate时自动启用backup")
```

#### 3.2 复用现有Vector表管理方法

```python
async def _execute_vector_table_management(self):
    """独立执行Vector表管理（复用命令行实现）"""
    if not (self.backup_vector_tables or self.truncate_vector_tables):
        return
        
    self.logger.info("🗂️ 开始执行Vector表管理...")
    
    try:
        # 直接复用命令行实现的VectorTableManager
        from data_pipeline.trainer.vector_table_manager import VectorTableManager
        
        vector_manager = VectorTableManager(
            task_output_dir=str(self.output_dir),
            task_id=self.task_id
        )
        
        # 执行vector表管理
        vector_stats = await vector_manager.execute_vector_management(
            backup=self.backup_vector_tables,
            truncate=self.truncate_vector_tables
        )
        
        # 记录结果到工作流状态
        self.workflow_state["artifacts"]["vector_management"] = vector_stats
        
        self.logger.info("✅ Vector表管理完成")
        
        return vector_stats
        
    except Exception as e:
        self.logger.error(f"❌ Vector表管理失败: {e}")
        raise
```

### 4. API 响应格式扩展

#### 4.1 完整工作流响应

```json
{
    "success": true,
    "task_id": "task_20250721_113010",
    "execution_mode": "complete",
    "result": {
        "workflow_state": {...},
        "artifacts": {
            "vector_management": {
                "backup_performed": true,
                "truncate_performed": true,
                "tables_backed_up": {
                    "langchain_pg_collection": {
                        "row_count": 1234,
                        "file_size": "45.6 KB",
                        "backup_file": "langchain_pg_collection_20250721_113010.csv",
                        "backup_path": "/path/to/task/vector_bak/langchain_pg_collection_20250721_113010.csv"
                    },
                    "langchain_pg_embedding": {
                        "row_count": 12345,
                        "file_size": "2.1 MB",
                        "backup_file": "langchain_pg_embedding_20250721_113010.csv",
                        "backup_path": "/path/to/task/vector_bak/langchain_pg_embedding_20250721_113010.csv"
                    }
                },
                "truncate_results": {
                    "langchain_pg_embedding": {
                        "success": true,
                        "rows_before": 12345,
                        "rows_after": 0
                    }
                },
                "duration": 12.5,
                "backup_directory": "/path/to/task/vector_bak"
            }
        }
    }
}
```

#### 4.2 单步执行响应

```json
{
    "success": true,
    "task_id": "task_20250721_113010",
    "execution_mode": "step",
    "step_name": "training_load",
    "result": {
        "training_data_load": {...},
        "vector_management": {
            // 同完整工作流的vector_management结构
        }
    }
}
```

### 5. 日志增强

#### 5.1 API 层日志

```python
# unified_api.py 中的日志增强
if backup_vector_tables or truncate_vector_tables:
    logger.info(f"📋 API请求包含Vector表管理参数: backup={backup_vector_tables}, truncate={truncate_vector_tables}")

# 非training_load步骤的警告日志
if execution_mode == 'step' and step_name != 'training_load':
    if backup_vector_tables or truncate_vector_tables:
        logger.warning(
            f"⚠️ Vector表管理参数仅在training_load步骤有效，当前步骤: {step_name}，忽略参数"
        )
```

#### 5.2 工作流层日志

```python
# SimpleWorkflowExecutor 中的日志增强
if self.backup_vector_tables or self.truncate_vector_tables:
    self.logger.info(f"🗂️ Vector表管理已启用: backup={self.backup_vector_tables}, truncate={self.truncate_vector_tables}")

# 记录备份文件信息
if vector_stats and vector_stats.get("backup_performed"):
    self.logger.info("📁 Vector表备份文件:")
    for table_name, info in vector_stats.get("tables_backed_up", {}).items():
        if info.get("success", False):
            self.logger.info(f"   ✅ {table_name}: {info['backup_file']} ({info['file_size']})")
```

## 影响评估

### 1. 对命令行执行的影响

**✅ 无影响**：
- 所有修改都是在 API 层面添加参数传递
- 复用现有的 `VectorTableManager` 类，不修改其实现
- `SchemaWorkflowOrchestrator` 的修改只是添加新参数，保持向后兼容
- 命令行调用路径不涉及 `SimpleWorkflowExecutor`

**验证点**：
- 现有命令行脚本继续正常工作
- `VectorTableManager` 的行为保持一致
- 参数传递逻辑与命令行实现相同

### 2. API 向后兼容性

**✅ 完全兼容**：
- 新参数都有默认值 `false`
- 不包含新参数的请求继续正常工作
- 响应格式向后兼容（新增字段不影响现有解析）

### 3. 错误处理兼容性

**✅ 优雅处理**：
- 非 `training_load` 步骤传递Vector参数：忽略 + WARNING日志
- Vector表管理失败：记录错误，不影响其他步骤
- 保持现有错误处理机制

## 实施步骤

### 阶段1：参数传递链路
1. 修改 `unified_api.py` 的execute路由
2. 修改 `task_executor.py` 参数解析
3. 修改 `SimpleWorkflowExecutor` 构造函数

### 阶段2：工作流集成
1. 修改 `SchemaWorkflowOrchestrator` 构造函数
2. 在 `SimpleWorkflowExecutor` 中集成Vector表管理调用
3. 确保复用现有 `VectorTableManager`

### 阶段3：响应和日志
1. 扩展API响应格式
2. 增强日志记录
3. 添加备份文件路径信息

### 阶段4：测试验证
1. API功能测试
2. 命令行兼容性测试
3. 边界条件测试

## 测试用例

### 1. 基本功能测试

```bash
# 完整工作流 + Vector表管理
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250721_113010/execute \
  -H "Content-Type: application/json" \
  -d '{
    "execution_mode": "complete",
    "backup_vector_tables": true,
    "truncate_vector_tables": true
  }'

# 单步执行 + Vector表管理
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250721_113010/execute \
  -H "Content-Type: application/json" \
  -d '{
    "execution_mode": "step",
    "step_name": "training_load",
    "backup_vector_tables": true
  }'
```

### 2. 边界条件测试

```bash
# 非training_load步骤传递Vector参数（应忽略并警告）
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250721_113010/execute \
  -H "Content-Type: application/json" \
  -d '{
    "execution_mode": "step",
    "step_name": "ddl_generation",
    "backup_vector_tables": true
  }'

# 不包含Vector参数（向后兼容）
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks/task_20250721_113010/execute \
  -H "Content-Type: application/json" \
  -d '{
    "execution_mode": "complete"
  }'
```

### 3. 命令行兼容性测试

```bash
# 验证现有命令行功能不受影响
python -m data_pipeline.schema_workflow --db-connection "..." --table-list "./tables.txt" --business-context "测试" --backup-vector-tables

python -m data_pipeline.trainer.run_training --data_path "./training_data/" --truncate-vector-tables
```

## 风险控制

### 1. 代码复用风险
- **风险**：修改 `VectorTableManager` 可能影响命令行
- **控制**：完全复用，不修改现有实现

### 2. 参数传递风险
- **风险**：参数传递链路复杂，容易遗漏
- **控制**：分阶段测试，逐层验证

### 3. 响应格式风险
- **风险**：新响应字段可能影响现有客户端
- **控制**：采用向后兼容的扩展方式

## 总结

本方案通过最小化修改实现API对Vector表管理功能的支持，主要特点：

1. **最大复用**：直接复用命令行实现的 `VectorTableManager`
2. **参数一致**：API与命令行使用相同的参数逻辑
3. **向后兼容**：现有API调用完全不受影响
4. **优雅降级**：非适用场景下忽略参数并记录警告
5. **完整响应**：API返回详细的备份文件信息

该方案确保了功能的一致性和代码的可维护性，同时最小化了对现有系统的影响。 