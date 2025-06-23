# SQL验证器使用指南

SQL验证器是Schema Tools的一个独立模块，用于验证Question-SQL对中的SQL语句是否有效。它通过执行`EXPLAIN`语句来检测SQL语法错误和表结构问题。

**⚠️ 重要提示**：
- **命令行模式默认行为**：启用LLM修复功能和文件修改功能
- **配置文件默认值**：禁用修复和文件修改功能（保守设置）
- 如需禁用默认功能，请使用 `--disable-llm-repair` 或 `--no-modify-file` 参数

## 功能特性

- 🔍 使用PostgreSQL的EXPLAIN语句验证SQL有效性
- ⚡ 支持并发验证，大幅提升验证效率
- 🔒 只读模式运行，安全可靠
- 📊 详细的验证报告和统计信息
- 🔄 自动重试机制，处理临时网络问题
- 📁 支持批处理，适合大量SQL验证
- 🔧 灵活的配置选项
- 🤖 **新增**：LLM自动修复错误SQL（可选启用）
- 📝 **新增**：自动修改原始JSON文件，更新修复后的SQL
- 🗑️ **新增**：自动删除无法修复的无效SQL条目
- 💾 **新增**：自动创建备份文件，保护原始数据

## 使用方法

### 1. 命令行使用

#### 基本用法
```bash
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./qs_highway_db_20240101_143052_pair.json
```

#### 指定输出目录
```bash
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --output-dir ./validation_reports
```

#### 调整验证参数
```bash
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --max-concurrent 10 \
  --batch-size 20 \
  --timeout 60 \
  --verbose
```

#### 预检查模式
```bash
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --dry-run
```

### 高级选项

```bash
# 基本使用（默认启用修复和文件修改）
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

# 预检查模式（仅验证文件格式）
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --dry-run
```

### 2. 编程接口使用

```python
import asyncio
from schema_tools import SQLValidationAgent

async def validate_sqls():
    agent = SQLValidationAgent(
        db_connection="postgresql://user:pass@localhost:5432/dbname",
        input_file="./qs_highway_db_20240101_143052_pair.json",
        output_dir="./validation_reports"
    )
    
    report = await agent.validate()
    
    print(f"验证完成:")
    print(f"  总SQL: {report['summary']['total_questions']}")
    print(f"  有效: {report['summary']['valid_sqls']}")
    print(f"  成功率: {report['summary']['success_rate']:.1%}")

asyncio.run(validate_sqls())
```

## 文件自动修改功能

### 功能说明
SQL验证器现在支持自动修改原始JSON文件：

1. **修复成功的SQL**：直接更新原始文件中的SQL内容
2. **无法修复的SQL**：从原始文件中删除对应的Question-SQL对
3. **自动备份**：修改前自动创建备份文件

### 默认行为
```bash
# 默认启用修复和文件修改
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json
```

执行后：
- 创建备份文件：`data.json.backup`
- 修改原文件：`data.json`（更新修复成功的SQL，删除无法修复的SQL）
- 生成修改日志：`file_modifications_时间戳.log`
- 生成验证报告：`sql_validation_时间戳_summary.txt`

### 仅生成报告

```bash
# 仅生成报告，不修改原文件
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --no-modify-file
```

执行后：
- 生成验证报告：`sql_validation_时间戳_summary.txt`
- 不修改原始文件

### 禁用LLM修复功能

```bash
# 启用文件修改，但禁用LLM修复（仅删除无效SQL）
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --disable-llm-repair
```

执行后：
- 创建备份文件：`data.json.backup`
- 修改原文件：`data.json`（删除验证失败的SQL，不进行LLM修复）
- 生成修改日志：`file_modifications_时间戳.log`
- 生成验证报告：`sql_validation_时间戳_summary.txt`

### 修改日志
每次修改都会生成详细的修改日志文件：

