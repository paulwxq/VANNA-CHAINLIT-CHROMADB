# Schema Tools

自动化数据库逆向工程工具，用于从PostgreSQL数据库生成vanna.ai格式的训练数据。

## 功能特性

- 🚀 自动连接PostgreSQL数据库
- 📋 批量处理表清单
- 🤖 LLM智能生成中文注释
- 🔍 自动检测枚举字段
- ⚡ 并发处理提高效率
- 📁 生成标准化的DDL和MD文档
- 🛡️ 完整的错误处理和日志记录
- 🎯 **新增**：Question-SQL训练数据生成
- ✅ **新增**：SQL语句有效性验证

## 安装依赖

```bash
pip install asyncpg asyncio
```

## 使用方法

### 1. 生成DDL和MD文档

#### 基本使用
```bash
python -m schema_tools \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --table-list tables.txt \
  --business-context "高速公路服务区管理系统"
```

#### 指定输出目录和处理链
```bash
python -m schema_tools \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --table-list tables.txt \
  --business-context "电商系统" \
  --output-dir ./output \
  --pipeline full
```

### 2. 生成Question-SQL训练数据

在生成DDL和MD文件后，可以使用新的Question-SQL生成功能：

```bash
python -m schema_tools.qs_generator \
  --output-dir ./output \
  --table-list ./tables.txt \
  --business-context "高速公路服务区管理系统" \
  --db-name highway_db
```

这将：
1. 验证DDL和MD文件数量是否正确
2. 读取所有MD文件内容
3. 使用LLM提取业务分析主题
4. 为每个主题生成10个Question-SQL对
5. 输出到 `qs_highway_db_时间戳_pair.json` 文件

### 3. 验证SQL语句有效性（新功能）

在生成Question-SQL对后，可以验证其中的SQL语句：

```bash
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./qs_highway_db_20240101_143052_pair.json \
  --output-dir ./validation_reports
```

这将：
1. 读取Question-SQL对文件
2. 使用PostgreSQL的EXPLAIN语句验证每个SQL
3. 生成详细的验证报告
4. 统计成功率和性能指标

#### SQL验证高级选项
```bash
# 基本验证（仅生成报告）
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json

# 删除无效SQL（不进行LLM修复）
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --modify-original-file

# 启用LLM修复功能
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --enable-llm-repair \
  --modify-original-file

# 性能调优参数
python -m schema_tools.sql_validator \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --input-file ./data.json \
  --max-concurrent 10 \
  --batch-size 20 \
  --timeout 60 \
  --verbose
```

### 4. 编程方式使用

#### 生成DDL/MD文档
```python
import asyncio
from schema_tools import SchemaTrainingDataAgent

async def generate_training_data():
    agent = SchemaTrainingDataAgent(
        db_connection="postgresql://user:pass@localhost:5432/dbname",
        table_list_file="tables.txt",
        business_context="高速公路服务区管理系统",
        output_dir="./output",
        pipeline="full"
    )
    
    report = await agent.generate_training_data()
    print(f"处理完成: {report['summary']}")

asyncio.run(generate_training_data())
```

#### 生成Question-SQL数据
```python
import asyncio
from schema_tools import QuestionSQLGenerationAgent

async def generate_qs_data():
    agent = QuestionSQLGenerationAgent(
        output_dir="./output",
        table_list_file="tables.txt",
        business_context="高速公路服务区管理系统",
        db_name="highway_db"
    )
    
    report = await agent.generate()
    print(f"生成完成: {report['total_questions']} 个问题")

asyncio.run(generate_qs_data())
```

#### 验证SQL语句
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
    print(f"验证完成: {report['summary']['success_rate']:.1%} 成功率")

asyncio.run(validate_sqls())
```

## 输出文件结构

```
output/
├── bss_car_day_count.ddl         # DDL文件
├── bss_car_day_count_detail.md   # MD文档
├── logs/                         # 日志目录
│   └── schema_tools_20240101_120000.log
├── filename_mapping.txt          # 文件名映射报告
├── qs_highway_db_20240101_143052_pair.json  # Question-SQL训练数据
├── metadata.txt                  # 主题元数据（INSERT语句）
└── validation_reports/           # SQL验证报告
    ├── sql_validation_20240101_150000_report.json
    └── sql_validation_20240101_150000_summary.txt
