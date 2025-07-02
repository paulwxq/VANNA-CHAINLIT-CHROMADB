# Data Pipeline 文件上传API设计文档

## 概述

本文档描述了Data Pipeline文件上传功能的详细设计，包括API接口设计、文件管理机制、安全控制和使用示例。

## 功能特性

### 1. 支持的文件类型
- `.ddl` - DDL文件
- `.md` - Markdown文档
- `.txt` - 文本文件
- `.json` - JSON文件
- `.sql` - SQL文件
- `.csv` - CSV文件

### 2. 文件大小限制
- 最大文件大小：10MB
- 空文件检查：不允许上传空文件

### 3. 重名处理模式
- **backup（默认）**：备份原文件，命名规则为 `原文件名_bak1`, `原文件名_bak2` 等
- **replace**：直接覆盖原文件
- **skip**：跳过上传，保留原文件

### 4. 安全控制
- 文件名安全检查：防止路径遍历攻击
- 文件类型验证：仅允许指定的文件扩展名
- 目录权限控制：文件只能上传到指定任务目录内

## API接口设计

### POST /api/v0/data_pipeline/tasks/{task_id}/files

上传文件到指定任务目录。

#### 请求参数

**路径参数：**
- `task_id` (string, required): 任务ID

**表单参数（multipart/form-data）：**
- `file` (file, required): 要上传的文件
- `overwrite_mode` (string, optional): 重名处理模式，可选值：`backup`（默认）、`replace`、`skip`

#### 响应格式

**成功响应（200）：**
```json
{
    "success": true,
    "code": 200,
    "message": "文件上传成功",
    "data": {
        "task_id": "task_20250701_123456",
        "uploaded_file": {
            "filename": "test.ddl",
            "size": 1024,
            "size_formatted": "1.0 KB",
            "uploaded_at": "2025-07-01T12:34:56",
            "overwrite_mode": "backup"
        },
        "backup_info": {  // 仅当overwrite_mode为backup且文件已存在时返回
            "had_existing_file": true,
            "backup_filename": "test.ddl_bak1",
            "backup_version": 1,
            "backup_created_at": "2025-07-01T12:34:56"
        }
    }
}
```

**跳过上传响应（200）：**
```json
{
    "success": true,
    "code": 200,
    "message": "文件已存在，跳过上传",
    "data": {
        "task_id": "task_20250701_123456",
        "skipped": true,
        "uploaded_file": {
            "filename": "test.ddl",
            "existed": true,
            "action": "skipped"
        }
    }
}
```

**错误响应：**
- `400 Bad Request`: 参数错误、文件验证失败
- `404 Not Found`: 任务不存在
- `500 Internal Server Error`: 服务器内部错误

#### 错误示例

**文件类型不支持（400）：**
```json
{
    "success": false,
    "code": 400,
    "message": "不支持的文件类型: .exe，允许的类型: .ddl, .md, .txt, .json, .sql, .csv"
}
```

**文件大小超限（400）：**
```json
{
    "success": false,
    "code": 400,
    "message": "文件大小超出限制: 11.0 MB，最大允许: 10.0 MB"
}
```

**任务不存在（404）：**
```json
{
    "success": false,
    "code": 404,
    "message": "任务不存在: task_invalid_id"
}
```

## 技术实现

### 1. 文件管理器架构

```python
class SimpleFileManager:
    # 支持的文件类型
    ALLOWED_EXTENSIONS = {'.ddl', '.md', '.txt', '.json', '.sql', '.csv'}
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    
    def upload_file_to_task(self, task_id, file_stream, filename, overwrite_mode="backup"):
        """上传文件到任务目录"""
        
    def validate_file_upload(self, filename, file_stream):
        """验证文件合法性"""
        
    def create_backup_file(self, original_path):
        """创建备份文件"""
        
    def find_next_backup_version(self, file_path):
        """查找下一个可用的备份版本号"""
```

### 2. 备份文件命名规则

当选择backup模式且目标文件已存在时，系统会自动创建备份文件：

- 原文件：`test.ddl`
- 第1次备份：`test.ddl_bak1`
- 第2次备份：`test.ddl_bak2`
- 以此类推...

### 3. 文件安全验证

#### 文件名安全检查
- 禁止路径遍历字符：`..`
- 禁止Windows危险字符：`<>:"|?*`
- 禁止控制字符：`\x00-\x1f`
- 禁止Windows保留文件名：`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`
- 文件名长度限制：255字符

#### 文件类型验证
- 基于文件扩展名进行验证
- 仅允许预定义的安全文件类型
- 大小写不敏感

#### 文件大小验证
- 最大10MB限制
- 禁止空文件上传
- 流式读取避免内存溢出

