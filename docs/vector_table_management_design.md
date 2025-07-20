# Vector表管理功能设计文档

## 概述

为 data_pipeline 添加两个新参数来管理 vector 表数据：
- `--backup_vector_tables`: 备份vector表数据
- `--truncate_vector_tables`: 清空vector表数据（自动启用备份）

## 需求分析

### 1. 参数依赖关系
- 可以单独使用 `--backup_vector_tables`
- 不可以单独使用 `--truncate_vector_tables`
- 使用 `--truncate_vector_tables` 时自动启用 `--backup_vector_tables`

### 2. 支持的执行入口
1. `python -m data_pipeline.schema_workflow`（包括使用 `--skip-training-load` 的情况）
2. `python -m data_pipeline.trainer.run_training`
3. API 接口：`POST /api/v0/data_pipeline/tasks/{task_id}/execute`

### 3. 特殊执行场景
- **跳过训练加载场景**: 即使 `schema_workflow` 使用了 `--skip-training-load` 参数，仍然要支持 `--backup-vector-tables` 和 `--truncate-vector-tables` 参数的执行
- **重复执行避免**: 由于 `schema_workflow` 的完整流程包含了 `run_training` 的调用，需要避免重复执行vector表管理操作

### 4. 影响的表
- `langchain_pg_collection`：只备份，不清空
- `langchain_pg_embedding`：备份并清空

## 详细设计

### 1. 参数定义和传递

#### 1.1 命令行参数
```bash
# schema_workflow.py 新增参数
--backup-vector-tables      # 备份vector表数据
--truncate-vector-tables    # 清空vector表数据（自动启用备份）

# run_training.py 新增参数
--backup-vector-tables      # 备份vector表数据  
--truncate-vector-tables    # 清空vector表数据（自动启用备份）
```

#### 1.2 参数传递链
```
CLI参数 -> SchemaWorkflowOrchestrator -> process_training_files -> VectorTableManager
```

### 2. 核心组件设计

#### 2.1 新增 VectorTableManager 类
**位置**: `data_pipeline/trainer/vector_table_manager.py`

```python
class VectorTableManager:
    """Vector表管理器，负责备份和清空操作"""
    
    def __init__(self, task_output_dir: str, task_id: str = None):
        """
        Args:
            task_output_dir: 任务输出目录（用于存放备份文件）
            task_id: 任务ID（用于日志记录）
        Note:
            数据库连接将从data_pipeline.config.SCHEMA_TOOLS_CONFIG自动获取
        """
        self.task_output_dir = task_output_dir
        self.task_id = task_id
        
        # 从data_pipeline.config获取配置
        from data_pipeline.config import SCHEMA_TOOLS_CONFIG
        self.config = SCHEMA_TOOLS_CONFIG.get("vector_table_management", {})
        
        # 初始化日志
        if task_id:
            from data_pipeline.dp_logging import get_logger
            self.logger = get_logger("VectorTableManager", task_id)
        else:
            import logging
            self.logger = logging.getLogger("VectorTableManager")
    
    async def backup_vector_tables(self) -> Dict[str, Any]:
        """备份vector表数据"""
    
    async def truncate_vector_tables(self) -> Dict[str, Any]: 
        """清空vector表数据（只清空langchain_pg_embedding）"""
        
    async def execute_vector_management(self, backup: bool, truncate: bool) -> Dict[str, Any]:
        """执行vector表管理操作"""
        
    def get_connection(self):
    """获取pgvector数据库连接（从data_pipeline.config获取配置）"""
    
def _format_file_size(self, size_bytes: int) -> str:
    """格式化文件大小显示"""
```

#### 2.2 主要执行流程

