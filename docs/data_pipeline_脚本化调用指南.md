# Data Pipeline 脚本化调用指南

## 概述

本文档详细介绍data_pipeline模块的脚本化调用方式、支持的参数列表以及脚本执行时的日志配置方式。data_pipeline是一个完整的数据库逆向工程和训练数据生成系统，支持从PostgreSQL数据库生成vanna.ai格式的训练数据。

## 目录

1. [模块架构概览](#1-模块架构概览)
2. [核心脚本入口](#2-核心脚本入口)
3. [一键工作流脚本](#3-一键工作流脚本)
4. [分步执行脚本](#4-分步执行脚本)
5. [日志配置](#5-日志配置)
6. [配置文件](#6-配置文件)
7. [使用示例](#7-使用示例)
8. [故障排查](#8-故障排查)

## 1. 模块架构概览

```
data_pipeline/
├── schema_workflow.py          # 🚀 一键工作流编排器（主要入口）
├── ddl_generation/
│   └── ddl_md_generator.py     # DDL/MD文档生成器
├── qa_generation/
│   └── qs_generator.py         # Question-SQL对生成器
├── validators/
│   └── sql_validate_cli.py     # SQL验证命令行工具
├── trainer/
│   └── run_training.py         # 训练数据加载脚本
├── task_executor.py            # 独立任务执行器（API专用）
├── config.py                   # 模块配置文件
└── dp_logging/                 # 日志管理模块
```

## 2. 核心脚本入口

### 2.1 主要脚本类型

| 脚本类型 | 入口点 | 用途 | 推荐使用场景 |
|---------|--------|------|-------------|
| **一键工作流** | `schema_workflow.py` | 完整的4步工作流 | ✅ 推荐：生产环境 |
| **DDL生成** | `ddl_generation/ddl_md_generator.py` | 仅生成DDL和MD文档 | 调试、分步执行 |
| **QA生成** | `qa_generation/qs_generator.py` | 仅生成Question-SQL对 | 调试、分步执行 |
| **SQL验证** | `validators/sql_validate_cli.py` | 仅验证SQL语句 | 调试、质量检查 |
| **训练加载** | `trainer/run_training.py` | 仅加载训练数据 | 调试、分步执行 |

### 2.2 执行方式

```bash
# 使用python -m方式（推荐）
python -m data_pipeline.schema_workflow [参数]
python -m data_pipeline.ddl_generation.ddl_md_generator [参数]
python -m data_pipeline.qa_generation.qs_generator [参数]
python -m data_pipeline.validators.sql_validate_cli [参数]
python -m data_pipeline.trainer.run_training [参数]

# 直接执行方式
python data_pipeline/schema_workflow.py [参数]
```

## 3. 一键工作流脚本

### 3.1 脚本概述

**入口点**: `data_pipeline/schema_workflow.py`  
**主要类**: `SchemaWorkflowOrchestrator`  
**功能**: 端到端执行完整的4步工作流程

### 3.2 执行步骤

1. **DDL/MD生成** (0% → 40%)
2. **Question-SQL生成** (40% → 70%)
3. **SQL验证** (70% → 90%)
4. **训练数据加载** (90% → 100%)

### 3.3 命令行参数

#### 必需参数

| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `--db-connection` | string | PostgreSQL连接字符串 | `postgresql://user:pass@host:5432/dbname` |
| `--table-list` | string | 表清单文件路径 | `./tables.txt` |
| `--business-context` | string | 业务上下文描述 | `"高速公路服务区管理系统"` |

#### 可选参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--output-dir` | string | `./data_pipeline/training_data/` | 输出目录路径 |
| `--skip-validation` | flag | `False` | 跳过SQL验证步骤 |
| `--disable-llm-repair` | flag | `False` | 禁用LLM修复功能 |
| `--no-modify-file` | flag | `False` | 不修改原始JSON文件 |
| `--skip-training-load` | flag | `False` | 跳过训练数据加载步骤 |
| `--verbose` | flag | `False` | 启用详细日志输出 |
| `--log-file` | string | 无 | 指定日志文件路径 |

### 3.4 使用示例

#### 基本使用（完整工作流）
```bash
python -m data_pipeline.schema_workflow \
  --db-connection "postgresql://postgres:postgres@localhost:5432/highway_db" \
  --table-list ./tables.txt \
  --business-context "高速公路服务区管理系统"
```

#### 跳过SQL验证
```bash
python -m data_pipeline.schema_workflow \
  --db-connection "postgresql://user:pass@localhost:5432/ecommerce_db" \
  --table-list ./tables.txt \
  --business-context "电商系统" \
  --skip-validation
```

#### 禁用LLM修复
```bash
python -m data_pipeline.schema_workflow \
  --db-connection "postgresql://user:pass@localhost:5432/management_db" \
  --table-list ./tables.txt \
  --business-context "管理系统" \
  --disable-llm-repair
```

#### 详细日志输出
```bash
python -m data_pipeline.schema_workflow \
  --db-connection "postgresql://user:pass@localhost:5432/business_db" \
  --table-list ./tables.txt \
  --business-context "业务系统" \
  --verbose \
  --log-file ./logs/workflow.log
```

## 4. 分步执行脚本

### 4.1 DDL/MD文档生成

**入口点**: `data_pipeline/ddl_generation/ddl_md_generator.py`

#### 参数列表

| 参数 | 必需 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--db-connection` | ✅ | string | - | 数据库连接字符串 |
| `--table-list` | ✅ | string | - | 表清单文件路径 |
| `--business-context` | ✅ | string | - | 业务上下文描述 |
| `--output-dir` | ❌ | string | config值 | 输出目录路径 |
| `--pipeline` | ❌ | enum | `full` | 处理链类型：`full`/`ddl_only`/`analysis_only` |
| `--max-concurrent` | ❌ | int | `1` | 最大并发表数量 |
| `--verbose` | ❌ | flag | `False` | 启用详细日志 |
| `--log-file` | ❌ | string | - | 日志文件路径 |
| `--no-filter-system-tables` | ❌ | flag | `False` | 禁用系统表过滤 |
| `--check-permissions-only` | ❌ | flag | `False` | 仅检查数据库权限 |

#### 使用示例

```bash
# 基本使用
python -m data_pipeline.ddl_generation.ddl_md_generator \
  --db-connection "postgresql://postgres:postgres@localhost:5432/highway_db" \
  --table-list ./tables.txt \
  --business-context "高速公路服务区管理系统"

# 仅生成DDL文件
python -m data_pipeline.ddl_generation.ddl_md_generator \
  --db-connection "postgresql://user:pass@localhost:5432/db" \
  --table-list ./tables.txt \
  --business-context "系统" \
  --pipeline ddl_only

# 权限检查
python -m data_pipeline.ddl_generation.ddl_md_generator \
  --db-connection "postgresql://user:pass@localhost:5432/db" \
  --check-permissions-only
```

### 4.2 Question-SQL对生成

**入口点**: `data_pipeline/qa_generation/qs_generator.py`

#### 参数列表

| 参数 | 必需 | 类型 | 说明 |
|------|------|------|------|
| `--output-dir` | ✅ | string | 包含DDL和MD文件的目录 |
| `--table-list` | ✅ | string | 表清单文件路径（用于验证） |
| `--business-context` | ✅ | string | 业务上下文描述 |
| `database_name` | ✅ | positional | 数据库名称 |
| `--verbose` | ❌ | flag | 启用详细日志 |

#### 使用示例

```bash
# 基本使用
python -m data_pipeline.qa_generation.qs_generator \
  --output-dir ./data_pipeline/training_data/ \
  --table-list ./tables.txt \
  --business-context "高速公路服务区管理系统" \
  highway_db

# 详细日志
python -m data_pipeline.qa_generation.qs_generator \
  --output-dir ./data_pipeline/training_data/ \
  --table-list ./tables.txt \
  --business-context "电商系统" \
  ecommerce_db \
  --verbose
```

### 4.3 SQL验证工具

**入口点**: `data_pipeline/validators/sql_validate_cli.py`

#### 参数列表

| 参数 | 必需 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--db-connection` | ✅ | string | - | 数据库连接字符串 |
| `--input-file` | ✅ | string | - | Question-SQL文件路径 |
| `--output-dir` | ❌ | string | 输入文件同目录 | 验证报告输出目录 |
| `--disable-llm-repair` | ❌ | flag | `False` | 禁用LLM修复功能 |
| `--no-modify-file` | ❌ | flag | `False` | 不修改原始JSON文件 |
| `--max-concurrent` | ❌ | int | `5` | 最大并发验证数 |
| `--batch-size` | ❌ | int | `10` | 批处理大小 |
| `--timeout` | ❌ | int | `30` | 单个验证超时时间（秒） |
| `--verbose` | ❌ | flag | `False` | 启用详细日志 |
| `--dry-run` | ❌ | flag | `False` | 仅解析文件不执行验证 |
| `--save-json` | ❌ | flag | `False` | 保存详细JSON报告 |

#### 使用示例

```bash
# 基本验证（默认：启用LLM修复和文件修改）
python -m data_pipeline.validators.sql_validate_cli \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./qs_highway_db_20240123_143052_pair.json

# 仅生成报告，不修改文件
python -m data_pipeline.validators.sql_validate_cli \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --no-modify-file

# 性能调优参数
python -m data_pipeline.validators.sql_validate_cli \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --max-concurrent 10 \
  --batch-size 20 \
  --timeout 60 \
  --verbose
```

### 4.4 训练数据加载

**入口点**: `data_pipeline/trainer/run_training.py`

#### 参数列表

| 参数 | 必需 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--data_path` | ❌ | string | config值 | 训练数据目录路径 |

#### 支持的文件格式

- **`.ddl`** 文件 → `train_ddl_statements()`
- **`.md/.markdown`** → `train_documentation_blocks()`
- **`_pair.json/_pairs.json`** → `train_json_question_sql_pairs()`
- **`_pair.sql/_pairs.sql`** → `train_formatted_question_sql_pairs()`
- **`.sql`** (其他) → `train_sql_examples()`

#### 使用示例

```bash
# 使用默认路径
python -m data_pipeline.trainer.run_training

# 指定路径
python -m data_pipeline.trainer.run_training \
  --data_path ./data_pipeline/training_data/task_20250627_143052/
```

## 5. 日志配置

### 5.1 日志系统架构

data_pipeline使用统一的日志管理系统，支持两种模式：

1. **脚本模式**: 生成`manual_YYYYMMDD_HHMMSS`格式的task_id
2. **API模式**: 使用传入的task_id

### 5.2 日志文件位置

#### 脚本模式日志
```
data_pipeline/training_data/manual_20250627_143052/
└── data_pipeline.log                    # 详细执行日志
```

#### API模式日志
```
data_pipeline/training_data/task_20250627_143052/
└── data_pipeline.log                    # 详细执行日志
```

#### 系统日志
```
logs/
├── app.log                              # 应用系统日志
├── agent.log                            # Agent日志
├── vanna.log                            # Vanna日志
└── data_pipeline.log                    # data_pipeline模块日志（已弃用）
```

### 5.3 日志配置方式

#### 5.3.1 使用内置日志系统

```python
from data_pipeline.dp_logging import get_logger

# 脚本模式
task_id = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
logger = get_logger("SchemaWorkflow", task_id)

# API模式
logger = get_logger("SchemaWorkflow", "task_20250627_143052")
```

#### 5.3.2 日志级别配置

| 级别 | 用途 | 输出位置 |
|------|------|----------|
| `DEBUG` | 详细调试信息 | 文件 |
| `INFO` | 正常流程信息 | 控制台 + 文件 |
| `WARNING` | 警告信息 | 控制台 + 文件 |
| `ERROR` | 错误信息 | 控制台 + 文件 |
| `CRITICAL` | 严重错误 | 控制台 + 文件 |

#### 5.3.3 日志格式

```
2025-07-01 14:30:52 [INFO] [SchemaWorkflowOrchestrator] schema_workflow.py:123 - 🚀 开始执行Schema工作流编排
2025-07-01 14:30:53 [INFO] [DDLMDGenerator] ddl_md_generator.py:45 - 开始处理表: bss_business_day_data
2025-07-01 14:31:20 [WARNING] [SQLValidator] sql_validator.py:78 - SQL验证失败，尝试LLM修复
2025-07-01 14:31:25 [ERROR] [TrainingDataLoader] run_training.py:234 - 训练数据加载失败: 连接超时
```

### 5.4 日志配置参数

#### 5.4.1 命令行参数

```bash
# 启用详细日志
python -m data_pipeline.schema_workflow \
  --verbose \
  [其他参数]

# 指定日志文件
python -m data_pipeline.schema_workflow \
  --log-file ./custom_logs/workflow.log \
  [其他参数]
```

#### 5.4.2 环境变量配置

```bash
# 设置日志级别
export DATA_PIPELINE_LOG_LEVEL=DEBUG

# 设置日志目录
export DATA_PIPELINE_LOG_DIR=./logs/data_pipeline/
```

#### 5.4.3 编程方式配置

```python
import logging
from data_pipeline.dp_logging import get_logger

# 配置日志级别
logging.getLogger("data_pipeline").setLevel(logging.DEBUG)

# 获取logger
logger = get_logger("CustomModule", "manual_20250627_143052")
logger.info("自定义日志消息")
```

## 6. 配置文件

### 6.1 主配置文件

**位置**: `data_pipeline/config.py`  
**变量**: `SCHEMA_TOOLS_CONFIG`

### 6.2 主要配置项

#### 6.2.1 核心配置

```python
{
    "output_directory": "./data_pipeline/training_data/",
    "default_business_context": "数据库管理系统",
    "default_pipeline": "full"
}
```

#### 6.2.2 处理链配置

```python
{
    "available_pipelines": {
        "full": ["database_inspector", "data_sampler", "comment_generator", "ddl_generator", "doc_generator"],
        "ddl_only": ["database_inspector", "data_sampler", "comment_generator", "ddl_generator"],
        "analysis_only": ["database_inspector", "data_sampler", "comment_generator"]
    }
}
```

#### 6.2.3 数据处理配置

```python
{
    "sample_data_limit": 20,                    # LLM分析的采样数据量
    "enum_detection_sample_limit": 5000,        # 枚举检测采样限制
    "enum_max_distinct_values": 20,             # 枚举字段最大不同值数量
    "large_table_threshold": 1000000            # 大表阈值（行数）
}
```

#### 6.2.4 并发配置

```python
{
    "max_concurrent_tables": 1,                 # 最大并发处理表数
    "max_concurrent_themes": 1,                 # 并行处理的主题数量
}
```

#### 6.2.5 Question-SQL生成配置

```python
{
    "qs_generation": {
        "max_tables": 20,                       # 最大表数量限制
        "theme_count": 5,                       # LLM生成的主题数量
        "questions_per_theme": 10,              # 每个主题生成的问题数
        "continue_on_theme_error": True,        # 主题生成失败是否继续
        "save_intermediate": True,              # 是否保存中间结果
        "output_file_prefix": "qs"              # 输出文件前缀
    }
}
```

#### 6.2.6 SQL验证配置

```python
{
    "sql_validation": {
        "max_concurrent_validations": 5,        # 并发验证数
        "validation_timeout": 30,               # 单个验证超时(秒)
        "batch_size": 10,                       # 批处理大小
        "enable_sql_repair": False,             # SQL修复功能
        "modify_original_file": False,          # 文件修改功能
        "readonly_mode": True                   # 启用只读模式
    }
}
```

### 6.3 配置优先级

```
命令行参数 > data_pipeline/config.py > 默认值
```

### 6.4 修改配置

#### 方法1: 直接修改配置文件

编辑 `data_pipeline/config.py` 文件中的 `SCHEMA_TOOLS_CONFIG` 字典。

#### 方法2: 编程方式修改

```python
from data_pipeline.config import SCHEMA_TOOLS_CONFIG, update_config

# 修改单个配置项
update_config("max_concurrent_tables", 2)

# 批量修改配置
update_config({
    "sample_data_limit": 50,
    "qs_generation.theme_count": 8
})
```

## 7. 使用示例

### 7.1 典型工作流场景

#### 场景1: 首次处理新数据库
```bash
# 1. 权限检查
python -m data_pipeline.ddl_generation.ddl_md_generator \
  --db-connection "postgresql://user:pass@localhost:5432/new_db" \
  --check-permissions-only

# 2. 完整工作流
python -m data_pipeline.schema_workflow \
  --db-connection "postgresql://user:pass@localhost:5432/new_db" \
  --table-list ./tables.txt \
  --business-context "新业务系统" \
  --verbose
```

#### 场景2: 调试模式分步执行
```bash
# 1. 仅生成DDL和MD
python -m data_pipeline.ddl_generation.ddl_md_generator \
  --db-connection "postgresql://user:pass@localhost:5432/db" \
  --table-list ./tables.txt \
  --business-context "测试系统" \
  --output-dir ./debug_output/

# 2. 检查结果后生成Q&A
python -m data_pipeline.qa_generation.qs_generator \
  --output-dir ./debug_output/ \
  --table-list ./tables.txt \
  --business-context "测试系统" \
  test_db

# 3. 验证SQL
python -m data_pipeline.validators.sql_validate_cli \
  --db-connection "postgresql://user:pass@localhost:5432/db" \
  --input-file ./debug_output/qs_test_db_*.json \
  --verbose
```

#### 场景3: 生产环境批量处理
```bash
# 创建处理脚本
cat > process_databases.sh << 'EOF'
#!/bin/bash

DATABASES=("db1" "db2" "db3")
BASE_CONNECTION="postgresql://user:pass@localhost:5432"

for db in "${DATABASES[@]}"; do
    echo "Processing database: $db"
    
    python -m data_pipeline.schema_workflow \
      --db-connection "${BASE_CONNECTION}/${db}" \
      --table-list "./tables_${db}.txt" \
      --business-context "${db}业务系统" \
      --output-dir "./output/${db}/" \
      --verbose
    
    if [ $? -eq 0 ]; then
        echo "✅ $db processed successfully"
    else
        echo "❌ $db processing failed"
    fi
done
EOF

chmod +x process_databases.sh
./process_databases.sh
```

### 7.2 表清单文件格式

#### 基本格式
```
# tables.txt
bss_business_day_data
bss_car_day_count
bss_company
bss_service_area
```

#### 包含Schema的格式
```
# tables_with_schema.txt
public.bss_business_day_data
public.bss_car_day_count
ods.dim_company
ods.fact_revenue
```

#### 带注释的格式
```
# tables_commented.txt
# 业务数据表
bss_business_day_data    # 营业日数据
bss_car_day_count        # 车流量统计

# 基础数据表
bss_company              # 公司信息
bss_service_area         # 服务区信息
```

### 7.3 输出文件结构

```
data_pipeline/training_data/manual_20250627_143052/
├── data_pipeline.log                           # 详细执行日志
├── bss_business_day_data.ddl                   # DDL文件
├── bss_business_day_data_detail.md             # MD文档
├── bss_car_day_count.ddl
├── bss_car_day_count_detail.md
├── qs_highway_db_20250627_143052_pair.json     # Question-SQL对
├── qs_highway_db_20250627_143052_pair.json.backup  # 备份文件
├── sql_validation_20250627_143052_summary.log  # SQL验证摘要
├── sql_validation_20250627_143052_report.json  # SQL验证详细报告
├── file_modifications_20250627_143052.log      # 文件修改日志
├── metadata.txt                                # 元数据文件
└── filename_mapping.txt                        # 文件名映射
```

## 8. 故障排查

### 8.1 常见错误

#### 8.1.1 表数量超过限制
```
错误信息: 表数量(25)超过限制(20)。请分批处理或调整配置中的max_tables参数。

解决方案:
1. 分批处理：将表清单分成多个文件
2. 修改配置：在config.py中增加max_tables限制
```

#### 8.1.2 DDL和MD文件数量不一致
```
错误信息: DDL文件数量(5)与表数量(6)不一致

解决方案:
1. 检查日志文件找出失败的表
2. 重新运行DDL/MD生成
3. 检查数据库权限
```

#### 8.1.3 LLM调用失败
```
错误信息: LLM调用超时或失败

解决方案:
1. 检查网络连接
2. 查看中间结果文件，从断点继续
3. 减少表数量或分批处理
4. 检查LLM服务配置
```

#### 8.1.4 权限不足
```
错误信息: 数据库查询权限不足

解决方案:
1. 使用--check-permissions-only检查权限
2. 确保数据库用户有SELECT权限
3. Data Pipeline支持只读数据库
```

### 8.2 日志分析

#### 8.2.1 查看详细日志
```bash
# 查看最新的任务日志
find data_pipeline/training_data/ -name "data_pipeline.log" -exec ls -t {} + | head -1 | xargs tail -f

# 搜索错误信息
grep -i "error" data_pipeline/training_data/manual_*/data_pipeline.log

# 搜索特定表的处理日志
grep "bss_company" data_pipeline/training_data/manual_*/data_pipeline.log
```

#### 8.2.2 日志级别调整
```bash
# 启用DEBUG级别日志
python -m data_pipeline.schema_workflow \
  --verbose \
  [其他参数]
```

### 8.3 性能优化

#### 8.3.1 并发配置调优
```python
# 在config.py中调整
"max_concurrent_tables": 2,              # 增加并发数（谨慎）
"max_concurrent_validations": 10,        # 增加SQL验证并发数
"batch_size": 20                         # 增加批处理大小
```

#### 8.3.2 数据采样优化
```python
# 减少采样数据量
"sample_data_limit": 10,                 # 从20减少到10
"enum_detection_sample_limit": 1000      # 从5000减少到1000
```

#### 8.3.3 跳过耗时步骤
```bash
# 跳过SQL验证
python -m data_pipeline.schema_workflow \
  --skip-validation \
  [其他参数]

# 跳过训练数据加载
python -m data_pipeline.schema_workflow \
  --skip-training-load \
  [其他参数]
```

### 8.4 环境检查

#### 8.4.1 依赖检查
```bash
# 检查Python版本
python --version

# 检查必需包
pip list | grep -E "(asyncpg|psycopg2|vanna)"

# 检查数据库连接
python -c "
import asyncpg
import asyncio
async def test():
    conn = await asyncpg.connect('postgresql://user:pass@host:5432/db')
    await conn.close()
    print('✅ 数据库连接正常')
asyncio.run(test())
"
```

#### 8.4.2 权限检查
```bash
# 使用内置权限检查工具
python -m data_pipeline.ddl_generation.ddl_md_generator \
  --db-connection "postgresql://user:pass@localhost:5432/db" \
  --check-permissions-only
```

#### 8.4.3 磁盘空间检查
```bash
# 检查输出目录空间
df -h data_pipeline/training_data/

# 清理旧任务（谨慎操作）
find data_pipeline/training_data/ -type d -name "manual_*" -mtime +7 -exec rm -rf {} +
```

## 总结

data_pipeline模块提供了完整的脚本化调用方式，支持从简单的一键工作流到复杂的分步调试。通过合理配置参数和日志系统，可以满足各种数据处理需求。建议在生产环境中使用一键工作流脚本，在开发调试时使用分步执行脚本。 