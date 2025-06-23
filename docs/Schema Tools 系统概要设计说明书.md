# Schema Tools 系统概要设计说明书

## 1. 项目概述

### 1.1 项目目标

扩展现有的training模块，新增自动化数据库逆向工程功能，将PostgreSQL数据库结构转换为vanna.ai格式的训练数据（DDL和MD文档）。

### 1.2 核心功能

- 自动连接PostgreSQL数据库
- 批量处理表清单
- 生成带中文注释的DDL文件
- 生成详细的MD格式说明文档
- LLM辅助的智能注释生成和枚举检测
- 并发处理提高效率
- 完整的错误处理和日志记录
- **新增**: Question-SQL训练数据生成功能

## 2. 系统架构

### 2.1 整体架构

```
schema_tools/                    # 独立的schema工具模块
├── __init__.py                 # 模块入口
├── config.py                   # 配置文件
├── training_data_agent.py      # 主AI Agent
├── qs_agent.py                 # Question-SQL生成Agent (新增)
├── qs_generator.py             # Question-SQL命令行入口 (新增)
├── tools/                      # Agent工具集
│   ├── __init__.py
│   ├── base.py                 # 基础工具类和注册机制
│   ├── database_inspector.py   # 数据库元数据检查工具
│   ├── data_sampler.py         # 数据采样工具
│   ├── comment_generator.py    # LLM注释生成工具
│   ├── ddl_generator.py        # DDL格式生成工具
│   └── doc_generator.py        # MD文档生成工具
├── validators/                 # 验证器模块 (新增)
│   ├── __init__.py
│   └── file_count_validator.py # 文件数量验证器
├── analyzers/                  # 分析器模块 (新增)
│   ├── __init__.py
│   ├── md_analyzer.py          # MD文件分析器
│   └── theme_extractor.py      # 主题提取器
├── prompts/                    # 提示词和业务词典
│   ├── table_comment_template.txt
│   ├── field_comment_template.txt
│   ├── enum_detection_template.txt
│   ├── business_context.txt
│   └── business_dictionary.txt
├── utils/                      # 工具函数
│   ├── __init__.py
│   ├── table_parser.py         # 表清单解析器
│   ├── logger.py               # 日志管理
│   └── file_utils.py           # 文件操作工具
└── __main__.py                 # 命令行入口
```

### 2.2 核心组件

#### 2.2.1 主AI Agent

- **类名**: `SchemaTrainingDataAgent`
- **职责**: 整体流程控制、工具调度、并发管理
- **特点**: 单一Agent管理多工具的架构

#### 2.2.2 Question-SQL生成Agent（新增）

- **类名**: `QuestionSQLGenerationAgent`
- **职责**: 生成Question-SQL训练数据对
- **特点**: 独立的功能模块，可在DDL/MD生成后单独执行

#### 2.2.3 Agent工具集（基于装饰器注册）

1. **DatabaseInspectorTool**: 获取表元数据
2. **DataSamplerTool**: 采样表数据
3. **CommentGeneratorTool**: LLM生成注释和枚举建议
4. **DDLGeneratorTool**: 生成DDL格式文件
5. **DocGeneratorTool**: 生成MD文档

#### 2.2.4 验证器和分析器（新增）

1. **FileCountValidator**: 验证DDL和MD文件数量
2. **MDFileAnalyzer**: 读取和分析MD文件内容
3. **ThemeExtractor**: 使用LLM提取业务分析主题

## 3. 详细设计

### 3.1 DDL/MD生成流程

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

### 3.2 Question-SQL生成流程（新增）

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

### 3.2 模块间接口规范

#### 3.2.1 统一数据结构定义

```python
from dataclasses import dataclass
from typing import List, Dict, Optional, Any

@dataclass
class FieldInfo:
    """字段信息标准结构"""
    name: str
    type: str
    nullable: bool
    default_value: Optional[str]
    comment: Optional[str]
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_enum: bool = False
    enum_values: Optional[List[str]] = None

@dataclass
class TableMetadata:
    """表元数据标准结构"""
    schema_name: str
    table_name: str
    full_name: str  # schema.table_name
    comment: Optional[str]
    fields: List[FieldInfo]
    sample_data: List[Dict[str, Any]]
    row_count: Optional[int]

@dataclass
class ProcessingResult:
    """工具处理结果标准结构"""
    success: bool
    data: Optional[Any]
    error_message: Optional[str]
    warnings: List[str] = None
```