```python
async def execute_vector_management(self, backup: bool, truncate: bool) -> Dict[str, Any]:
    """执行vector表管理操作的主流程"""
    
    start_time = time.time()
    
    # 1. 参数验证和自动启用逻辑
    if truncate and not backup:
        backup = True
        self.logger.info("🔄 启用truncate时自动启用backup")
    
    if not backup and not truncate:
        self.logger.info("⏭️ 未启用vector表管理，跳过操作")
        return {"backup_performed": False, "truncate_performed": False}
    
    # 2. 初始化结果统计
    result = {
        "backup_performed": backup,
        "truncate_performed": truncate,
        "tables_backed_up": {},
        "truncate_results": {},
        "errors": [],
        "backup_directory": None,
        "duration": 0
    }
    
    try:
        # 3. 创建备份目录
        backup_dir = Path(self.task_output_dir) / self.config["backup_directory"]
        if backup:
            backup_dir.mkdir(parents=True, exist_ok=True)
            result["backup_directory"] = str(backup_dir)
            self.logger.info(f"📁 备份目录: {backup_dir}")
        
        # 4. 执行备份操作
        if backup:
            self.logger.info("🗂️ 开始备份vector表...")
            backup_results = await self.backup_vector_tables()
            result["tables_backed_up"] = backup_results
            
            # 检查备份是否全部成功
            backup_failed = any(not r.get("success", False) for r in backup_results.values())
            if backup_failed:
                result["errors"].append("部分表备份失败")
                if truncate:
                    self.logger.error("❌ 备份失败，取消清空操作")
                    result["truncate_performed"] = False
                    truncate = False
        
        # 5. 执行清空操作（仅在备份成功时）
        if truncate:
            self.logger.info("🗑️ 开始清空vector表...")
            truncate_results = await self.truncate_vector_tables()
            result["truncate_results"] = truncate_results
            
            # 检查清空是否成功
            truncate_failed = any(not r.get("success", False) for r in truncate_results.values())
            if truncate_failed:
                result["errors"].append("部分表清空失败")
        
        # 6. 生成备份日志文件
        if backup and backup_dir.exists():
            self._write_backup_log(backup_dir, result)
        
        # 7. 计算总耗时
        result["duration"] = time.time() - start_time
        
        # 8. 记录最终状态
        if result["errors"]:
            self.logger.warning(f"⚠️ Vector表管理完成，但有错误: {'; '.join(result['errors'])}")
        else:
            self.logger.info(f"✅ Vector表管理完成，耗时: {result['duration']:.2f}秒")
        
        return result
        
    except Exception as e:
        result["duration"] = time.time() - start_time
        result["errors"].append(f"执行失败: {str(e)}")
        self.logger.error(f"❌ Vector表管理失败: {e}")
        raise
```

#### 2.3 数据库连接管理

**配置获取层次**：
```
VectorTableManager
  ↓
data_pipeline.config.SCHEMA_TOOLS_CONFIG["default_db_connection"]
  ↓
app_config.PGVECTOR_CONFIG (在config.py中自动继承)
```

