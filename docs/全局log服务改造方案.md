# 项目日志系统改造设计方案（精简实用版）

## 1. 整体设计理念

基于您的需求，设计一套类似Log4j的统一日志服务，专注核心功能：
- 统一的日志级别管理（info/error/debug/warning）
- 可配置的日志输出路径
- 支持控制台和文件输出
- 不同模块独立日志文件（data_pipeline、agent、vanna等）
- 自动日志轮转和清理
- 与现有vanna/langchain/langgraph技术栈兼容

## 2. 核心架构设计

### 2.1 精简的日志服务层次结构

```
项目根目录/
├── core/
│   └── logging/
│       ├── __init__.py           # 日志服务入口
│       └── log_manager.py        # 核心日志管理器
├── logs/                         # 日志文件目录
│   ├── data_pipeline.log        # data_pipeline模块日志
│   ├── agent.log                # agent模块日志
│   ├── vanna.log                # vanna模块日志
│   ├── langchain.log            # langchain模块日志
│   ├── langgraph.log            # langgraph模块日志
│   └── app.log                  # 主应用日志
└── config/
    └── logging_config.yaml       # 日志配置文件
```

### 2.2 核心日志管理器设计（增强版）

基于用户反馈，增强版包含以下特性：
- **异步日志支持**
- **灵活的上下文管理**（user_id可选）
- **错误降级策略**
- **重点支持citu_app.py**

