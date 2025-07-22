# 文件命名策略重构方案

## 概述

当前在重复执行 API 步骤时，会产生重复文件导致后续步骤加载冗余数据的问题。本方案通过修改文件命名策略，使重复执行产生的旧文件不会被后续步骤识别和加载。

## 问题分析

### 当前行为

1. **`ddl_generation` 步骤**：
   - 重复执行时产生 `bss_company_1.ddl`、`bss_company_detail_1.md` 等文件
   - 这些文件仍然会被 `training_load` 步骤识别为有效训练文件

2. **`qa_generation` 步骤**：
   - 重复执行时产生多个时间戳文件：`qs_db_20250721_100000_pair.json`、`qs_db_20250721_100500_pair.json`
   - 所有 `*_pair.json` 文件都会被 `training_load` 步骤加载

3. **`sql_validation` 步骤**：
   - 创建备份文件 `*.json.backup`
   - 这些备份文件可能被误识别

### 问题影响

- `training_load` 步骤会加载所有符合命名规则的文件，导致训练数据重复
- 数据质量降低，模型性能受影响
- 存储空间浪费

## 解决方案

### 1. DDL Generation 文件命名策略修改

**目标**：将冲突文件的后缀放在扩展名之后，使其不被识别为有效文件。

**当前行为**：
```
bss_company.ddl → bss_company_1.ddl
bss_company_detail.md → bss_company_detail_1.md
```

**修改后行为**：
```
bss_company.ddl → bss_company.ddl_1
bss_company_detail.md → bss_company_detail.md_1
```

**修改位置**：`data_pipeline/utils/file_manager.py`

### 2. QA Generation 文件重命名策略

**目标**：在生成新文件前，将现有的 `*_pair.json` 文件重命名为 `*_pair.json_old`。

**修改逻辑**：
- 检查任务目录下是否存在 `*_pair.json` 文件
- 如果存在，重命名为 `*_pair.json_old`
- 同时处理 `*_pair.json.backup` → `*_pair.json.backup_old`

**修改位置**：`data_pipeline/qa_generation/qs_agent.py`

### 3. 确保各步骤忽略重命名文件

**Training Load 步骤**：
- 确保只加载标准扩展名文件（`.ddl`、`.md`、`_pair.json`）
- 忽略带 `_数字` 后缀的文件（如 `.ddl_1`、`.md_1`、`.json_old`）

**SQL Validation 步骤**：
- 确保只扫描标准的 `*_pair.json` 文件
- 忽略 `*_pair.json_old`、`*_pair.json.backup_old` 文件

## 详细实现方案

### 步骤 1：修改 FileNameManager

**文件**：`data_pipeline/utils/file_manager.py`

**修改方法**：`_ensure_unique_filename`

```python
def _ensure_unique_filename(self, filename: str) -> str:
    """确保文件名唯一性"""
    if filename not in self.used_names:
        return filename
    
    # 如果重名，在扩展名后添加数字后缀
    counter = 1
    
    while True:
        unique_name = f"{filename}_{counter}"
        if unique_name not in self.used_names:
            self.logger.warning(f"文件名冲突，'{filename}' 重命名为 '{unique_name}'")
            return unique_name
        counter += 1
```

**影响评估**：
- 只影响 `ddl_generation` 步骤的文件生成
- 不影响现有的命令行功能
- 向后兼容：现有文件不受影响

### 步骤 2：修改 QA Generation Agent

**文件**：`data_pipeline/qa_generation/qs_agent.py`

**新增方法**：在 `generate` 方法开始前调用文件清理

```python
async def _rename_existing_files(self):
    """重命名现有的输出文件"""
    try:
        # 查找现有的 *_pair.json 文件
        pair_files = list(self.output_dir.glob("*_pair.json"))
        
        for pair_file in pair_files:
            old_name = f"{pair_file}_old"
            pair_file.rename(old_name)
            self.logger.info(f"重命名文件: {pair_file.name} → {Path(old_name).name}")
        
        # 查找现有的 backup 文件
        backup_files = list(self.output_dir.glob("*_pair.json.backup"))
        
        for backup_file in backup_files:
            old_name = f"{backup_file}_old"
            backup_file.rename(old_name)
            self.logger.info(f"重命名备份文件: {backup_file.name} → {Path(old_name).name}")
            
    except Exception as e:
        self.logger.warning(f"重命名现有文件时出错: {e}")
```

