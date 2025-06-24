# Schema Tools 使用说明

## 目录

1. [功能概述](#1-功能概述)
2. [安装与配置](#2-安装与配置)
3. [一键执行完整工作流（推荐）](#3-一键执行完整工作流推荐)
4. [生成DDL和MD文档](#4-生成ddl和md文档)
5. [生成Question-SQL训练数据](#5-生成question-sql训练数据)
6. [配置详解](#6-配置详解)
7. [常见问题](#7-常见问题)

## 1. 功能概述

Schema Tools 提供两个主要功能：

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

### 1.3 一键工作流编排器（推荐）
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

Schema Tools 使用项目现有的 LLM 配置，无需额外配置数据库连接。

## 3. 一键执行完整工作流（推荐）

### 3.1 工作流编排器概述

`SchemaWorkflowOrchestrator` 是 Schema Tools 的核心组件，提供端到端的自动化处理流程：

1. **DDL和MD文档生成** - 连接数据库，生成表结构文档
2. **Question-SQL对生成** - 基于文档生成训练数据
3. **SQL验证和修复** - 验证SQL有效性并自动修复错误

### 3.2 命令行使用

#### 基本使用（完整工作流）
```bash
python -m schema_tools.schema_workflow_orchestrator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --table-list tables.txt \
  --business-context "高速公路服务区管理系统" \
  --db-name highway_db \
  --output-dir ./output
```

#### 跳过SQL验证
```bash
python -m schema_tools.schema_workflow_orchestrator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --table-list tables.txt \
  --business-context "电商系统" \
  --db-name ecommerce_db \
  --skip-validation
```

#### 禁用LLM修复
```bash
python -m schema_tools.schema_workflow_orchestrator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --table-list tables.txt \
  --business-context "管理系统" \
  --db-name management_db \
  --disable-llm-repair
```

#### 不修改原始文件（仅生成报告）
```bash
python -m schema_tools.schema_workflow_orchestrator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --table-list tables.txt \
  --business-context "业务系统" \
  --db-name business_db \
  --no-modify-file
```

python -m schema_tools.schema_workflow_orchestrator --db-connection "postgresql://postgres:postgres@localhost:6432/highway_db" --table-list ./schema_tools/tables.txt --business-context "高速公路服务区管理系统"  --db-name highway_db --output-dir ./output


### 3.3 编程方式使用

```python
import asyncio
from schema_tools.schema_workflow_orchestrator import SchemaWorkflowOrchestrator

async def run_complete_workflow():
    # 创建工作流编排器
    orchestrator = SchemaWorkflowOrchestrator(
        db_connection="postgresql://user:pass@localhost:5432/dbname",
        table_list_file="tables.txt",
        business_context="高速公路服务区管理系统",
        db_name="highway_db",
        output_dir="./output",
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
| `--db-connection` | 数据库连接字符串 | 必需 |
| `--table-list` | 表清单文件路径 | 必需 |
| `--business-context` | 业务上下文描述 | 必需 |
| `--db-name` | 数据库名称（用于文件命名） | 必需 |
| `--output-dir` | 输出目录 | `./output` |
| `--skip-validation` | 跳过SQL验证步骤 | `False`（默认执行SQL验证） |
| `--disable-llm-repair` | 禁用LLM修复功能 | `False`（默认启用LLM修复） |
| `--no-modify-file` | 不修改原始JSON文件 | `False`（默认修改原文件） |
| `--verbose` | 启用详细日志 | `False` |
| `--log-file` | 日志文件路径 | 无 |

### 3.5 工作流执行报告

工作流编排器会生成详细的执行报告，包括：

```python
{
    "success": True,
    "workflow_summary": {
        "total_duration": 245.67,
        "completed_steps": ["ddl_md_generation", "question_sql_generation", "sql_validation"],
        "total_steps": 3
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
        }
    },
    "final_outputs": {
        "primary_output_file": "./output/qs_highway_db_20240123_143052_pair.json",
        "final_question_count": 47
    },
    "performance_metrics": {
        "step1_duration": 89.23,
        "step2_duration": 123.45,
        "step3_duration": 32.99,
        "total_duration": 245.67
    }
}
```

### 3.6 优势特性

- **自动化流程**：一个命令完成所有步骤
- **错误恢复**：失败时保留已完成步骤的输出
- **灵活配置**：可选择跳过验证、禁用修复等
- **详细报告**：提供完整的执行状态和性能指标
- **向后兼容**：支持所有现有参数和配置

## 4. 生成DDL和MD文档（分步执行）

### 4.1 命令格式

```bash
python -m schema_tools \
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
| `--output-dir` | 输出目录路径 | `training/generated_data` |
| `--pipeline` | 处理链类型 | `full` |
| `--max-concurrent` | 最大并发表数量 | `1` |
| `--verbose` | 启用详细日志 | `False` |
| `--log-file` | 日志文件路径 | `无` |
| `--no-filter-system-tables` | 禁用系统表过滤 | `False` |
| `--check-permissions-only` | 仅检查数据库权限 | `False` |

### 4.4 处理链类型

- **full**: 完整处理链（默认）- 生成DDL和MD文档
- **ddl_only**: 仅生成DDL文件
- **analysis_only**: 仅分析不生成文件

### 4.5 使用示例

#### 基本使用
```bash
python -m schema_tools \
  --db-connection "postgresql://postgres:postgres@localhost:6432/highway_db" \
  --table-list ./schema_tools/tables.txt \
  --business-context "高速公路服务区管理系统"
```

#### 指定输出目录和启用详细日志
```bash
python -m schema_tools \
  --db-connection "postgresql://postgres:postgres@localhost:6432/highway_db" \
  --table-list ./schema_tools/tables.txt \
  --business-context "高速公路服务区管理系统" \
  --output-dir ./output \
  --verbose
```

#### 仅生成DDL文件
```bash
python -m schema_tools \
  --db-connection "postgresql://postgres:postgres@localhost:6432/highway_db" \
  --table-list ./schema_tools/tables.txt \
  --business-context "高速公路服务区管理系统" \
  --pipeline ddl_only
```

#### 权限检查
```bash
python -m schema_tools \
  --db-connection "postgresql://postgres:postgres@localhost:6432/highway_db" \
  --check-permissions-only
```

### 4.6 表清单文件格式

创建一个文本文件（如 `tables.txt`），每行一个表名：

```text
# 这是注释行
public.bss_service_area
public.bss_company
bss_car_day_count  # 默认为public schema
hr.employees       # 指定schema
```

### 4.7 输出文件

生成的文件都放在输出目录下（不创建子目录）：

```
output/
├── bss_service_area.ddl              # DDL文件
├── bss_service_area_detail.md        # MD文档
├── bss_company.ddl
├── bss_company_detail.md
├── filename_mapping.txt              # 文件名映射
└── logs/                            # 日志目录
    └── schema_tools_20240123.log
```

## 5. 生成Question-SQL训练数据（分步执行）

### 5.1 前置条件

必须先执行DDL和MD文档生成，确保输出目录中有完整的DDL和MD文件。

### 5.2 命令格式

```bash
python -m schema_tools.qs_generator \
  --output-dir <输出目录> \
  --table-list <表清单文件> \
  --business-context <业务上下文> \
  [可选参数]
```

### 5.3 必需参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--output-dir` | 包含DDL和MD文件的目录 | `./output` |
| `--table-list` | 表清单文件路径（用于验证） | `./tables.txt` |
| `--business-context` | 业务上下文描述 | `"高速公路服务区管理系统"` |

### 5.4 可选参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--db-name` | 数据库名称（用于文件命名） | `db` |
| `--verbose` | 启用详细日志 | `False` |
| `--log-file` | 日志文件路径 | `无` |

### 5.5 使用示例

#### 基本使用
```bash
python -m schema_tools.qs_generator \
  --output-dir ./output \
  --table-list ./schema_tools/tables.txt \
  --business-context "高速公路服务区管理系统" \
  --db-name highway_db
```

#### 启用详细日志
```bash
python -m schema_tools.qs_generator \
  --output-dir ./output \
  --table-list ./schema_tools/tables.txt \
  --business-context "高速公路服务区管理系统" \
  --db-name highway_db \
  --verbose
```

### 5.6 SQL验证和修复

生成Question-SQL对后，可以使用SQL验证功能。**注意：命令行使用时，默认启用LLM修复和文件修改功能**。

```bash
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./qs_highway_db_20240123_143052_pair.json \
  --output-dir ./validation_reports
```

#### SQL验证参数说明

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

#### SQL验证使用示例

```bash
# 基本验证（默认：启用LLM修复和文件修改）
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json

# 仅生成报告，不修改文件
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --no-modify-file

# 启用文件修改，但禁用LLM修复（仅删除无效SQL）
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --disable-llm-repair

# 性能调优参数
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --max-concurrent 10 \
  --batch-size 20 \
  --timeout 60 \
  --verbose
```

### 5.7 执行流程

1. **文件验证**：检查DDL和MD文件数量是否正确
2. **表数量限制**：最多处理20个表（可配置）
3. **主题提取**：LLM分析表结构，提取5个业务分析主题
4. **Question-SQL生成**：每个主题生成10个问题
5. **结果保存**：输出到 `qs_<db_name>_<时间戳>_pair.json`
6. **SQL验证**：验证生成的SQL语句有效性
7. **自动修复**：使用LLM修复无效的SQL语句（可选）

### 5.8 输出文件

```
output/
├── qs_highway_db_20240123_143052_pair.json  # 最终结果
├── qs_highway_db_20240123_143052_pair.json.backup  # 原文件备份（如果启用文件修改）
├── qs_intermediate_20240123_143052.json     # 中间结果（成功后自动删除）
├── qs_recovery_20240123_143052.json         # 恢复文件（异常中断时生成）
├── sql_validation_20240123_150000_summary.txt  # SQL验证报告
└── file_modifications_20240123_150000.log  # 文件修改日志（如果启用文件修改）
```

### 5.9 输出格式示例

```json
[
  {
    "question": "按服务区统计每日营收趋势（最近30天）？",
    "sql": "SELECT service_name AS 服务区, oper_date AS 营业日期, SUM(pay_sum) AS 每日营收 FROM bss_business_day_data WHERE oper_date >= CURRENT_DATE - INTERVAL '30 day' AND delete_ts IS NULL GROUP BY service_name, oper_date ORDER BY 营业日期 ASC;"
  },
  {
    "question": "哪个服务区的车流量最大？",
    "sql": "SELECT service_area_id, SUM(customer_count) AS 总车流量 FROM bss_car_day_count WHERE delete_ts IS NULL GROUP BY service_area_id ORDER BY 总车流量 DESC LIMIT 1;"
  }
]
```

## 6. 配置详解

### 6.1 主要配置项

配置文件位于 `schema_tools/config.py`：

```python
# DDL/MD生成相关配置
"output_directory": "training/generated_data",     # 输出目录
"create_subdirectories": False,                    # 不创建子目录
"max_concurrent_tables": 1,                        # 最大并发数（避免LLM并发问题）
"sample_data_limit": 20,                          # 数据采样量
"large_table_threshold": 1000000,                 # 大表阈值（100万行）
"filter_system_tables": True,                      # 过滤系统表
"continue_on_error": True,                         # 错误后继续

# Question-SQL生成配置
"qs_generation": {
    "max_tables": 20,                             # 最大表数量限制
    "theme_count": 5,                             # 主题数量
    "questions_per_theme": 10,                    # 每主题问题数
    "max_concurrent_themes": 1,                   # 并行主题数（避免LLM并发问题）
    "continue_on_theme_error": True,              # 主题失败继续
    "save_intermediate": True,                    # 保存中间结果
}

# SQL验证配置
"sql_validation": {
    "max_concurrent_validations": 5,              # 并发验证数
    "validation_timeout": 30,                     # 单个验证超时(秒)
    "batch_size": 10,                             # 批处理大小
    "enable_sql_repair": False,                   # SQL修复功能（命令行覆盖为True）
    "modify_original_file": False,                # 文件修改功能（命令行覆盖为True）
    "readonly_mode": True,                        # 启用只读模式
}
```

### 6.2 修改配置

可以通过编辑 `schema_tools/config.py` 文件来修改默认配置。

## 7. 常见问题

### 7.1 表数量超过20个怎么办？

**错误信息**：
```
表数量(25)超过限制(20)。请分批处理或调整配置中的max_tables参数。
```

**解决方案**：
1. 分批处理：将表清单分成多个文件，每个不超过20个表
2. 修改配置：在 `config.py` 中增加 `max_tables` 限制

### 7.2 DDL和MD文件数量不一致

**错误信息**：
```
DDL文件数量(5)与表数量(6)不一致
```

**解决方案**：
1. 检查是否有表处理失败
2. 查看日志文件找出失败的表
3. 重新运行DDL/MD生成

### 7.3 LLM调用失败

**可能原因**：
- 网络连接问题
- API配额限制
- Token超限

**解决方案**：
1. 检查网络连接
2. 查看中间结果文件，从断点继续
3. 减少表数量或分批处理

### 7.4 权限不足

**错误信息**：
```
数据库查询权限不足
```

**解决方案**：
1. 使用 `--check-permissions-only` 检查权限
2. 确保数据库用户有SELECT权限
3. Schema Tools支持只读数据库

### 7.5 如何处理大表？

Schema Tools会自动检测大表（超过100万行）并使用智能采样策略：
- **前N行采样**：使用 `SELECT * FROM table LIMIT N` 获取前N行
- **随机中间采样**：使用 `TABLESAMPLE SYSTEM` 进行随机采样（失败时回退到OFFSET采样）
- **后N行采样**：使用ROW_NUMBER窗口函数获取最后N行
- 三段采样确保数据的代表性，有效处理大表的多样性

**大表阈值**：默认为100万行（可在config.py中修改`large_table_threshold`）

### 7.6 生成的SQL语法错误

目前生成的SQL使用PostgreSQL语法。如果需要其他数据库语法：
1. 在业务上下文中明确指定目标数据库
2. 未来版本将支持MySQL等其他数据库

### 7.7 工作流编排器相关问题

**Q: 工作流中途失败，如何恢复？**
A: 工作流编排器会保留已完成步骤的输出文件，可以手动从失败步骤开始重新执行。

**Q: 如何只执行部分步骤？**
A: 使用 `--skip-validation` 跳过SQL验证，或使用分步执行方式调用各个模块。

**Q: 工作流执行时间过长怎么办？**
A: 可以通过减少表数量、调整并发参数、或分批处理来优化执行时间。

### 7.8 SQL验证器默认行为说明

**重要**：SQL验证器的命令行模式与配置文件中的默认值不同：

- **配置文件默认**：`enable_sql_repair=False`, `modify_original_file=False`
- **命令行默认**：启用LLM修复和文件修改功能
- **原因**：命令行使用时通常期望完整的修复功能，而配置文件提供保守的默认值

如需禁用，请明确使用 `--disable-llm-repair` 或 `--no-modify-file` 参数。

## 8. 最佳实践

### 8.1 推荐工作流程

**方式一：一键执行（推荐）**
```bash
# 完整工作流程，一个命令搞定
python -m schema_tools.schema_workflow_orchestrator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --table-list tables.txt \
  --business-context "高速公路服务区管理系统" \
  --db-name highway_db \
  --output-dir ./output
```

**方式二：分步执行（调试时使用）**
1. **第一步**：生成DDL和MD文档
   ```bash
   python -m schema_tools --db-connection "..." --table-list tables.txt --business-context "..." --output-dir ./output
   ```

2. **第二步**：人工检查
   - 检查DDL文件的表结构是否正确
   - 确认MD文档中的注释是否准确
   - 根据需要手动调整

3. **第三步**：生成Question-SQL
   ```bash
   python -m schema_tools.qs_generator --output-dir ./output --table-list tables.txt --business-context "..."
   ```

4. **第四步**：验证SQL（可选）
   ```bash
   python -m schema_tools.sql_validator --db-connection "..." --input-file ./qs_xxx.json
   ```

### 8.2 表清单组织

- 按业务模块分组
- 每组不超过15-20个表
- 使用注释说明每组的用途

### 8.3 业务上下文优化

- 提供准确的业务背景描述
- 包含行业特定术语
- 说明主要业务流程

### 8.4 输出文件管理

- 定期备份生成的文件
- 使用版本控制管理DDL文件
- 保留中间结果用于调试

### 8.5 工作流编排器最佳实践

- **首次使用**：建议启用详细日志（`--verbose`）观察执行过程
- **生产环境**：使用默认参数，启用SQL验证和修复
- **调试阶段**：可以使用 `--skip-validation` 跳过验证步骤加快执行
- **质量要求高**：使用 `--no-modify-file` 仅生成报告，手动审查后再决定是否修改 