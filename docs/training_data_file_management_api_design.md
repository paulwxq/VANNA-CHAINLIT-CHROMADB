# Training Data 文件管理系统 API 设计方案

## 📋 项目概述

### 设计目标
为 `data_pipeline/training_data/` 目录设计一套完整的文件管理API系统，提供目录浏览、文件操作、安全管理等功能。

### 应用场景
- **开发调试**: 查看和管理训练数据文件
- **数据维护**: 上传、删除、下载训练文件  
- **目录管理**: 浏览项目目录结构
- **文件监控**: 跟踪文件变化和使用情况

### 设计原则
- ✅ **安全性**: 严格限制在training_data目录范围内
- ✅ **简洁性**: RESTful API设计，易于理解和使用
- ✅ **完整性**: 覆盖文件管理的基本需求
- ✅ **兼容性**: 与现有data_pipeline系统无缝集成

## 🎯 功能需求分析

### 1. 目录遍历功能
| 需求 | 描述 | 优先级 |
|------|------|--------|
| **递归遍历** | 支持整个training_data目录的递归遍历 | 🟢 高 |
| **层级控制** | 可指定遍历深度，避免性能问题 | 🟡 中 |
| **筛选功能** | 按文件类型、大小、时间等条件筛选 | 🟡 中 |
| **排序功能** | 按名称、时间、大小等排序 | 🟡 中 |

### 2. 文件列表功能
| 需求 | 描述 | 优先级 |
|------|------|--------|
| **基本信息** | 文件名、大小、类型、修改时间等 | 🟢 高 |
| **详细属性** | 权限、创建时间、文件哈希等 | 🟡 中 |
| **分页支持** | 大目录的分页展示 | 🟡 中 |
| **搜索功能** | 按文件名模糊搜索 | 🟡 中 |

### 3. 文件下载功能
| 需求 | 描述 | 优先级 |
|------|------|--------|
| **单文件下载** | 支持各种文件类型下载 | 🟢 高 |
| **流式下载** | 大文件的流式传输 | 🟡 中 |
| **批量下载** | 多文件打包下载 | 🔴 低 |
| **断点续传** | 大文件下载中断恢复 | 🔴 低 |

### 4. 文件删除功能
| 需求 | 描述 | 优先级 |
|------|------|--------|
| **单文件删除** | 删除指定文件 | 🟢 高 |
| **批量删除** | 删除多个文件 | 🟡 中 |
| **安全确认** | 删除前的确认机制 | 🟢 高 |
| **回收站** | 软删除，可恢复 | 🔴 低 |

### 5. 文件上传功能
| 需求 | 描述 | 优先级 |
|------|------|--------|
| **单文件上传** | 支持各种文件类型上传 | 🟢 高 |
| **同名覆盖** | 自动覆盖同名文件 | 🟢 高 |
| **分片上传** | 大文件分片上传 | 🟡 中 |
| **进度跟踪** | 上传进度实时反馈 | 🟡 中 |

## 🏗️ API 设计方案

### API 基础信息

**基础路径**: `/api/v0/training_data/files`
**认证方式**: 继承现有系统认证
**响应格式**: JSON
**错误处理**: 标准HTTP状态码 + 详细错误信息

### 1. 目录遍历 API

#### 1.1 获取目录树结构
```http
GET /api/v0/training_data/files/tree
```

**查询参数**:
- `max_depth`: 最大遍历深度 (默认: 3)
- `include_files`: 是否包含文件 (默认: true)
- `file_types`: 筛选文件类型 (如: ddl,md,json)

