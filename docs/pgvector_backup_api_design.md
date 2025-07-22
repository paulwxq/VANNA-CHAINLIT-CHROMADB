# PgVector 备份 API 设计文档

## 概述

为系统添加一个专用的 pgvector 表备份 API，支持备份 `langchain_pg_collection` 和 `langchain_pg_embedding` 两张表。该 API **充分复用现有的成熟备份功能**，仅需要薄薄的API封装层。

## 现有功能优势

### ✅ 已有的强大备份功能
现有的 `VectorTableManager` 已经非常完善：

- **🚀 流式处理**: 使用 `cursor.itersize = batch_size` 支持大数据量导出
- **📊 分批处理**: 每批10,000条记录，避免内存溢出，支持TB级数据
- **📈 进度监控**: 每5万条记录报告进度，便于监控长时间任务
- **🔒 原子操作**: 先写入`.tmp`文件，成功后重命名为`.csv`，保证数据完整性
- **📋 完整统计**: 自动记录行数、文件大小、耗时等详细信息
- **⚠️ 错误处理**: 完善的异常处理和临时文件清理机制
- **🔄 事务管理**: 正确的autocommit处理，避免数据库锁定
- **⚙️ 配置化**: 支持可配置的表列表、时间戳格式、备份目录等

### ✅ 已有的智能目录管理
- **📁 灵活路径**: 自动支持task_id目录结构
- **🔧 自动创建**: 智能创建`vector_bak`目录
- **📝 详细日志**: 生成完整的`vector_backup_log.txt`备份日志

### ✅ 已有的多层数据库连接
- **🎯 智能连接**: 现有的 `VectorTableManager` 已包含完善的数据库连接优先级处理
- **🔧 自动适配**: 支持连接字符串和配置对象两种方式

## API 端点设计

### 基本信息

- **端点**: `POST /api/v0/data_pipeline/vector/backup`
- **方法**: POST
- **内容类型**: application/json
- **认证**: 无（当前版本）

### 请求参数

| 参数名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `task_id` | string | 否 | null | 任务ID，如果提供则在该task目录下创建备份 |
| `db_connection` | string | 否 | null | PostgreSQL连接字符串，不提供则从config.py获取 |
| `truncate_vector_tables` | boolean | 否 | false | 备份完成后是否清空vector表 |
| `backup_vector_tables` | boolean | 否 | true | 是否执行备份操作（默认为true，不需要显式设置） |

### 请求示例

#### 1. **空参数调用（最简单的用法）** ⭐
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/backup \
  -H "Content-Type: application/json" \
  -d '{}'
```
**行为**: 在 `data_pipeline/training_data/vector_bak/` 目录下创建备份，使用默认数据库连接。

#### 2. 在指定task_id目录下备份
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/backup \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task_20250721_213627",
    "truncate_vector_tables": false
  }'
```

#### 3. 在training_data目录下备份
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/backup \
  -H "Content-Type: application/json" \
  -d '{
    "truncate_vector_tables": false
  }'
```

#### 4. 备份并清空表
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/backup \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task_20250721_213627",
    "truncate_vector_tables": true
  }'
```

#### 5. 使用自定义数据库连接
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/backup \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task_20250721_213627",
    "db_connection": "postgresql://user:password@localhost:5432/dbname",
    "truncate_vector_tables": false
  }'
