# PgVector 恢复备份 API 使用示例

## 概述

本文档提供了Vector恢复备份API的具体使用示例，帮助您快速上手。

## 前置条件

1. 确保服务正在运行：`http://localhost:8084`
2. 确保有可用的备份文件（通过备份API创建）

## API 1: 列出备份文件

### 基本用法

#### 1. 查询所有备份文件
```bash
curl "http://localhost:8084/api/v0/data_pipeline/vector/restore/list"
```

**响应示例**：
```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    "response": "成功扫描到 6 个备份位置，共 6 个备份集",
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
      }
    ],
    "summary": {
      "total_locations": 6,
      "total_backup_sets": 6,
      "global_backups": 1,
      "task_backups": 5,
      "scan_time": "2025-07-22T11:28:25.156158"
    },
    "timestamp": "2025-07-22T11:28:25.156158"
  }
}
```

#### 2. 仅查询全局备份
```bash
curl "http://localhost:8084/api/v0/data_pipeline/vector/restore/list?global_only=true"
```

#### 3. 查询特定任务的备份
```bash
curl "http://localhost:8084/api/v0/data_pipeline/vector/restore/list?task_id=task_20250721_213627"
```

## API 2: 恢复备份数据

### 基本用法

#### 1. 恢复所有表（推荐）
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/restore \
  -H "Content-Type: application/json" \
  -d '{
    "backup_path": "./data_pipeline/training_data/task_20250721_213627/vector_bak",
    "timestamp": "20250721_215758",
    "truncate_before_restore": true
  }'
```

**响应示例**：
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
    "pg_conn": "postgresql://user:password@localhost:5432/target_db",
    "truncate_before_restore": true
  }'
```

## 实际使用场景

### 场景1: 数据迁移

```bash
# 步骤1: 在源环境列出备份
curl "http://source-server:8084/api/v0/data_pipeline/vector/restore/list"

# 步骤2: 复制备份文件到目标环境（手动操作）
# scp source:/path/to/backups/* target:/path/to/backups/

# 步骤3: 在目标环境恢复数据
curl -X POST http://target-server:8084/api/v0/data_pipeline/vector/restore \
  -H "Content-Type: application/json" \
  -d '{
    "backup_path": "./data_pipeline/training_data/vector_bak",
    "timestamp": "20250722_010318",
    "truncate_before_restore": true
  }'
```

### 场景2: 数据回滚

```bash
# 步骤1: 查找回滚点
curl "http://localhost:8084/api/v0/data_pipeline/vector/restore/list?task_id=task_20250721_213627"

# 步骤2: 恢复到指定时间点
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/restore \
  -H "Content-Type: application/json" \
  -d '{
    "backup_path": "./data_pipeline/training_data/task_20250721_213627/vector_bak",
    "timestamp": "20250721_215758",
    "truncate_before_restore": true
  }'
```

### 场景3: 部分数据恢复

```bash
# 仅恢复embedding表
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/restore \
  -H "Content-Type: application/json" \
  -d '{
    "backup_path": "./data_pipeline/training_data/vector_bak",
    "timestamp": "20250722_010318",
    "tables": ["langchain_pg_embedding"],
    "truncate_before_restore": false
  }'
```

## 错误处理示例

### 备份文件不存在
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/restore \
  -H "Content-Type: application/json" \
  -d '{
    "backup_path": "./data_pipeline/training_data/nonexistent",
    "timestamp": "20250722_999999"
  }'
```

**错误响应**：
```json
{
  "code": 404,
  "success": false,
  "message": "资源未找到",
  "data": {
    "response": "备份目录不存在: ./data_pipeline/training_data/nonexistent",
    "error_type": "RESOURCE_NOT_FOUND",
    "timestamp": "2025-07-22T10:35:20+08:00"
  }
}
```

### 参数错误
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/restore \
  -H "Content-Type: application/json" \
  -d '{}'
```

**错误响应**：
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

## 最佳实践

### 1. 恢复前的准备
- 确认目标数据库连接正常
- 如果是重要数据，建议先创建当前数据的备份
- 确认备份文件的完整性

### 2. 参数选择建议
- **生产环境**: 建议使用 `truncate_before_restore: true` 确保数据干净
- **测试环境**: 可以使用 `truncate_before_restore: false` 进行数据叠加测试
- **部分恢复**: 仅在明确知道影响范围时使用 `tables` 参数

### 3. 监控和日志
- 关注恢复操作的 `duration` 字段，了解性能表现
- 检查 `errors` 数组，确保没有恢复失败的表
- 验证 `rows_restored` 与预期的数据量一致

### 4. 错误恢复
- 如果恢复失败，检查错误信息中的具体原因
- 确认数据库连接配置和权限设置
- 验证备份文件的格式和完整性

## 性能参考

根据测试，恢复性能参考：

| 数据量 | Collection表 | Embedding表 | 总耗时 |
|--------|-------------|-------------|--------|
| 小量数据 | < 0.1s | < 0.7s | < 1s |
| 中等数据 | < 0.5s | < 3s | < 4s |
| 大量数据 | < 2s | < 15s | < 20s |

*注：实际性能取决于数据库配置和硬件性能* 