### 4. 目录结构

```
data_pipeline/
└── training_data/
    └── {task_id}/
        ├── test.ddl
        ├── test.ddl_bak1
        ├── test.md
        ├── config.json
        └── ...
```

## 使用示例

### 1. 基本文件上传

```bash
curl -X POST \
  http://localhost:8084/api/v0/data_pipeline/tasks/task_20250701_123456/files \
  -F "file=@test.ddl" \
  -F "overwrite_mode=backup"
```

### 2. Python客户端示例

```python
import requests

def upload_file(task_id, file_path, overwrite_mode="backup"):
    url = f"http://localhost:8084/api/v0/data_pipeline/tasks/{task_id}/files"
    
    with open(file_path, 'rb') as f:
        files = {'file': (file_path.name, f)}
        data = {'overwrite_mode': overwrite_mode}
        
        response = requests.post(url, files=files, data=data)
        
    return response.json()

# 使用示例
result = upload_file("task_20250701_123456", "test.ddl", "backup")
print(result)
```

### 3. JavaScript客户端示例

```javascript
async function uploadFile(taskId, file, overwriteMode = 'backup') {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('overwrite_mode', overwriteMode);
    
    const response = await fetch(
        `/api/v0/data_pipeline/tasks/${taskId}/files`,
        {
            method: 'POST',
            body: formData
        }
    );
    
    return await response.json();
}

// 使用示例
const fileInput = document.getElementById('fileInput');
const file = fileInput.files[0];
const result = await uploadFile('task_20250701_123456', file, 'backup');
console.log(result);
```

## 配置说明

### 1. 文件类型配置

可以通过修改 `SimpleFileManager.ALLOWED_EXTENSIONS` 来调整支持的文件类型：

```python
ALLOWED_EXTENSIONS = {'.ddl', '.md', '.txt', '.json', '.sql', '.csv', '.py'}
```

### 2. 文件大小限制配置

可以通过修改 `SimpleFileManager.MAX_FILE_SIZE` 来调整文件大小限制：

```python
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
```

## 错误处理

### 1. 常见错误类型

| 错误类型 | HTTP状态码 | 说明 |
|---------|-----------|------|
| 参数缺失 | 400 | 缺少必需的file参数 |
| 文件类型不支持 | 400 | 文件扩展名不在允许列表中 |
| 文件大小超限 | 400 | 文件大小超过10MB限制 |
| 文件为空 | 400 | 上传的文件内容为空 |
| 文件名不安全 | 400 | 文件名包含危险字符 |
| 任务不存在 | 404 | 指定的task_id不存在 |
| 服务器错误 | 500 | 文件保存失败等内部错误 |

### 2. 错误处理最佳实践

- 客户端应检查响应状态码
- 根据错误类型给用户提供友好的错误提示
- 对于5xx错误，建议实现重试机制
- 记录详细的错误日志用于调试

## 性能考虑

### 1. 文件上传性能
- 使用流式处理避免大文件占用过多内存
- 支持并发上传（不同任务间）
- 文件大小限制防止滥用

### 2. 存储空间管理
- 定期清理过期的备份文件
- 监控磁盘空间使用情况
- 考虑实现文件压缩存储

## 安全考虑

### 1. 文件安全
- 严格的文件类型白名单
- 文件名安全验证
- 防止路径遍历攻击

### 2. 访问控制
- 任务级别的文件隔离
- 文件只能上传到对应任务目录
- 未来可扩展用户权限控制

### 3. 资源限制
- 文件大小限制
- 上传频率限制（可扩展）
- 存储空间配额（可扩展）

## 测试验证

### 1. 功能测试
- 正常文件上传测试
- 重名处理模式测试
- 文件类型验证测试
- 文件大小限制测试

### 2. 安全测试
- 恶意文件名测试
- 路径遍历攻击测试
- 大文件攻击测试

### 3. 性能测试
- 并发上传测试
- 大文件上传测试
- 存储空间压力测试

## 未来扩展

### 1. 功能扩展
- 支持更多文件类型
- 批量文件上传
- 文件版本管理
- 文件内容预览

### 2. 安全扩展
- 用户权限控制
- 文件访问日志
- 病毒扫描集成

### 3. 性能扩展
- 分布式文件存储
- CDN集成
- 文件压缩和去重

## 总结

Data Pipeline文件上传API提供了一个安全、可靠的文件管理解决方案，支持多种文件类型和灵活的重名处理策略。通过严格的安全控制和完善的错误处理，确保了系统的稳定性和安全性。

该API设计遵循RESTful原则，提供了清晰的接口定义和详细的文档说明，便于开发者集成和使用。 