```

## 响应格式

### 成功响应

**HTTP状态码**: 200

使用 `common/result.py` 的 `success_response()` 格式：

```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "response": "Vector表备份完成",
    "backup_performed": true,
    "truncate_performed": false,
    "backup_directory": "/path/to/training_data/task_20250721_213627/vector_bak",
    "tables_backed_up": {
      "langchain_pg_collection": {
        "success": true,
        "row_count": 4,
        "file_size": "209.0 B",
        "backup_file": "langchain_pg_collection_20250721_234914.csv",
        "duration": 0.105
      },
      "langchain_pg_embedding": {
        "success": true,
        "row_count": 58,
        "file_size": "764.0 KB",
        "backup_file": "langchain_pg_embedding_20250721_234914.csv",
        "duration": 0.312
      }
    },
    "truncate_results": {
      "langchain_pg_embedding": {
        "success": true,
        "rows_before": 58,
        "rows_after": 0,
        "duration": 0.068
      }
    },
    "errors": [],
    "duration": 0.498,
    "timestamp": "2025-07-21T23:49:14+08:00"
  }
}
```

### 错误响应

**HTTP状态码**: 400/404/500

使用 `common/result.py` 的相应错误响应方法：

#### 参数错误 (400)
```json
{
  "code": 400,
  "success": false,
  "message": "请求参数错误",
  "data": {
    "response": "无效的task_id格式，只能包含字母、数字和下划线",
    "error_type": "INVALID_PARAMS",
    "timestamp": "2025-07-21T23:49:14+08:00"
  }
}
```

#### 任务不存在 (404)
```json
{
  "code": 404,
  "success": false,
  "message": "资源未找到",
  "data": {
    "response": "指定的任务目录不存在: task_20250721_999999",
    "error_type": "RESOURCE_NOT_FOUND",
    "timestamp": "2025-07-21T23:49:14+08:00"
  }
}
```

#### 系统错误 (500)
```json
{
  "code": 500,
  "success": false,
  "message": "系统内部错误",
  "data": {
    "response": "数据库连接失败，请检查连接配置",
    "error_type": "DATABASE_ERROR",
    "can_retry": true,
    "timestamp": "2025-07-21T23:49:14+08:00"
  }
}
```

## 功能详细说明

### 1. 目录结构逻辑

#### 情况1: 提供task_id
- 备份目录: `data_pipeline/training_data/{task_id}/vector_bak/`
- 如果task_id目录不存在，返回404错误
- 如果vector_bak目录不存在，自动创建

#### 情况2: 不提供task_id（空参数 `{}` 调用）
- 备份目录: `data_pipeline/training_data/vector_bak/`
- 如果vector_bak目录不存在，自动创建
- 如果已存在，直接使用

### 2. 文件命名规则

备份文件使用时间戳命名：
- `langchain_pg_collection_{YYYYMMDD_HHMMSS}.csv`
- `langchain_pg_embedding_{YYYYMMDD_HHMMSS}.csv`

示例：
- `langchain_pg_collection_20250721_234914.csv`
- `langchain_pg_embedding_20250721_234914.csv`

### 3. 数据库连接处理

API支持两种连接方式：
1. **自定义连接**: 在请求中提供 `db_connection` 参数
2. **默认连接**: 使用现有系统的配置（由 `VectorTableManager` 自动处理）

#### 连接字符串格式
```
postgresql://username:password@host:port/database
```

### 4. 备份操作流程

1. **参数验证**: 验证task_id、数据库连接等参数
2. **目录创建**: 根据task_id创建或确认备份目录
3. **数据库连接**: 建立数据库连接
4. **表备份**: 逐表执行CSV导出
   - **🚀 流式处理**: 使用`cursor.itersize`分批读取，支持大数据量
   - **📊 进度监控**: 每5万条记录报告进度
   - **🔒 原子操作**: 先导出到.tmp文件，完成后重命名为.csv
   - **📋 详细统计**: 记录行数、文件大小、耗时等统计信息
5. **表清空**（可选): 如果设置了truncate_vector_tables，清空langchain_pg_embedding表
6. **📝 日志记录**: 生成详细的`vector_backup_log.txt`备份日志文件
7. **返回结果**: 返回备份操作的详细结果

### 5. 错误处理

#### 常见错误场景
- task_id目录不存在
- 数据库连接失败
- 磁盘空间不足
- 权限不足（无法执行COPY或TRUNCATE）
- 表不存在

#### 错误响应方法（使用 common/result.py）
- `bad_request_response()`: 参数错误
- `not_found_response()`: 任务不存在
- `internal_error_response()`: 系统内部错误
- `service_unavailable_response()`: 数据库服务不可用

## 极简化实现方案 ⭐

### 1. **仅需要薄薄的API封装层**

```python
# 在 unified_api.py 中直接添加路由，无需新建文件
@app.route('/api/v0/data_pipeline/vector/backup', methods=['POST'])
def backup_pgvector_tables():
    """专用的pgvector表备份API - 直接复用VectorTableManager"""
    try:
        # 支持空参数调用 {}
        req = request.get_json(force=True) if request.is_json else {}
        
        # 解析参数（全部可选）
        task_id = req.get('task_id')
        db_connection = req.get('db_connection')
        truncate_vector_tables = req.get('truncate_vector_tables', False)
        backup_vector_tables = req.get('backup_vector_tables', True)
        
        # 参数验证
        if task_id and not re.match(r'^[a-zA-Z0-9_]+$', task_id):
            return jsonify(bad_request_response(
                "无效的task_id格式，只能包含字母、数字和下划线"
            )), 400
        
        # 确定备份目录
        if task_id:
            # 验证task_id目录是否存在
            task_dir = Path(f"data_pipeline/training_data/{task_id}")
            if not task_dir.exists():
                return jsonify(not_found_response(
                    f"指定的任务目录不存在: {task_id}"
                )), 404
            backup_base_dir = str(task_dir)
        else:
            # 使用training_data根目录（支持空参数调用）
            backup_base_dir = "data_pipeline/training_data"
        
        # 直接使用现有的VectorTableManager
        from data_pipeline.trainer.vector_table_manager import VectorTableManager
        
        # 临时修改数据库连接配置（如果提供了自定义连接）
        original_config = None
        if db_connection:
            from data_pipeline.config import SCHEMA_TOOLS_CONFIG
            original_config = SCHEMA_TOOLS_CONFIG.get("default_db_connection")
            SCHEMA_TOOLS_CONFIG["default_db_connection"] = db_connection
        
        try:
            # 使用现有的成熟管理器
            vector_manager = VectorTableManager(
                task_output_dir=backup_base_dir,
                task_id=task_id or "api_backup"
            )
            
            # 执行备份（完全复用现有逻辑）
            result = vector_manager.execute_vector_management(
                backup=backup_vector_tables,
                truncate=truncate_vector_tables
            )
            
            # 使用 common/result.py 的标准格式
            return jsonify(success_response(
                response_text="Vector表备份完成",
                data=result
            )), 200
            
        finally:
            # 恢复原始配置
            if original_config is not None:
                SCHEMA_TOOLS_CONFIG["default_db_connection"] = original_config
        
    except Exception as e:
        logger.error(f"Vector表备份失败: {str(e)}")
        return jsonify(internal_error_response(
            "Vector表备份失败，请稍后重试"
        )), 500