#### 3.2.2 工具接口规范

```python
class BaseTool:
    async def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> ProcessingResult:
        """
        统一工具执行接口
        Args:
            input_data: 输入数据字典
            context: 全局上下文
        Returns:
            ProcessingResult: 标准化处理结果
        """
        pass
```

### 3.3 可插拔处理链设计

#### 3.3.1 Pipeline配置

```python
# 支持灵活的处理链配置
PROCESSING_PIPELINES = {
    "full": [  # 完整处理链
        "database_inspector",
        "data_sampler", 
        "comment_generator",
        "ddl_generator",
        "doc_generator"
    ],
    "ddl_only": [  # 仅生成DDL
        "database_inspector",
        "data_sampler",
        "comment_generator", 
        "ddl_generator"
    ],
    "analysis_only": [  # 仅分析不生成文件
        "database_inspector",
        "data_sampler",
        "comment_generator"
    ]
}
```

#### 3.3.2 Pipeline执行器

```python
class PipelineExecutor:
    def __init__(self, pipeline_name: str):
        self.steps = PROCESSING_PIPELINES[pipeline_name]
        self.tools = {name: ToolRegistry.get_tool(name) for name in self.steps}
    
    async def execute(self, table_metadata: TableMetadata, context: Dict) -> Dict[str, ProcessingResult]:
        """按配置的处理链执行工具"""
        results = {}
        current_data = {"table_metadata": table_metadata}
        
        for step_name in self.steps:
            result = await self.tools[step_name].execute(current_data, context)
            results[step_name] = result
            if result.success:
                current_data[f"{step_name}_result"] = result.data
            else:
                # 根据配置决定是否继续
                if not SCHEMA_TOOLS_CONFIG["continue_on_error"]:
                    break
        
        return results
```

### 3.4 并发处理策略

#### 3.4.1 表级并发

- 最大并发表数: 可配置（默认3个）
- 使用asyncio.Semaphore控制并发数
- 单表内工具串行执行

#### 3.4.2 工具执行顺序

1. `DatabaseInspectorTool` → 获取表结构元数据
2. `DataSamplerTool` → 采样20条数据
3. `CommentGeneratorTool` → LLM生成注释和枚举建议
4. 枚举字段验证 → SELECT DISTINCT确认枚举值
5. `DDLGeneratorTool` → 生成DDL文件
6. `DocGeneratorTool` → 基于DDL结果生成MD文档

### 3.3 LLM集成设计

#### 3.3.1 LLM实例复用

```python
# 复用现有vanna实例，支持qwen/deepseek/ollama
from core.vanna_llm_factory import create_vanna_instance
vn = create_vanna_instance()
```

#### 3.3.2 智能注释生成

**输入**: 表元数据 + 20条样例数据 + 业务上下文 **输出**: 中文注释 + 枚举字段建议 **特点**: 一次LLM调用完成注释生成和枚举检测

#### 3.3.3 枚举检测策略

1. **规则预筛选**: ENUM类型、VARCHAR+关键词
2. **LLM智能判断**: 基于字段名、注释、样例数据
3. **数据验证**: SELECT DISTINCT确认实际枚举值

### 3.4 工具注册机制

#### 3.4.1 装饰器注册

```python
@ToolRegistry.register("database_inspector")
class DatabaseInspectorTool(BaseTool):
    needs_llm = False  # 是否需要LLM实例
```

#### 3.4.2 自动依赖注入

- 自动为需要LLM的工具注入vanna实例
- 确保所有工具使用相同的LLM配置

### 3.5 数据流设计

#### 3.5.1 工具间数据传递

- 方案B: 工具间直接传递数据
- DDLGeneratorTool的结果作为DocGeneratorTool的输入
- 通过input_data字典传递中间结果

#### 3.5.2 上下文管理

```python
context = {
    'business_context': '高速公路服务区管理系统',
    'table_name': 'bss_service_area',
    'output_dir': 'training/generated_data',
    'vn': vanna_instance
}
```

## 4. 配置设计

### 4.1 配置文件结构