```python
# core/logging/log_manager.py
import logging
import logging.handlers
import os
from typing import Dict, Optional
from pathlib import Path
import yaml
import asyncio
from concurrent.futures import ThreadPoolExecutor
import contextvars

# 上下文变量，存储可选的上下文信息
log_context = contextvars.ContextVar('log_context', default={})

class ContextFilter(logging.Filter):
    """添加上下文信息到日志记录"""
    def filter(self, record):
        ctx = log_context.get()
        # 设置默认值，避免格式化错误
        record.session_id = ctx.get('session_id', 'N/A')
        record.user_id = ctx.get('user_id', 'anonymous')
        record.request_id = ctx.get('request_id', 'N/A')
        return True

class LogManager:
    """统一日志管理器 - 类似Log4j的功能"""
    
    _instance = None
    _loggers: Dict[str, logging.Logger] = {}
    _initialized = False
    _executor = None
    _fallback_to_console = False  # 标记是否降级到控制台
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.config = None
            self.base_log_dir = Path("logs")
            self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="log")
            self._setup_base_directory()
            LogManager._initialized = True
    
    def initialize(self, config_path: str = "config/logging_config.yaml"):
        """初始化日志系统"""
        self.config = self._load_config(config_path)
        self._setup_base_directory()
        self._configure_root_logger()
    
    def get_logger(self, name: str, module: str = "default") -> logging.Logger:
        """获取指定模块的logger"""
        logger_key = f"{module}.{name}"
        
        if logger_key not in self._loggers:
            logger = logging.getLogger(logger_key)
            self._configure_logger(logger, module)
            self._loggers[logger_key] = logger
        
        return self._loggers[logger_key]
    
    async def alog(self, logger: logging.Logger, level: str, message: str, **kwargs):
        """异步日志方法"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._executor,
            lambda: getattr(logger, level)(message, **kwargs)
        )
    
    def set_context(self, **kwargs):
        """设置日志上下文（可选）"""
        ctx = log_context.get()
        ctx.update(kwargs)
        log_context.set(ctx)
    
    def clear_context(self):
        """清除日志上下文"""
        log_context.set({})
    
    def _load_config(self, config_path: str) -> dict:
        """加载配置文件（带错误处理）"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"[WARNING] 配置文件 {config_path} 未找到，使用默认配置")
            return self._get_default_config()
        except Exception as e:
            print(f"[ERROR] 加载配置文件失败: {e}，使用默认配置")
            return self._get_default_config()
    
    def _setup_base_directory(self):
        """创建日志目录（带降级策略）"""
        try:
            self.base_log_dir.mkdir(parents=True, exist_ok=True)
            self._fallback_to_console = False
        except Exception as e:
            print(f"[WARNING] 无法创建日志目录 {self.base_log_dir}，将只使用控制台输出: {e}")
            self._fallback_to_console = True
    
    def _configure_logger(self, logger: logging.Logger, module: str):
        """配置具体的logger（支持降级）"""
        module_config = self.config.get('modules', {}).get(module, self.config['default'])
        
        # 设置日志级别
        level = getattr(logging, module_config['level'].upper())
        logger.setLevel(level)
        
        # 清除已有处理器
        logger.handlers.clear()
        logger.propagate = False
        
        # 添加控制台处理器
        if module_config.get('console', {}).get('enabled', True):
            console_handler = self._create_console_handler(module_config['console'])
            console_handler.addFilter(ContextFilter())
            logger.addHandler(console_handler)
        
        # 添加文件处理器（如果没有降级到控制台）
        if not self._fallback_to_console and module_config.get('file', {}).get('enabled', True):
            try:
                file_handler = self._create_file_handler(module_config['file'], module)
                file_handler.addFilter(ContextFilter())
                logger.addHandler(file_handler)
            except Exception as e:
                print(f"[WARNING] 无法创建文件处理器: {e}")
    
    def _get_default_config(self) -> dict:
        """获取默认配置"""
        return {
            'global': {'base_level': 'INFO'},
            'default': {
                'level': 'INFO',
                'console': {
                    'enabled': True,
                    'level': 'INFO',
                    'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
                },
                'file': {
                    'enabled': True,
                    'level': 'DEBUG',
                    'filename': 'app.log',
                    'format': '%(asctime)s [%(levelname)s] [%(name)s] [user:%(user_id)s] [session:%(session_id)s] %(filename)s:%(lineno)d - %(message)s',
                    'rotation': {
                        'enabled': True,
                        'max_size': '50MB',
                        'backup_count': 10
                    }
                }
            },
            'modules': {}
        }
    
    def _create_console_handler(self, console_config: dict) -> logging.StreamHandler:
        """创建控制台处理器"""
        handler = logging.StreamHandler()
        handler.setLevel(getattr(logging, console_config.get('level', 'INFO').upper()))
        
        formatter = logging.Formatter(
            console_config.get('format', '%(asctime)s [%(levelname)s] %(name)s: %(message)s'),
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        return handler
    
    def _create_file_handler(self, file_config: dict, module: str) -> logging.Handler:
        """创建文件处理器（支持自动轮转）"""
        log_file = self.base_log_dir / file_config.get('filename', f'{module}.log')
        
        # 使用RotatingFileHandler实现自动轮转和清理
        rotation_config = file_config.get('rotation', {})
        if rotation_config.get('enabled', False):
            handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=self._parse_size(rotation_config.get('max_size', '50MB')),
                backupCount=rotation_config.get('backup_count', 10),
                encoding='utf-8'
            )
        else:
            handler = logging.FileHandler(log_file, encoding='utf-8')
        
        handler.setLevel(getattr(logging, file_config.get('level', 'DEBUG').upper()))
        
        formatter = logging.Formatter(
            file_config.get('format', '%(asctime)s [%(levelname)s] [%(name)s] %(filename)s:%(lineno)d - %(message)s'),
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        return handler
    
    def _parse_size(self, size_str: str) -> int:
        """解析大小字符串，如 '50MB' -> 字节数"""
        size_str = size_str.upper()
        if size_str.endswith('KB'):
            return int(size_str[:-2]) * 1024
        elif size_str.endswith('MB'):
            return int(size_str[:-2]) * 1024 * 1024
        elif size_str.endswith('GB'):
            return int(size_str[:-2]) * 1024 * 1024 * 1024
        else:
            return int(size_str)
    
    def __del__(self):
        """清理资源"""
        if self._executor:
            self._executor.shutdown(wait=False)
```

