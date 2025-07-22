# Vector 恢复备份 API 用户指南

## 📖 概述

Vector恢复备份API提供了完整的pgvector表数据恢复功能，包括备份文件列表查询和数据恢复操作。这套API与现有的备份API形成完整的数据管理解决方案。

## 🔧 前置条件

1. **服务运行**: 确保统一API服务正在运行
   ```bash
   python unified_api.py
   ```

2. **数据库连接**: 确保pgvector数据库连接正常

3. **备份文件**: 确保存在可用的备份文件（通过备份API创建）

## 📋 API 1: 备份文件列表查询

### 基本信息
- **端点**: `GET /api/v0/data_pipeline/vector/restore/list`
- **功能**: 扫描并列出所有可用的vector表备份文件
- **返回**: 结构化的备份文件列表信息

### 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `global_only` | boolean | 否 | false | 仅查询全局备份（`training_data/vector_bak/`目录） |
| `task_id` | string | 否 | - | 查询指定任务的备份文件 |

### 参数说明

#### 1. 查询所有备份文件（默认）
```bash
curl "http://localhost:8084/api/v0/data_pipeline/vector/restore/list"
```

#### 2. 仅查询全局备份
```bash
curl "http://localhost:8084/api/v0/data_pipeline/vector/restore/list?global_only=true"
```

#### 3. 查询特定任务的备份
```bash
curl "http://localhost:8084/api/v0/data_pipeline/vector/restore/list?task_id=task_20250721_213627"
```

### 响应格式

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

### 响应字段说明

#### backup_locations 数组
- **type**: 备份类型（`global` 或 `task`）
- **task_id**: 任务ID（仅task类型有此字段）
- **relative_path**: 相对路径（Unix风格）
- **backups**: 该位置下的备份集数组

#### backups 数组中的备份信息
- **timestamp**: 备份时间戳（格式：YYYYMMDD_HHMMSS）
- **collection_file**: collection表备份文件名
- **embedding_file**: embedding表备份文件名
- **collection_size**: collection文件大小（可读格式）
- **embedding_size**: embedding文件大小（可读格式）
- **backup_date**: 备份日期（可读格式）
- **has_log**: 是否有备份日志文件
- **log_file**: 日志文件名

#### summary 汇总信息
- **total_locations**: 扫描到的备份位置总数
- **total_backup_sets**: 备份集总数
- **global_backups**: 全局备份数量
- **task_backups**: 任务备份数量
- **scan_time**: 扫描时间戳

## 🔄 API 2: 备份数据恢复

### 基本信息
- **端点**: `POST /api/v0/data_pipeline/vector/restore`
- **功能**: 从备份文件恢复vector表数据到PostgreSQL数据库
- **支持**: 全量恢复、部分表恢复、数据清空等选项

### 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `backup_path` | string | ✅ | - | 备份文件目录路径（相对路径） |
| `timestamp` | string | ✅ | - | 备份时间戳（YYYYMMDD_HHMMSS格式） |
| `tables` | array | 否 | null | 要恢复的表名列表，空则恢复所有表 |
| `pg_conn` | string | 否 | null | 自定义PostgreSQL连接字符串 |
| `truncate_before_restore` | boolean | 否 | false | 恢复前是否清空目标表 |

### 参数详细说明

#### backup_path（必填）
- **格式**: 相对路径，Unix风格斜杠
- **示例**: `"./data_pipeline/training_data/vector_bak"`
- **示例**: `"./data_pipeline/training_data/task_20250721_213627/vector_bak"`

#### timestamp（必填）
- **格式**: `YYYYMMDD_HHMMSS`
- **示例**: `"20250721_215758"`
- **说明**: 必须与备份文件名中的时间戳匹配

#### tables（可选）
- **格式**: 字符串数组
- **可选值**: `["langchain_pg_collection"]`, `["langchain_pg_embedding"]`, `["langchain_pg_collection", "langchain_pg_embedding"]`
- **默认**: `null`（恢复所有表）

#### pg_conn（可选）
- **格式**: PostgreSQL连接字符串
- **示例**: `"postgresql://user:password@host:port/database"`
- **默认**: 使用配置文件中的连接信息

#### truncate_before_restore（可选）
- **类型**: 布尔值
- **默认**: `false`
- **说明**: 
  - `true`: 恢复前清空目标表（推荐用于生产环境）
  - `false`: 直接追加数据（可能导致主键冲突）

### 使用示例