```python
# schema_tools/config.py
SCHEMA_TOOLS_CONFIG = {
    # 核心配置
    "default_db_connection": None,
    "default_business_context": "数据库管理系统", 
    "output_directory": "training/generated_data",
    
    # 处理链配置
    "default_pipeline": "full",  # full, ddl_only, analysis_only
    "available_pipelines": {
        "full": ["database_inspector", "data_sampler", "comment_generator", "ddl_generator", "doc_generator"],
        "ddl_only": ["database_inspector", "data_sampler", "comment_generator", "ddl_generator"],
        "analysis_only": ["database_inspector", "data_sampler", "comment_generator"]
    },
    
    # 数据处理配置
    "sample_data_limit": 20,
    "enum_detection_sample_limit": 5000,
    "enum_max_distinct_values": 20,
    "enum_varchar_keywords": ["性别", "状态", "类型", "级别", "方向", "品类"],
    "large_table_threshold": 1000000,  # 大表阈值
    
    # 并发配置
    "max_concurrent_tables": 3,
    
    # LLM配置
    "use_app_config_llm": True,
    "comment_generation_timeout": 30,
    "max_llm_retries": 3,
    
    # 系统表过滤配置
    "filter_system_tables": True,
    "custom_system_prefixes": [],  # 用户自定义的系统表前缀
    "custom_system_schemas": [],   # 用户自定义的系统schema
    
    # 权限与安全配置
    "check_permissions": True,
    "require_select_permission": True,
    "allow_readonly_database": True,
    
    # 错误处理配置
    "continue_on_error": True,
    "max_table_failures": 5,
    "skip_large_tables": False,  # 是否跳过超大表
    "max_table_size": 10000000,  # 最大表行数限制
    
    # 文件配置
    "ddl_file_suffix": ".ddl",
    "doc_file_suffix": "_detail.md",
    "log_file": "schema_tools.log",
    "create_subdirectories": False,  # 不创建子目录，所有文件放在output目录下
    
    # 输出格式配置
    "include_sample_data_in_comments": True,  # 注释中是否包含示例数据
    "max_comment_length": 500,  # 最大注释长度
    "include_field_statistics": True,  # 是否包含字段统计信息
    
    # Question-SQL生成配置（新增）
    "qs_generation": {
        "max_tables": 20,                    # 最大表数量限制
        "theme_count": 5,                    # LLM生成的主题数量
        "questions_per_theme": 10,           # 每个主题生成的问题数
        "max_concurrent_themes": 3,          # 并行处理的主题数量
        "continue_on_theme_error": True,     # 主题生成失败是否继续
        "save_intermediate": True,           # 是否保存中间结果
        "output_file_prefix": "qs",          # 输出文件前缀
    }
}
```

### 4.2 配置优先级

```
命令行参数 > schema_tools/config.py > app_config.py默认值
```

### 4.3 多Schema场景处理

#### 4.3.1 文件命名防冲突机制

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

# 示例:
# public.users → users.ddl
# hr.employees → hr__employees.ddl
# sales.order-items → sales__order_items.ddl
```

#### 4.3.2 输出目录结构

```
training/generated_data/
├── ddl/
│   ├── users.ddl                    # public.users
│   ├── hr__employees.ddl            # hr.employees  
│   └── sales__order_items.ddl       # sales.order-items
├── docs/
│   ├── users_detail.md
│   ├── hr__employees_detail.md
│   └── sales__order_items_detail.md
└── logs/
    └── schema_tools.log
```

#### 4.3.3 重名检测与处理

```python
class FileNameManager:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.used_names = set()
    
    def get_unique_filename(self, schema_name: str, table_name: str, suffix: str) -> str:
        """确保文件名唯一性"""
        base_name = generate_safe_filename(schema_name, table_name, suffix)
        
        if base_name not in self.used_names:
            self.used_names.add(base_name)
            return base_name
        
        # 如果重名，添加数字后缀
        counter = 1
        while True:
            name_parts = base_name.rsplit('.', 1)
            if len(name_parts) == 2:
                unique_name = f"{name_parts[0]}_{counter}.{name_parts[1]}"
            else:
                unique_name = f"{base_name}_{counter}"
            
            if unique_name not in self.used_names:
                self.used_names.add(unique_name)
                return unique_name
            counter += 1