```python
def get_connection(self):
    """获取pgvector数据库连接"""
    import psycopg2
    
    try:
        # 方法1：如果SCHEMA_TOOLS_CONFIG中有连接字符串，直接使用
        connection_string = self.config.get("default_db_connection")
        if connection_string:
            conn = psycopg2.connect(connection_string)
        else:
            # 方法2：从app_config获取pgvector数据库配置
            import app_config
            pgvector_config = app_config.PGVECTOR_CONFIG
            conn = psycopg2.connect(
                host=pgvector_config.get('host'),
                port=pgvector_config.get('port'),
                database=pgvector_config.get('dbname'),
                user=pgvector_config.get('user'),
                password=pgvector_config.get('password')
            )
        
        # 设置自动提交，避免事务问题
        conn.autocommit = True
        return conn
        
    except Exception as e:
        self.logger.error(f"pgvector数据库连接失败: {e}")
        raise

def _write_backup_log(self, backup_dir: Path, result: Dict[str, Any]):
    """写入详细的备份日志"""
    log_file = backup_dir / "vector_backup_log.txt"
    
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write("=== Vector Table Backup Log ===\n")
            f.write(f"Backup Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Task ID: {self.task_id or 'Unknown'}\n")
            f.write(f"Duration: {result.get('duration', 0):.2f}s\n\n")
            
            # 备份状态
            f.write("Tables Backup Status:\n")
            for table_name, info in result.get("tables_backed_up", {}).items():
                if info.get("success", False):
                    f.write(f"✓ {table_name}: {info['row_count']} rows -> {info['backup_file']} ({info['file_size']})\n")
                else:
                    f.write(f"✗ {table_name}: FAILED - {info.get('error', 'Unknown error')}\n")
            
            # 清空状态
            if result.get("truncate_performed", False):
                f.write("\nTruncate Status:\n")
                for table_name, info in result.get("truncate_results", {}).items():
                    if info.get("success", False):
                        f.write(f"✓ {table_name}: TRUNCATED ({info['rows_before']} rows removed)\n")
                    else:
                        f.write(f"✗ {table_name}: FAILED - {info.get('error', 'Unknown error')}\n")
            else:
                f.write("\nTruncate Status:\n- Not performed\n")
            
            # 错误汇总
            if result.get("errors"):
                f.write(f"\nErrors: {'; '.join(result['errors'])}\n")
                
    except Exception as e:
        self.logger.warning(f"写入备份日志失败: {e}")
```

#### 2.4 备份文件命名规则
```
{task_output_dir}/vector_bak/langchain_pg_collection_{timestamp}.csv
{task_output_dir}/vector_bak/langchain_pg_embedding_{timestamp}.csv
```

时间戳格式：`YYYYMMDD_HHMMSS`

### 3. 执行流程设计

#### 3.1 完整工作流 (schema_workflow.py)
```
步骤1: DDL/MD生成
步骤2: Question-SQL生成  
步骤3: SQL验证（可选）
步骤4: 训练数据加载
  ├── 4.1 Vector表管理（新增）
  │   ├── 备份vector表（如果启用）
  │   └── 清空vector表（如果启用）
  └── 4.2 加载训练数据
```

#### 3.2 独立训练加载 (run_training.py)
```
前置步骤: Vector表管理（新增）
├── 备份vector表（如果启用）
└── 清空vector表（如果启用）
主要步骤: 训练数据加载
```

### 4. 文件结构设计

#### 4.1 目录结构
```
data_pipeline/training_data/manual_20250720_121007/
├── *.ddl                           # DDL文件
├── *.md                            # 文档文件
├── *.json                          # QS文件
├── data_pipeline.log               # 任务日志（直接在根目录）
├── vector_bak/                     # 新增：vector备份目录
│   ├── langchain_pg_collection_20250720_121007.csv
│   ├── langchain_pg_embedding_20250720_121007.csv
│   └── vector_backup_log.txt       # 备份操作日志
└── task_config.json                # 任务配置文件
```

#### 4.2 备份操作日志格式
```
=== Vector Table Backup Log ===
Backup Time: 2025-01-20 12:10:07
Task ID: manual_20250720_121007
Database: highway_db

Tables Backup Status:
✓ langchain_pg_collection: 1,234 rows -> langchain_pg_collection_20250720_121007.csv (45.6 KB)
✓ langchain_pg_embedding: 12,345 rows -> langchain_pg_embedding_20250720_121007.csv (2.1 MB)

Truncate Status:
✓ langchain_pg_embedding: TRUNCATED
- langchain_pg_collection: SKIPPED (collection table preserved)
```

### 5. 脚本总结报告设计

**要求**：在脚本作业的日志最后的summary阶段，必须总结是否执行了备份和truncate。

#### 5.1 schema_workflow.py 总结修改
在 `print_final_summary()` 方法中添加vector管理总结：