```

注意：配置已更新为不再创建ddl/和docs/子目录，所有文件直接放在output目录下。

## 配置选项

主要配置在 `schema_tools/config.py` 中：

```python
SCHEMA_TOOLS_CONFIG = {
    # 核心配置
    "output_directory": "training/generated_data",
    "default_pipeline": "full",
    "create_subdirectories": False,       # 不创建子目录
    
    # 数据处理配置
    "sample_data_limit": 20,              # 采样数据量
    "max_concurrent_tables": 3,           # 最大并发数
    
    # Question-SQL生成配置
    "qs_generation": {
        "max_tables": 20,                 # 最大表数量限制
        "theme_count": 5,                 # 生成主题数量
        "questions_per_theme": 10,        # 每主题问题数
        "max_concurrent_themes": 3,       # 并行处理主题数
    },
    
    # SQL验证配置
    "sql_validation": {
        "reuse_connection_pool": True,    # 复用现有连接池
        "max_concurrent_validations": 5,  # 并发验证数
        "validation_timeout": 30,         # 单个验证超时(秒)
        "batch_size": 10,                 # 批处理大小
        "continue_on_error": True,        # 错误时是否继续
        "save_validation_report": True,   # 保存验证报告
        "readonly_mode": True,            # 启用只读模式
    }
}
```

## 处理链类型

- **full**: 完整处理链（默认）
  - 数据库检查 → 数据采样 → 注释生成 → DDL生成 → MD文档生成

- **ddl_only**: 仅生成DDL
  - 数据库检查 → 数据采样 → 注释生成 → DDL生成

- **analysis_only**: 仅分析不生成文件
  - 数据库检查 → 数据采样 → 注释生成

## Question-SQL生成特性

### 功能亮点
- 🔍 自动验证文件完整性
- 📊 智能提取5个业务分析主题
- 🤖 每个主题生成10个高质量Question-SQL对
- 💾 支持中间结果保存和恢复
- ⚡ 支持并行处理提高效率

### 限制说明
- 一次最多处理20个表（可配置）
- 表数量超限会抛出异常
- 主题生成失败可跳过继续处理

### 输出格式
```json
[
  {
    "question": "按服务区统计每日营收趋势（最近30天）？",
    "sql": "SELECT service_name AS 服务区, oper_date AS 营业日期, SUM(pay_sum) AS 每日营收 FROM bss_business_day_data WHERE oper_date >= CURRENT_DATE - INTERVAL '30 day' AND delete_ts IS NULL GROUP BY service_name, oper_date ORDER BY 营业日期 ASC;"
  }
]
```

## SQL验证特性

### 功能亮点
- ✅ 使用EXPLAIN语句验证SQL有效性
- ⚡ 支持并发验证，提升验证效率
- 🔒 只读模式运行，安全可靠
- 📊 详细的验证报告和统计信息
- 🔄 自动重试机制，处理临时网络问题

### 验证流程
1. 读取Question-SQL对JSON文件
2. 提取SQL语句并分批处理
3. 使用PostgreSQL的EXPLAIN验证语法和表结构
4. 生成详细验证报告（JSON和文本格式）
5. 统计成功率和性能指标

### 报告内容
- 总体统计（成功率、平均耗时等）
- 错误详情和重试信息
- 单个SQL的验证结果
- 配置和元数据信息

## 常见问题

### Q: 如何处理只读数据库？
A: 工具自动检测并适配只读数据库，不会尝试写操作。SQL验证器专门设计为只读模式。

### Q: 如何处理重名表？
A: 自动生成唯一文件名，如 `hr__users.ddl` 和 `sales__users.ddl`。

### Q: 如何跳过某些表？
A: 在表清单文件中注释掉（使用 # 开头）或删除相应行。

### Q: LLM调用失败怎么办？
A: 自动重试3次，失败后使用原始注释或默认值。

### Q: SQL验证失败率很高怎么办？
A: 检查SQL语法、表名是否正确，使用 `--verbose` 查看详细错误信息。

## 注意事项

1. **数据库权限**：至少需要SELECT权限
2. **LLM配置**：复用项目的vanna实例配置
3. **并发控制**：默认最大3个表并发，可调整
4. **内存使用**：大表采样会限制数据量
5. **SQL验证**：需要对所有相关表有SELECT权限

## 开发与扩展

### 添加新工具

1. 创建工具类：
```python
from schema_tools.tools.base import BaseTool, ToolRegistry

@ToolRegistry.register("my_tool")
class MyTool(BaseTool):
    needs_llm = False
    tool_name = "我的工具"
    
    async def execute(self, context):
        # 实现工具逻辑
        return ProcessingResult(success=True)
```

2. 添加到处理链：
```python
"my_pipeline": [
    "database_inspector",
    "my_tool",
    "ddl_generator"
]
```

## 许可证

本工具作为VANNA-CHAINLIT-CHROMADB项目的一部分，遵循项目许可证。