```

### 4.4 边界情况处理

#### 4.4.1 系统表过滤

```python
class SystemTableFilter:
    """系统表过滤器"""
    
    # PostgreSQL系统表前缀
    PG_SYSTEM_PREFIXES = [
        'pg_', 'information_schema', 'sql_', 'cardinal_number',
        'character_data', 'sql_identifier', 'time_stamp', 'yes_or_no'
    ]
    
    # 系统schema
    SYSTEM_SCHEMAS = [
        'information_schema', 'pg_catalog', 'pg_toast', 
        'pg_temp_1', 'pg_toast_temp_1'
    ]
    
    @classmethod
    def is_system_table(cls, schema_name: str, table_name: str) -> bool:
        """判断是否为系统表"""
        # 检查系统schema
        if schema_name.lower() in cls.SYSTEM_SCHEMAS:
            return True
        
        # 检查表名前缀
        table_lower = table_name.lower()
        return any(table_lower.startswith(prefix) for prefix in cls.PG_SYSTEM_PREFIXES)
    
    @classmethod
    def filter_user_tables(cls, table_list: List[str]) -> List[str]:
        """过滤出用户表"""
        user_tables = []
        filtered_count = 0
        
        for table_spec in table_list:
            if '.' in table_spec:
                schema, table = table_spec.split('.', 1)
            else:
                schema, table = 'public', table_spec
            
            if not cls.is_system_table(schema, table):
                user_tables.append(table_spec)
            else:
                filtered_count += 1
                logging.info(f"过滤系统表: {table_spec}")
        
        logging.info(f"过滤了 {filtered_count} 个系统表，保留 {len(user_tables)} 个用户表")
        return user_tables
```

#### 4.4.2 数据库权限检查

```python
class DatabasePermissionChecker:
    """数据库权限检查器"""
    
    def __init__(self, db_inspector):
        self.db_inspector = db_inspector
    
    async def check_permissions(self) -> Dict[str, bool]:
        """检查数据库权限"""
        permissions = {
            'connect': False,
            'select_metadata': False,
            'select_data': False,
            'is_readonly': False
        }
        
        try:
            # 检查连接权限
            await self.db_inspector.test_connection()
            permissions['connect'] = True
            
            # 检查元数据查询权限
            await self.db_inspector.get_schemas()
            permissions['select_metadata'] = True
            
            # 检查数据查询权限（测试一个已知表）
            try:
                await self.db_inspector.execute_query("SELECT 1 LIMIT 1")
                permissions['select_data'] = True
            except Exception as e:
                logging.warning(f"数据查询权限受限: {e}")
            
            # 检查是否为只读库（尝试创建临时表）
            try:
                await self.db_inspector.execute_query("CREATE TEMP TABLE test_write_permission (id int)")
                await self.db_inspector.execute_query("DROP TABLE test_write_permission")
            except Exception:
                permissions['is_readonly'] = True
                logging.info("检测到只读数据库，这是正常的")
            
        except Exception as e:
            logging.error(f"权限检查失败: {e}")
            
        return permissions
```

#### 4.4.3 大表处理策略

```python
class LargeTableHandler:
    """大表处理策略"""
    
    @staticmethod
    async def get_smart_sample(db_inspector, table_name: str, limit: int = 20) -> List[Dict]:
        """智能采样策略"""
        # 1. 先检查表大小
        row_count = await db_inspector.get_table_row_count(table_name)
        
        if row_count <= limit * 10:  # 小表，直接采样
            return await db_inspector.sample_table_data(table_name, limit)
        
        # 2. 大表使用分层采样
        logging.info(f"表 {table_name} 有 {row_count} 行，使用智能采样")
        
        # 前N行 + 随机中间N行 + 后N行
        samples_per_section = limit // 3
        
        samples = []
        
        # 前N行
        front_samples = await db_inspector.execute_query(
            f"SELECT * FROM {table_name} LIMIT {samples_per_section}"
        )
        samples.extend(front_samples)
        
        # 随机中间N行
        if row_count > samples_per_section * 2:
            middle_samples = await db_inspector.execute_query(f"""
                SELECT * FROM {table_name} 
                TABLESAMPLE SYSTEM(1) 
                LIMIT {samples_per_section}
            """)
            samples.extend(middle_samples)
        
        # 后N行
        remaining = limit - len(samples)
        if remaining > 0:
            tail_samples = await db_inspector.execute_query(f"""
                SELECT * FROM (
                    SELECT * FROM {table_name} 
                    ORDER BY CTID DESC 
                    LIMIT {remaining}
                ) sub ORDER BY CTID
            """)
            samples.extend(tail_samples)
        
        return samples[:limit]