```
原始JSON文件修改日志
==================================================
修改时间: 2024-01-01 15:30:45
原始文件: ./qs_highway_db_20240101_143052_pair.json
备份文件: ./qs_highway_db_20240101_143052_pair.json.backup

修改的SQL (3个):
----------------------------------------
1. 索引: 5
   问题: 查询订单与车辆数据的相关性分析？
   原SQL: SELECT EXTRACT(year FROM oper_date) AS 年份, COUNT(*) FROM bss_business_day_data GROUP BY 年份;
   新SQL: SELECT EXTRACT(year FROM oper_date)::integer AS 年份, COUNT(*) FROM bss_business_day_data GROUP BY EXTRACT(year FROM oper_date);

删除的无效项 (2个):
----------------------------------------
1. 索引: 12
   问题: 查询不存在的表数据？
   SQL: SELECT * FROM non_existent_table;
   错误: relation "non_existent_table" does not exist
```
```

## 输入文件格式

SQL验证器接受标准的Question-SQL对JSON文件，格式如下：

```json
[
  {
    "question": "按服务区统计每日营收趋势（最近30天）？",
    "sql": "SELECT service_name AS 服务区, oper_date AS 营业日期, SUM(pay_sum) AS 每日营收 FROM bss_business_day_data WHERE oper_date >= CURRENT_DATE - INTERVAL '30 day' AND delete_ts IS NULL GROUP BY service_name, oper_date ORDER BY 营业日期 ASC;"
  },
  {
    "question": "查看车流量最大的前10个服务区",
    "sql": "SELECT service_name AS 服务区, SUM(car_count) AS 总车流量 FROM bss_car_day_count WHERE delete_ts IS NULL GROUP BY service_name ORDER BY 总车流量 DESC LIMIT 10;"
  }
]
```

## 输出报告

### 默认输出
验证完成后，默认只生成一个**文本摘要报告**：
- 文件名格式：`sql_validation_时间戳_summary.txt`
- 包含验证统计信息和**完整的错误SQL**
- 便于直接查看和分析错误

### 可选JSON报告
如果需要程序化处理验证结果，可以启用详细JSON报告：

```bash
# 启用JSON报告
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --save-json
```

### 报告内容

#### 文本摘要报告包含：
1. **验证统计**：总数、成功率、平均耗时等
2. **SQL修复统计**：修复尝试数、成功数、失败数、修复成功率
3. **原始文件修改统计**：修改的SQL数量、删除的无效项数量、修改失败数量
4. **完整错误详情**：
   - 问题描述
   - 错误信息
   - **完整SQL语句**（不截断）
   - LLM修复尝试结果
   - 修复后的SQL（如果成功）
   - 重试次数
5. **成功修复的SQL列表**：显示原始错误和修复后的SQL

#### JSON报告包含：
- 所有验证结果的详细数据
- 适合程序化分析和处理

## 示例输出

### 验证过程日志
```
🚀 开始SQL验证...
📁 输入文件: ./qs_highway_db_20240101_143052_pair.json
🔗 数据库: postgresql://***:***@localhost:5432/highway_db
📦 处理批次 1/5 (10 个SQL)
✅ 批次 1 完成: 9/10 有效
📊 验证报告已保存: output/sql_validation_20240101_150000_summary.txt

🎉 验证完成，成功率: 90.0%
📊 详细结果: 45/50 SQL有效
```

### 文本摘要报告示例
```
SQL验证报告
==================================================

输入文件: ./qs_highway_db_20240101_143052_pair.json
验证时间: 2024-01-01T15:00:00
验证耗时: 2.45秒

验证结果摘要:
  总SQL数量: 50
  有效SQL: 45
  无效SQL: 5
  成功率: 90.00%
  平均耗时: 0.049秒
  重试次数: 0

SQL修复统计:
  尝试修复: 5
  修复成功: 3
  修复失败: 2
  修复成功率: 60.00%

原始文件修改统计:
  修改的SQL: 3
  删除的无效项: 2
  修改失败: 0

错误详情（共2个）:
==================================================

1. 问题: 查询订单与车辆数据的相关性分析？  
   错误: 函数 round(double precision, integer) 不存在
   LLM修复尝试: 失败
   修复失败原因: 无法识别正确的函数语法
   完整SQL:
   SELECT a.oper_date, a.order_sum AS 订单数量, b.customer_count AS 车辆数量, 
          ROUND(CORR(a.order_sum, b.customer_count), 2) AS 相关系数
   FROM bss_business_day_data a 
   JOIN bss_car_day_count b ON a.oper_date = b.count_date;
   ----------------------------------------

成功修复的SQL（共3个）:
==================================================

1. 问题: 各区域管理公司单位能耗产出对比（需结合能耗表）
   原始错误: 对于表"e",丢失FROM子句项
   修复后SQL:
   SELECT c.company_name AS 公司名称,
       ROUND(SUM(b.pay_sum)::numeric/SUM(b.order_sum)::numeric, 2) AS 单位订单产出
   FROM bss_company c
   JOIN bss_service_area sa ON c.id = sa.company_id
   JOIN bss_business_day_data b ON sa.service_area_no = b.service_no
   WHERE b.oper_date BETWEEN '2023-01-01' AND '2023-03-31'
   GROUP BY c.company_name
   ORDER BY 单位订单产出 DESC;
   ----------------------------------------
