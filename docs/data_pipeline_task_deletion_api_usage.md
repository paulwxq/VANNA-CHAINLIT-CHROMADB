# Data Pipeline 任务删除API使用说明

## API概述

**端点**: `DELETE /api/v0/data_pipeline/tasks`  
**功能**: 删除任务目录，支持单个和批量删除  
**主要用途**: 清理不需要的任务目录以节省存储空间，同时保留任务记录用于历史查询

## 简单使用例子

### 1. 删除单个任务

```bash
curl -X DELETE \
  http://localhost:8084/api/v0/data_pipeline/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": ["task_20250702_223802"],
    "confirm": true
  }'
```

### 2. 删除多个任务

```bash
curl -X DELETE \
  http://localhost:8084/api/v0/data_pipeline/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": ["task_20250702_223802", "task_20250702_223751", "task_20250702_223705"],
    "confirm": true,
    "delete_database_records": false,
    "continue_on_error": true
  }'
```

### 3. Python调用示例

```python
import requests
import json

# 删除单个任务（只删除目录，保留数据库记录）
def delete_single_task(task_id):
    payload = {
        "task_ids": [task_id],
        "confirm": True,
        "delete_database_records": False
    }
    
    response = requests.delete(
        'http://localhost:8084/api/v0/data_pipeline/tasks', 
        json=payload
    )
    
    return response.json()

# 批量删除任务
def delete_multiple_tasks(task_ids):
    payload = {
        "task_ids": task_ids,
        "confirm": True,
        "delete_database_records": False,
        "continue_on_error": True
    }
    
    response = requests.delete(
        'http://localhost:8084/api/v0/data_pipeline/tasks', 
        json=payload
    )
    
    return response.json()

# 使用示例
result = delete_single_task("task_20250702_223802")
print(json.dumps(result, indent=2, ensure_ascii=False))
```

## 完整参数说明

### 请求参数

| 参数名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `task_ids` | Array[String] | ✅ | - | 要删除的任务ID列表，支持单个或多个 |
| `confirm` | Boolean | ✅ | - | 确认删除操作，必须为 `true` |
| `delete_database_records` | Boolean | ❌ | `false` | 是否删除数据库记录 |
| `continue_on_error` | Boolean | ❌ | `true` | 批量删除时遇到错误是否继续 |

### 参数详细说明

#### `task_ids` (必需)
- **类型**: 字符串数组
- **说明**: 要删除的任务ID列表
- **示例**: 
  - 单个: `["task_20250702_223802"]`
  - 多个: `["task_20250702_223802", "task_20250702_223751"]`

#### `confirm` (必需)
- **类型**: 布尔值
- **说明**: 安全确认参数，防止误操作
- **值**: 必须为 `true`
- **注意**: 如果不提供或值不为 `true`，将返回400错误

#### `delete_database_records` (可选)
- **类型**: 布尔值
- **默认值**: `false`
- **说明**: 控制是否删除数据库中的任务记录
  - `false`: 只删除目录，保留任务记录（推荐）
  - `true`: 同时删除目录和数据库记录
- **推荐**: 使用默认值 `false`，保留历史记录

#### `continue_on_error` (可选)
- **类型**: 布尔值
- **默认值**: `true`
- **说明**: 批量删除时的错误处理策略
  - `true`: 遇到错误继续删除其他任务
  - `false`: 遇到第一个错误就停止

## 响应格式

### 成功响应 (200)

```json
{
  "success": true,
  "code": 200,
  "message": "任务目录删除成功",
  "data": {
    "deleted_at": "2025-07-02T22:57:21.317708",
    "deleted_tasks": [
      {
        "success": true,
        "task_id": "task_20250702_223802",
        "directory_deleted": true,
        "database_records_deleted": false,
        "deleted_files_count": 15,
        "deleted_size": "2.5 MB",
        "deleted_at": "2025-07-02T22:57:21.317708"
      }
    ],
    "failed_tasks": [],
    "summary": {
      "total_requested": 1,
      "successfully_deleted": 1,
      "failed": 0
    }
  }
}
```

### 部分成功响应 (200)