**响应示例**:
```json
{
  "success": true,
  "data": {
    "directory": "training_data",
    "path": "./data_pipeline/training_data",
    "children": [
      {
        "name": "vector_bak",
        "type": "directory",
        "path": "./data_pipeline/training_data/vector_bak",
        "file_count": 4,
        "size": "1.6MB",
        "children": [
          {
            "name": "langchain_pg_collection_20250722_132518.csv",
            "type": "file",
            "path": "./data_pipeline/training_data/vector_bak/langchain_pg_collection_20250722_132518.csv",
            "size": "209B",
            "modified_at": "2025-07-22T13:25:18Z",
            "file_type": "csv"
          }
        ]
      }
    ]
  },
  "meta": {
    "total_directories": 15,
    "total_files": 89,
    "total_size": "25.4MB",
    "scan_time": "0.234s"
  }
}
```

#### 1.2 获取指定目录内容
```http
GET /api/v0/training_data/files/list
```

**查询参数**:
- `path`: 相对路径 (默认: ".")
- `page`: 页码 (默认: 1)
- `page_size`: 每页大小 (默认: 50)
- `sort_by`: 排序字段 (name|size|modified_at)
- `sort_order`: 排序方向 (asc|desc)
- `search`: 文件名搜索关键词

**响应示例**:
```json
{
  "success": true,
  "data": {
    "current_path": "./data_pipeline/training_data/task_20250721_213627",
    "items": [
      {
        "name": "bss_business_day_data.ddl",
        "type": "file",
        "size": 1024,
        "size_formatted": "1.0 KB",
        "modified_at": "2025-07-21T21:36:27Z",
        "created_at": "2025-07-21T21:36:27Z",
        "file_type": "ddl",
        "permissions": "rw-r--r--"
      },
      {
        "name": "vector_bak",
        "type": "directory", 
        "size": 819200,
        "size_formatted": "800 KB",
        "modified_at": "2025-07-22T01:03:18Z",
        "file_count": 4
      }
    ]
  },
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total": 25,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  }
}
```

### 2. 文件下载 API

#### 2.1 下载单个文件
```http
GET /api/v0/training_data/files/download
```

**查询参数**:
- `path`: 文件相对路径 (必需)
- `inline`: 是否内联显示 (默认: false)

**响应**: 文件流
**Headers**: 
- `Content-Type`: 根据文件类型自动设置
- `Content-Disposition`: attachment; filename="文件名"
- `Content-Length`: 文件大小

#### 2.2 预览文件内容 (文本文件)
```http
GET /api/v0/training_data/files/preview
```

**查询参数**:
- `path`: 文件相对路径 (必需)
- `lines`: 预览行数 (默认: 100)
- `encoding`: 文件编码 (默认: utf-8)

**响应示例**:
```json
{
  "success": true,
  "data": {
    "file_path": "./data_pipeline/training_data/task_xxx/metadata.txt",
    "file_size": 2048,
    "content_preview": "业务日数据表...",
    "total_lines": 45,
    "preview_lines": 100,
    "encoding": "utf-8",
    "is_text_file": true
  }
}
```

### 3. 文件删除 API

#### 3.1 删除单个文件
```http
DELETE /api/v0/training_data/files/delete
```

**请求体**:
```json
{
  "path": "./data_pipeline/training_data/task_xxx/old_file.json",
  "confirm": true
}
```

**响应示例**:
```json
{
  "success": true,
  "message": "文件删除成功",
  "data": {
    "deleted_file": {
      "path": "./data_pipeline/training_data/task_xxx/old_file.json",
      "name": "old_file.json",
      "size": 1024,
      "deleted_at": "2025-07-22T15:30:00Z"
    }
  }
}
```

#### 3.2 批量删除文件
```http
POST /api/v0/training_data/files/batch_delete
```

**请求体**:
```json
{
  "paths": [
    "./data_pipeline/training_data/task_xxx/file1.json",
    "./data_pipeline/training_data/task_xxx/file2.ddl"
  ],
  "confirm": true
}
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "deleted_files": [
      {
        "path": "./data_pipeline/training_data/task_xxx/file1.json",
        "success": true
      }
    ],
    "failed_files": [
      {
        "path": "./data_pipeline/training_data/task_xxx/file2.ddl", 
        "success": false,
        "error": "文件不存在"
      }
    ],
    "summary": {
      "total": 2,
      "success": 1,
      "failed": 1
    }
  }
}
```

