# Data Pipeline 系统概要设计说明书

## 1. 项目概述

### 1.1 项目目标

**Data Pipeline** 是一个完整的数据库逆向工程和训练数据生成系统，将PostgreSQL数据库结构转换为vanna.ai格式的训练数据，包括DDL文档、Markdown说明、Question-SQL问答对以及训练数据加载。

### 1.2 核心功能

- 自动连接PostgreSQL数据库
- 批量处理表清单，支持多Schema
- 生成带中文注释的DDL文件
- 生成详细的MD格式说明文档
- LLM辅助的智能注释生成和枚举检测
- Question-SQL训练数据生成
- SQL验证和自动修复
- 训练数据加载到向量数据库
- 端到端工作流编排
- 完整的错误处理和日志记录

## 2. 系统架构

### 2.1 整体架构

```
data_pipeline/                   # 数据管道模块
├── __init__.py                 # 模块入口
├── config.py                   # 统一配置文件
├── schema_workflow.py          # 端到端工作流编排器
├── ddl_generation/             # DDL/MD生成模块
│   ├── __init__.py
│   ├── ddl_md_generator.py     # 命令行入口
│   └── training_data_agent.py  # 主AI Agent
├── qa_generation/              # Question-SQL生成模块
│   ├── __init__.py
│   ├── qs_agent.py            # Q&A生成Agent
│   └── qs_generator.py        # Q&A命令行入口
├── validators/                 # SQL验证模块
│   ├── __init__.py
│   ├── sql_validation_agent.py # SQL验证Agent
│   ├── sql_validate_cli.py    # SQL验证命令行入口
│   ├── sql_validator.py       # SQL验证器核心
│   └── file_count_validator.py # 文件数量验证器
├── trainer/                    # 训练数据管理模块
│   ├── __init__.py
│   ├── run_training.py        # 训练数据加载脚本
│   └── vanna_trainer.py       # 训练器核心模块
├── tools/                      # Agent工具集
│   ├── __init__.py
│   ├── base.py                # 基础工具类和注册机制
│   ├── database_inspector.py  # 数据库元数据检查工具
│   ├── data_sampler.py        # 数据采样工具
│   ├── comment_generator.py   # LLM注释生成工具
│   ├── ddl_generator.py       # DDL格式生成工具
│   └── doc_generator.py       # MD文档生成工具
├── analyzers/                  # 分析器模块
│   ├── __init__.py
│   ├── md_analyzer.py         # MD文件分析器
│   └── theme_extractor.py     # 主题提取器
├── utils/                      # 工具函数
│   ├── __init__.py
│   ├── table_parser.py        # 表清单解析器
│   ├── logger.py              # 日志管理
│   ├── file_manager.py        # 文件管理器
│   ├── data_structures.py     # 数据结构定义
│   ├── large_table_handler.py # 大表处理
│   ├── permission_checker.py  # 权限检查器
│   └── system_filter.py       # 系统表过滤器
├── prompts/                    # 提示词和业务词典
│   ├── __init__.py
│   └── business_dictionary.txt
└── training_data/              # 训练数据存储目录
    ├── *.ddl                   # DDL文件
    ├── *_detail.md            # MD文档
    ├── qs_*_pair.json         # 问答对文件
    └── filename_mapping.txt    # 文件映射
```

### 2.2 核心组件

#### 2.2.1 工作流编排器
- **类名**: `SchemaWorkflowOrchestrator`
- **文件**: `schema_workflow.py`
- **职责**: 端到端执行完整的数据管道流程
- **特点**: 统一管理4个步骤的执行，支持配置覆盖

#### 2.2.2 DDL/MD生成Agent
- **类名**: `SchemaTrainingDataAgent`
- **文件**: `ddl_generation/training_data_agent.py`
- **职责**: 数据库逆向工程，生成DDL和MD文档
- **特点**: 单一Agent管理多工具的架构

#### 2.2.3 Question-SQL生成Agent
- **类名**: `QuestionSQLGenerationAgent`
- **文件**: `qa_generation/qs_agent.py`
- **职责**: 基于DDL/MD生成Question-SQL训练数据对
- **特点**: 独立的功能模块，支持主题分析和并发生成

#### 2.2.4 SQL验证Agent
- **类名**: `SQLValidationAgent`
- **文件**: `validators/sql_validation_agent.py`
- **职责**: 验证Question-SQL对中的SQL语句有效性，支持LLM自动修复
- **特点**: 支持并发验证、自动修复、原文件修改

