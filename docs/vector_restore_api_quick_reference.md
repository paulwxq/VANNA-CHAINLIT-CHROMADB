# Vector 恢复备份 API 快速参考

## 🚀 快速开始

### 启动服务
```bash
python unified_api.py
```

### 1. 查看所有备份
```bash
curl "http://localhost:8084/api/v0/data_pipeline/vector/restore/list"
```

### 2. 恢复备份（推荐用法）
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/vector/restore \
  -H "Content-Type: application/json" \
  -d '{
    "backup_path": "./data_pipeline/training_data/task_20250721_213627/vector_bak",
    "timestamp": "20250721_215758",
    "truncate_before_restore": true
  }'
```

## 📋 API 概览

| API | 方法 | 端点 | 功能 |
|-----|------|------|------|
| 列表API | GET | `/api/v0/data_pipeline/vector/restore/list` | 查看所有备份文件 |
| 恢复API | POST | `/api/v0/data_pipeline/vector/restore` | 恢复备份数据 |

## 🔧 常用参数

### 列表API参数
- `global_only=true` - 仅查看全局备份
- `task_id=xxx` - 查看指定任务备份

### 恢复API参数（必填）
- `backup_path` - 备份目录路径
- `timestamp` - 时间戳（YYYYMMDD_HHMMSS）

### 恢复API参数（可选）
- `truncate_before_restore: true` - 清空后恢复（推荐）
- `tables: ["langchain_pg_embedding"]` - 仅恢复指定表
- `pg_conn: "postgresql://..."` - 自定义数据库连接

## 📝 常用命令

### 查看特定任务备份
```bash
curl "http://localhost:8084/api/v0/data_pipeline/vector/restore/list?task_id=task_20250721_213627"
```

### 查看全局备份
```bash
curl "http://localhost:8084/api/v0/data_pipeline/vector/restore/list?global_only=true"
```

### 仅恢复embedding表
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

### 跨数据库恢复
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

## ⚠️ 注意事项

- ✅ **生产环境**：建议使用 `truncate_before_restore: true`
- ⚠️ **备份路径**：使用Unix风格路径（`./data_pipeline/...`）
- 📅 **时间戳格式**：必须是 `YYYYMMDD_HHMMSS` 格式
- 🔄 **文件完整性**：确保collection和embedding文件都存在

## 🐛 常见错误

### 参数缺失
```bash
# 错误：缺少必填参数
{"code": 400, "message": "缺少必需参数: backup_path, timestamp"}
```

### 文件不存在
```bash
# 错误：备份文件不存在
{"code": 404, "message": "备份目录不存在"}
```

### JSON格式问题
```bash
# 已修复：cmetadata列JSON格式自动转换
# 无需手动处理Python字典格式问题
```

## 🎯 常见场景

### 数据回滚
1. 查找历史备份点
2. 使用 `truncate_before_restore: true` 恢复

### 数据迁移  
1. 在源环境列出备份
2. 复制备份文件到目标环境
3. 在目标环境恢复数据

### 部分恢复
1. 使用 `tables` 参数指定表
2. 设置 `truncate_before_restore: false`

---

**💡 提示**: 详细文档请参考 `vector_restore_api_user_guide.md` 