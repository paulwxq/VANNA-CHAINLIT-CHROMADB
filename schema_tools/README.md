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

## 安装依赖

```bash
pip install asyncpg asyncio
```

## 使用方法

### 1. 命令行方式

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

#### 仅检查数据库权限
```bash
python -m schema_tools \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --check-permissions-only
```

### 2. 编程方式

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

### 3. 表清单文件格式

创建一个文本文件（如 `tables.txt`），每行一个表名：

```text
# 这是注释行
public.users
public.orders
hr.employees
sales.products
```

## 输出文件结构

```
output/
├── ddl/                          # DDL文件目录
│   ├── users.ddl
│   ├── orders.ddl
│   └── hr__employees.ddl
├── docs/                         # MD文档目录
│   ├── users_detail.md
│   ├── orders_detail.md
│   └── hr__employees_detail.md
├── logs/                         # 日志目录
│   └── schema_tools_20240101_120000.log
└── filename_mapping.txt          # 文件名映射报告
```

## 配置选项

主要配置在 `schema_tools/config.py` 中：

```python
SCHEMA_TOOLS_CONFIG = {
    # 核心配置
    "output_directory": "training/generated_data",
    "default_pipeline": "full",
    
    # 数据处理配置
    "sample_data_limit": 20,              # 采样数据量
    "max_concurrent_tables": 3,           # 最大并发数
    
    # LLM配置
    "max_llm_retries": 3,                # LLM重试次数
    "comment_generation_timeout": 30,     # 超时时间
    
    # 系统表过滤
    "filter_system_tables": True,         # 过滤系统表
    
    # 错误处理
    "continue_on_error": True,            # 错误后继续
}
```

## 处理链类型

- **full**: 完整处理链（默认）
  - 数据库检查 → 数据采样 → 注释生成 → DDL生成 → MD文档生成

- **ddl_only**: 仅生成DDL
  - 数据库检查 → 数据采样 → 注释生成 → DDL生成

- **analysis_only**: 仅分析不生成文件
  - 数据库检查 → 数据采样 → 注释生成

## 业务上下文

业务上下文帮助LLM更好地理解表和字段的含义：

### 方式1：命令行参数
```bash
--business-context "高速公路服务区管理系统"
```

### 方式2：文件方式
```bash
--business-context-file business_context.txt
```

### 方式3：业务词典
编辑 `schema_tools/prompts/business_dictionary.txt`：
```text
BSS - Business Support System，业务支撑系统
SA - Service Area，服务区
POS - Point of Sale，销售点
```

## 高级功能

### 1. 自定义系统表过滤

```python
from schema_tools.utils.system_filter import SystemTableFilter

filter = SystemTableFilter()
filter.add_custom_prefix("tmp_")      # 添加自定义前缀
filter.add_custom_schema("temp")      # 添加自定义schema
```

### 2. 大表智能采样

对于超过100万行的大表，自动使用分层采样策略：
- 前N行
- 随机中间行
- 后N行

### 3. 枚举字段检测

自动检测并验证枚举字段：
- VARCHAR类型
- 样例值重复度高
- 字段名包含类型关键词（状态、类型、级别等）

## 常见问题

### Q: 如何处理只读数据库？
A: 工具自动检测并适配只读数据库，不会尝试写操作。

### Q: 如何处理重名表？
A: 自动生成唯一文件名，如 `hr__users.ddl` 和 `sales__users.ddl`。

### Q: 如何跳过某些表？
A: 在表清单文件中注释掉（使用 # 开头）或删除相应行。

### Q: LLM调用失败怎么办？
A: 自动重试3次，失败后使用原始注释或默认值。

## 注意事项

1. **数据库权限**：至少需要SELECT权限
2. **LLM配置**：复用项目的vanna实例配置
3. **并发控制**：默认最大3个表并发，可调整
4. **内存使用**：大表采样会限制数据量

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