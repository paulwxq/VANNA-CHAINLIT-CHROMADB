# Data Pipeline API 配置变更说明

## 变更概述

基于用户需求，Data Pipeline API 进行了重要的配置变更，主要目的是：

1. **简化API调用**：移除 `db_connection` 必填参数
2. **统一配置管理**：使用 `app_config.py` 中的配置
3. **明确数据库职责**：任务管理表存储在向量数据库中

## 主要变更内容

### 1. API参数变更

#### 变更前
```json
{
  "db_connection": "postgresql://user:pass@host:5432/dbname",  // 必填
  "table_list_file": "tables.txt",
  "business_context": "业务描述"
}
```

#### 变更后
```json
{
  "table_list_file": "tables.txt",                            // 必填
  "business_context": "业务描述",                            // 必填
  "db_name": "highway_db"                                     // 可选
}
```

### 2. 数据库连接配置

#### 业务数据库连接
- **配置来源**: `app_config.py` 中的 `APP_DB_CONFIG`
- **用途**: Schema分析和训练数据生成的源数据库
- **自动构建**: 系统自动构建连接字符串用于 `schema_workflow` 执行

#### 任务管理数据库连接
- **配置来源**: `app_config.py` 中的 `PGVECTOR_CONFIG`
- **用途**: 存储任务状态、执行记录、日志等管理信息
- **表结构**: 4个管理表都创建在向量数据库中

### 3. 代码变更清单

#### 修改的文件：

1. **`data_pipeline/api/simple_db_manager.py`**
   - 修改 `create_task()` 方法签名
   - 移除 `db_connection` 必填参数
   - 添加 `_build_db_connection_string()` 方法
   - 从 `APP_DB_CONFIG` 自动获取业务数据库配置

2. **`data_pipeline/api/simple_workflow.py`**
   - 修改 `SimpleWorkflowManager.create_task()` 方法
   - 更新参数传递逻辑

3. **`citu_app.py`**
   - 更新 `/api/v0/data_pipeline/tasks` POST 接口
   - 移除 `db_connection` 参数验证
   - 添加可选的 `db_name` 参数支持

4. **文档更新**
   - `docs/data_pipeline_api_usage_guide.md`
   - `docs/data_pipeline_api_design.md`
   - 更新API调用示例和参数说明

## 数据库架构

### 双数据库设计

```
┌─────────────────────┐       ┌─────────────────────┐
│   业务数据库        │       │   向量数据库        │
│  (APP_DB_CONFIG)    │       │  (PGVECTOR_CONFIG)  │
├─────────────────────┤       ├─────────────────────┤
│ • 业务表数据        │       │ • 任务管理表        │
│ • Schema信息        │  ───→ │ • 执行记录表        │
│ • 训练数据源        │       │ • 日志表            │
│                     │       │ • 文件输出表        │
└─────────────────────┘       └─────────────────────┘
      ↑                              ↑
      │                              │
 schema_workflow              SimpleTaskManager
  数据处理执行                    任务状态管理
```

## 向前兼容性

### API兼容性
- **破坏性变更**: 是的，移除了 `db_connection` 必填参数
- **迁移方案**: 
  1. 更新API调用代码，移除 `db_connection` 参数
  2. 确保 `app_config.py` 中正确配置了 `APP_DB_CONFIG`
  3. 可选择性添加 `db_name` 参数指定特定数据库

### 数据库兼容性
- **表结构**: 无变更，继续使用现有的4个管理表
- **存储位置**: 确保表创建在向量数据库中
- **初始化**: 使用 `data_pipeline/sql/init_tables.sql` 在向量数据库中创建

## 配置示例

### app_config.py 示例配置

```python
# 业务数据库配置（用于数据处理）
APP_DB_CONFIG = {
    'host': '192.168.67.1',
    'port': 6432,
    'dbname': 'highway_db',
    'user': 'postgres',
    'password': 'password'
}

# 向量数据库配置（用于任务管理）
PGVECTOR_CONFIG = {
    'host': '192.168.67.1',
    'port': 5432,
    'dbname': 'highway_pgvector_db',
    'user': 'postgres',
    'password': 'password'
}
```

## 测试方法

### 1. 使用新API格式
```bash
curl -X POST http://localhost:8084/api/v0/data_pipeline/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "table_list_file": "data_pipeline/tables.txt",
    "business_context": "高速公路服务区管理系统",
    "db_name": "highway_db"
  }'
```

### 2. 运行测试脚本
```bash
python test_api_changes.py
```

## 注意事项

1. **配置检查**: 确保 `app_config.py` 中的数据库配置正确
2. **权限验证**: 确保应用有权限访问两个数据库
3. **表初始化**: 在向量数据库中执行 `init_tables.sql`
4. **监控日志**: 关注任务创建和执行过程中的日志信息

## 常见问题

### Q: 为什么要移除 db_connection 参数？
A: 
- 简化API调用，避免敏感信息在请求中传递
- 统一配置管理，便于维护
- 与现有系统架构保持一致

### Q: 如何指定不同的业务数据库？
A: 
- 使用可选的 `db_name` 参数
- 或在 `app_config.py` 中修改 `APP_DB_CONFIG`

### Q: 旧的API调用会怎样？
A: 
- 包含 `db_connection` 的请求会被忽略此参数
- 必须提供 `table_list_file` 和 `business_context`
- 建议更新到新的API格式

### Q: 任务管理表为什么放在向量数据库中？
A: 
- 向量数据库用于存储系统元数据
- 避免污染业务数据库
- 便于系统数据的统一管理

## 总结

这次变更使Data Pipeline API更加简洁和易用，同时保持了系统的功能完整性。通过将配置管理集中到 `app_config.py`，提高了系统的可维护性和安全性。