```

### 2. **文件结构 - 无需新增文件**

```
# 现有文件，无需修改
data_pipeline/
├── trainer/
│   ├── vector_table_manager.py       # ✅ 复用：现有成熟备份逻辑
│   └── ...
└── config.py                         # ✅ 复用：现有配置管理

common/
└── result.py                         # ✅ 复用：标准响应格式

# 仅需修改一个文件
unified_api.py                        # ✅ 修改：添加新路由（约50行代码）
```

### 3. **极简的核心逻辑**

整个API实现只需要：
1. **参数解析和验证** (10行代码)
2. **目录逻辑处理** (10行代码)  
3. **调用现有VectorTableManager** (5行代码)
4. **使用common/result.py格式化响应** (5行代码)

**总计不超过50行代码！**

## 与现有API的关系

### 1. 功能对比

| 功能 | 现有execute API | 新的backup API |
|------|----------------|---------------|
| 用途 | 完整工作流执行的一部分 | 专用的vector表备份 |
| 复杂度 | 复杂（包含多个步骤） | 简单（仅备份功能） |
| 执行时机 | 工作流的特定步骤 | 任何时候独立执行 |
| 参数依赖 | 需要完整的任务配置 | 仅需要备份相关参数（支持空参数） |
| **核心逻辑** | **相同的VectorTableManager** | **相同的VectorTableManager** |
| **响应格式** | **common/result.py** | **common/result.py** |

### 2. 复用程度

- **🎯 100%复用**: `VectorTableManager` 的完整备份逻辑
- **🎯 100%复用**: 数据库连接配置机制
- **🎯 100%复用**: 目录管理和文件命名逻辑
- **🎯 100%复用**: `common/result.py` 标准响应格式
- **🆕 仅新增**: 薄薄的API参数处理层（50行代码）

### 3. 兼容性

- ✅ 新API不影响现有的execute API功能
- ✅ 两个API可以并行使用
- ✅ 备份文件格式完全一致
- ✅ 配置系统完全共享
- ✅ 响应格式完全统一

## 性能优势 🚀

### 1. 大数据量处理能力
- **流式处理**: 支持TB级数据导出而不会内存溢出
- **分批读取**: 每批10,000条记录，保证性能稳定
- **进度监控**: 实时监控大文件导出进度

### 2. 高效的文件操作
- **原子写入**: `.tmp` → `.csv` 重命名保证文件完整性
- **UTF-8编码**: 正确处理中文等多字节字符
- **自动清理**: 失败时自动清理临时文件

### 3. 数据库优化
- **事务管理**: 正确的autocommit处理避免长时间锁表
- **连接复用**: 高效的数据库连接管理
- **批量操作**: 避免逐行处理的性能问题

## 使用场景

### 1. 定期备份
```bash
# 每日定时备份到独立目录（支持大数据量）
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/backup \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 2. 任务相关备份
```bash
# 在特定任务执行前备份（流式处理，不会阻塞）
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/backup \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task_20250721_213627",
    "truncate_vector_tables": true
  }'
```

### 3. 数据迁移
```bash
# 备份现有数据用于迁移（支持TB级数据）
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/backup \
  -H "Content-Type: application/json" \
  -d '{
    "db_connection": "postgresql://source_user:pass@source_host:5432/source_db"
  }'
```

## 后续扩展

### 1. 可能的增强功能
- 支持增量备份
- 压缩备份文件
- 远程存储集成（S3、OSS等）
- 备份文件自动清理

### 2. 集成计划
- 与现有任务系统集成
- 备份状态查询API
- 备份文件下载API

## 总结

这个**极简化的专用pgvector备份API**将：

✅ **100%复用现有成熟功能** - 无重复开发  
✅ **仅需50行新代码** - 最小化实现成本  
✅ **支持TB级大数据量** - 流式处理能力  
✅ **完美兼容现有系统** - 零影响集成  
✅ **提供简单独立接口** - 专用备份功能  
✅ **使用标准响应格式** - 复用common/result.py  
✅ **支持空参数调用** - 最简单的使用方式  

这是一个**真正充分利用现有功能**的设计方案！ 