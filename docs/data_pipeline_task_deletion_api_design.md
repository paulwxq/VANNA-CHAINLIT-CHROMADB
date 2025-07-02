# Data Pipeline 任务删除API设计文档

## 概述

本文档描述了Data Pipeline任务删除功能的详细设计，包括目录删除、数据库记录管理、批量操作等功能。该API主要用于删除任务对应的文件目录以节省存储空间，同时提供灵活的数据库记录管理选项。

## 需求背景

- **存储空间管理**：删除不再需要的任务目录以节省磁盘空间
- **数据保留**：保留任务执行记录用于历史查询和分析
- **批量操作**：支持批量删除多个任务目录
- **状态跟踪**：在数据库中标记目录删除状态

## 功能特性

### 1. 删除范围
- **目录删除**：删除 `data_pipeline/training_data/{task_id}/` 整个目录及所有文件
- **数据库管理**：可选择是否删除数据库中的任务记录
- **状态更新**：更新数据库中的目录存在状态

### 2. 操作模式
- **单个删除**：删除指定的单个任务
- **批量删除**：一次删除多个任务
- **选择性删除**：可选择保留或删除数据库记录

### 3. 安全控制
- **确认机制**：强制要求confirm参数防止误操作
- **状态检查**：检查任务运行状态，运行中的任务不允许删除
- **强制删除**：提供force参数跳过状态检查（谨慎使用）

## 数据库设计

### 表结构修改

在 `data_pipeline_tasks` 表中添加以下字段：

```sql
ALTER TABLE data_pipeline_tasks ADD COLUMN directory_exists BOOLEAN DEFAULT TRUE;
ALTER TABLE data_pipeline_tasks ADD COLUMN updated_at TIMESTAMP NULL;
```

### 字段说明
- `directory_exists`: 标记任务目录是否存在
  - `TRUE`: 目录存在（默认值）
  - `FALSE`: 目录已被删除
- `updated_at`: 记录最后更新时间
  - `NULL`: 从未更新过（默认值）
  - `TIMESTAMP`: 最后更新的时间戳

### 涉及的数据库表
- **主表**: `data_pipeline_tasks` - 任务主记录
- **关联表**: `data_pipeline_task_steps` - 任务步骤记录

## API接口设计

### 1. 单个任务删除

#### 接口定义
```
DELETE /api/v0/data_pipeline/tasks/{task_id}
```

#### 路径参数
- `task_id` (string, required): 要删除的任务ID

#### 请求体
```json
{
  "confirm": true,                    // 必需，确认删除操作
  "delete_database_records": false,   // 可选，是否删除数据库记录，默认false
  "force": false                      // 可选，强制删除（跳过状态检查），默认false
}
```

#### 响应示例

**成功响应 (200)**:
```json
{
  "success": true,
  "code": 200,
  "message": "任务目录删除成功",
  "data": {
    "task_id": "task_20250702_173932",
    "directory_deleted": true,
    "database_records_deleted": false,
    "deleted_files_count": 15,
    "deleted_size": "2.5 MB",
    "deleted_at": "2025-07-02T21:45:30"
  }
}
```

### 2. 批量任务删除

#### 接口定义
```
DELETE /api/v0/data_pipeline/tasks
```

#### 请求体
```json
{
  "task_ids": ["task_20250702_173932", "task_20250702_174521"],  // 必需，任务ID列表
  "confirm": true,                    // 必需，确认删除操作
  "delete_database_records": false,   // 可选，是否删除数据库记录，默认false
  "force": false,                     // 可选，强制删除（跳过状态检查），默认false
  "continue_on_error": true           // 可选，遇到错误是否继续删除其他任务，默认true
}
```

#### 响应示例

**成功响应 (200)**:
```json
{
  "success": true,
  "code": 200,
  "message": "批量删除完成",
  "data": {
    "deleted_tasks": [
      {
        "task_id": "task_20250702_173932",
        "directory_deleted": true,
        "database_records_deleted": false,
        "deleted_files_count": 15,
        "deleted_size": "2.5 MB"
      },
      {
        "task_id": "task_20250702_174521",
        "directory_deleted": true,
        "database_records_deleted": false,
        "deleted_files_count": 8,
        "deleted_size": "1.2 MB"
      }
    ],
    "failed_tasks": [],
    "summary": {
      "total_requested": 2,
      "successfully_deleted": 2,
      "failed": 0,
      "total_size_freed": "3.7 MB"
    },
    "deleted_at": "2025-07-02T21:45:30"
  }
}
```

