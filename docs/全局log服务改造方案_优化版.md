# 项目日志系统改造设计方案（优化版）

## 1. 整体设计理念

基于您的需求和反馈，设计一套统一的日志服务，专注核心功能：
- 统一的日志级别管理（info/error/debug/warning）
- 可配置的日志输出路径
- 支持控制台和文件输出
- 4个模块独立日志文件（app、agent、vanna、data_pipeline）
- 自动日志轮转和清理
- 灵活的上下文管理

## 2. 核心架构设计

### 2.1 精简的日志服务层次结构

```
项目根目录/
├── core/
│   └── logging/
│       ├── __init__.py           # 日志服务入口
│       └── log_manager.py        # 核心日志管理器
├── logs/                         # 日志文件目录
│   ├── app.log                  # 主应用日志（citu_app.py和通用模块）
│   ├── agent.log                # agent模块日志
│   ├── vanna.log                # vanna相关模块日志
│   └── data_pipeline.log        # data_pipeline模块日志
└── config/
    └── logging_config.yaml       # 日志配置文件
```

### 2.2 核心日志管理器设计

```python
# core/logging/log_manager.py
import logging
import logging.handlers
import os
from typing import Dict, Optional
from pathlib import Path
import yaml
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
    _fallback_to_console = False  # 标记是否降级到控制台
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.config = None
            self.base_log_dir = Path("logs")
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
    
    def set_context(self, **kwargs):
        """设置日志上下文（可选）"""
        ctx = log_context.get()
        ctx.update(kwargs)
        log_context.set(ctx)
    
    def clear_context(self):
        """清除日志上下文"""
        log_context.set({})
    
    def _load_config(self, config_path: str) -> dict:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"[WARNING] 配置文件 {config_path} 未找到，使用默认配置")
            return self._get_default_config()
        except Exception as e:
            print(f"[ERROR] 加载配置文件失败: {e}，使用默认配置")
            return self._get_default_config()
    
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
    
    def _setup_base_directory(self):
        """创建日志目录（带降级策略）"""
        try:
            self.base_log_dir.mkdir(parents=True, exist_ok=True)
            self._fallback_to_console = False
        except Exception as e:
            print(f"[WARNING] 无法创建日志目录 {self.base_log_dir}，将只使用控制台输出: {e}")
            self._fallback_to_console = True
    
    def _configure_root_logger(self):
        """配置根日志器"""
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, self.config['global']['base_level'].upper()))
    
    def _configure_logger(self, logger: logging.Logger, module: str):
        """配置具体的logger"""
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
```

### 2.3 统一日志接口

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

def get_app_logger(name: str) -> logging.Logger:
    """获取app模块logger"""
    return get_logger(name, "app")

# 上下文管理便捷方法
def set_log_context(**kwargs):
    """设置日志上下文（可选）
    示例: set_log_context(user_id='user123', session_id='sess456')
    """
    _log_manager.set_context(**kwargs)

def clear_log_context():
    """清除日志上下文"""
    _log_manager.clear_context()
```

### 2.4 日志配置文件

```yaml
# config/logging_config.yaml
version: 1

# 全局配置
global:
  base_level: INFO
  
# 默认配置（用于app.log）
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
    format: "%(asctime)s [%(levelname)s] [%(name)s] [user:%(user_id)s] [session:%(session_id)s] %(filename)s:%(lineno)d - %(message)s"
    rotation:
      enabled: true
      max_size: "50MB"
      backup_count: 10

# 模块特定配置
modules:
  app:
    level: INFO
    console:
      enabled: true
      level: INFO
      format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    file:
      enabled: true
      level: DEBUG
      filename: "app.log"
      format: "%(asctime)s [%(levelname)s] [%(name)s] [user:%(user_id)s] [session:%(session_id)s] %(filename)s:%(lineno)d - %(message)s"
      rotation:
        enabled: true
        max_size: "50MB"
        backup_count: 10
  
  data_pipeline:
    level: DEBUG
    console:
      enabled: true
      level: INFO
      format: "%(asctime)s [%(levelname)s] Pipeline: %(message)s"
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
      format: "%(asctime)s [%(levelname)s] Agent: %(message)s"
    file:
      enabled: true
      level: DEBUG
      filename: "agent.log"
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
      format: "%(asctime)s [%(levelname)s] Vanna: %(message)s"
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

3. **集成到citu_app.py**
   ```python
   # 在citu_app.py的开头添加
   from core.logging import initialize_logging, get_app_logger, set_log_context, clear_log_context
   
   # 初始化日志系统
   initialize_logging("config/logging_config.yaml")
   app_logger = get_app_logger("CituApp")
   
   # 在Flask应用配置后集成
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

#### 3.2.1 改造Agent模块

```python
# 替换所有print语句
# agent/citu_agent.py
from core.logging import get_agent_logger

class CituLangGraphAgent:
    def __init__(self):
        self.logger = get_agent_logger("CituAgent")
        self.logger.info("LangGraph Agent初始化")
        # 直接替换原有的 print 语句