### 2.3 统一日志接口（增强版）

```python
# core/logging/__init__.py
from .log_manager import LogManager
import logging

# 全局日志管理器实例
_log_manager = LogManager()

def initialize_logging(config_path: str = "config/logging_config.yaml"):
    """初始化项目日志系统"""
    _log_manager.initialize(config_path)

def get_logger(name: str, module: str = "default") -> logging.Logger:
    """获取logger实例 - 主要API"""
    return _log_manager.get_logger(name, module)

# 便捷方法
def get_data_pipeline_logger(name: str) -> logging.Logger:
    """获取data_pipeline模块logger"""
    return get_logger(name, "data_pipeline")

def get_agent_logger(name: str) -> logging.Logger:
    """获取agent模块logger"""
    return get_logger(name, "agent")

def get_vanna_logger(name: str) -> logging.Logger:
    """获取vanna模块logger"""
    return get_logger(name, "vanna")

# 上下文管理便捷方法
def set_log_context(**kwargs):
    """设置日志上下文（可选）
    示例: set_log_context(user_id='user123', session_id='sess456')
    """
    _log_manager.set_context(**kwargs)

def clear_log_context():
    """清除日志上下文"""
    _log_manager.clear_context()

# 异步日志便捷方法
async def alog_info(logger: logging.Logger, message: str, **kwargs):
    """异步记录INFO日志"""
    await _log_manager.alog(logger, 'info', message, **kwargs)

async def alog_error(logger: logging.Logger, message: str, **kwargs):
    """异步记录ERROR日志"""
    await _log_manager.alog(logger, 'error', message, **kwargs)

async def alog_debug(logger: logging.Logger, message: str, **kwargs):
    """异步记录DEBUG日志"""
    await _log_manager.alog(logger, 'debug', message, **kwargs)

async def alog_warning(logger: logging.Logger, message: str, **kwargs):
    """异步记录WARNING日志"""
    await _log_manager.alog(logger, 'warning', message, **kwargs)
```

### 2.4 日志配置文件（支持上下文信息）

```yaml
# config/logging_config.yaml
version: 1

# 全局配置
global:
  base_level: INFO
  
# 默认配置
default:
  level: INFO
  console:
    enabled: true
    level: INFO
    format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  file:
    enabled: true
    level: DEBUG
    filename: "app.log"
    # 支持上下文信息，但有默认值避免错误
    format: "%(asctime)s [%(levelname)s] [%(name)s] [user:%(user_id)s] [session:%(session_id)s] %(filename)s:%(lineno)d - %(message)s"
    rotation:
      enabled: true
      max_size: "50MB"
      backup_count: 10

# 模块特定配置
modules:
  data_pipeline:
    level: DEBUG
    console:
      enabled: true
      level: INFO
      format: "🔄 %(asctime)s [%(levelname)s] Pipeline: %(message)s"
    file:
      enabled: true
      level: DEBUG
      filename: "data_pipeline.log"
      format: "%(asctime)s [%(levelname)s] [%(name)s] %(filename)s:%(lineno)d - %(message)s"
      rotation:
        enabled: true
        max_size: "30MB"
        backup_count: 8
  
  agent:
    level: DEBUG
    console:
      enabled: true
      level: INFO
      format: "🤖 %(asctime)s [%(levelname)s] Agent: %(message)s"
    file:
      enabled: true
      level: DEBUG
      filename: "agent.log"
      # Agent模块支持user_id和session_id
      format: "%(asctime)s [%(levelname)s] [%(name)s] [user:%(user_id)s] [session:%(session_id)s] %(filename)s:%(lineno)d - %(message)s"
      rotation:
        enabled: true
        max_size: "30MB"
        backup_count: 8
  
  vanna:
    level: INFO
    console:
      enabled: true
      level: INFO
      format: "🧠 %(asctime)s [%(levelname)s] Vanna: %(message)s"
    file:
      enabled: true
      level: DEBUG
      filename: "vanna.log"
      format: "%(asctime)s [%(levelname)s] [%(name)s] %(filename)s:%(lineno)d - %(message)s"
      rotation:
        enabled: true
        max_size: "20MB"
        backup_count: 5
```