**部分失败响应 (200)**:
```json
{
  "success": true,
  "code": 200,
  "message": "批量删除部分完成",
  "data": {
    "deleted_tasks": [
      {
        "task_id": "task_20250702_173932",
        "directory_deleted": true,
        "database_records_deleted": false,
        "deleted_files_count": 15,
        "deleted_size": "2.5 MB"
      }
    ],
    "failed_tasks": [
      {
        "task_id": "task_20250702_174521",
        "error": "任务正在运行中，无法删除",
        "error_code": "TASK_RUNNING"
      }
    ],
    "summary": {
      "total_requested": 2,
      "successfully_deleted": 1,
      "failed": 1,
      "total_size_freed": "2.5 MB"
    },
    "deleted_at": "2025-07-02T21:45:30"
  }
}
```

## 错误处理

### 错误状态码

| 状态码 | 错误类型 | 说明 |
|--------|----------|------|
| 400 | Bad Request | 参数错误、缺少必需参数 |
| 404 | Not Found | 任务不存在 |
| 409 | Conflict | 任务正在运行，无法删除 |
| 403 | Forbidden | 权限不足 |
| 500 | Internal Server Error | 服务器内部错误、删除操作失败 |

### 错误响应示例

**任务不存在 (404)**:
```json
{
  "success": false,
  "code": 404,
  "message": "任务不存在: task_invalid_id"
}
```

**任务正在运行 (409)**:
```json
{
  "success": false,
  "code": 409,
  "message": "任务正在运行中，无法删除",
  "data": {
    "task_id": "task_20250702_173932",
    "current_status": "running"
  }
}
```

**缺少确认参数 (400)**:
```json
{
  "success": false,
  "code": 400,
  "message": "缺少必需参数: confirm",
  "missing_params": ["confirm"]
}
```

## 技术实现

### 1. 删除流程

#### 单个任务删除流程
1. **参数验证**：检查必需参数（confirm等）
2. **任务存在性检查**：验证task_id是否存在
3. **状态检查**：检查任务是否正在运行（除非force=true）
4. **目录删除**：使用`shutil.rmtree`删除整个目录
5. **数据库更新**：更新directory_exists和updated_at字段
6. **可选数据库删除**：根据参数决定是否删除数据库记录
7. **返回结果**：返回删除统计信息

#### 批量删除流程
1. **参数验证**：检查task_ids和confirm参数
2. **循环处理**：对每个task_id执行单个删除流程
3. **错误处理**：根据continue_on_error参数决定是否继续
4. **统计汇总**：汇总成功和失败的任务
5. **返回结果**：返回批量删除统计信息

### 2. 数据库操作

#### 更新目录状态
```sql
UPDATE data_pipeline_tasks 
SET directory_exists = FALSE, 
    updated_at = CURRENT_TIMESTAMP 
WHERE task_id = %s
```

#### 删除数据库记录（可选）
```sql
-- 删除任务步骤记录
DELETE FROM data_pipeline_task_steps WHERE task_id = %s;

-- 删除任务主记录
DELETE FROM data_pipeline_tasks WHERE task_id = %s;
```

### 3. 跨平台兼容性

#### 文件系统操作
- 使用 `pathlib.Path` 处理路径
- 使用 `shutil.rmtree` 递归删除目录
- 处理Windows文件锁定问题
- 处理权限不足的情况

#### 错误处理
```python
import shutil
from pathlib import Path

def delete_task_directory(task_id):
    try:
        task_dir = Path("data_pipeline/training_data") / task_id
        if task_dir.exists():
            # 获取删除前的统计信息
            file_count, total_size = get_directory_stats(task_dir)
            
            # 删除目录
            shutil.rmtree(task_dir)
            
            return {
                "deleted": True,
                "file_count": file_count,
                "size": total_size
            }
        else:
            return {
                "deleted": False,
                "error": "目录不存在"
            }
    except PermissionError:
        return {
            "deleted": False,
            "error": "权限不足"
        }
    except Exception as e:
        return {
            "deleted": False,
            "error": str(e)
        }
```

## 查询API增强

### 修改现有的任务列表API

在 `GET /api/v0/data_pipeline/tasks` 响应中添加目录状态信息：