```

#### 3.2.2 改造data_pipeline模块（直接改造，无需兼容）

```python
# 方案一：完全删除 data_pipeline/utils/logger.py
# 直接在所有使用位置导入新的日志系统

# 方案二：保留文件但清空实现
# data_pipeline/utils/logger.py
"""
原有日志系统已被新的统一日志系统替代
保留此文件仅为避免导入错误
"""
from core.logging import get_data_pipeline_logger

def setup_logging(verbose: bool = False, log_file: str = None, log_dir: str = None):
    """函数保留以避免调用错误，但不做任何事"""
    pass

def get_logger(name: str = "DataPipeline"):
    """直接返回新的logger"""
    return get_data_pipeline_logger(name)

# 在各个文件中直接使用新的logger
# data_pipeline/schema_workflow.py
from core.logging import get_data_pipeline_logger

class SchemaWorkflowOrchestrator:
    def __init__(self, ...):
        # 原来: self.logger = logging.getLogger("schema_tools.SchemaWorkflowOrchestrator") 
        # 现在: 直接使用新系统
        self.logger = get_data_pipeline_logger("SchemaWorkflow")

# data_pipeline/qa_generation/qs_agent.py
from core.logging import get_data_pipeline_logger

class QuestionSQLGenerationAgent:
    def __init__(self, ...):
        # 原来: self.logger = logging.getLogger("schema_tools.QSAgent")
        # 现在: 直接替换
        self.logger = get_data_pipeline_logger("QSAgent")
```

#### 3.2.3 改造Vanna相关代码

```python
# customllm/base_llm_chat.py
from core.logging import get_vanna_logger

class BaseLLMChat(VannaBase, ABC):
    def __init__(self, config=None):
        VannaBase.__init__(self, config=config)
        self.logger = get_vanna_logger("BaseLLMChat")
        
        # 替换原有的print
        self.logger.info("传入的 config 参数如下：")
        for key, value in self.config.items():
            self.logger.info(f"  {key}: {value}")
```

### 3.3 第三阶段：通用模块改造

```python
# common/qa_feedback_manager.py
from core.logging import get_app_logger

class QAFeedbackManager:
    def __init__(self, vanna_instance=None):
        self.logger = get_app_logger("QAFeedbackManager")
        # 替换原有的print
        self.logger.info("QAFeedbackManager 初始化")
```

## 4. 实际使用示例

### 4.1 在citu_app.py中的使用

```python
# citu_app.py
from core.logging import initialize_logging, get_app_logger, get_agent_logger, set_log_context
import uuid

# 应用启动时初始化
initialize_logging("config/logging_config.yaml")
app_logger = get_app_logger("CituApp")

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
        
        logger.info("开始处理请求")
        # ... 业务逻辑
        
        logger.info("请求处理成功")
        return success_response(...)
        
    except Exception as e:
        logger.error(f"请求处理失败: {str(e)}", exc_info=True)
        return error_response(...)
    finally:
        clear_log_context()
```

### 4.2 在data_pipeline中的使用

```python
# data_pipeline/schema_workflow.py
import time
from core.logging import get_data_pipeline_logger

class SchemaWorkflowOrchestrator:
    def __init__(self, ...):
        self.logger = get_data_pipeline_logger("SchemaWorkflow")
    
    async def execute_complete_workflow(self):
        """执行完整工作流"""
        workflow_start = time.time()
        self.logger.info("开始执行完整的Schema工作流")
        
        # 保持原有的跨函数时间统计逻辑
        try:
            # 步骤1
            step1_start = time.time()
            self.logger.info("步骤1: 开始生成DDL和MD文件")
            # ... 执行逻辑
            step1_time = time.time() - step1_start
            self.logger.info(f"步骤1完成，耗时: {step1_time:.2f}秒")
            
            # 继续其他步骤...
            
        except Exception as e:
            self.logger.error(f"工作流执行失败: {str(e)}", exc_info=True)
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
```

## 6. 注意事项

1. **上下文安全性**：即使没有用户信息，日志系统也能正常工作（使用默认值）
2. **降级策略**：当文件系统不可用时，自动降级到控制台输出
3. **模块分离**：4个模块（app/agent/vanna/data_pipeline）的日志完全分离
4. **直接改造**：data_pipeline模块直接使用新系统，无需兼容
5. **性能考虑**：保持原有的跨函数时间统计方式

## 7. 总结

这个优化后的方案特点：

1. **4个模块清晰分离**：app、agent、vanna、data_pipeline各自独立日志文件
2. **直接改造策略**：所有模块（包括data_pipeline）直接使用新系统，不考虑兼容性
3. **移除冗余特性**：去掉异步支持、原有标签等，专注核心功能
4. **简单统一的API**：每个模块都有专门的获取logger方法

该方案已根据您的反馈完全优化，可以直接落地实施。 