```json
{
  "success": true,
  "code": 200,
  "message": "批量删除部分完成",
  "data": {
    "deleted_at": "2025-07-02T22:57:21.317708",
    "deleted_tasks": [
      {
        "success": true,
        "task_id": "task_20250702_223802",
        "directory_deleted": true,
        "database_records_deleted": false,
        "deleted_files_count": 15,
        "deleted_size": "2.5 MB",
        "deleted_at": "2025-07-02T22:57:21.317708"
      }
    ],
    "failed_tasks": [
      {
        "task_id": "task_20250702_invalid",
        "error": "任务目录不存在",
        "error_code": "DELETE_FAILED"
      }
    ],
    "summary": {
      "total_requested": 2,
      "successfully_deleted": 1,
      "failed": 1
    }
  }
}
```

### 错误响应

#### 缺少确认参数 (400)
```json
{
  "success": false,
  "code": 400,
  "message": "缺少必需参数: confirm",
  "missing_params": ["confirm"]
}
```

#### 参数格式错误 (400)
```json
{
  "success": false,
  "code": 400,
  "message": "task_ids必须是非空的任务ID列表"
}
```

#### 服务器错误 (500)
```json
{
  "success": false,
  "code": 500,
  "message": "删除任务失败，请稍后重试"
}
```

## 响应字段说明

### 删除结果字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `success` | Boolean | 该任务是否删除成功 |
| `task_id` | String | 任务ID |
| `directory_deleted` | Boolean | 目录是否被删除 |
| `database_records_deleted` | Boolean | 数据库记录是否被删除 |
| `deleted_files_count` | Integer | 删除的文件数量 |
| `deleted_size` | String | 删除的文件总大小（格式化） |
| `deleted_at` | String | 删除时间（ISO格式） |

### 汇总字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `total_requested` | Integer | 请求删除的任务总数 |
| `successfully_deleted` | Integer | 成功删除的任务数 |
| `failed` | Integer | 删除失败的任务数 |

## 数据库影响

### 默认行为 (`delete_database_records: false`)
- ✅ 删除任务目录及所有文件
- ✅ 更新 `data_pipeline_tasks.directory_exists = false`
- ✅ 更新 `data_pipeline_tasks.updated_at = 当前时间`
- ❌ 保留任务记录和步骤记录

### 完全删除 (`delete_database_records: true`)
- ✅ 删除任务目录及所有文件
- ✅ 删除 `data_pipeline_tasks` 表中的任务记录
- ✅ 删除 `data_pipeline_task_steps` 表中的步骤记录

## 查看删除效果

删除后可以通过任务列表API查看效果：

```bash
curl http://localhost:8084/api/v0/data_pipeline/tasks?limit=5
```

响应中会显示：
```json
{
  "tasks": [
    {
      "task_id": "task_20250702_223802",
      "directory_exists": false,
      "updated_at": "2025-07-02T22:57:21.550474",
      ...
    }
  ]
}
```

## 注意事项

1. **安全性**: 必须提供 `confirm: true` 参数
2. **不可逆**: 目录删除后无法恢复，请谨慎操作
3. **推荐做法**: 使用默认的 `delete_database_records: false`，保留历史记录
4. **批量操作**: 支持一次删除多个任务，提高效率
5. **错误处理**: 默认继续执行，可通过 `continue_on_error` 控制

## 常见使用场景

### 1. 清理测试任务
```bash
curl -X DELETE \
  http://localhost:8084/api/v0/data_pipeline/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": ["task_20250702_test1", "task_20250702_test2"],
    "confirm": true
  }'
```

### 2. 清理失败的任务
```bash
curl -X DELETE \
  http://localhost:8084/api/v0/data_pipeline/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": ["task_20250702_failed"],
    "confirm": true,
    "delete_database_records": true
  }'
```

### 3. 定期清理旧任务
```python
import requests
from datetime import datetime, timedelta

def cleanup_old_tasks(days_old=30):
    # 先获取任务列表
    response = requests.get('http://localhost:8084/api/v0/data_pipeline/tasks?limit=100')
    tasks = response.json()['data']['tasks']
    
    # 筛选出旧任务
    cutoff_date = datetime.now() - timedelta(days=days_old)
    old_task_ids = []
    
    for task in tasks:
        if task.get('created_at'):
            created_at = datetime.fromisoformat(task['created_at'].replace('Z', '+00:00'))
            if created_at < cutoff_date:
                old_task_ids.append(task['task_id'])
    
    # 批量删除
    if old_task_ids:
        payload = {
            "task_ids": old_task_ids,
            "confirm": True,
            "delete_database_records": False
        }
        
        response = requests.delete(
            'http://localhost:8084/api/v0/data_pipeline/tasks',
            json=payload
        )
        
        return response.json()
    
    return {"message": "没有找到需要清理的旧任务"}
``` 