### 4. 文件上传 API

#### 4.1 上传单个文件
```http
POST /api/v0/training_data/files/upload
```

**请求**: `multipart/form-data`
- `file`: 文件数据 (必需)
- `path`: 目标目录相对路径 (默认: ".")
- `filename`: 自定义文件名 (可选)
- `overwrite`: 是否覆盖同名文件 (默认: true)

**响应示例**:
```json
{
  "success": true,
  "message": "文件上传成功",
  "data": {
    "uploaded_file": {
      "original_name": "table_list.txt",
      "saved_name": "table_list.txt", 
      "path": "./data_pipeline/training_data/task_xxx/table_list.txt",
      "size": 256,
      "size_formatted": "256 B",
      "uploaded_at": "2025-07-22T15:45:00Z",
      "file_type": "text",
      "overwrite_occurred": true
    },
    "backup_info": {
      "backup_created": true,
      "backup_path": "./data_pipeline/training_data/task_xxx/table_list.txt.bak1",
      "backup_created_at": "2025-07-22T15:45:00Z"
    }
  }
}
```

#### 4.2 批量上传文件
```http
POST /api/v0/training_data/files/batch_upload
```

**请求**: `multipart/form-data`
- `files[]`: 多个文件 (必需)
- `path`: 目标目录相对路径 (默认: ".")
- `overwrite`: 是否覆盖同名文件 (默认: true)

### 5. 文件管理 API

#### 5.1 获取目录统计信息
```http
GET /api/v0/training_data/files/stats
```

**查询参数**:
- `path`: 目录相对路径 (默认: ".")
- `recursive`: 是否递归统计 (默认: true)

**响应示例**:
```json
{
  "success": true,
  "data": {
    "directory_stats": {
      "path": "./data_pipeline/training_data",
      "total_directories": 12,
      "total_files": 87,
      "total_size": 26542080,
      "total_size_formatted": "25.3 MB",
      "file_type_breakdown": {
        "ddl": {"count": 18, "size": 45120},
        "md": {"count": 18, "size": 234560}, 
        "json": {"count": 15, "size": 1024000},
        "csv": {"count": 8, "size": 25000000},
        "txt": {"count": 12, "size": 15360},
        "log": {"count": 16, "size": 223040}
      },
      "largest_files": [
        {
          "name": "langchain_pg_embedding_20250722_132518.csv",
          "path": "./data_pipeline/training_data/vector_bak/langchain_pg_embedding_20250722_132518.csv",
          "size": 838860,
          "size_formatted": "819 KB"
        }
      ]
    }
  }
}
```

#### 5.2 搜索文件
```http
GET /api/v0/training_data/files/search
```

**查询参数**:
- `query`: 搜索关键词 (必需)
- `file_types`: 文件类型筛选 (可选)
- `max_results`: 最大结果数 (默认: 50)
- `search_type`: 搜索类型 (name|content) (默认: name)

**响应示例**:
```json
{
  "success": true,
  "data": {
    "search_query": "business_day",
    "search_type": "name",
    "results": [
      {
        "name": "bss_business_day_data.ddl",
        "path": "./data_pipeline/training_data/task_20250721_213627/bss_business_day_data.ddl",
        "size": 1024,
        "modified_at": "2025-07-21T21:36:27Z",
        "file_type": "ddl",
        "match_score": 0.95
      }
    ],
    "summary": {
      "total_results": 3,
      "search_time": "0.045s"
    }
  }
}
```

## 🔒 安全设计

### 路径安全策略

#### 1. 路径验证
```python
def validate_path(relative_path: str) -> bool:
    """验证路径安全性"""
    # 1. 禁止绝对路径
    if os.path.isabs(relative_path):
        return False
    
    # 2. 禁止路径遍历
    if '..' in relative_path:
        return False
    
    # 3. 解析后验证在允许范围内
    full_path = os.path.join(TRAINING_DATA_ROOT, relative_path)
    real_path = os.path.realpath(full_path)
    return real_path.startswith(os.path.realpath(TRAINING_DATA_ROOT))
```