## 3. 改造实施步骤

### 3.1 第一阶段：基础架构搭建

1. **创建日志服务目录结构**
   ```bash
   mkdir -p core/logging
   mkdir -p config
   mkdir -p logs
   ```

2. **实现核心组件**
   - 创建 `core/logging/log_manager.py`
   - 创建 `core/logging/__init__.py`
   - 创建 `config/logging_config.yaml`

3. **集成到citu_app.py（主要应用）**
   ```python
   # 在citu_app.py的开头添加
   from core.logging import initialize_logging, get_logger, set_log_context, clear_log_context
   import uuid
   
   # 初始化日志系统
   initialize_logging("config/logging_config.yaml")
   app_logger = get_logger("CituApp", "default")
   
   # 在Flask应用配置后集成请求级别的日志上下文
   @app.flask_app.before_request
   def before_request():
       # 为每个请求设置上下文（如果有的话）
       request_id = str(uuid.uuid4())[:8]
       user_id = request.headers.get('X-User-ID', 'anonymous')
       set_log_context(request_id=request_id, user_id=user_id)
   
   @app.flask_app.after_request
   def after_request(response):
       # 清理上下文
       clear_log_context()
       return response
   ```

### 3.2 第二阶段：模块改造

#### 3.2.1 改造data_pipeline模块

```python
# 替换 data_pipeline/utils/logger.py 中的使用方式
from core.logging import get_data_pipeline_logger

def setup_logging(verbose: bool = False, log_file: str = None, log_dir: str = None):
    """
    保持原有接口，内部使用新的日志系统
    """
    # 不再需要复杂的设置，直接使用统一日志系统
    pass

# 在各个文件中使用
# data_pipeline/qa_generation/qs_agent.py
class QuestionSQLGenerationAgent:
    def __init__(self, ...):
        # 替换原有的 logging.getLogger("schema_tools.QSAgent")
        self.logger = get_data_pipeline_logger("QSAgent")
        
    async def generate(self):
        self.logger.info("🚀 开始生成Question-SQL训练数据")
        # ... 其他代码
        
        # 手动记录关键节点的时间
        start_time = time.time()
        self.logger.info("开始初始化LLM组件")
        
        self._initialize_llm_components()
        
        init_time = time.time() - start_time
        self.logger.info(f"LLM组件初始化完成，耗时: {init_time:.2f}秒")
```

#### 3.2.2 改造Agent模块（支持可选的用户上下文）

```python
# 在ask_agent接口中使用
@app.flask_app.route('/api/v0/ask_agent', methods=['POST'])
def ask_agent():
    logger = get_agent_logger("AskAgent")
    
    try:
        data = request.json
        question = data.get('question', '')
        user_id = data.get('user_id')  # 可选
        session_id = data.get('session_id')  # 可选
        
        # 设置上下文（如果有的话）
        if user_id or session_id:
            set_log_context(user_id=user_id or 'anonymous', session_id=session_id or 'N/A')
        
        logger.info(f"收到问题: {question[:50]}...")
        
        # 异步记录示例（在async函数中）
        # await alog_info(logger, f"开始处理问题: {question}")
        
        # ... 其他处理逻辑
        
    except Exception as e:
        logger.error(f"处理失败: {str(e)}", exc_info=True)
        # ...
```

#### 3.2.3 改造vanna相关代码

由于vanna使用print方式，创建简单的适配器：

