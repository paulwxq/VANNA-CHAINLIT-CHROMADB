# PgVector 恢复备份 API 设计文档

## 概述

为系统添加两个专用的 pgvector 表恢复备份 API，与现有的 `/api/v0/data_pipeline/vector/backup` API 相对应。这两个API将把导出为CSV的文件重新写回到PostgreSQL数据库中，充分复用现有的数据库连接和配置机制。

## 📋 路径使用说明

**重要结论**：经过技术分析，恢复备份API **不需要绝对路径**！

### 技术原因
1. **PostgreSQL COPY FROM STDIN**：恢复时使用 `cursor.copy_expert("COPY table FROM STDIN WITH CSV", file_object)`
2. **文件对象处理**：Python使用相对路径打开文件对象即可，无需绝对路径
3. **与备份不同**：备份时需要绝对路径是为了Python文件写入操作，而非PostgreSQL要求

### API设计优化
- ✅ **列表API**：只返回相对路径（`./data_pipeline/training_data/...`）
- ✅ **恢复API**：只接收相对路径参数  
- ✅ **跨平台兼容**：使用 `Path` 对象处理路径，响应统一使用Unix风格路径

## API 端点概览

| API | 端点 | 功能 |
|-----|------|------|
| **备份文件列表API** | `GET /api/v0/data_pipeline/vector/restore/list` | 列出可用的备份文件 |
| **备份恢复API** | `POST /api/v0/data_pipeline/vector/restore` | 执行备份恢复操作 |

---

## API 1: 备份文件列表 API

### 基本信息

- **端点**: `GET /api/v0/data_pipeline/vector/restore/list`
- **方法**: GET
- **内容类型**: application/json
- **认证**: 无（当前版本）

### 请求参数（查询参数）

| 参数名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `global_only` | boolean | 否 | false | 仅查询全局备份目录（training_data/vector_bak/） |
| `task_id` | string | 否 | null | 指定task_id，仅查询该任务下的备份文件 |

**参数逻辑**：
- 不传任何参数：查询所有备份目录
- 仅传 `global_only=true`：仅查询 `training_data/vector_bak/`
- 仅传 `task_id=xxx`：仅查询指定任务的备份文件
- 同时传递两个参数：`task_id` 优先级更高

### 扫描目录逻辑

#### 扫描范围
1. **全局备份目录**: `./data_pipeline/training_data/vector_bak/`
2. **任务相关目录**: 
   - `./data_pipeline/training_data/task_*/vector_bak/`
   - `./data_pipeline/training_data/manual_*/vector_bak/`

#### 文件筛选条件
- 必须同时存在 `langchain_pg_collection_*.csv` 和 `langchain_pg_embedding_*.csv`
- 文件名格式：`langchain_pg_{table}_{timestamp}.csv`
- 时间戳格式：`YYYYMMDD_HHMMSS`

### 请求示例

```bash
# 1. 查询所有备份文件
curl "http://localhost:8084/api/v0/data_pipeline/vector/restore/list"

# 2. 仅查询全局备份
curl "http://localhost:8084/api/v0/data_pipeline/vector/restore/list?global_only=true"

# 3. 查询特定任务的备份
curl "http://localhost:8084/api/v0/data_pipeline/vector/restore/list?task_id=task_20250721_213627"
```

### 响应格式

#### 成功响应 (200)