```python
def print_final_summary(self, report: Dict[str, Any]):
    # 现有总结逻辑...
    
    # 新增：Vector表管理总结
    vector_stats = report.get("vector_management_stats")
    if vector_stats:
        self.logger.info("📊 Vector表管理:")
        if vector_stats.get("backup_performed", False):
            tables_count = len(vector_stats.get("tables_backed_up", {}))
            total_size = sum(info.get("file_size", 0) for info in vector_stats.get("tables_backed_up", {}).values())
            self.logger.info(f"   ✅ 备份执行: {tables_count}个表，总大小: {self._format_size(total_size)}")
        else:
            self.logger.info("   - 备份执行: 未执行")
            
        if vector_stats.get("truncate_performed", False):
            self.logger.info("   ✅ 清空执行: langchain_pg_embedding表已清空")
        else:
            self.logger.info("   - 清空执行: 未执行")
            
        duration = vector_stats.get("duration", 0)
        self.logger.info(f"   ⏱️  执行耗时: {duration:.1f}秒")
    else:
        self.logger.info("📊 Vector表管理: 未执行（未启用相关参数）")
```

#### 5.2 run_training.py 总结修改
在 `main()` 函数的最终统计部分添加vector管理报告：

```python
def main():
    # 现有逻辑...
    
    # 执行训练处理
    process_successful, vector_stats = process_training_files(data_path, task_id, 
                                                             backup_vector_tables, 
                                                             truncate_vector_tables)
    
    # 原有成功统计...
    
    # 新增：Vector表管理总结
    print("\n===== Vector表管理统计 =====")
    if vector_stats:
        if vector_stats.get("backup_performed", False):
            tables_info = vector_stats.get("tables_backed_up", {})
            print(f"✓ 备份执行: 成功备份 {len(tables_info)} 个表")
            for table_name, info in tables_info.items():
                print(f"  - {table_name}: {info['row_count']}行 -> {info['backup_file']} ({info['file_size']})")
        if vector_stats.get("truncate_performed", False):
            print("✓ 清空执行: langchain_pg_embedding表已清空")
        print(f"✓ 总耗时: {vector_stats.get('duration', 0):.1f}秒")
    else:
        print("- 未执行vector表管理操作")
    
    print("===========================")
```

### 6. 具体修改方案

#### 6.1 修改 schema_workflow.py

**新增参数**:
```python
parser.add_argument(
    "--backup-vector-tables",
    action="store_true",
    help="备份vector表数据到任务目录"
)

parser.add_argument(
    "--truncate-vector-tables", 
    action="store_true",
    help="清空vector表数据（自动启用备份）"
)
```

**修改 SchemaWorkflowOrchestrator 构造函数**:
```python
def __init__(self, ..., backup_vector_tables: bool = False, truncate_vector_tables: bool = False):
    # 参数验证和自动启用逻辑
    if truncate_vector_tables:
        backup_vector_tables = True
```

**修改 _execute_step_4_training_data_load**:
```python
async def _execute_step_4_training_data_load(self):
    # 新增：Vector表管理
    if self.backup_vector_tables or self.truncate_vector_tables:
        await self._execute_vector_table_management()
    
    # 原有：训练数据加载
    load_successful = process_training_files(
        training_data_dir, 
        self.task_id,
        backup_vector_tables=False,  # 避免重复执行
        truncate_vector_tables=False  # 避免重复执行
    )
```

**新增独立的Vector表管理方法**:
```python
async def _execute_vector_table_management(self):
    """独立执行Vector表管理（支持--skip-training-load场景）"""
    if not (self.backup_vector_tables or self.truncate_vector_tables):
        return
        
    self.logger.info("🗂️ 开始执行Vector表管理...")
    
    try:
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
        
    except Exception as e:
        self.logger.error(f"❌ Vector表管理失败: {e}")
        raise
```

**修改主工作流以支持--skip-training-load场景**:
```python
async def execute_complete_workflow(self) -> Dict[str, Any]:
    # 现有步骤1-3...
    
    # 新增：独立的Vector表管理（在训练加载之前或替代训练加载）
    if self.backup_vector_tables or self.truncate_vector_tables:
        await self._execute_vector_table_management()
    
    # 步骤4: 训练数据加载（如果启用）
    if self.enable_training_data_load:
        await self._execute_step_4_training_data_load()
    else:
        self.logger.info("⏭️ 跳过训练数据加载步骤")
```