```json
{
  "tasks": [
    {
      "task_id": "task_20250702_173932",
      "task_name": "测试任务",
      "status": "completed",
      "directory_exists": true,          // 新增字段
      "updated_at": null,                // 新增字段
      "created_at": "2025-07-02T17:39:32"
    },
    {
      "task_id": "task_20250702_174521",
      "task_name": "已删除目录的任务",
      "status": "completed",
      "directory_exists": false,         // 目录已删除
      "updated_at": "2025-07-02T21:45:30", // 删除时间
      "created_at": "2025-07-02T17:45:21"
    }
  ]
}
```

## 使用示例

### 1. 单个任务删除

```bash
# 删除任务目录，保留数据库记录
curl -X DELETE \
  http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_173932 \
  -H "Content-Type: application/json" \
  -d '{
    "confirm": true,
    "delete_database_records": false
  }'

# 删除任务目录和数据库记录
curl -X DELETE \
  http://localhost:8084/api/v0/data_pipeline/tasks/task_20250702_173932 \
  -H "Content-Type: application/json" \
  -d '{
    "confirm": true,
    "delete_database_records": true
  }'
```

### 2. 批量删除

```bash
# 批量删除多个任务目录
curl -X DELETE \
  http://localhost:8084/api/v0/data_pipeline/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": ["task_20250702_173932", "task_20250702_174521"],
    "confirm": true,
    "delete_database_records": false,
    "continue_on_error": true
  }'
```

### 3. Python客户端示例

```python
import requests

def delete_task(task_id, delete_db_records=False):
    """删除单个任务"""
    url = f"http://localhost:8084/api/v0/data_pipeline/tasks/{task_id}"
    payload = {
        "confirm": True,
        "delete_database_records": delete_db_records
    }
    
    response = requests.delete(url, json=payload)
    return response.json()

def delete_tasks_batch(task_ids, delete_db_records=False):
    """批量删除任务"""
    url = "http://localhost:8084/api/v0/data_pipeline/tasks"
    payload = {
        "task_ids": task_ids,
        "confirm": True,
        "delete_database_records": delete_db_records,
        "continue_on_error": True
    }
    
    response = requests.delete(url, json=payload)
    return response.json()

# 使用示例
result = delete_task("task_20250702_173932")
print(result)

batch_result = delete_tasks_batch([
    "task_20250702_173932", 
    "task_20250702_174521"
])
print(batch_result)
```

## 安全考虑

### 1. 操作安全
- **确认机制**：强制要求confirm=true参数
- **状态检查**：防止删除正在运行的任务
- **路径验证**：确保只能删除training_data目录下的文件
- **权限检查**：验证文件系统操作权限

### 2. 数据安全
- **事务处理**：数据库操作使用事务保证一致性
- **错误恢复**：提供详细的错误信息和处理建议
- **操作日志**：记录所有删除操作的详细日志

### 3. 防误操作
- **必需确认**：confirm参数必须显式设置为true
- **详细响应**：返回详细的删除统计信息
- **批量限制**：可考虑限制单次批量删除的任务数量

## 性能考虑

### 1. 删除性能
- **并发限制**：避免同时删除过多任务导致系统负载过高
- **大目录处理**：对于包含大量文件的目录，提供进度反馈
- **异步处理**：对于大批量删除，可考虑异步处理

### 2. 数据库性能
- **批量操作**：批量删除时使用批量SQL操作
- **索引优化**：在task_id字段上确保有适当的索引
- **事务大小**：控制单个事务的大小避免锁定过久

## 监控和日志

### 1. 操作日志
记录以下信息：
- 删除操作的发起者
- 删除的任务ID列表
- 删除的文件数量和大小
- 操作结果（成功/失败）
- 错误详情（如果有）

### 2. 监控指标
- 删除操作频率
- 释放的存储空间
- 操作成功率
- 平均删除时间

## 未来扩展

### 1. 功能扩展
- **定时清理**：自动删除超过指定时间的任务目录
- **存储配额**：基于存储使用量的自动清理
- **恢复功能**：从备份恢复误删的任务（如果有备份）

### 2. 管理功能
- **批量管理界面**：Web界面批量管理任务
- **存储分析**：分析存储使用情况和清理建议
- **策略配置**：配置自动清理策略

## 总结

Data Pipeline任务删除API提供了灵活、安全的任务目录管理功能。通过数据库状态跟踪和可选的记录删除，平衡了存储空间节省和历史数据保留的需求。批量操作支持提高了管理效率，而完善的安全机制确保了操作的可靠性。 