```

#### 4.4.4 异常表结构处理

```python
class TableStructureValidator:
    """表结构验证器"""
    
    @staticmethod
    def validate_table_structure(table_metadata: TableMetadata) -> List[str]:
        """验证表结构，返回警告信息"""
        warnings = []
        
        # 检查是否有字段
        if not table_metadata.fields:
            warnings.append("表没有字段定义")
            return warnings
        
        # 检查是否有主键
        has_primary_key = any(field.is_primary_key for field in table_metadata.fields)
        if not has_primary_key:
            warnings.append("表没有主键")
        
        # 检查字段名是否合规
        for field in table_metadata.fields:
            if not field.name or field.name.strip() == '':
                warnings.append(f"发现空字段名")
            
            # 检查特殊字符
            if any(char in field.name for char in [' ', '-', '.']):
                warnings.append(f"字段名包含特殊字符: {field.name}")
        
        # 检查超大字段数量
        if len(table_metadata.fields) > 100:
            warnings.append(f"表字段数量过多: {len(table_metadata.fields)} 个字段")
        
        return warnings
```

## 5. 错误处理与日志

### 5.1 错误处理策略

#### 5.1.1 表级错误处理

- 某表处理失败 → 记录错误，继续下一表
- 失败表数超过阈值 → 警告但继续执行

#### 5.1.2 工具级错误处理

- `DatabaseInspectorTool`失败 → 跳过该表
- `CommentGeneratorTool`失败 → 使用原始注释
- `EnumDetectorTool`失败 → 跳过枚举检测
- 所有失败都记录到日志

#### 5.1.3 LLM调用错误处理

- 超时/失败 → 自动重试（最大3次）
- 重试失败 → 使用原始注释或默认注释

### 5.2 日志设计

#### 5.2.1 日志级别

- **INFO**: 正常处理流程
- **WARNING**: 可恢复错误（使用默认值、重试成功）
- **ERROR**: 影响结果的错误（表处理失败、工具异常）

#### 5.2.2 日志输出

- **控制台**: 进度信息和关键错误
- **文件**: 详细执行日志（schema_tools.log）
- **格式**: 文本格式，包含时间戳、级别、消息

## 6. 文件格式设计

### 6.1 DDL文件格式

```sql
-- 中文名: 服务区基础信息表
-- 描述: 记录高速公路服务区的基础属性，包括服务区编码、名称、方向、公司归属、地理位置、服务类型和状态，是业务分析与服务区定位的核心表。
create table bss_service_area (
  id varchar(32) not null,              -- 服务区唯一标识（主键，UUID)
  version integer not null,             -- 版本号
  service_area_name varchar(255),       -- 服务区名称
  service_area_no varchar(255),         -- 服务区编码（业务唯一标识）
  service_area_type varchar(50),        -- 服务区类型（枚举：信息化服务区、智能化服务区）
  primary key (id)
);
```

### 6.2 MD文档格式

```markdown
## bss_service_area（服务区基础信息表）
bss_service_area 表记录高速公路服务区的基础属性...

字段列表：
- id (varchar(32)) - 服务区唯一标识（主键，UUID) [示例: 0271d68ef93de9684b7ad8c7aae600b6]
- service_area_type (varchar(50)) - 服务区类型（枚举：信息化服务区、智能化服务区）[示例: 信息化服务区]

字段补充说明：
- service_area_type 为枚举字段，包含两个取值：信息化服务区、智能化服务区。
```

### 6.3 Question-SQL文件格式（新增）

```json
[
  {
    "question": "按服务区统计每日营收趋势（最近30天）？",
    "sql": "SELECT service_name AS 服务区, oper_date AS 营业日期, SUM(pay_sum) AS 每日营收 FROM bss_business_day_data WHERE oper_date >= CURRENT_DATE - INTERVAL '30 day' AND delete_ts IS NULL GROUP BY service_name, oper_date ORDER BY 营业日期 ASC NULLS LAST;"
  },
  {
    "question": "按月统计服务区营收趋势？",
    "sql": "SELECT service_name AS 服务区, DATE_TRUNC('month', oper_date) AS 月份, SUM(pay_sum) AS 月营收 FROM bss_business_day_data WHERE delete_ts IS NULL GROUP BY service_name, 月份 ORDER BY 月份 ASC NULLS LAST;"
  }
]
```

## 7. 使用方式

### 7.1 命令行方式

#### 7.1.1 生成DDL和MD文档

```bash
# 基本使用
python -m schema_tools \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --table-list tables.txt \
  --business-context "高速公路服务区管理系统"