#### 6.2 修改 run_training.py

**新增参数处理**:
```python
parser.add_argument('--backup-vector-tables', action='store_true', help='备份vector表数据')
parser.add_argument('--truncate-vector-tables', action='store_true', help='清空vector表数据（自动启用备份）')
```

**修改 process_training_files 函数**:
```python
def process_training_files(data_path, task_id=None, backup_vector_tables=False, truncate_vector_tables=False):
    # 参数验证和自动启用逻辑
    if truncate_vector_tables:
        backup_vector_tables = True
    
    # Vector表管理（前置步骤）
    vector_stats = None
    if backup_vector_tables or truncate_vector_tables:
        vector_manager = VectorTableManager(data_path, task_id)
        vector_stats = asyncio.run(vector_manager.execute_vector_management(backup_vector_tables, truncate_vector_tables))
    
    # 原有训练数据处理逻辑...
    
    # 在最终统计中包含vector管理信息
    return process_successful, vector_stats
```

#### 6.3 修改 API 相关文件

**SimpleWorkflowExecutor 修改**:
```python
def __init__(self, task_id: str, backup_vector_tables: bool = False, truncate_vector_tables: bool = False):
    # 传递参数给 orchestrator
```

**API 路由处理**（后续步骤，当前不实现）:
```json
{
    "execution_mode": "complete",
    "step_name": null,
    "backup_vector_tables": false,
    "truncate_vector_tables": false
}
```

### 7. SQL操作设计

#### 7.1 备份操作

**SQL命令设计**：
```sql
-- 设置编码
SET client_encoding TO 'UTF8';

-- 导出数据（先导出为.tmp文件）
COPY langchain_pg_collection TO '{backup_path}/langchain_pg_collection_{timestamp}.csv.tmp' WITH CSV HEADER;
COPY langchain_pg_embedding TO '{backup_path}/langchain_pg_embedding_{timestamp}.csv.tmp' WITH CSV HEADER;
```

**Python实现方式**：
```python
async def backup_vector_tables(self) -> Dict[str, Any]:
    """备份vector表数据"""
    
    # 1. 创建备份目录
    backup_dir = Path(self.task_output_dir) / "vector_bak"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. 生成时间戳
    timestamp = datetime.now().strftime(self.config["timestamp_format"])
    
    # 3. 执行备份（每个表分别处理）
    results = {}
    
    for table_name in self.config["supported_tables"]:
        try:
            # 3.1 定义文件路径（.tmp临时文件）
            temp_file = backup_dir / f"{table_name}_{timestamp}.csv.tmp"
            final_file = backup_dir / f"{table_name}_{timestamp}.csv"
            
            # 3.2 执行COPY命令导出到.tmp文件
            copy_sql = f"""
                SET client_encoding TO 'UTF8';
                COPY {table_name} TO '{temp_file}' WITH CSV HEADER;
            """
            
            # 3.3 通过psycopg2执行SQL
            start_time = time.time()
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # 执行编码设置
                    cursor.execute("SET client_encoding TO 'UTF8'")
                    
                    # 执行COPY命令
                    cursor.execute(f"COPY {table_name} TO '{temp_file}' WITH CSV HEADER")
                    
                    # 获取导出行数
                    row_count = cursor.rowcount
            
            # 3.4 导出完成后，重命名文件 (.tmp -> .csv)
            if temp_file.exists():
                temp_file.rename(final_file)
                
                # 3.5 获取文件信息
                file_stat = final_file.stat()
                duration = time.time() - start_time
                
                results[table_name] = {
                    "success": True,
                    "row_count": row_count,
                    "file_size": self._format_file_size(file_stat.st_size),
                    "backup_file": final_file.name,
                    "duration": duration
                }
                
                self.logger.info(f"✅ {table_name} 备份成功: {row_count}行 -> {final_file.name}")
            else:
                raise Exception(f"临时文件 {temp_file} 未生成")
                
        except Exception as e:
            results[table_name] = {
                "success": False,
                "error": str(e)
            }
            self.logger.error(f"❌ {table_name} 备份失败: {e}")
            
            # 清理可能的临时文件
            if temp_file.exists():
                temp_file.unlink()
    
    return results

# 注意：get_connection()方法在类的其他地方已定义，这里不需要重复
```