#### 2.2.5 训练数据管理
- **文件**: `trainer/run_training.py`
- **职责**: 将生成的训练数据加载到向量数据库
- **特点**: 支持多种文件格式，自动识别和分类

#### 2.2.6 Agent工具集（基于装饰器注册）
1. **DatabaseInspectorTool**: 获取表元数据
2. **DataSamplerTool**: 采样表数据
3. **CommentGeneratorTool**: LLM生成注释和枚举建议
4. **DDLGeneratorTool**: 生成DDL格式文件
5. **DocGeneratorTool**: 生成MD文档

#### 2.2.7 验证器和分析器
1. **FileCountValidator**: 验证DDL和MD文件数量
2. **SQLValidator**: 验证SQL语句有效性，支持LLM自动修复
3. **MDFileAnalyzer**: 读取和分析MD文件内容
4. **ThemeExtractor**: 使用LLM提取业务分析主题

## 3. 详细设计

### 3.1 完整工作流程（4步骤）

```mermaid
graph TD
    A[开始] --> B[步骤1: DDL/MD生成]
    B --> C{成功?}
    C -->|否| D[生成错误报告]
    C -->|是| E[步骤2: Question-SQL生成]
    E --> F{成功?}
    F -->|否| D
    F -->|是| G{启用SQL验证?}
    G -->|否| H[步骤4: 训练数据加载]
    G -->|是| I[步骤3: SQL验证和修复]
    I --> J{成功?}
    J -->|否| D
    J -->|是| K{启用训练数据加载?}
    K -->|否| L[生成最终报告]
    K -->|是| H
    H --> M{成功?}
    M -->|否| D
    M -->|是| L
    L --> N[完成]
    D --> N
```

### 3.2 DDL/MD生成流程

```mermaid
graph TD
    A[开始处理表] --> B[DatabaseInspectorTool]
    B --> C[DataSamplerTool]
    C --> D[CommentGeneratorTool<br/>生成注释+枚举建议]
    D --> E[验证枚举字段<br/>SELECT DISTINCT]
    E --> F[DDLGeneratorTool]
    F --> G[DocGeneratorTool]
    G --> H[写入文件]
    H --> I[记录日志]
    I --> J[完成]
```

### 3.3 Question-SQL生成流程

```mermaid
graph TD
    A[开始] --> B[FileCountValidator<br/>验证文件数量]
    B --> C{验证通过?}
    C -->|否| D[报错退出]
    C -->|是| E[MDFileAnalyzer<br/>读取所有MD文件]
    E --> F[ThemeExtractor<br/>提取分析主题]
    F --> G[处理每个主题]
    G --> H[生成Question-SQL对]
    H --> I[保存JSON文件]
    I --> J[完成]
```

### 3.4 SQL验证和修复流程

```mermaid
graph TD
    A[开始] --> B[读取Question-SQL文件]
    B --> C[提取SQL语句]
    C --> D[批量验证SQL]
    D --> E{有失败的SQL?}
    E -->|否| F[生成验证报告]
    E -->|是| G{启用LLM修复?}
    G -->|否| H[仅生成报告]
    G -->|是| I[LLM修复失败SQL]
    I --> J[重新验证修复后SQL]
    J --> K{启用文件修改?}
    K -->|否| F
    K -->|是| L[创建备份文件]
    L --> M[更新原文件]
    M --> N[生成修改日志]
    N --> F
    F --> O[完成]
    H --> F
```

### 3.5 训练数据加载流程

```mermaid
graph TD
    A[开始] --> B[扫描训练数据目录]
    B --> C[识别文件类型]
    C --> D[处理DDL文件]
    C --> E[处理MD文件]
    C --> F[处理JSON问答对]
    C --> G[处理SQL文件]
    D --> H[加载到向量数据库]
    E --> H
    F --> H
    G --> H
    H --> I[验证加载结果]
    I --> J[生成统计报告]
    J --> K[完成]
```

## 4. 配置设计

### 4.1 统一配置架构

所有data_pipeline相关配置统一在 `data_pipeline/config.py` 中：