# 指定处理链
python -m schema_tools \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --table-list tables.txt \
  --pipeline ddl_only \
  --business-context "高速公路服务区管理系统"

# 高级参数
python -m schema_tools \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --table-list tables.txt \
  --business-context-file business_context.txt \
  --output-dir custom_output \
  --max-concurrent 5 \
  --pipeline full \
  --no-filter-system-tables

# 权限检查模式
python -m schema_tools \
  --db-connection "postgresql://user:pass@localhost:5432/dbname" \
  --check-permissions-only
```

#### 7.1.2 生成Question-SQL训练数据（新增）

```bash
# 基本使用（在生成DDL/MD文件后执行）
python -m schema_tools.qs_generator \
  --output-dir ./output \
  --table-list ./schema_tools/tables.txt \
  --business-context "高速公路服务区管理系统" \
  --db-name highway_db

# 启用详细日志
python -m schema_tools.qs_generator \
  --output-dir ./output \
  --table-list ./tables.txt \
  --business-context "电商系统" \
  --db-name ecommerce_db \
  --verbose
```

### 7.2 编程方式

```python
from schema_tools import SchemaTrainingDataAgent

# 基本使用
agent = SchemaTrainingDataAgent(
    db_connection="postgresql://user:pass@localhost:5432/dbname",
    table_list_file="tables.txt",
    business_context="高速公路服务区管理系统"
)

await agent.generate_training_data()

# 指定处理链
agent = SchemaTrainingDataAgent(
    db_connection="postgresql://user:pass@localhost:5432/dbname",
    table_list_file="tables.txt",
    business_context="高速公路服务区管理系统",
    pipeline="ddl_only"
)

await agent.generate_training_data()

# 权限检查
permissions = await agent.check_database_permissions()
if permissions['select_data']:
    await agent.generate_training_data()
else:
    print("数据库权限不足")