```

## 配置选项

SQL验证器的配置位于 `schema_tools/config.py` 中：

```python
"sql_validation": {
    "reuse_connection_pool": True,       # 复用现有连接池
    "max_concurrent_validations": 5,     # 并发验证数
    "validation_timeout": 30,            # 单个验证超时(秒)
    "batch_size": 10,                    # 批处理大小
    "continue_on_error": True,           # 错误时是否继续
    "save_validation_report": True,      # 保存验证报告
    "save_detailed_json_report": False,  # 保存详细JSON报告（可选）
    "readonly_mode": True,               # 启用只读模式
    "max_retry_count": 2,                # 验证失败重试次数
    "report_file_prefix": "sql_validation",  # 报告文件前缀
    
    # SQL修复配置
    "enable_sql_repair": False,          # 启用SQL修复功能（配置文件默认禁用）
    "llm_repair_timeout": 120,           # LLM修复超时时间(秒)
    "repair_batch_size": 2,              # 修复批处理大小
    
    # 文件修改配置
    "modify_original_file": False,       # 是否修改原始JSON文件（配置文件默认禁用）
}
```

**重要说明**：
- 配置文件中的默认值为保守设置（禁用修复和文件修改）
- 命令行模式下会自动启用修复和文件修改功能
- 可通过命令行参数 `--disable-llm-repair` 和 `--no-modify-file` 禁用

## 命令行参数说明

### 必需参数
| 参数 | 类型 | 说明 |
|------|------|------|
| `--db-connection` | string | PostgreSQL数据库连接字符串 |
| `--input-file` | string | 输入的JSON文件路径（包含Question-SQL对） |

### 可选参数
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--output-dir` | string | 输入文件同目录 | 验证报告输出目录 |
| `--max-concurrent` | int | 5 | 最大并发验证数 |
| `--batch-size` | int | 10 | 批处理大小 |
| `--timeout` | int | 30 | 单个SQL验证超时时间（秒） |
| `--verbose` | flag | False | 启用详细日志输出 |
| `--log-file` | string | 无 | 日志文件路径 |
| `--dry-run` | flag | False | 仅读取和解析文件，不执行验证 |
| `--save-json` | flag | False | 同时保存详细的JSON报告 |

### SQL修复和文件修改参数
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--disable-llm-repair` | flag | False | 禁用LLM自动修复功能 |
| `--enable-llm-repair` | flag | - | 启用LLM修复（向后兼容，与--disable-llm-repair相反） |
| `--no-modify-file` | flag | False | 不修改原始JSON文件（仅生成验证报告） |
| `--modify-original-file` | flag | - | 修改原始JSON文件（向后兼容，与--no-modify-file相反） |

**注意**：
- 命令行模式下，默认启用LLM修复和文件修改功能
- 如需禁用，请明确使用 `--disable-llm-repair` 或 `--no-modify-file` 参数
- 向后兼容参数仍然有效，但建议使用新的参数格式

## 错误处理机制

1. **超时处理**：单个SQL验证超过配置的超时时间会被标记为失败
2. **重试机制**：网络相关错误会自动重试，最多重试2次
3. **错误容忍**：单个SQL失败不会中断整个验证流程
4. **批处理隔离**：批次间相互独立，一个批次失败不影响其他批次

## 性能优化建议

1. **并发调优**：根据数据库性能调整 `max_concurrent_validations`
2. **批处理优化**：大文件建议增加 `batch_size` 以减少内存占用
3. **超时设置**：复杂SQL可适当增加 `validation_timeout`
4. **连接池复用**：启用 `reuse_connection_pool` 以减少连接开销

## 安全说明

- SQL验证器运行在只读模式下，不会修改数据库
- 使用EXPLAIN语句进行验证，不会执行实际的数据操作
- 敏感信息（如密码）在日志中会被自动隐藏

## 故障排除

### 常见问题

1. **连接失败**
   ```
   解决：检查数据库连接字符串和网络连通性
   ```

2. **权限不足**
   ```
   解决：确保数据库用户有SELECT权限
   ```

3. **表不存在**
   ```
   解决：检查SQL中的表名是否正确，注意schema前缀
   ```

4. **语法错误**
   ```
   解决：检查SQL语法，注意PostgreSQL的语法特性
   ```

### 调试技巧

1. 使用 `--verbose` 获取详细日志
2. 使用 `--dry-run` 预检查文件格式
3. 减小 `--batch-size` 以便定位问题SQL
4. 检查验证报告中的错误详情

## 与其他模块的集成

SQL验证器可以与Schema Tools的其他模块无缝集成：

```python
# 先生成Question-SQL对
from schema_tools import QuestionSQLGenerationAgent

qs_agent = QuestionSQLGenerationAgent(...)
qs_report = await qs_agent.generate()

# 然后验证生成的SQL
from schema_tools import SQLValidationAgent

sql_agent = SQLValidationAgent(
    db_connection="...",
    input_file=qs_report['output_file']
)
validation_report = await sql_agent.validate()
``` 