```python
SCHEMA_TOOLS_CONFIG = {
    # 核心配置
    "default_db_connection": None,
    "default_business_context": "数据库管理系统", 
    "output_directory": "./data_pipeline/training_data/",
    
    # 处理链配置
    "default_pipeline": "full",
    "available_pipelines": {
        "full": ["database_inspector", "data_sampler", "comment_generator", "ddl_generator", "doc_generator"],
        "ddl_only": ["database_inspector", "data_sampler", "comment_generator", "ddl_generator"],
        "analysis_only": ["database_inspector", "data_sampler", "comment_generator"]
    },
    
    # 数据处理配置
    "sample_data_limit": 20,
    "enum_detection_sample_limit": 5000,
    "enum_max_distinct_values": 20,
    "large_table_threshold": 1000000,
    
    # 并发配置
    "max_concurrent_tables": 1,  # 避免LLM并发调用问题
    
    # Question-SQL生成配置
    "qs_generation": {
        "max_tables": 20,
        "theme_count": 5,
        "questions_per_theme": 10,
        "max_concurrent_themes": 1,
        "continue_on_theme_error": True,
        "save_intermediate": True,
        "output_file_prefix": "qs",
    },
    
    # SQL验证配置
    "sql_validation": {
        "max_concurrent_validations": 5,
        "validation_timeout": 30,
        "batch_size": 10,
        "enable_sql_repair": False,  # 默认禁用
        "modify_original_file": False,  # 默认禁用
        "readonly_mode": True,
    }
}
```

### 4.2 配置优先级

```
命令行参数 > data_pipeline/config.py > 默认值
```

### 4.3 与全局配置的分离

- **系统级配置** (`app_config.py`): LLM配置、向量数据库配置、全局开关
- **模块级配置** (`data_pipeline/config.py`): 数据管道专用配置
- **清晰分工**: 避免配置冲突和重复

## 5. 使用方式

### 5.1 端到端工作流（推荐）

```bash
# 完整4步流程
python -m data_pipeline.schema_workflow \
  --db-connection "postgresql://user:pass@localhost:5432/database_name" \
  --table-list tables.txt \
  --business-context "高速公路服务区管理系统" \
  --output-dir ./data_pipeline/training_data/

# 跳过SQL验证
python -m data_pipeline.schema_workflow \
  --db-connection "postgresql://user:pass@localhost:5432/database_name" \
  --table-list tables.txt \
  --business-context "电商系统" \
  --skip-validation

# 跳过训练数据加载
python -m data_pipeline.schema_workflow \
  --db-connection "postgresql://user:pass@localhost:5432/database_name" \
  --table-list tables.txt \
  --business-context "管理系统" \
  --skip-training-load
```

### 5.2 分步执行

```bash
# 第1步：DDL/MD生成
python -m data_pipeline.ddl_generation.ddl_md_generator \
  --db-connection "postgresql://user:pass@localhost:5432/database" \
  --table-list tables.txt \
  --business-context "业务描述"

# 第2步：Q&A生成
python -m data_pipeline.qa_generation.qs_generator \
  --output-dir ./data_pipeline/training_data/ \
  --table-list tables.txt \
  --business-context "业务描述"

# 第3步：SQL验证
python -m data_pipeline.validators.sql_validate_cli \
  --db-connection "postgresql://user:pass@localhost:5432/database" \
  --input-file ./qs_xxx.json

# 第4步：训练数据加载
python -m data_pipeline.trainer.run_training \
  --data_path ./data_pipeline/training_data/
```

### 5.3 编程方式

```python
import asyncio
from data_pipeline.schema_workflow import SchemaWorkflowOrchestrator

async def run_complete_workflow():
    orchestrator = SchemaWorkflowOrchestrator(
        db_connection="postgresql://user:pass@localhost:5432/database_name",
        table_list_file="tables.txt",
        business_context="高速公路服务区管理系统",
        output_dir="./data_pipeline/training_data/",
        enable_sql_validation=True,
        enable_llm_repair=True,
        modify_original_file=True,
        enable_training_data_load=True
    )
    
    report = await orchestrator.execute_complete_workflow()
    return report

# 运行工作流程
asyncio.run(run_complete_workflow())
```

## 6. 文件格式设计

### 6.1 DDL文件格式

```sql
-- 中文名: 存储高速公路管理公司信息
-- 描述: 存储高速公路管理公司信息，用于服务区运营管理
create table public.bss_company (
  id varchar(32) not null     -- 主键ID，主键,
  version integer not null    -- 版本号,
  company_name varchar(255)   -- 公司名称,
  primary key (id)
);
```

### 6.2 MD文档格式

```markdown
## bss_company（存储高速公路管理公司信息）
bss_company 表存储高速公路管理公司信息，用于服务区运营管理

字段列表：
- id (varchar(32)) - 主键ID [主键, 非空] [示例: 30675d85ba5044c31acfa243b9d16334]
- company_name (varchar(255)) - 公司名称 [示例: 上饶分公司, 宜春分公司]

字段补充说明：
- id 为主键
```