```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "response": "成功扫描到 3 个备份位置，共 4 个备份集",
         "backup_locations": [
       {
         "type": "global",
         "relative_path": "./data_pipeline/training_data/vector_bak",
         "backups": [
          {
            "timestamp": "20250722_010318",
            "collection_file": "langchain_pg_collection_20250722_010318.csv",
            "embedding_file": "langchain_pg_embedding_20250722_010318.csv",
            "collection_size": "209 B",
            "embedding_size": "819 KB",
            "backup_date": "2025-07-22 01:03:18",
            "has_log": true,
            "log_file": "vector_backup_log.txt"
          }
        ]
      },
             {
         "type": "task",
         "task_id": "task_20250721_213627",
         "relative_path": "./data_pipeline/training_data/task_20250721_213627/vector_bak",
         "backups": [
          {
            "timestamp": "20250721_215758",
            "collection_file": "langchain_pg_collection_20250721_215758.csv",
            "embedding_file": "langchain_pg_embedding_20250721_215758.csv",
            "collection_size": "209 B",
            "embedding_size": "764 KB",
            "backup_date": "2025-07-21 21:57:58",
            "has_log": true,
            "log_file": "vector_backup_log.txt"
          }
        ]
      },
             {
         "type": "task",
         "task_id": "task_20250721_183935",
         "relative_path": "./data_pipeline/training_data/task_20250721_183935/vector_bak",
         "backups": [
          {
            "timestamp": "20250721_201447",
            "collection_file": "langchain_pg_collection_20250721_201447.csv",
            "embedding_file": "langchain_pg_embedding_20250721_201447.csv",
            "collection_size": "210 B",
            "embedding_size": "780 KB",
            "backup_date": "2025-07-21 20:14:47",
            "has_log": true,
            "log_file": "vector_backup_log.txt"
          }
        ]
      }
    ],
    "summary": {
      "total_locations": 3,
      "total_backup_sets": 4,
      "global_backups": 1,
      "task_backups": 3,
      "scan_time": "2025-07-22T10:30:45+08:00"
    },
    "timestamp": "2025-07-22T10:30:45+08:00"
  }
}
```

#### 无备份文件响应 (200)

```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "response": "未找到任何可用的备份文件",
    "backup_locations": [],
    "summary": {
      "total_locations": 0,
      "total_backup_sets": 0,
      "global_backups": 0,
      "task_backups": 0,
      "scan_time": "2025-07-22T10:30:45+08:00"
    },
    "timestamp": "2025-07-22T10:30:45+08:00"
  }
}
```

#### 错误响应 (400/500)

```json
{
  "code": 400,
  "success": false,
  "message": "请求参数错误",
  "data": {
    "response": "无效的task_id格式，只能包含字母、数字和下划线",
    "error_type": "INVALID_PARAMS",
    "timestamp": "2025-07-22T10:30:45+08:00"
  }
}
```

---

## API 2: 备份恢复 API

### 基本信息

- **端点**: `POST /api/v0/data_pipeline/vector/restore`
- **方法**: POST
- **内容类型**: application/json
- **认证**: 无（当前版本）

### 请求参数

| 参数名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `backup_path` | string | 是 | - | 备份文件所在的目录路径（相对路径） |
| `timestamp` | string | 是 | - | 备份文件的时间戳（用于确定具体文件） |
| `tables` | array[string] | 否 | ["langchain_pg_collection", "langchain_pg_embedding"] | 要恢复的表名列表 |
| `db_connection` | string | 否 | null | PostgreSQL连接字符串，不提供则从config获取 |
| `truncate_before_restore` | boolean | 否 | false | 恢复前是否清空目标表 |

### 请求示例

#### 1. 恢复所有表（推荐用法）
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/restore \
  -H "Content-Type: application/json" \
  -d '{
    "backup_path": "./data_pipeline/training_data/task_20250721_213627/vector_bak",
    "timestamp": "20250721_215758",
    "truncate_before_restore": true
  }'
```

#### 2. 仅恢复特定表
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/restore \
  -H "Content-Type: application/json" \
  -d '{
    "backup_path": "./data_pipeline/training_data/vector_bak",
    "timestamp": "20250722_010318",
    "tables": ["langchain_pg_embedding"],
    "truncate_before_restore": false
  }'
```

#### 3. 使用自定义数据库连接
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/restore \
  -H "Content-Type: application/json" \
  -d '{
    "backup_path": "./data_pipeline/training_data/vector_bak",
    "timestamp": "20250722_010318",
    "db_connection": "postgresql://user:password@localhost:5432/target_db",
    "truncate_before_restore": true
  }'