```python
# core/logging/vanna_adapter.py
from core.logging import get_vanna_logger

class VannaLogAdapter:
    """Vanna日志适配器 - 将print转换为logger调用"""
    
    def __init__(self, logger_name: str = "VannaBase"):
        self.logger = get_vanna_logger(logger_name)
    
    def log(self, message: str):
        """替换vanna的log方法"""
        # 根据内容判断日志级别
        message_lower = message.lower()
        if any(keyword in message_lower for keyword in ['error', 'exception', 'fail']):
            self.logger.error(message)
        elif any(keyword in message_lower for keyword in ['warning', 'warn']):
            self.logger.warning(message)
        else:
            self.logger.info(message)

# 使用装饰器改造vanna实例
def enhance_vanna_logging(vanna_instance):
    """增强vanna实例的日志功能"""
    adapter = VannaLogAdapter(vanna_instance.__class__.__name__)
    
    # 替换log方法
    vanna_instance.log = adapter.log
    return vanna_instance

# 在vanna实例创建时使用
# core/vanna_llm_factory.py
from core.logging.vanna_adapter import enhance_vanna_logging

def create_vanna_instance():
    # 原有创建逻辑
    vn = VannaDefault(...)
    
    # 增强日志功能
    vn = enhance_vanna_logging(vn)
    
    return vn
```

### 3.3 第三阶段：workflow级别的时间统计

对于跨多个函数的执行时间统计，在关键业务节点手动记录：

```python
# data_pipeline/schema_workflow.py
import time
from core.logging import get_data_pipeline_logger

class SchemaWorkflowOrchestrator:
    def __init__(self, ...):
        self.logger = get_data_pipeline_logger("SchemaWorkflow")
    
    async def run_full_workflow(self):
        """执行完整工作流"""
        workflow_start = time.time()
        self.logger.info("🚀 开始执行完整的Schema工作流")
        
        try:
            # 步骤1：生成DDL和MD文件
            step1_start = time.time()
            self.logger.info("📝 步骤1: 开始生成DDL和MD文件")
            
            result1 = await self.generate_ddl_md()
            
            step1_time = time.time() - step1_start
            self.logger.info(f"✅ 步骤1完成，生成了{result1['ddl_count']}个DDL文件和{result1['md_count']}个MD文件，耗时: {step1_time:.2f}秒")
            
            # 步骤2：生成Question-SQL对
            step2_start = time.time()
            self.logger.info("❓ 步骤2: 开始生成Question-SQL对")
            
            result2 = await self.generate_qa_pairs()
            
            step2_time = time.time() - step2_start
            self.logger.info(f"✅ 步骤2完成，生成了{result2['qa_count']}个问答对，耗时: {step2_time:.2f}秒")
            
            # 步骤3：验证SQL
            step3_start = time.time()
            self.logger.info("🔍 步骤3: 开始验证SQL")
            
            result3 = await self.validate_sql()
            
            step3_time = time.time() - step3_start
            self.logger.info(f"✅ 步骤3完成，验证了{result3['validated_count']}个SQL，修复了{result3['fixed_count']}个，耗时: {step3_time:.2f}秒")
            
            # 步骤4：加载训练数据
            step4_start = time.time()
            self.logger.info("📚 步骤4: 开始加载训练数据")
            
            result4 = await self.load_training_data()
            
            step4_time = time.time() - step4_start
            self.logger.info(f"✅ 步骤4完成，加载了{result4['loaded_count']}个训练文件，耗时: {step4_time:.2f}秒")
            
            # 总结
            total_time = time.time() - workflow_start
            self.logger.info(f"🎉 完整工作流执行成功！总耗时: {total_time:.2f}秒")
            self.logger.info(f"   - DDL/MD生成: {step1_time:.2f}秒")
            self.logger.info(f"   - QA生成: {step2_time:.2f}秒")  
            self.logger.info(f"   - SQL验证: {step3_time:.2f}秒")
            self.logger.info(f"   - 数据加载: {step4_time:.2f}秒")
            
            return {
                "success": True,
                "total_time": total_time,
                "steps": {
                    "ddl_md": {"time": step1_time, "result": result1},
                    "qa_generation": {"time": step2_time, "result": result2},
                    "sql_validation": {"time": step3_time, "result": result3},
                    "data_loading": {"time": step4_time, "result": result4}
                }
            }
            
        except Exception as e:
            total_time = time.time() - workflow_start
            self.logger.error(f"❌ 工作流执行失败，耗时: {total_time:.2f}秒，错误: {str(e)}")
            raise
```