#### 2. 文件类型限制
- **允许的文件类型**: `.ddl`, `.sql`, `.md`, `.json`, `.txt`, `.csv`, `.log`
- **禁止的文件类型**: `.exe`, `.bat`, `.sh`, `.py` (可执行文件)
- **大小限制**: 单文件最大 100MB

#### 3. 操作权限控制
| 操作 | 权限要求 | 说明 |
|------|----------|------|
| **目录浏览** | 只读 | 所有用户 |
| **文件下载** | 只读 | 所有用户 |
| **文件上传** | 读写 | 需要认证 |
| **文件删除** | 读写 | 需要认证 + 确认 |

### 错误处理策略

#### 标准错误响应格式
```json
{
  "success": false,
  "error": {
    "code": "FILE_NOT_FOUND",
    "message": "指定的文件不存在",
    "details": {
      "path": "./data_pipeline/training_data/nonexistent.txt",
      "timestamp": "2025-07-22T15:30:00Z"
    }
  }
}
```

#### 错误代码定义
| 错误代码 | HTTP状态 | 说明 |
|----------|----------|------|
| `INVALID_PATH` | 400 | 路径格式错误或不安全 |
| `FILE_NOT_FOUND` | 404 | 文件不存在 |
| `DIRECTORY_NOT_FOUND` | 404 | 目录不存在 |
| `PERMISSION_DENIED` | 403 | 权限不足 |
| `FILE_TOO_LARGE` | 413 | 文件超过大小限制 |
| `UNSUPPORTED_FILE_TYPE` | 415 | 不支持的文件类型 |
| `DISK_SPACE_FULL` | 507 | 磁盘空间不足 |

## 🚀 实施方案

### 阶段1: 核心功能实现 (1-2周)
- ✅ 基础文件管理器类
- ✅ 目录遍历API
- ✅ 文件列表API  
- ✅ 文件下载API
- ✅ 基础安全验证

### 阶段2: 上传和删除功能 (1周)
- ✅ 单文件上传API
- ✅ 单文件删除API
- ✅ 文件覆盖策略
- ✅ 错误处理完善

### 阶段3: 高级功能 (1周)
- ✅ 批量操作API
- ✅ 文件搜索功能
- ✅ 统计信息API
- ✅ 文件预览功能

### 阶段4: 优化和完善 (1周)
- ✅ 性能优化
- ✅ 缓存策略
- ✅ 日志记录
- ✅ 监控告警

## 📊 技术架构

### 系统架构图
```
┌─────────────────────────────────────────────────────────────┐
│                    Training Data File Management API        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────┐ │
│  │   目录API   │  │   文件API   │  │   上传API   │  │ 统计 │ │
│  │  tree/list  │  │download/del │  │upload/batch │  │ API  │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └──────┘ │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐ │
│  │           TrainingDataFileManager (核心管理器)            │ │
│  │  • 路径安全验证  • 文件操作封装  • 错误处理  • 日志记录   │ │
│  └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │   路径管理   │  │   文件操作   │  │      安全策略       │ │
│  │ • 路径解析   │  │ • 读写操作   │  │ • 权限验证          │ │
│  │ • 安全检查   │  │ • 元数据     │  │ • 类型检查          │ │
│  │ • 目录遍历   │  │ • 流式处理   │  │ • 大小限制          │ │
│  └──────────────┘  └──────────────┘  └─────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    现有 data_pipeline 基础设施               │
│           • unified_api.py 路由  • 日志系统  • 配置管理     │
└─────────────────────────────────────────────────────────────┘
```

### 核心类设计

