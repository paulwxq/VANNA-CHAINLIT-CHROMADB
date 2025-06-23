# Schema Tools 使用说明

## 目录

1. [功能概述](#1-功能概述)
2. [安装与配置](#2-安装与配置)
3. [生成DDL和MD文档](#3-生成ddl和md文档)
4. [生成Question-SQL训练数据](#4-生成question-sql训练数据)
5. [配置详解](#5-配置详解)
6. [常见问题](#6-常见问题)

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

## 2. 安装与配置

### 2.1 依赖安装

```bash
pip install asyncpg asyncio
```

### 2.2 基本配置

Schema Tools 使用项目现有的 LLM 配置，无需额外配置数据库连接。

## 3. 生成DDL和MD文档

### 3.1 命令格式

```bash
python -m schema_tools \
  --db-connection <数据库连接字符串> \
  --table-list <表清单文件> \
  --business-context <业务上下文> \
  [可选参数]
```

### 3.2 必需参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--db-connection` | PostgreSQL数据库连接字符串 | `postgresql://user:pass@localhost:5432/dbname` |
| `--table-list` | 表清单文件路径 | `./tables.txt` |
| `--business-context` | 业务上下文描述 | `"高速公路服务区管理系统"` |

### 3.3 可选参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--output-dir` | 输出目录路径 | `training/generated_data` |
| `--pipeline` | 处理链类型 | `full` |
| `--max-concurrent` | 最大并发表数量 | `3` |
| `--verbose` | 启用详细日志 | `False` |
| `--log-file` | 日志文件路径 | `无` |
| `--no-filter-system-tables` | 禁用系统表过滤 | `False` |
| `--check-permissions-only` | 仅检查数据库权限 | `False` |

### 3.4 处理链类型

- **full**: 完整处理链（默认）- 生成DDL和MD文档
- **ddl_only**: 仅生成DDL文件
- **analysis_only**: 仅分析不生成文件

### 3.5 使用示例

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

### 3.6 表清单文件格式

创建一个文本文件（如 `tables.txt`），每行一个表名：

```text
# 这是注释行
public.bss_service_area
public.bss_company
bss_car_day_count  # 默认为public schema
hr.employees       # 指定schema
```

### 3.7 输出文件

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

## 4. 生成Question-SQL训练数据

### 4.1 前置条件

必须先执行DDL和MD文档生成，确保输出目录中有完整的DDL和MD文件。

### 4.2 命令格式

```bash
python -m schema_tools.qs_generator \
  --output-dir <输出目录> \
  --table-list <表清单文件> \
  --business-context <业务上下文> \
  [可选参数]
```

### 4.3 必需参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--output-dir` | 包含DDL和MD文件的目录 | `./output` |
| `--table-list` | 表清单文件路径（用于验证） | `./tables.txt` |
| `--business-context` | 业务上下文描述 | `"高速公路服务区管理系统"` |

### 4.4 可选参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--db-name` | 数据库名称（用于文件命名） | `db` |
| `--verbose` | 启用详细日志 | `False` |
| `--log-file` | 日志文件路径 | `无` |

### 4.5 使用示例

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

### 4.6 执行流程

1. **文件验证**：检查DDL和MD文件数量是否正确
2. **表数量限制**：最多处理20个表（可配置）
3. **主题提取**：LLM分析表结构，提取5个业务分析主题
4. **Question-SQL生成**：每个主题生成10个问题
5. **结果保存**：输出到 `qs_<db_name>_<时间戳>_pair.json`

### 4.7 输出文件

```
output/
├── qs_highway_db_20240123_143052_pair.json  # 最终结果
├── qs_intermediate_20240123_143052.json     # 中间结果（成功后自动删除）
└── qs_recovery_20240123_143052.json         # 恢复文件（异常中断时生成）
```

### 4.8 输出格式示例

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

## 5. 配置详解

### 5.1 主要配置项

配置文件位于 `schema_tools/config.py`：

```python
# DDL/MD生成相关配置
"output_directory": "training/generated_data",     # 输出目录
"create_subdirectories": False,                    # 不创建子目录
"max_concurrent_tables": 3,                        # 最大并发数
"sample_data_limit": 20,                          # 数据采样量
"filter_system_tables": True,                      # 过滤系统表
"continue_on_error": True,                         # 错误后继续

# Question-SQL生成配置
"qs_generation": {
    "max_tables": 20,                             # 最大表数量限制
    "theme_count": 5,                             # 主题数量
    "questions_per_theme": 10,                    # 每主题问题数
    "max_concurrent_themes": 3,                   # 并行主题数
    "continue_on_theme_error": True,              # 主题失败继续
    "save_intermediate": True,                    # 保存中间结果
}
```

### 5.2 修改配置

可以通过编辑 `schema_tools/config.py` 文件来修改默认配置。

## 6. 常见问题

### 6.1 表数量超过20个怎么办？

**错误信息**：
```
表数量(25)超过限制(20)。请分批处理或调整配置中的max_tables参数。
```

**解决方案**：
1. 分批处理：将表清单分成多个文件，每个不超过20个表
2. 修改配置：在 `config.py` 中增加 `max_tables` 限制

### 6.2 DDL和MD文件数量不一致

**错误信息**：
```
DDL文件数量(5)与表数量(6)不一致
```

**解决方案**：
1. 检查是否有表处理失败
2. 查看日志文件找出失败的表
3. 重新运行DDL/MD生成

### 6.3 LLM调用失败

**可能原因**：
- 网络连接问题
- API配额限制
- Token超限

**解决方案**：
1. 检查网络连接
2. 查看中间结果文件，从断点继续
3. 减少表数量或分批处理

### 6.4 权限不足

**错误信息**：
```
数据库查询权限不足
```

**解决方案**：
1. 使用 `--check-permissions-only` 检查权限
2. 确保数据库用户有SELECT权限
3. Schema Tools支持只读数据库

### 6.5 如何处理大表？

Schema Tools会自动检测大表（超过100万行）并使用智能采样策略：
- 前N行 + 随机中间行 + 后N行
- 确保采样数据的代表性

### 6.6 生成的SQL语法错误

目前生成的SQL使用PostgreSQL语法。如果需要其他数据库语法：
1. 在业务上下文中明确指定目标数据库
2. 未来版本将支持MySQL等其他数据库

## 7. 最佳实践

### 7.1 工作流程建议

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

### 7.2 表清单组织

- 按业务模块分组
- 每组不超过15-20个表
- 使用注释说明每组的用途

### 7.3 业务上下文优化

- 提供准确的业务背景描述
- 包含行业特定术语
- 说明主要业务流程

### 7.4 输出文件管理

- 定期备份生成的文件
- 使用版本控制管理DDL文件
- 保留中间结果用于调试 