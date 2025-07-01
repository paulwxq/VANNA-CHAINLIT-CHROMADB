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
            import sys
            sys.stderr.write(f"[WARNING] 配置文件 {config_path} 未找到，使用默认配置\n")
            return self._get_default_config()
        except Exception as e:
            import sys
            sys.stderr.write(f"[ERROR] 加载配置文件失败: {e}，使用默认配置\n")
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
            os.makedirs(self.base_log_dir, exist_ok=True)
            self._fallback_to_console = False
        except Exception as e:
            import sys
            sys.stderr.write(f"[WARNING] 无法创建日志目录 {self.base_log_dir}，将只使用控制台输出: {e}\n")
            self._fallback_to_console = True
    
    def _configure_root_logger(self):
        """配置根日志器"""
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, self.config['global']['base_level'].upper()))
    
    def _configure_logger(self, logger: logging.Logger, module: str):
        """配置具体的logger"""
        # 如果配置未初始化，使用默认的控制台日志配置
        if self.config is None:
            logger.setLevel(logging.INFO)
            if not logger.handlers:
                console_handler = logging.StreamHandler()
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
                console_handler.setFormatter(formatter)
                logger.addHandler(console_handler)
                logger.propagate = False
            return
            
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
                import sys
                sys.stderr.write(f"[WARNING] 无法创建文件处理器: {e}\n")
                # 如果文件处理器创建失败，标记降级
                self._fallback_to_console = True
    
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