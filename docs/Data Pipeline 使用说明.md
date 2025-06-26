# Data Pipeline 使用说明

## 目录

1. [功能概述](#1-功能概述)
2. [安装与配置](#2-安装与配置)
3. [一键执行完整工作流（推荐）](#3-一键执行完整工作流推荐)
4. [生成DDL和MD文档](#4-生成ddl和md文档)
5. [生成Question-SQL训练数据](#5-生成question-sql训练数据)
6. [SQL验证和修复](#6-sql验证和修复)
7. [训练数据管理](#7-训练数据管理)
8. [配置详解](#8-配置详解)
9. [常见问题](#9-常见问题)
10. [最佳实践](#10-最佳实践)

## 1. 功能概述

Data Pipeline 是一个完整的数据库逆向工程和训练数据生成系统，提供以下核心功能：

### 1.1 DDL和MD文档生成
- 自动连接PostgreSQL数据库
- 批量处理表清单
- 使用LLM生成中文注释
- 自动检测枚举字段
- 生成标准化的DDL和MD文档

### 1.2 Question-SQL训练数据生成
- 验证DDL和MD文件完整性
- 分析表结构提取业务主题
- 为每个主题生成高质量的Question-SQL对
- 支持中断恢复和并行处理

### 1.3 SQL验证和修复
- 自动验证生成的SQL语句
- 使用EXPLAIN语法检查SQL有效性
- LLM自动修复无效SQL语句
- 详细的验证报告和统计信息

### 1.4 训练数据管理
- 自动识别多种训练数据格式
- 统一的训练数据加载和处理
- 支持DDL、文档、Q&A对等多种数据类型

### 1.5 一键工作流编排器（推荐）
- 端到端自动化执行完整流程
- DDL/MD生成 → Question-SQL生成 → SQL验证修复
- 详细的执行报告和性能指标
- 支持灵活配置和错误恢复

## 2. 安装与配置

### 2.1 依赖安装

```bash
pip install asyncpg asyncio
```

### 2.2 基本配置

Data Pipeline 使用项目现有的 LLM 配置，无需额外配置数据库连接。

### 2.3 目录结构

```
data_pipeline/
├── ddl_generation/          # DDL/MD文档生成工具
│   ├── ddl_md_generator.py
│   └── training_data_agent.py
├── qa_generation/           # Q&A生成工具
│   ├── qs_agent.py
│   └── qs_generator.py
├── validators/              # SQL验证工具  
│   ├── sql_validate_cli.py
│   ├── sql_validation_agent.py
│   └── sql_validator.py
├── trainer/                 # 训练数据管道
│   ├── run_training.py
│   └── vanna_trainer.py
├── training_data/           # 训练数据存储目录
├── tools/                   # 核心工具
├── utils/                   # 工具函数
├── config.py               # 配置文件
└── schema_workflow.py  # 工作流编排器
```

## 3. 一键执行完整工作流（推荐）

### 3.1 工作流编排器概述

`SchemaWorkflowOrchestrator` 是 Data Pipeline 的核心组件，提供端到端的自动化处理流程：

1. **DDL和MD文档生成** - 连接数据库，生成表结构文档
2. **Question-SQL对生成** - 基于文档生成训练数据
3. **SQL验证和修复** - 验证SQL有效性并自动修复错误
4. **训练数据加载** - 将生成的数据加载到向量数据库中

### 3.2 命令行使用

#### 基本使用（完整工作流）
```bash
python -m data_pipeline.schema_workflow \
  --db-connection "postgresql://user:pass@localhost:5432/highway_db" \
  --table-list tables.txt \
  --business-context "高速公路服务区管理系统" \
  --output-dir ./data_pipeline/training_data/
```

#### 跳过SQL验证
```bash
python -m data_pipeline.schema_workflow \
  --db-connection "postgresql://user:pass@localhost:5432/ecommerce_db" \
  --table-list tables.txt \
  --business-context "电商系统" \
  --skip-validation
```

#### 禁用LLM修复
```bash
python -m data_pipeline.schema_workflow \
  --db-connection "postgresql://user:pass@localhost:5432/management_db" \
  --table-list tables.txt \
  --business-context "管理系统" \
  --disable-llm-repair
```

#### 不修改原始文件（仅生成报告）
```bash
python -m data_pipeline.schema_workflow \
  --db-connection "postgresql://user:pass@localhost:5432/business_db" \
  --table-list tables.txt \
  --business-context "业务系统" \
  --no-modify-file
```

### 3.3 编程方式使用

```python
import asyncio
from data_pipeline.schema_workflow import SchemaWorkflowOrchestrator

async def run_complete_workflow():
    # 创建工作流编排器
    orchestrator = SchemaWorkflowOrchestrator(
        db_connection="postgresql://user:pass@localhost:5432/highway_db",
        table_list_file="tables.txt",
        business_context="高速公路服务区管理系统",
        output_dir="./data_pipeline/training_data/",
        enable_sql_validation=True,      # 启用SQL验证
        enable_llm_repair=True,          # 启用LLM修复
        modify_original_file=True        # 修改原始JSON文件
    )
    
    # 执行完整工作流程
    report = await orchestrator.execute_complete_workflow()
    
    # 处理结果
    if report["success"]:
        print(f"✅ 工作流程执行成功！")
        print(f"📄 最终输出文件: {report['final_outputs']['primary_output_file']}")
        print(f"❓ 最终问题数量: {report['final_outputs']['final_question_count']}")
        print(f"⏱️  总耗时: {report['performance_metrics']['total_duration']} 秒")
    else:
        print(f"❌ 工作流程执行失败: {report['error']['message']}")
        print(f"💥 失败步骤: {report['error']['failed_step']}")

# 运行工作流程
asyncio.run(run_complete_workflow())
```

### 3.4 工作流参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--db-connection` | 数据库连接字符串（包含数据库名） | 必需 |
| `--table-list` | 表清单文件路径 | 必需 |
| `--business-context` | 业务上下文描述 | 必需 |
| `--output-dir` | 输出目录 | `./data_pipeline/training_data/` |
| `--skip-validation` | 跳过SQL验证步骤 | `False`（默认执行SQL验证） |
| `--disable-llm-repair` | 禁用LLM修复功能 | `False`（默认启用LLM修复） |
| `--no-modify-file` | 不修改原始JSON文件 | `False`（默认修改原文件） |
| `--skip-training-load` | 跳过训练数据加载步骤 | `False`（默认执行训练数据加载） |
| `--verbose` | 启用详细日志 | `False` |
| `--log-file` | 日志文件路径 | 无 |

### 3.5 工作流执行报告

工作流编排器会生成详细的执行报告，包括：

```python
{
    "success": True,
    "workflow_summary": {
        "total_duration": 285.34,
        "completed_steps": ["ddl_md_generation", "question_sql_generation", "sql_validation", "training_data_load"],
        "total_steps": 4
    },
    "processing_results": {
        "ddl_md_generation": {
            "total_tables": 8,
            "processed_successfully": 8,
            "duration": 89.23
        },
        "question_sql_generation": {
            "total_questions": 50,
            "total_themes": 5,
            "duration": 123.45
        },
        "sql_validation": {
            "success_rate": 0.94,
            "valid_sql_count": 47,
            "invalid_sql_count": 3,
            "duration": 32.99
        },
        "training_data_load": {
            "total_records": 195,
            "data_type_counts": {
                "ddl": 8,
                "documentation": 8,
                "sql": 47
            },
            "duration": 39.67
        }
    },
    "final_outputs": {
        "primary_output_file": "./data_pipeline/training_data/qs_highway_db_20240123_143052_pair.json",
        "final_question_count": 47
    },
    "performance_metrics": {
        "step1_duration": 89.23,
        "step2_duration": 123.45,
        "step3_duration": 32.99,
        "step4_duration": 39.67,
        "total_duration": 285.34
    }
}
```

## 4. 生成DDL和MD文档（分步执行）

### 4.1 命令格式

```bash
python -m data_pipeline.ddl_generation.ddl_md_generator \
  --db-connection <数据库连接字符串> \
  --table-list <表清单文件> \
  --business-context <业务上下文> \
  [可选参数]
```

### 4.2 必需参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--db-connection` | PostgreSQL数据库连接字符串 | `postgresql://user:pass@localhost:5432/dbname` |
| `--table-list` | 表清单文件路径 | `./tables.txt` |
| `--business-context` | 业务上下文描述 | `"高速公路服务区管理系统"` |

### 4.3 可选参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--output-dir` | 输出目录路径 | `./data_pipeline/training_data/` |
| `--pipeline` | 处理链类型 | `full` |
| `--max-concurrent` | 最大并发表数量 | `1` |
| `--verbose` | 启用详细日志 | `False` |
| `--log-file` | 日志文件路径 | `无` |
| `--no-filter-system-tables` | 禁用系统表过滤 | `False` |
| `--check-permissions-only` | 仅检查数据库权限 | `False` |

### 4.4 使用示例

#### 基本使用
```bash
python -m data_pipeline.ddl_generation.ddl_md_generator \
  --db-connection "postgresql://postgres:postgres@localhost:5432/highway_db" \
  --table-list ./tables.txt \
  --business-context "高速公路服务区管理系统"
```

#### 指定输出目录和启用详细日志
```bash
python -m data_pipeline.ddl_generation.ddl_md_generator \
  --db-connection "postgresql://postgres:postgres@localhost:5432/highway_db" \
  --table-list ./tables.txt \
  --business-context "高速公路服务区管理系统" \
  --output-dir ./data_pipeline/training_data/ \
  --verbose
```

#### 权限检查
```bash
python -m data_pipeline.ddl_generation.ddl_md_generator \
  --db-connection "postgresql://postgres:postgres@localhost:5432/highway_db" \
  --check-permissions-only
```

## 5. 生成Question-SQL训练数据（分步执行）

### 5.1 前置条件

必须先执行DDL和MD文档生成，确保输出目录中有完整的DDL和MD文件。

### 5.2 命令格式

```bash
python -m data_pipeline.qa_generation.qs_generator \
  --output-dir <输出目录> \
  --table-list <表清单文件> \
  --business-context <业务上下文> \
  [可选参数]
```

### 5.3 必需参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--output-dir` | 包含DDL和MD文件的目录 | `./data_pipeline/training_data/` |
| `--table-list` | 表清单文件路径（用于验证） | `./tables.txt` |
| `--business-context` | 业务上下文描述 | `"高速公路服务区管理系统"` |

### 5.4 使用示例

#### 基本使用
```bash
python -m data_pipeline.qa_generation.qs_generator \
  --output-dir ./data_pipeline/training_data/ \
  --table-list ./tables.txt \
  --business-context "高速公路服务区管理系统" \
   highway_db
```

#### 启用详细日志
```bash
python -m data_pipeline.qa_generation.qs_generator \
  --output-dir ./data_pipeline/training_data/ \
  --table-list ./tables.txt \
  --business-context "高速公路服务区管理系统" \
   highway_db \
  --verbose
```

## 6. SQL验证和修复

### 6.1 命令格式

生成Question-SQL对后，可以使用SQL验证功能。**注意：命令行使用时，默认启用LLM修复和文件修改功能**。

```bash
python -m data_pipeline.validators.sql_validate_cli \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./qs_highway_db_20240123_143052_pair.json \
  --output-dir ./validation_reports
```

### 6.2 SQL验证参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--db-connection` | 数据库连接字符串 | 必需 |
| `--input-file` | Question-SQL文件路径 | 必需 |
| `--output-dir` | 验证报告输出目录 | 输入文件同目录 |
| `--disable-llm-repair` | 禁用LLM修复功能 | `False`（默认启用修复） |
| `--no-modify-file` | 不修改原始JSON文件 | `False`（默认修改原文件） |
| `--max-concurrent` | 最大并发验证数 | `5` |
| `--batch-size` | 批处理大小 | `10` |
| `--timeout` | 单个验证超时时间（秒） | `30` |
| `--verbose` | 启用详细日志 | `False` |
| `--dry-run` | 仅解析文件不执行验证 | `False` |
| `--save-json` | 保存详细JSON报告 | `False` |

### 6.3 SQL验证使用示例

```bash
# 基本验证（默认：启用LLM修复和文件修改）
python -m data_pipeline.validators.sql_validate_cli \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json

# 仅生成报告，不修改文件
python -m data_pipeline.validators.sql_validate_cli \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --no-modify-file

# 启用文件修改，但禁用LLM修复（仅删除无效SQL）
python -m data_pipeline.validators.sql_validate_cli \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --disable-llm-repair

# 性能调优参数
python -m data_pipeline.validators.sql_validate_cli \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --max-concurrent 10 \
  --batch-size 20 \
  --timeout 60 \
  --verbose
```

## 7. 训练数据管理

### 7.1 训练数据加载

```bash
# 使用训练数据管道
python -m data_pipeline.trainer.run_training \
  --data_path ./data_pipeline/training_data/
```

### 7.2 支持的文件格式

Data Pipeline 自动识别以下训练数据格式：

- **`.ddl`** 文件 → `train_ddl_statements()`
- **`.md/.markdown`** → `train_documentation_blocks()`
- **`_pair.json/_pairs.json`** → `train_json_question_sql_pairs()`
- **`_pair.sql/_pairs.sql`** → `train_formatted_question_sql_pairs()`
- **`.sql`** (其他) → `train_sql_examples()`

### 7.3 训练数据目录结构

```
data_pipeline/training_data/
├── bss_service_area.ddl              # DDL文件
├── bss_service_area_detail.md        # MD文档
├── bss_company.ddl
├── bss_company_detail.md
├── qs_highway_db_20240123_143052_pair.json  # Q&A训练数据
├── filename_mapping.txt              # 文件名映射
└── logs/                            # 日志目录
    └── data_pipeline_20240123.log
```

## 8. 配置详解

### 8.1 主要配置项

配置文件位于 `data_pipeline/config.py`：

```python
# DDL/MD生成相关配置
"output_directory": "./data_pipeline/training_data/",   # 输出目录
"create_subdirectories": False,                        # 不创建子目录
"max_concurrent_tables": 1,                            # 最大并发数（避免LLM并发问题）
"sample_data_limit": 20,                              # 数据采样量
"large_table_threshold": 1000000,                     # 大表阈值（100万行）
"filter_system_tables": True,                          # 过滤系统表
"continue_on_error": True,                             # 错误后继续

# Question-SQL生成配置
"qs_generation": {
    "max_tables": 20,                                 # 最大表数量限制
    "theme_count": 5,                                 # 主题数量
    "questions_per_theme": 10,                        # 每主题问题数
    "max_concurrent_themes": 1,                       # 并行主题数（避免LLM并发问题）
    "continue_on_theme_error": True,                  # 主题失败继续
    "save_intermediate": True,                        # 保存中间结果
}

# SQL验证配置
"sql_validation": {
    "max_concurrent_validations": 5,                  # 并发验证数
    "validation_timeout": 30,                         # 单个验证超时(秒)
    "batch_size": 10,                                 # 批处理大小
    "enable_sql_repair": False,                       # SQL修复功能（命令行覆盖为True）
    "modify_original_file": False,                    # 文件修改功能（命令行覆盖为True）
    "readonly_mode": True,                            # 启用只读模式
}
```

### 8.2 修改配置

可以通过编辑 `data_pipeline/config.py` 文件来修改默认配置。

## 9. 常见问题

### 9.1 表数量超过20个怎么办？

**错误信息**：
```
表数量(25)超过限制(20)。请分批处理或调整配置中的max_tables参数。
```

**解决方案**：
1. 分批处理：将表清单分成多个文件，每个不超过20个表
2. 修改配置：在 `config.py` 中增加 `max_tables` 限制

### 9.2 DDL和MD文件数量不一致

**错误信息**：
```
DDL文件数量(5)与表数量(6)不一致
```

**解决方案**：
1. 检查是否有表处理失败
2. 查看日志文件找出失败的表
3. 重新运行DDL/MD生成

### 9.3 LLM调用失败

**可能原因**：
- 网络连接问题
- API配额限制
- Token超限

**解决方案**：
1. 检查网络连接
2. 查看中间结果文件，从断点继续
3. 减少表数量或分批处理

### 9.4 权限不足

**错误信息**：
```
数据库查询权限不足
```

**解决方案**：
1. 使用 `--check-permissions-only` 检查权限
2. 确保数据库用户有SELECT权限
3. Data Pipeline支持只读数据库

### 9.5 工作流编排器相关问题

**Q: 工作流中途失败，如何恢复？**
A: 工作流编排器会保留已完成步骤的输出文件，可以手动从失败步骤开始重新执行。

**Q: 如何只执行部分步骤？**
A: 使用 `--skip-validation` 跳过SQL验证，或使用分步执行方式调用各个模块。

**Q: 工作流执行时间过长怎么办？**
A: 可以通过减少表数量、调整并发参数、或分批处理来优化执行时间。

### 9.6 SQL验证器默认行为说明

**重要**：SQL验证器的命令行模式与配置文件中的默认值不同：

- **配置文件默认**：`enable_sql_repair=False`, `modify_original_file=False`
- **命令行默认**：启用LLM修复和文件修改功能
- **原因**：命令行使用时通常期望完整的修复功能，而配置文件提供保守的默认值

如需禁用，请明确使用 `--disable-llm-repair` 或 `--no-modify-file` 参数。

## 10. 最佳实践

### 10.1 推荐工作流程

**方式一：一键执行（推荐）**
```bash
# 完整工作流程，一个命令搞定
python -m data_pipeline.schema_workflow \
  --db-connection "postgresql://user:pass@localhost:5432/highway_db" \
  --table-list tables.txt \
  --business-context "高速公路服务区管理系统" \
  --output-dir ./data_pipeline/training_data/
```

**方式二：分步执行（调试时使用）**
1. **第一步**：生成DDL和MD文档
   ```bash
   python -m data_pipeline.ddl_generation.ddl_md_generator --db-connection "..." --table-list tables.txt --business-context "..." --output-dir ./data_pipeline/training_data/
   ```

2. **第二步**：人工检查
   - 检查DDL文件的表结构是否正确
   - 确认MD文档中的注释是否准确
   - 根据需要手动调整

3. **第三步**：生成Question-SQL
   ```bash
   python -m data_pipeline.qa_generation.qs_generator --output-dir ./data_pipeline/training_data/ --table-list tables.txt --business-context "..."
   ```

4. **第四步**：验证SQL（可选）
   ```bash
   python -m data_pipeline.validators.sql_validate_cli --db-connection "..." --input-file ./qs_xxx.json
   ```

5. **第五步**：训练数据加载
   ```bash
   python -m data_pipeline.trainer.run_training --data_path ./data_pipeline/training_data/
   ```

### 10.2 表清单组织

- 按业务模块分组
- 每组不超过15-20个表
- 使用注释说明每组的用途

### 10.3 业务上下文优化

- 提供准确的业务背景描述
- 包含行业特定术语
- 说明主要业务流程

### 10.4 输出文件管理

- 定期备份生成的文件
- 使用版本控制管理DDL文件
- 保留中间结果用于调试
- 统一使用 `./data_pipeline/training_data/` 目录

### 10.5 工作流编排器最佳实践

- **首次使用**：建议启用详细日志（`--verbose`）观察执行过程
- **生产环境**：使用默认参数，启用SQL验证和修复
- **调试阶段**：可以使用 `--skip-validation` 跳过验证步骤加快执行
- **质量要求高**：使用 `--no-modify-file` 仅生成报告，手动审查后再决定是否修改

### 10.6 数据管道集成

- **训练数据统一管理**：所有生成的数据都存储在 `data_pipeline/training_data/` 目录
- **自动化训练**：可以定期运行工作流编排器更新训练数据
- **版本控制**：建议对训练数据进行版本管理
- **监控和报告**：利用详细的执行报告监控数据质量

## 总结

Data Pipeline 提供了完整的数据库逆向工程解决方案，从原始数据库schema到可用的训练数据，整个流程完全自动化。通过工作流编排器，用户可以一键完成所有步骤，也可以根据需要分步执行和调试。系统设计考虑了容错性、可扩展性和易用性，适合各种规模的数据处理需求。

-------
  一键执行（推荐）：

  # 完整的4步流程
  python -m data_pipeline.schema_workflow \
    --db-connection "postgresql://user:pass@localhost:5432/highway_db" \
    --table-list tables.txt \
    --business-context "高速公路服务区管理系统" \
    --output-dir ./data_pipeline/training_data/

  # 如需跳过训练数据加载
  python -m data_pipeline.schema_workflow \
    --db-connection "postgresql://user:pass@localhost:5432/test_db" \
    --table-list tables.txt \
    --business-context "测试系统" \
    --skip-training-load

  分步执行：

  # 第1步：DDL/MD生成
  python -m data_pipeline.ddl_generation.ddl_md_generator --db-connection "..." --table-list tables.txt --business-context "..."

  # 第2步：Q&A生成
  python -m data_pipeline.qa_generation.qs_generator --output-dir ./data_pipeline/training_data/ --table-list tables.txt --business-context "..."

  # 第3步：SQL验证
  python -m data_pipeline.validators.sql_validate_cli --db-connection "..." --input-file ./qs_xxx.json

  # 第4步：训练数据加载
  python -m data_pipeline.trainer.run_training --data_path ./data_pipeline/training_data/