```

### 响应格式

#### 成功响应 (200)

```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "response": "Vector表恢复完成",
    "restore_performed": true,
    "truncate_performed": true,
    "backup_info": {
      "backup_path": "./data_pipeline/training_data/task_20250721_213627/vector_bak",
      "timestamp": "20250721_215758",
      "backup_date": "2025-07-21 21:57:58"
    },
    "truncate_results": {
      "langchain_pg_collection": {
        "success": true,
        "rows_before": 4,
        "rows_after": 0,
        "duration": 0.025
      },
      "langchain_pg_embedding": {
        "success": true,
        "rows_before": 58,
        "rows_after": 0,
        "duration": 0.063
      }
    },
    "restore_results": {
      "langchain_pg_collection": {
        "success": true,
        "source_file": "langchain_pg_collection_20250721_215758.csv",
        "rows_restored": 4,
        "file_size": "209 B",
        "duration": 0.145
      },
      "langchain_pg_embedding": {
        "success": true,
        "source_file": "langchain_pg_embedding_20250721_215758.csv",
        "rows_restored": 58,
        "file_size": "764 KB",
        "duration": 0.678
      }
    },
    "errors": [],
    "duration": 0.911,
    "timestamp": "2025-07-22T10:35:20+08:00"
  }
}
```

#### 部分失败响应 (200)

```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "response": "Vector表恢复部分完成，部分表恢复失败",
    "restore_performed": true,
    "truncate_performed": false,
    "backup_info": {
      "backup_path": "./data_pipeline/training_data/vector_bak",
      "timestamp": "20250722_010318",
      "backup_date": "2025-07-22 01:03:18"
    },
    "restore_results": {
      "langchain_pg_collection": {
        "success": true,
        "source_file": "langchain_pg_collection_20250722_010318.csv",
        "rows_restored": 4,
        "file_size": "209 B",
        "duration": 0.134
      },
      "langchain_pg_embedding": {
        "success": false,
        "source_file": "langchain_pg_embedding_20250722_010318.csv",
        "error": "文件读取失败: [Errno 2] No such file or directory"
      }
    },
    "errors": ["langchain_pg_embedding表恢复失败"],
    "duration": 0.234,
    "timestamp": "2025-07-22T10:35:20+08:00"
  }
}
```

#### 错误响应

##### 文件不存在 (404)
```json
{
  "code": 404,
  "success": false,
  "message": "资源未找到",
  "data": {
    "response": "备份文件不存在: ./data_pipeline/training_data/vector_bak/langchain_pg_collection_20250722_999999.csv",
    "error_type": "RESOURCE_NOT_FOUND",
    "timestamp": "2025-07-22T10:35:20+08:00"
  }
}
```

##### 参数错误 (400)
```json
{
  "code": 400,
  "success": false,
  "message": "请求参数错误",
  "data": {
    "response": "缺少必需参数: backup_path, timestamp",
    "error_type": "MISSING_REQUIRED_PARAMS",
    "missing_params": ["backup_path", "timestamp"],
    "timestamp": "2025-07-22T10:35:20+08:00"
  }
}
```

##### 数据库错误 (500)
```json
{
  "code": 500,
  "success": false,
  "message": "系统内部错误",
  "data": {
    "response": "数据库连接失败，请检查连接配置",
    "error_type": "DATABASE_ERROR",
    "can_retry": true,
    "timestamp": "2025-07-22T10:35:20+08:00"
  }
}
```

---

## 功能详细设计

### 1. 文件扫描逻辑（列表API）

#### 目录扫描策略
1. **基础目录**: 从 `data_pipeline/config.py` 的 `output_directory` 配置获取
2. **全局备份**: 扫描 `{output_directory}/vector_bak/`
3. **任务备份**: 扫描 `{output_directory}/task_*/vector_bak/` 和 `{output_directory}/manual_*/vector_bak/`

#### 文件匹配算法
```python
def find_backup_sets(backup_dir):
    """查找备份集（同时存在collection和embedding文件的时间戳）"""
    collection_files = glob.glob(f"{backup_dir}/langchain_pg_collection_*.csv")
    embedding_files = glob.glob(f"{backup_dir}/langchain_pg_embedding_*.csv")
    
    # 提取时间戳
    collection_timestamps = set(extract_timestamp(f) for f in collection_files)
    embedding_timestamps = set(extract_timestamp(f) for f in embedding_files)
    
    # 找到同时存在两个文件的时间戳
    valid_timestamps = collection_timestamps & embedding_timestamps
    
    return sorted(valid_timestamps, reverse=True)  # 最新的在前