**关键设计点**：
1. **临时文件机制**: 先导出为 `.csv.tmp` 文件，完成后重命名为 `.csv`
2. **原子性操作**: 确保文件重命名是原子操作，避免下载到未完成的文件
3. **错误处理**: 如果导出失败，自动清理临时文件
4. **逐表处理**: 每个表单独备份，一个失败不影响其他表

#### 7.2 清空操作

**SQL命令设计**：
```sql
-- 只清空 embedding 表，保留 collection 表
TRUNCATE TABLE langchain_pg_embedding;
```

**Python实现方式**：
```python
async def truncate_vector_tables(self) -> Dict[str, Any]:
    """清空vector表数据（只清空langchain_pg_embedding）"""
    
    results = {}
    
    # 只清空配置中指定的表（通常只有langchain_pg_embedding）
    truncate_tables = self.config["truncate_tables"]
    
    for table_name in truncate_tables:
        try:
            # 记录清空前的行数（用于统计）
            count_sql = f"SELECT COUNT(*) FROM {table_name}"
            
            start_time = time.time()
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # 1. 获取清空前的行数
                    cursor.execute(count_sql)
                    rows_before = cursor.fetchone()[0]
                    
                    # 2. 执行TRUNCATE
                    cursor.execute(f"TRUNCATE TABLE {table_name}")
                    
                    # 3. 验证清空结果
                    cursor.execute(count_sql)
                    rows_after = cursor.fetchone()[0]
            
            duration = time.time() - start_time
            
            if rows_after == 0:
                results[table_name] = {
                    "success": True,
                    "rows_before": rows_before,
                    "rows_after": rows_after,
                    "duration": duration
                }
                self.logger.info(f"✅ {table_name} 清空成功: {rows_before}行 -> 0行")
            else:
                raise Exception(f"清空失败，表中仍有 {rows_after} 行数据")
                
        except Exception as e:
            results[table_name] = {
                "success": False,
                "error": str(e)
            }
            self.logger.error(f"❌ {table_name} 清空失败: {e}")
    
    return results
```

**关键设计点**：
1. **选择性清空**: 只清空 `langchain_pg_embedding` 表，保留 `langchain_pg_collection` 表
2. **统计信息**: 记录清空前后的行数，便于统计报告
3. **验证机制**: 清空后验证表确实为空
4. **事务安全**: 每个表的操作在独立的连接中执行

#### 7.3 恢复操作（备用，不在当前需求中）
```sql
SET client_encoding TO 'UTF8';
COPY langchain_pg_collection FROM '{backup_path}/langchain_pg_collection_{timestamp}.csv' WITH CSV HEADER;
COPY langchain_pg_embedding FROM '{backup_path}/langchain_pg_embedding_{timestamp}.csv' WITH CSV HEADER;
```

### 8. 错误处理和回滚

#### 8.1 错误场景
1. 数据库连接失败
2. 权限不足（无法执行 COPY 或 TRUNCATE）
3. 磁盘空间不足
4. 备份文件写入失败
5. 清空操作失败

#### 8.2 回滚策略
- 如果备份失败，不执行清空操作
- 如果清空失败，保留备份文件，记录错误状态
- 提供详细的错误日志和状态报告

### 9. 配置管理

