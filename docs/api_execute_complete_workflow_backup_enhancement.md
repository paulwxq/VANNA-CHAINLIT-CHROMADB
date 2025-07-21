# API执行完整工作流文件备份增强方案

## 需求概述

当调用 Data Pipeline API 的完整工作流执行接口时，如果任务目录下已存在文件，需要自动备份这些文件，避免被新生成的文件覆盖。

### 触发条件

- **API端点**：`POST /api/v0/data_pipeline/tasks/{task_id}/execute`
- **执行模式**：`{"execution_mode": "complete"}`
- **触发时机**：仅在执行完整工作流时触发，单步执行不受影响

## 功能需求

### 1. 自动检测文件
- 检查任务目录 `./data_pipeline/training_data/{task_id}/` 下是否存在文件
- 只处理文件，不处理子目录
- 排除 `table_list.txt` 文件（用户上传的输入文件，需要保留）

### 2. 备份目录创建
- 在当前任务目录下创建备份子目录
- 命名格式：`file_bak_{YYYYMMDD_HHMMSS}`
- 示例：`file_bak_20250121_094400`

### 3. 文件移动
- 将除 `table_list.txt` 之外的所有文件移动到备份目录
- **保持原文件名不变**
- 包括所有文件类型：`*.ddl`、`*.md`、`*.json`、`*.log`、`*.txt` 等

### 4. 备份范围
**包括的文件：**
- DDL文件：`*.ddl`
- 详细文档：`*_detail.md`
- 问答对文件：`qs_*.json`、`qs_*.json.backup`
- 元数据文件：`metadata.txt`、`filename_mapping.txt`
- 验证日志：`sql_validation_*.log`、`sql_validation_*.json`
- 训练日志：`training_load_*.log`
- 配置文件：`task_config.json`、`task_result.json`
- 数据管道日志：`data_pipeline.log`
- 其他所有文件

**排除的文件：**
- `table_list.txt`（严格按文件名匹配）

**排除的目录：**
- 不处理子目录（如 `vector_bak/` 等）

## 实施方案

### 1. 修改位置

**主要文件**：`data_pipeline/api/simple_workflow.py`  
**修改方法**：`SimpleWorkflowExecutor.execute_complete_workflow()`

### 2. 执行流程

```
1. API调用 POST /api/v0/data_pipeline/tasks/{task_id}/execute
2. execution_mode == "complete"
3. 进入 SimpleWorkflowExecutor.execute_complete_workflow()
4. _ensure_task_directory() - 确保目录存在
5. _backup_existing_files_if_needed() - 🆕 检查并备份文件
   ├── 扫描 task_dir 下的所有文件（不包括子目录）
   ├── 排除 table_list.txt
   ├── 如果有文件需要备份：
   │   ├── 创建 file_bak_YYYYMMDD_HHMMSS 目录
   │   ├── 移动文件到备份目录（保持原文件名）
   │   └── 写入 backup_info.json 记录
   └── 记录备份日志
6. 继续正常的工作流执行...
```

### 3. 核心代码结构

```python
async def execute_complete_workflow(self) -> Dict[str, Any]:
    """执行完整工作流"""
    try:
        # 确保任务目录存在
        if not self._ensure_task_directory():
            raise Exception("无法创建任务目录")
        
        # 🆕 新增：备份现有文件（仅在complete模式下）
        self._backup_existing_files_if_needed()
        
        # 开始任务
        self.task_manager.update_task_status(self.task_id, 'in_progress')
        
        # ... 其余代码保持不变

def _backup_existing_files_if_needed(self):
    """如果需要，备份现有文件（仅备份文件，不包括子目录）"""
    # 1. 扫描任务目录中的文件
    # 2. 排除 table_list.txt 和子目录
    # 3. 如果有文件需要备份，创建备份目录
    # 4. 移动文件到备份目录
    # 5. 生成备份记录文件
    # 6. 记录日志
```

### 4. 备份记录

在备份目录中创建 `backup_info.json` 文件：

```json
{
  "backup_time": "2025-01-21T09:44:00.123456",
  "backup_directory": "file_bak_20250121_094400",
  "moved_files": ["old_file.ddl", "old_data.json"],
  "failed_files": [],
  "task_id": "task_20250721_083557"
}
```

### 5. 冲突处理

如果备份目录名已存在，添加序号后缀：
- `file_bak_20250121_094400`
- `file_bak_20250121_094400_1`
- `file_bak_20250121_094400_2`
- ...

## 效果示例

### 执行前

```
task_20250721_083557/
├── table_list.txt          # 用户上传的表清单
├── old_file.ddl            # 之前生成的DDL文件
├── old_data.json           # 之前生成的数据文件
├── some_log.log            # 之前的日志文件
└── some_subdir/            # 子目录不处理
    └── file.txt
```

### 执行后

```
task_20250721_083557/
├── table_list.txt                    # 保留在原位置
├── file_bak_20250121_094400/         # 新建备份目录
│   ├── old_file.ddl                  # 移动过来，文件名不变
│   ├── old_data.json                 # 移动过来，文件名不变
│   ├── some_log.log                  # 移动过来，文件名不变
│   └── backup_info.json              # 备份记录
├── some_subdir/                      # 子目录不动
│   └── file.txt
└── [新生成的文件...]                # 工作流新生成的文件
```

## 影响范围

### ✅ 会受影响

- **API调用**：`POST /api/v0/data_pipeline/tasks/{task_id}/execute` + `{"execution_mode": "complete"}`
- **完整工作流模式**：所有通过API执行的完整工作流

### ❌ 不受影响

- **单步执行模式**：`{"execution_mode": "step"}` 不会触发备份
- **脚本执行**：`python -m data_pipeline.schema_workflow` 不受影响
- **其他API接口**：文件上传、任务管理等其他接口不受影响
- **现有功能**：不影响任何现有的执行逻辑

### 向后兼容性

- ✅ 完全向后兼容
- ✅ 不改变现有API接口
- ✅ 不影响现有文件结构
- ✅ 不影响执行性能

## 错误处理

### 1. 备份失败处理
- 如果备份目录创建失败，记录错误但不阻止主流程
- 如果单个文件移动失败，记录警告但继续处理其他文件
- 备份过程完全失败，记录错误但允许工作流继续执行

### 2. 日志记录
- 备份开始和完成时间
- 移动的文件列表
- 备份目录路径
- 任何移动失败的文件和错误信息

### 3. 无需备份的情况
- 任务目录为空：不创建备份，直接继续
- 只有 `table_list.txt`：不创建备份，直接继续
- 只有子目录：不创建备份，直接继续

## 测试场景

1. **空目录测试**：任务目录为空，不应创建备份
2. **仅表清单测试**：只有 `table_list.txt`，不应创建备份
3. **有文件测试**：有其他文件，应创建备份并移动文件
4. **混合内容测试**：有文件、子目录和 `table_list.txt`，只移动文件
5. **备份冲突测试**：备份目录已存在，应创建序号后缀目录
6. **权限测试**：文件移动权限问题，应记录错误但继续执行
7. **重复执行测试**：多次执行应创建多个备份目录

## 实施优先级

- **P0**：核心备份功能实现
- **P1**：错误处理和日志记录
- **P2**：备份记录文件生成
- **P3**：冲突处理和序号后缀

## 后续优化建议

1. **配置选项**：未来可考虑添加备份开关配置
2. **清理策略**：考虑添加旧备份目录的自动清理机制
3. **备份统计**：在API响应中包含备份统计信息
4. **恢复功能**：考虑添加从备份恢复文件的功能 