#### 1. 基本恢复（推荐）
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/restore \
  -H "Content-Type: application/json" \
  -d '{
    "backup_path": "./data_pipeline/training_data/task_20250721_213627/vector_bak",
    "timestamp": "20250721_215758",
    "truncate_before_restore": true
  }'
```

#### 2. 仅恢复embedding表
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

### 响应格式

#### 成功响应
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

### 响应字段说明

#### 顶层字段
- **restore_performed**: 是否执行了恢复操作
- **truncate_performed**: 是否执行了清空操作
- **backup_info**: 备份信息
- **truncate_results**: 清空操作结果
- **restore_results**: 恢复操作结果
- **errors**: 错误信息数组
- **duration**: 总耗时（秒）

#### truncate_results 字段
- **success**: 清空是否成功
- **rows_before**: 清空前的行数
- **rows_after**: 清空后的行数
- **duration**: 清空耗时（秒）

#### restore_results 字段
- **success**: 恢复是否成功
- **source_file**: 源CSV文件名
- **rows_restored**: 恢复的行数
- **file_size**: 文件大小（可读格式）
- **duration**: 恢复耗时（秒）
- **error**: 错误信息（仅失败时出现）

## ⚠️ 错误处理

### 常见错误类型

#### 1. 参数错误（400）
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

#### 2. 文件未找到（404）
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

#### 3. 数据库错误（500）
```json
{
  "code": 500,
  "success": false,
  "message": "系统内部错误",
  "data": {
    "response": "数据库连接失败，请稍后重试",
    "error_type": "DATABASE_ERROR",
    "timestamp": "2025-07-22T10:35:20+08:00"
  }
}
```

## 🎯 使用场景

### 1. 数据迁移
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

### 2. 数据回滚
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

### 3. 部分数据恢复
```bash
# 仅恢复embedding表，不影响collection表
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/restore \
  -H "Content-Type: application/json" \
  -d '{
    "backup_path": "./data_pipeline/training_data/vector_bak",
    "timestamp": "20250722_010318",
    "tables": ["langchain_pg_embedding"],
    "truncate_before_restore": false
  }'
```

## 💡 最佳实践

### 1. 恢复前准备
- ✅ 确认目标数据库连接正常
- ✅ 如果是重要数据，建议先创建当前数据的备份
- ✅ 确认备份文件的完整性（collection和embedding文件都存在）
- ✅ 检查目标数据库的存储空间

### 2. 参数选择建议
- **生产环境**: 建议使用 `truncate_before_restore: true` 确保数据干净
- **测试环境**: 可以使用 `truncate_before_restore: false` 进行数据叠加测试
- **部分恢复**: 仅在明确知道影响范围时使用 `tables` 参数
- **跨环境**: 使用 `pg_conn` 参数指定目标数据库

### 3. 监控和验证
- 📊 关注恢复操作的 `duration` 字段，了解性能表现
- 🔍 检查 `errors` 数组，确保没有恢复失败的表
- ✅ 验证 `rows_restored` 与预期的数据量一致
- 📝 查看备份日志文件了解备份时的状态

### 4. 故障排除
- 🔧 如果恢复失败，检查错误信息中的具体原因
- 🔐 确认数据库连接配置和权限设置
- 📁 验证备份文件的格式和完整性
- 🌐 检查网络连接和防火墙设置

## 📊 性能参考

根据测试，恢复性能参考：

| 数据量级 | Collection表 | Embedding表 | 总耗时 | 说明 |
|----------|-------------|-------------|--------|------|
| 小量数据（< 100行） | < 0.1s | < 0.7s | < 1s | 开发测试环境 |
| 中等数据（< 10K行） | < 0.5s | < 3s | < 4s | 小型生产环境 |
| 大量数据（< 100K行） | < 2s | < 15s | < 20s | 中型生产环境 |
| 超大数据（> 100K行） | < 10s | < 60s | < 80s | 大型生产环境 |

*注：实际性能取决于数据库配置、硬件性能和网络状况*

## 🔗 相关API

- **备份API**: `POST /api/v0/data_pipeline/vector/backup` - 创建vector表备份
- **健康检查**: `GET /health` - 检查API服务状态
- **训练数据API**: `/api/v0/training_data/*` - 训练数据管理

## 📞 技术支持

如果遇到问题，请检查：

1. **API服务状态**: 访问 `http://localhost:8084/health`
2. **数据库连接**: 检查连接字符串和权限
3. **文件权限**: 确保API有读取备份文件的权限
4. **日志文件**: 查看 `logs/app.log` 了解详细错误信息

---

**文档版本**: v1.0  
**最后更新**: 2025-07-22  
**适用版本**: unified_api.py v1.0+ 