#### 9.1 新增配置项
```python
# data_pipeline/config.py 新增配置项
SCHEMA_TOOLS_CONFIG = {
    # 现有配置...
    
    # 新增：Vector表管理配置
    "vector_table_management": {
        "backup_enabled": True,
        "backup_directory": "vector_bak",
        "supported_tables": [
            "langchain_pg_collection",
            "langchain_pg_embedding"
        ],
        "truncate_tables": [
            "langchain_pg_embedding"  # 只清空embedding表
        ],
        "timestamp_format": "%Y%m%d_%H%M%S",
        "backup_temp_suffix": ".tmp"
    }
}
```

### 10. 日志和监控

#### 10.1 日志级别
- INFO: 正常操作（开始备份、完成备份等）
- WARNING: 非致命问题（权限限制、文件已存在等）
- ERROR: 操作失败（连接失败、磁盘满等）

#### 10.2 统计信息

**统计信息将出现在以下位置**：
1. **API 返回结果**：任务执行完成后的JSON响应中
2. **脚本日志摘要**：命令行脚本的最终总结阶段
3. **任务目录日志文件**：详细的操作日志

**统计信息格式**：
```python
{
    "vector_management_stats": {
        "backup_performed": True,
        "truncate_performed": True,
        "tables_backed_up": {
            "langchain_pg_collection": {
                "row_count": 1234,
                "file_size": "45.6 KB",
                "backup_file": "langchain_pg_collection_20250720_121007.csv"
            },
            "langchain_pg_embedding": {
                "row_count": 12345,
                "file_size": "2.1 MB", 
                "backup_file": "langchain_pg_embedding_20250720_121007.csv"
            }
        },
        "truncate_results": {
            "langchain_pg_embedding": "SUCCESS"
        },
        "duration": 12.5,
        "backup_directory": "/path/to/task/vector_bak"
    }
}
```

**脚本总结示例**：
```
📊 工作流程执行统计
===================
✅ Vector表管理:
   - 备份执行: 是
   - 清空执行: 是  
   - 备份文件: 2个 (共2.15MB)
   - 执行耗时: 12.5秒

或者（如果未执行vector管理）：
📊 工作流程执行统计
===================
- Vector表管理: 未执行（未启用相关参数）
```

### 11. API 支持设计考虑

#### 11.1 当前 API 结构分析
当前执行 API：`POST /api/v0/data_pipeline/tasks/{task_id}/execute`

请求体格式：
```json
{
    "execution_mode": "complete|step",
    "step_name": "ddl_generation|qa_generation|sql_validation|training_load"
}
```

#### 11.2 API 扩展方案
**方案1**: 在请求体中添加 vector 管理参数
```json
{
    "execution_mode": "complete",
    "step_name": null,
    "vector_options": {
        "backup_vector_tables": false,
        "truncate_vector_tables": false
    }
}
```

**方案2**: 扁平化参数结构
```json
{
    "execution_mode": "complete",
    "step_name": null,
    "backup_vector_tables": false,
    "truncate_vector_tables": false
}
```

#### 11.3 API 响应扩展
响应中包含 vector 管理操作的结果：
```json
{
    "success": true,
    "task_id": "manual_20250720_121007",
    "execution_mode": "complete", 
    "result": {
        "workflow_state": {...},
        "vector_management": {
            "backup_performed": true,
            "truncate_performed": true,
            "backup_files": [...],
            "statistics": {...}
        }
    }
}
```

### 12. 测试策略

#### 12.1 单元测试
- VectorTableManager 类的各个方法
- 参数验证逻辑
- SQL 操作封装

#### 12.2 集成测试  
- 完整工作流中的 vector 管理
- 独立训练加载中的 vector 管理
- API 调用场景

#### 12.3 边界测试
- 大数据量备份
- 磁盘空间不足场景
- 数据库权限限制场景

### 13. 实施计划

#### 阶段1: 核心功能实现
1. 创建 VectorTableManager 类
2. 修改 schema_workflow.py 参数处理
3. 修改 run_training.py 参数处理
4. 实现备份和清空逻辑