```

### 7.3 表清单文件格式

```text
bss_service_area
bss_branch
public.bss_company
highway.bss_car_day_count
```

## 8. 扩展性设计

### 8.1 数据库适配

- 当前支持: PostgreSQL
- 预留扩展: MySQL适配接口
- 设计原则: 数据库特定代码隔离在DatabaseInspectorTool中

### 8.2 LLM模型适配

- 当前支持: qwen/deepseek/ollama
- 复用现有vanna配置，自动适配不同模型
- 提示词模板支持不同模型的特点

### 8.3 输出格式扩展

- 当前: DDL + MD
- 预留: JSON格式、Excel格式等

## 9. 性能考虑

### 9.1 并发控制

- 表级并发: 控制数据库连接数
- LLM调用: 避免过于频繁的API调用
- 内存管理: 及时释放大数据集

### 9.2 数据采样优化

- 限制采样数量避免大表性能问题
- 智能采样策略（如分页采样）

### 9.3 缓存策略

- 表元数据缓存（单次运行内）
- LLM结果缓存（避免重复调用）

## 10. 测试策略

### 10.1 单元测试

#### 10.1.1 工具测试

- **DatabaseInspectorTool**: Mock数据库连接，测试元数据提取
- **CommentGeneratorTool**: Mock LLM调用，测试注释生成逻辑
- **DDLGeneratorTool**: 测试DDL格式生成的正确性
- **DocGeneratorTool**: 测试MD文档格式和内容

#### 10.1.2 边界条件测试

- **文件名冲突**: 测试多schema重名表的文件名生成
- **系统表过滤**: 测试各种系统表的正确过滤
- **大表处理**: 测试智能采样策略
- **权限异常**: 测试只读库、权限不足等场景

#### 10.1.3 数据结构测试

- **TableMetadata**: 测试各种表结构的正确解析
- **FieldInfo**: 测试枚举字段检测逻辑
- **ProcessingResult**: 测试错误处理和结果传递

### 10.2 集成测试

#### 10.2.1 完整流程测试

- **标准流程**: 正常表的完整处理链测试
- **Pipeline测试**: 不同处理链配置的正确执行
- **并发测试**: 多表并发处理的稳定性

#### 10.2.2 数据库适配测试

- **不同PostgreSQL版本**: 9.6, 10, 11, 12, 13, 14, 15
- **不同schema配置**: public, 多schema, 复杂层级
- **特殊表结构**: 无主键表、超多字段表、复杂数据类型

#### 10.2.3 LLM集成测试

- **不同模型**: qwen, deepseek, ollama各版本
- **网络异常**: 超时、重试、降级处理
- **Token限制**: 超长输入的分段处理

#### 10.2.4 错误场景测试

- **网络中断**: 数据库连接中断恢复
- **权限变化**: 运行中权限被收回
- **磁盘空间**: 输出目录空间不足
- **内存限制**: 大量表并发处理

### 10.3 性能测试

#### 10.3.1 规模测试

- **小规模**: 10个表，验证基本功能
- **中规模**: 100个表，验证并发效率
- **大规模**: 1000+个表，验证内存和稳定性

#### 10.3.2 压力测试

- **长时间运行**: 24小时连续处理
- **资源限制**: 低内存、低CPU环境
- **高并发**: 最大并发数的边界测试

#### 10.3.3 性能基准

- **处理速度**: 平均每表处理时间
- **资源消耗**: 内存、CPU、网络使用率
- **LLM调用**: API调用频率和响应时间

### 10.4 用户验收测试

#### 10.4.1 功能验收

- **输出质量**: DDL和MD文档的正确性和可读性
- **中文注释**: 翻译质量和业务相关性
- **枚举检测**: 准确率和误报率
- **错误处理**: 异常情况的友好提示

#### 10.4.2 易用性测试

- **命令行接口**: 参数的直观性和错误提示
- **配置文件**: 配置项的完整性和说明
- **日志输出**: 进度显示和错误定位

#### 10.4.3 兼容性测试

- **操作系统**: Windows, Linux, macOS
- **Python版本**: 3.8, 3.9, 3.10, 3.11
- **依赖版本**: 各关键依赖库的版本兼容性

### 10.5 测试环境配置

#### 10.5.1 测试数据准备

```sql
-- 创建测试schema和表
CREATE SCHEMA test_schema;
CREATE SCHEMA hr;

-- 标准表（有主键、外键、注释）
CREATE TABLE test_schema.standard_table (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL COMMENT '姓名',
    status VARCHAR(20) DEFAULT 'active' COMMENT '状态'
);

-- 枚举字段表
CREATE TABLE test_schema.enum_table (
    id SERIAL PRIMARY KEY,
    gender VARCHAR(10), -- 性别: 男/女
    education VARCHAR(20), -- 学历: 本科/硕士/博士
    type INTEGER -- 类型: 1,2,3
);

-- 无主键表
CREATE TABLE test_schema.no_pk_table (
    col1 VARCHAR(50),
    col2 INTEGER
);

-- 大字段表
CREATE TABLE test_schema.wide_table (
    id SERIAL PRIMARY KEY
    -- 动态生成100个字段
);
```

#### 10.5.2 Mock数据配置

```python
# 测试用的Mock LLM响应
MOCK_LLM_RESPONSES = {
    "table_comment": {
        "standard_table": "标准测试表，用于验证基本功能",
        "enum_table": "枚举字段测试表，包含多种枚举类型字段"
    },
    "field_comments": {
        "gender": "性别字段，枚举值：男、女",
        "education": "教育程度，枚举值：本科、硕士、博士"
    },
    "enum_suggestions": {
        "gender": ["男", "女"],
        "education": ["本科", "硕士", "博士"],
        "type": ["1", "2", "3"]
    }
}
```

#### 10.5.3 CI/CD集成

```yaml
# .github/workflows/test.yml
name: Schema Tools Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:13
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.9
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-asyncio
    
    - name: Setup test database
      run: |
        python tests/setup_test_db.py
    
    - name: Run unit tests
      run: pytest tests/unit/
    
    - name: Run integration tests
      run: pytest tests/integration/
    
    - name: Run performance tests
      run: pytest tests/performance/ --benchmark-only
```