```

#### 跨平台兼容性
- 使用 `Path` 对象处理路径，自动适配Windows和Linux
- 相对路径始终使用Unix风格（`/`）进行返回，确保API响应的一致性
- 文件大小格式化使用统一的 `_format_file_size()` 函数

### 2. 数据恢复逻辑（恢复API）

#### 恢复流程
1. **参数验证**: 验证备份路径、时间戳、表名等
2. **文件检查**: 确认备份文件存在且可读
3. **数据库连接**: 建立目标数据库连接
4. **表清空**（可选）: 执行 TRUNCATE 操作
5. **数据导入**: 使用 PostgreSQL COPY 命令导入CSV
6. **结果验证**: 检查导入的行数是否正确
7. **日志记录**: 记录详细的恢复操作日志

#### 数据导入实现
```python
 def restore_table_from_csv(self, table_name: str, csv_file: Path) -> Dict[str, Any]:
     """从CSV文件恢复表数据 - 使用相对路径即可"""
     try:
         start_time = time.time()
         
         with self.get_connection() as conn:
             with conn.cursor() as cursor:
                 # 使用COPY FROM STDIN命令高效导入（不需要绝对路径）
                 with open(csv_file, 'r', encoding='utf-8') as f:
                     # 跳过CSV头部
                     next(f)
                     cursor.copy_expert(
                         f"COPY {table_name} FROM STDIN WITH CSV",
                         f
                     )
                 
                 # 验证导入结果
                 cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                 rows_restored = cursor.fetchone()[0]
         
         duration = time.time() - start_time
         file_size = csv_file.stat().st_size
         
         return {
             "success": True,
             "source_file": csv_file.name,
             "rows_restored": rows_restored,
             "file_size": self._format_file_size(file_size),
             "duration": duration
         }
         
     except Exception as e:
         return {
             "success": False,
             "source_file": csv_file.name,
             "error": str(e)
         }
```

#### 错误处理策略
- **文件级错误**: 文件不存在、权限不足、格式错误
- **数据库级错误**: 连接失败、表不存在、权限不足
- **数据级错误**: CSV格式不匹配、数据类型错误、约束冲突

#### 回滚策略
- 如果 `truncate_before_restore=true`，在数据导入失败时不进行自动回滚
- 建议用户在重要操作前先创建备份
- 提供详细的错误信息帮助用户手动修复

### 3. 数据库连接管理

#### 连接优先级
1. **显式连接**: 请求参数中的 `db_connection`
2. **配置连接**: `data_pipeline.config.SCHEMA_TOOLS_CONFIG.default_db_connection`
3. **默认连接**: `app_config.PGVECTOR_CONFIG`

#### 连接字符串格式
```
postgresql://username:password@host:port/database
```

#### 临时连接配置
```python
# 临时修改数据库连接（恢复API中使用）
original_config = None
if db_connection:
    from data_pipeline.config import SCHEMA_TOOLS_CONFIG
    original_config = SCHEMA_TOOLS_CONFIG.get("default_db_connection")
    SCHEMA_TOOLS_CONFIG["default_db_connection"] = db_connection

try:
    # 执行恢复操作
    pass
finally:
    # 恢复原始配置
    if original_config is not None:
        SCHEMA_TOOLS_CONFIG["default_db_connection"] = original_config
```

### 4. 性能优化

#### 大文件处理
- 使用 PostgreSQL 的 COPY 命令进行高效批量导入
- 支持大型CSV文件（GB级别）的流式处理
- 避免将整个文件加载到内存中

#### 并发考虑
- 单个API调用中串行处理多个表（避免锁竞争）
- 支持多个API调用并发执行（不同的备份恢复操作）

#### 内存优化
- 使用流式CSV读取，逐行处理
- 避免缓存大量数据在内存中
- 及时释放数据库连接和文件句柄

---

## 实现架构

### 实现方式（与现有备份API保持一致）

**核心实现位置**：在 `unified_api.py` 中直接添加两个新路由

```python
# 在 unified_api.py 中添加以下两个路由：

@app.route('/api/v0/data_pipeline/vector/restore/list', methods=['GET'])
def list_vector_backups():
    """列出可用的vector表备份文件"""
    # 实现列表API逻辑
    