#### TrainingDataFileManager
```python
class TrainingDataFileManager:
    """Training Data 文件管理器"""
    
    def __init__(self, base_path: str = "data_pipeline/training_data"):
        self.base_path = Path(base_path)
        self.logger = get_logger("TrainingDataFileManager")
    
    # 核心方法
    def get_directory_tree(self, max_depth: int = 3) -> Dict
    def list_directory_contents(self, path: str, **kwargs) -> Dict
    def download_file(self, path: str) -> FileResponse
    def upload_file(self, file_data, target_path: str) -> Dict
    def delete_file(self, path: str) -> Dict
    def get_file_stats(self, path: str) -> Dict
    def search_files(self, query: str, **kwargs) -> Dict
    
    # 安全验证
    def validate_path(self, path: str) -> bool
    def check_file_type(self, filename: str) -> bool
    def check_file_size(self, size: int) -> bool
```

### 配置管理

#### 新增配置项
```python
# data_pipeline/config.py
TRAINING_DATA_FILE_MANAGEMENT = {
    "enabled": True,
    "max_file_size": 100 * 1024 * 1024,  # 100MB
    "allowed_extensions": [".ddl", ".sql", ".md", ".json", ".txt", ".csv", ".log"],
    "max_tree_depth": 5,
    "max_search_results": 100,
    "cache_enabled": True,
    "cache_ttl": 300,  # 5分钟
    "upload_chunk_size": 1024 * 1024,  # 1MB
}
```

## 🔧 使用示例

### 前端集成示例

#### JavaScript调用示例
```javascript
// 获取目录树
const getDirectoryTree = async () => {
    const response = await fetch('/api/v0/training_data/files/tree?max_depth=3');
    const data = await response.json();
    return data;
};

// 上传文件
const uploadFile = async (file, targetPath = '.') => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('path', targetPath);
    formData.append('overwrite', 'true');
    
    const response = await fetch('/api/v0/training_data/files/upload', {
        method: 'POST',
        body: formData
    });
    return await response.json();
};

// 删除文件
const deleteFile = async (filePath) => {
    const response = await fetch('/api/v0/training_data/files/delete', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: filePath, confirm: true })
    });
    return await response.json();
};
```

### 命令行工具示例

#### cURL命令示例
```bash
# 获取目录列表
curl "http://localhost:8084/api/v0/training_data/files/list?path=task_20250721_213627"

# 下载文件
curl -O "http://localhost:8084/api/v0/training_data/files/download?path=task_xxx/metadata.txt"

# 上传文件
curl -X POST -F "file=@local_file.txt" -F "path=task_xxx" \
     "http://localhost:8084/api/v0/training_data/files/upload"

# 删除文件
curl -X DELETE -H "Content-Type: application/json" \
     -d '{"path":"task_xxx/old_file.json","confirm":true}' \
     "http://localhost:8084/api/v0/training_data/files/delete"

# 搜索文件
curl "http://localhost:8084/api/v0/training_data/files/search?query=business&file_types=ddl,md"
```

## 📝 总结

这个文件管理系统API设计方案提供了：

### ✅ 核心功能
- **完整的CRUD操作**: 创建、读取、更新、删除文件
- **目录管理**: 递归遍历、层级展示、统计信息
- **安全保障**: 路径验证、权限控制、类型限制
- **用户友好**: RESTful设计、详细响应、错误处理

### ✅ 技术特色
- **高性能**: 流式处理、分页支持、缓存策略
- **高可靠**: 详细日志、错误恢复、操作确认
- **易集成**: 标准HTTP接口、JSON格式、现有架构兼容
- **易扩展**: 模块化设计、配置驱动、插件机制

### ✅ 实施价值
- **提升效率**: 简化文件管理操作
- **降低风险**: 严格的安全控制机制  
- **改善体验**: 直观的API设计和响应格式
- **便于维护**: 清晰的架构和完善的文档

这个设计方案可以作为后续开发的详细指导，确保实现一个功能完整、安全可靠、易于使用的文件管理系统。

---

**文档版本**: v1.0  
**创建日期**: 2025-07-22  
**作者**: AI Assistant  
**审核状态**: 待审核 