### 6.3 Question-SQL文件格式

```json
[
  {
    "question": "查询所有公司信息",
    "sql": "SELECT * FROM bss_company WHERE delete_ts IS NULL"
  },
  {
    "question": "按公司统计服务区数量",
    "sql": "SELECT company_name, COUNT(*) FROM bss_service_area GROUP BY company_name"
  }
]
```

## 7. 多Schema支持

### 7.1 文件命名防冲突机制

```python
def generate_safe_filename(schema_name: str, table_name: str, suffix: str) -> str:
    """
    生成安全的文件名，避免冲突
    
    规则:
    - public.table_name → table_name.ddl
    - schema.table_name → schema__table_name.ddl  
    - 特殊字符替换: . → __, - → _, 空格 → _
    """
    if schema_name.lower() == 'public':
        safe_name = table_name
    else:
        safe_name = f"{schema_name}__{table_name}"
    
    # 替换特殊字符
    safe_name = safe_name.replace('.', '__').replace('-', '_').replace(' ', '_')
    
    return f"{safe_name}{suffix}"
```

### 7.2 输出目录结构

```
data_pipeline/training_data/
├── bss_company.ddl                          # public.bss_company
├── hr__employees.ddl                        # hr.employees  
├── sales__order_items.ddl                   # sales.order_items
├── bss_company_detail.md                    # 对应的MD文档
├── hr__employees_detail.md
├── sales__order_items_detail.md
├── qs_highway_db_20240626_pair.json         # Question-SQL对文件
├── filename_mapping.txt                     # 文件名映射
└── sql_validation_20240626_summary.log      # SQL验证报告
```

## 8. 错误处理与容错

### 8.1 错误处理策略

#### 8.1.1 工作流级错误处理
- 步骤失败 → 生成详细错误报告，包含失败原因和已完成步骤
- 支持从失败步骤重新开始
- 保留中间结果用于调试

#### 8.1.2 表级错误处理
- 某表处理失败 → 记录错误，继续下一表
- 失败表数超过阈值 → 警告但继续执行

#### 8.1.3 LLM调用错误处理
- 超时/失败 → 自动重试（最大3次）
- 重试失败 → 使用原始注释或默认注释

### 8.2 日志设计

#### 8.2.1 日志级别
- **INFO**: 正常处理流程
- **WARNING**: 可恢复错误
- **ERROR**: 影响结果的错误

#### 8.2.2 日志输出
- **控制台**: 进度信息和关键错误
- **文件**: 详细执行日志
- **格式**: 包含时间戳、级别、组件、消息

## 9. 性能考虑

### 9.1 并发控制
- 表级并发: 控制数据库连接数
- LLM调用: 避免过于频繁的API调用（建议最大并发1）
- 内存管理: 及时释放大数据集

### 9.2 数据采样优化
- 限制采样数量避免大表性能问题
- 智能采样策略（分层采样）
- 大表检测和特殊处理

### 9.3 缓存策略
- 表元数据缓存（单次运行内）
- LLM结果缓存（避免重复调用）
- 连接池复用

## 10. 扩展性设计

### 10.1 数据库适配
- 当前支持: PostgreSQL
- 预留扩展: MySQL适配接口
- 设计原则: 数据库特定代码隔离在DatabaseInspectorTool中

### 10.2 LLM模型适配
- 当前支持: qwen/deepseek/ollama
- 复用现有vanna配置，自动适配不同模型
- 提示词模板支持不同模型的特点

### 10.3 输出格式扩展
- 当前: DDL + MD + JSON
- 预留: Excel格式、其他结构化格式

### 10.4 工作流扩展
- 模块化设计，可添加新的处理步骤
- 插件式架构，支持自定义工具
- 配置驱动，灵活组合处理链

## 11. 总结

Data Pipeline系统提供了完整的数据库逆向工程解决方案，从原始数据库schema到可用的训练数据，整个流程完全自动化。系统设计遵循以下原则：

1. **模块化**: 清晰的模块划分，便于维护和扩展
2. **可配置**: 丰富的配置选项，适应不同场景需求
3. **容错性**: 完善的错误处理，确保系统稳定运行
4. **可观测**: 详细的日志和报告，便于问题定位
5. **高性能**: 合理的并发控制和资源管理
6. **可扩展**: 预留扩展接口，支持未来功能增强

通过工作流编排器，用户可以一键完成所有步骤，也可以根据需要分步执行和调试。系统适合各种规模的数据处理需求，是vanna.ai训练数据准备的理想解决方案。