@app.route('/api/v0/data_pipeline/vector/restore', methods=['POST'])
def restore_vector_tables():
    """恢复vector表数据"""
    # 实现恢复API逻辑
```

### 文件结构（极简实现）

```
# 新增核心实现类
data_pipeline/api/
├── vector_restore_manager.py # 新增：VectorRestoreManager类
└── ...

# 复用现有文件
data_pipeline/
├── config.py                 # 复用：配置管理
└── trainer/
    └── vector_table_manager.py  # 参考：数据库连接逻辑

common/
└── result.py                 # 复用：标准响应格式

# 修改现有文件  
unified_api.py                # 修改：添加两个新路由（约100行代码）
```

### 实现架构详细说明

#### 1. VectorRestoreManager 类 (新增文件)
**文件位置**: `data_pipeline/api/vector_restore_manager.py`

```python
class VectorRestoreManager:
    """Vector表恢复管理器 - 仿照VectorTableManager设计"""
    
    def __init__(self, base_output_dir: str = None):
        """初始化恢复管理器，复用现有配置机制"""
        
    def scan_backup_files(self, global_only: bool = False, task_id: str = None) -> Dict[str, Any]:
        """扫描可用的备份文件"""
        
    def restore_from_backup(self, backup_path: str, timestamp: str, 
                          tables: List[str] = None, db_connection: str = None,
                          truncate_before_restore: bool = False) -> Dict[str, Any]:
        """从备份文件恢复数据"""
        
    def get_connection(self):
        """获取数据库连接 - 完全复用VectorTableManager的连接逻辑"""
        
    def _restore_table_from_csv(self, table_name: str, csv_file: Path) -> Dict[str, Any]:
        """从CSV文件恢复单个表 - 使用COPY FROM STDIN"""
```

#### 2. API路由实现 (修改现有文件)
**文件位置**: `unified_api.py` (在现有备份API附近添加)

```python
@app.route('/api/v0/data_pipeline/vector/restore/list', methods=['GET'])
def list_vector_backups():
    """列出可用的vector表备份文件 - 约40行代码"""
    try:
        # 解析查询参数
        global_only = request.args.get('global_only', 'false').lower() == 'true'
        task_id = request.args.get('task_id')
        
        # 使用VectorRestoreManager扫描
        restore_manager = VectorRestoreManager()
        result = restore_manager.scan_backup_files(global_only, task_id)
        
        # 返回标准格式
        return jsonify(success_response(
            response_text=f"成功扫描到 {len(result['backup_locations'])} 个备份位置",
            data=result
        )), 200
        
    except Exception as e:
        return jsonify(internal_error_response("扫描备份文件失败")), 500
    
@app.route('/api/v0/data_pipeline/vector/restore', methods=['POST'])
def restore_vector_tables():
    """恢复vector表数据 - 约60行代码"""
    try:
        req = request.get_json()
        # 参数解析和验证...
        
        # 执行恢复
        restore_manager = VectorRestoreManager()
        result = restore_manager.restore_from_backup(...)
        
        # 返回结果
        return jsonify(success_response(
            response_text="Vector表恢复完成",
            data=result
        )), 200
        
    except Exception as e:
        return jsonify(internal_error_response("Vector表恢复失败")), 500