#### 阶段2: 集成测试
1. 完整工作流测试
2. 独立训练加载测试
3. 错误场景测试

#### 阶段3: API 支持（后续）
1. 修改 SimpleWorkflowExecutor
2. 扩展 API 接口
3. API 测试

### 14. 风险评估

#### 14.1 主要风险
1. **数据丢失风险**: 清空操作不可逆，必须确保备份成功
2. **磁盘空间风险**: 备份大量数据可能填满磁盘
3. **权限风险**: COPY 命令需要足够的文件系统权限
4. **并发风险**: 训练过程中其他进程可能在访问 vector 表

#### 14.2 风险缓解
1. 备份失败时不执行清空操作
2. 预先检查磁盘空间
3. 权限检查和友好的错误提示
4. 清晰的操作日志和状态报告

### 15. 文档和用户指南

#### 15.1 用户文档
- 参数使用说明
- 备份文件位置和命名规则
- 常见错误及解决方案

#### 15.2 开发文档
- VectorTableManager API 文档
- 配置项说明
- 扩展指南

## 总结

这个设计提供了一个完整的 vector 表管理功能，包括：

1. **清晰的参数依赖关系**: 确保数据安全
2. **灵活的执行方式**: 支持多种入口
3. **完善的错误处理**: 确保操作可靠性
4. **详细的日志记录**: 便于问题诊断
5. **API 扩展考虑**: 为后续功能做准备

### 对用户反馈的修正

根据用户反馈，已对以下问题进行了修正：

#### 第一轮修正：
1. **数据库连接配置**: 修正为从 `data_pipeline.config.SCHEMA_TOOLS_CONFIG` 获取（该配置从 `app_config.PGVECTOR_CONFIG` 继承），而不是通过参数传递
2. **目录结构**: 修正了任务目录结构，日志文件直接存储在任务根目录，而不是 `logs/` 子目录
3. **参数默认值**: 明确说明 `--backup-vector-tables` 和 `--truncate-vector-tables` 都是可选参数，没有默认值
4. **配置格式**: 修正了配置项格式，使用正确的 Python 字典格式而不是 YAML 格式
5. **统计信息位置**: 明确了统计信息将出现在 API 返回结果、脚本日志摘要和任务目录日志文件中
6. **脚本总结**: 添加了详细的脚本总结报告设计，确保在脚本作业的日志最后总结是否执行了备份和truncate

#### 第二轮修正：
7. **临时文件机制**: 补充了完整的 `.csv.tmp` 临时文件设计，确保导出过程的原子性
   - 先导出为 `.csv.tmp` 文件
   - 导出完成后重命名为 `.csv` 文件
   - 如果导出失败，自动清理临时文件
8. **SQL执行方式**: 补充了详细的PostgreSQL命令执行设计
   - 使用 `psycopg2` 连接pgvector数据库（配置从 `data_pipeline.config` 获取）
   - 详细的连接管理和错误处理
   - 完整的备份和清空操作实现代码
9. **主要执行流程**: 添加了完整的 `execute_vector_management()` 方法设计
   - 参数验证和自动启用逻辑
   - 备份成功验证后再执行清空
   - 详细的错误处理和状态跟踪
10. **备份日志**: 补充了详细的备份操作日志写入机制

#### 第三轮修正：
11. **--skip-training-load场景**: 补充了当 `schema_workflow` 使用 `--skip-training-load` 时仍支持vector表管理的设计
    - 独立的 `_execute_vector_table_management()` 方法
    - 在主工作流中独立执行，不依赖训练加载步骤
12. **重复执行避免机制**: 设计了防止vector表管理操作重复执行的机制
    - `schema_workflow` 中独立执行vector管理
    - 传递给 `run_training` 时禁用vector管理参数（设为False）
    - 确保操作只执行一次

核心原则是**安全优先**，确保在任何情况下都不会意外丢失数据。 