## 4. 实际使用示例

### 4.1 在citu_app.py中的使用（主要应用）

```python
# citu_app.py
from core.logging import initialize_logging, get_logger, set_log_context, clear_log_context
import uuid

# 应用启动时初始化
initialize_logging("config/logging_config.yaml")
app_logger = get_logger("CituApp", "default")

# API端点示例
@app.flask_app.route('/api/v0/ask_agent', methods=['POST'])
def ask_agent():
    logger = get_agent_logger("AskAgent")
    request_id = str(uuid.uuid4())[:8]
    
    try:
        data = request.json
        user_id = data.get('user_id')
        
        # 设置上下文（安全的，即使没有user_id）
        set_log_context(
            request_id=request_id,
            user_id=user_id or 'anonymous'
        )
        
        logger.info(f"开始处理请求")
        # ... 业务逻辑
        
        logger.info(f"请求处理成功")
        return success_response(...)
        
    except Exception as e:
        logger.error(f"请求处理失败: {str(e)}", exc_info=True)
        return error_response(...)
    finally:
        clear_log_context()
```

### 4.2 在data_pipeline中的使用

```python
# data_pipeline/ddl_generation/training_data_agent.py
from core.logging import get_data_pipeline_logger
import time

class SchemaTrainingDataAgent:
    def __init__(self, db_config, output_dir):
        self.logger = get_data_pipeline_logger("TrainingDataAgent")
        self.db_config = db_config
        self.output_dir = output_dir
        
    async def process_tables(self, table_list):
        """处理表列表"""
        start_time = time.time()
        self.logger.info(f"开始处理{len(table_list)}个表的训练数据生成")
        
        success_count = 0
        failed_tables = []
        
        for table in table_list:
            try:
                table_start = time.time()
                self.logger.debug(f"开始处理表: {table}")
                
                await self._process_single_table(table)
                
                table_time = time.time() - table_start
                self.logger.info(f"表 {table} 处理完成，耗时: {table_time:.2f}秒")
                success_count += 1
                
            except Exception as e:
                self.logger.error(f"表 {table} 处理失败: {str(e)}")
                failed_tables.append(table)
        
        total_time = time.time() - start_time
        self.logger.info(f"批量处理完成，成功: {success_count}个，失败: {len(failed_tables)}个，总耗时: {total_time:.2f}秒")
        
        if failed_tables:
            self.logger.warning(f"处理失败的表: {failed_tables}")
            
        return {
            "success_count": success_count,
            "failed_count": len(failed_tables),
            "failed_tables": failed_tables,
            "total_time": total_time
        }
```

### 4.3 在Agent中的使用（支持异步）

```python
# agent/citu_agent.py
from core.logging import get_agent_logger, alog_info, alog_error

class CituLangGraphAgent:
    def __init__(self):
        self.logger = get_agent_logger("CituAgent")
    
    async def process_question(self, question: str, session_id: str = None, user_id: str = None):
        """异步处理问题"""
        # 设置上下文（如果有的话）
        if user_id or session_id:
            set_log_context(user_id=user_id or 'anonymous', session_id=session_id or 'N/A')
        
        # 同步日志
        self.logger.info(f"开始处理问题: {question[:50]}...")
        
        try:
            # 异步日志
            await alog_info(self.logger, f"开始分类问题")
            
            # 业务逻辑
            result = await self._classify_question(question)
            
            await alog_info(self.logger, f"分类完成: {result.question_type}")
            
            return result
            
        except Exception as e:
            await alog_error(self.logger, f"处理失败: {str(e)}")
            raise
```