```

### 实现工作量总结

| 组件 | 文件 | 工作量 | 说明 |
|------|------|--------|------|
| **核心类** | `data_pipeline/api/vector_restore_manager.py` | 新增 ~200行 | 扫描和恢复逻辑 |
| **API路由** | `unified_api.py` | 新增 ~100行 | 两个路由函数 |
| **总计** | | **~300行代码** | 复用现有架构 |

### 实现步骤
1. **创建VectorRestoreManager类** - 仿照现有VectorTableManager
2. **在unified_api.py中添加两个路由** - 紧邻现有备份API
3. **测试验证** - 确保与现有备份文件兼容

---

## 与现有系统的集成

### 1. 配置复用
- 复用 `data_pipeline/config.py` 的 `output_directory` 配置
- 复用现有的数据库连接配置机制
- 复用 `vector_table_management` 配置节

### 2. 工具复用
- 复用 `VectorTableManager` 的数据库连接逻辑
- 复用 `common/result.py` 的标准响应格式
- 复用现有的日志记录机制 [[memory:3840221]]

### 3. 文件格式兼容
- 完全兼容现有备份API生成的CSV文件格式
- 支持所有现有的备份文件命名规范
- 与现有备份日志格式保持一致

### 4. 错误处理统一
- 使用相同的错误分类和响应码
- 复用现有的参数验证逻辑
- 保持错误消息的一致性

---

## 安全考虑

### 1. 路径安全
- 验证备份路径，防止路径遍历攻击
- 限制只能访问训练数据目录下的文件
- 使用相对路径和 `Path` 对象进行安全的路径处理

### 2. 文件安全
- 验证CSV文件格式，防止恶意文件
- 检查文件大小限制，防止资源耗尽
- 使用安全的文件读取方式

### 3. 数据库安全
- 使用参数化查询，防止SQL注入
- 验证表名，限制只能操作指定的vector表
- 正确处理数据库连接，避免连接泄露

### 4. 输入验证
- 严格验证所有API参数
- 使用正则表达式验证task_id格式
- 检查时间戳格式的有效性

---

## 测试策略

### 1. 单元测试
- 文件扫描逻辑测试
- CSV解析和恢复逻辑测试
- 错误处理流程测试

### 2. 集成测试
- 端到端备份和恢复流程测试
- 与现有备份API的兼容性测试
- 跨平台路径处理测试

### 3. 性能测试
- 大文件恢复性能测试
- 并发恢复操作测试
- 内存使用情况监控

### 4. 错误场景测试
- 文件不存在情况
- 数据库连接失败情况
- 磁盘空间不足情况

---

## 部署说明

### 1. 依赖要求
- Python 3.8+
- psycopg2-binary
- 现有的项目依赖

### 2. 配置要求
- 确保 `data_pipeline/config.py` 配置正确
- 确保数据库连接配置可用
- 确保目标数据库有相应的表结构

### 3. 权限要求
- 文件系统读取权限（访问备份文件）
- 数据库写入权限（INSERT、TRUNCATE）
- 临时文件创建权限

---

## 使用场景

### 1. 数据迁移
```bash
# 1. 列出源环境的备份
curl "http://source-server:8084/api/v0/data_pipeline/vector/restore/list"

# 2. 复制备份文件到目标环境

# 3. 在目标环境恢复数据
curl -X POST http://target-server:8084/api/v0/data_pipeline/vector/restore \
  -d '{"backup_path": "./data_pipeline/training_data/vector_bak", "timestamp": "20250722_010318"}'
```

### 2. 数据回滚
```bash
# 1. 查找回滚点
curl "http://localhost:8084/api/v0/data_pipeline/vector/restore/list?task_id=task_20250721_213627"

# 2. 恢复到指定时间点
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/restore \
  -d '{"backup_path": "./data_pipeline/training_data/task_20250721_213627/vector_bak", "timestamp": "20250721_215758", "truncate_before_restore": true}'
```

### 3. 部分数据恢复
```bash
# 仅恢复embedding表
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/restore \
  -d '{"backup_path": "./data_pipeline/training_data/vector_bak", "timestamp": "20250722_010318", "tables": ["langchain_pg_embedding"], "truncate_before_restore": false}'
```

---

## 总结

这两个恢复备份API将提供：

✅ **完整的备份文件管理** - 智能扫描和列出所有可用备份  
✅ **灵活的恢复选项** - 支持全量/部分恢复、清空/追加模式  
✅ **跨平台兼容性** - 同时支持Windows和Ubuntu系统  
✅ **高性能数据处理** - 使用PostgreSQL COPY命令高效导入  
✅ **完善的错误处理** - 详细的错误信息和恢复建议  
✅ **标准化API设计** - 复用现有的响应格式和错误处理  
✅ **安全的文件操作** - 防止路径遍历和文件安全风险  
✅ **与现有系统兼容** - 完全兼容现有备份文件格式  

这个设计充分利用了现有的系统组件，提供了完整而强大的vector表备份恢复功能！ 