**修改位置**：在 `generate` 方法中，文件验证之后，主题提取之前调用

### 步骤 3：确保 Training Load 步骤的文件过滤

**文件**：`data_pipeline/trainer/run_training.py`

**修改方法**：`process_training_files` 中的文件扫描逻辑

```python
# 在文件类型判断中添加排除逻辑
if file_lower.endswith(".ddl") and not file_lower.endswith(".ddl_1") and not file_lower.endswith(".ddl_2"):
    # 处理DDL文件
elif file_lower.endswith(".md") and not any(file_lower.endswith(f".md_{i}") for i in range(1, 10)):
    # 处理MD文件
elif (file_lower.endswith("_pair.json") and 
      not file_lower.endswith("_pair.json_old") and 
      not file_lower.endswith("_pair.json.backup_old")):
    # 处理问答对文件
```

**更优雅的实现**：创建文件过滤器函数

```python
def _is_valid_training_file(self, filename: str) -> bool:
    """判断是否为有效的训练文件"""
    filename_lower = filename.lower()
    
    # 排除带数字后缀的文件
    if re.search(r'\.(ddl|md)_\d+$', filename_lower):
        return False
    
    # 排除 _old 后缀的文件
    if filename_lower.endswith('_old'):
        return False
    
    # 排除 .backup 相关文件
    if '.backup' in filename_lower:
        return False
    
    return True
```

### 步骤 4：确保 SQL Validation 步骤的文件过滤

**文件**：`data_pipeline/validators/sql_validate_cli.py`

**修改方法**：`resolve_input_file_and_output_dir` 中的文件搜索逻辑

```python
# 在任务目录中查找Question-SQL文件
if task_dir.exists():
    # 只搜索标准命名的文件，排除 _old 后缀
    possible_files = [
        f for f in task_dir.glob("*_pair.json") 
        if not f.name.endswith('_old') and '.backup' not in f.name
    ]
    if possible_files:
        # 选择最新的文件（按修改时间排序）
        input_file = str(max(possible_files, key=lambda f: f.stat().st_mtime))
    else:
        input_file = None
```

## 测试验证方案

### 测试场景 1：DDL Generation 重复执行

1. 执行 `ddl_generation` 步骤生成初始文件
2. 再次执行 `ddl_generation` 步骤
3. 验证：
   - 新文件为标准命名（如 `bss_company.ddl`）
   - 旧文件被重命名（如 `bss_company.ddl_1`）
   - `training_load` 只加载标准命名文件

### 测试场景 2：QA Generation 重复执行

1. 执行 `qa_generation` 步骤生成初始 JSON 文件
2. 再次执行 `qa_generation` 步骤
3. 验证：
   - 旧 JSON 文件被重命名为 `*_pair.json_old`
   - 新 JSON 文件使用标准命名
   - `sql_validation` 和 `training_load` 只处理标准文件

### 测试场景 3：完整流程测试

1. 在同一任务目录下重复执行完整流程
2. 验证每个步骤都能正确处理文件
3. 确认 `training_load` 不会加载重复数据

## 风险评估

### 低风险

- 文件重命名操作是原子性的
- 只影响新生成的冲突文件
- 现有文件和工作流程不受影响

### 中等风险

- 需要确保所有步骤的文件扫描逻辑一致
- 可能需要更新相关文档和使用说明

### 缓解措施

- 分步骤实施，逐一验证
- 保持向后兼容性
- 添加详细的日志记录
- 制定回滚方案

## 实施优先级

1. **高优先级**：修改 `FileNameManager` 的命名策略
2. **高优先级**：修改 `qa_generation` 的文件重命名逻辑
3. **中优先级**：更新 `training_load` 的文件过滤逻辑
4. **中优先级**：更新 `sql_validation` 的文件搜索逻辑
5. **低优先级**：完善测试用例和文档

## 预期效果

实施后，重复执行任何步骤都不会导致：
- 训练数据重复
- 文件冲突覆盖
- 存储空间浪费

同时保持：
- 完整的执行历史记录
- 清晰的文件组织结构
- 良好的可追溯性 