### 4.4 增强vanna日志

```python
# core/vanna_llm_factory.py
from core.logging.vanna_adapter import enhance_vanna_logging
from core.logging import get_vanna_logger

def create_vanna_instance():
    """创建增强了日志功能的vanna实例"""
    logger = get_vanna_logger("VannaFactory")
    logger.info("🧠 开始创建Vanna实例")
    
    try:
        # 原有创建逻辑
        vn = VannaDefault(
            config={
                'api_key': os.getenv('OPENAI_API_KEY'),
                'model': 'gpt-4'
            }
        )
        
        # 增强日志功能
        vn = enhance_vanna_logging(vn)
        
        logger.info("✅ Vanna实例创建成功")
        return vn
        
    except Exception as e:
        logger.error(f"❌ Vanna实例创建失败: {str(e)}")
        raise
```

## 5. 配置调优建议

### 5.1 开发环境配置

```yaml
# config/logging_config_dev.yaml
version: 1

global:
  base_level: DEBUG

default:
  level: DEBUG
  console:
    enabled: true
    level: DEBUG
  file:
    enabled: false  # 开发环境可以只用控制台

modules:
  data_pipeline:
    level: DEBUG
    console:
      enabled: true
      level: DEBUG
      format: "🔄 %(asctime)s [%(levelname)s] Pipeline: %(message)s"
    file:
      enabled: true
      level: DEBUG
      filename: "data_pipeline.log"
      
  agent:
    level: DEBUG
    console:
      enabled: true
      level: DEBUG
      format: "🤖 %(asctime)s [%(levelname)s] Agent: %(message)s"
```

### 5.2 生产环境配置

```yaml
# config/logging_config_prod.yaml
version: 1

global:
  base_level: INFO

default:
  level: INFO
  console:
    enabled: false  # 生产环境不输出到控制台
  file:
    enabled: true
    level: INFO
    rotation:
      enabled: true
      max_size: "100MB"
      backup_count: 20

modules:
  data_pipeline:
    level: INFO
    console:
      enabled: false
    file:
      enabled: true
      level: INFO
      filename: "data_pipeline.log"
      rotation:
        enabled: true
        max_size: "50MB"
        backup_count: 15
        
  langchain:
    level: ERROR  # 生产环境只记录错误
    console:
      enabled: false
    file:
      enabled: true
      level: ERROR
```

## 6. 注意事项

基于用户反馈，特别注意以下几点：

1. **上下文安全性**：即使没有用户信息，日志系统也能正常工作（使用默认值）
2. **降级策略**：当文件系统不可用时，自动降级到控制台输出
3. **异步支持**：在async函数中使用异步日志方法，避免阻塞
4. **主应用聚焦**：重点关注citu_app.py的集成，忽略flask_app.py和chainlit_app.py
5. **性能考虑**：保持原有的跨函数时间统计方式，不强制使用装饰器

## 7. 总结

这个精简实用的日志改造方案提供了：

1. **统一的日志管理**：类似Log4j的架构，单一配置文件管理所有日志
2. **模块化日志文件**：每个模块独立的日志文件，便于问题定位
3. **自动日志轮转**：使用RotatingFileHandler自动管理日志文件大小和数量
4. **灵活的配置**：支持不同环境的配置，控制台和文件输出可独立配置
5. **简单易用**：提供便捷的API，一行代码获取对应模块的logger
6. **性能友好**：手动记录关键节点时间，不影响整体性能
7. **技术栈兼容**：专门为vanna/langchain/langgraph设计适配器
8. **异步支持**：适配项目大量使用async/await的特点
9. **安全容错**：上下文信息可选，文件系统可降级

该方案专注核心功能，去掉了不必要的复杂性，是一个可以直接落地实施的实用设计。