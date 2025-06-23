import logging
import os
import sys
from datetime import datetime
from typing import Optional

def setup_logging(verbose: bool = False, log_file: Optional[str] = None, log_dir: Optional[str] = None):
    """
    设置日志系统
    
    Args:
        verbose: 是否启用详细日志
        log_file: 日志文件名
        log_dir: 日志目录
    """
    # 确定日志级别
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # 创建根logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # 清除已有的处理器
    root_logger.handlers.clear()
    
    # 设置日志格式
    console_format = "%(asctime)s [%(levelname)s] %(message)s"
    file_format = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(console_format, datefmt=date_format)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # 文件处理器（如果指定）
    if log_file:
        # 确定日志文件路径
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, log_file)
        else:
            log_path = log_file
        
        # 添加时间戳到日志文件名
        base_name, ext = os.path.splitext(log_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = f"{base_name}_{timestamp}{ext}"
        
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter(file_format, datefmt=date_format)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
        
        # 记录日志文件位置
        root_logger.info(f"日志文件: {os.path.abspath(log_path)}")
    
    # 设置schema_tools模块的日志级别
    schema_tools_logger = logging.getLogger("schema_tools")
    schema_tools_logger.setLevel(log_level)
    
    # 设置第三方库的日志级别（避免过多输出）
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    # 返回schema_tools的logger
    return schema_tools_logger

class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器（用于控制台）"""
    
    # ANSI颜色代码
    COLORS = {
        'DEBUG': '\033[36m',     # 青色
        'INFO': '\033[32m',      # 绿色
        'WARNING': '\033[33m',   # 黄色
        'ERROR': '\033[31m',     # 红色
        'CRITICAL': '\033[35m',  # 紫色
    }
    RESET = '\033[0m'
    
    def format(self, record):
        # 保存原始级别名
        levelname = record.levelname
        
        # 添加颜色
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"
        
        # 格式化消息
        formatted = super().format(record)
        
        # 恢复原始级别名
        record.levelname = levelname
        
        return formatted

def get_colored_console_handler(level=logging.INFO):
    """获取带颜色的控制台处理器"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    
    # 检查是否支持颜色（Windows需要特殊处理）
    if sys.platform == "win32":
        try:
            import colorama
            colorama.init()
            use_color = True
        except ImportError:
            use_color = False
    else:
        # Unix/Linux/Mac通常支持ANSI颜色
        use_color = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    
    if use_color:
        formatter = ColoredFormatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    
    handler.setFormatter(formatter)
    return handler

class TableProcessingLogger:
    """表处理专用日志器"""
    
    def __init__(self, logger_name: str = "schema_tools.TableProcessor"):
        self.logger = logging.getLogger(logger_name)
        self.current_table = None
        self.start_time = None
    
    def start_table(self, table_name: str):
        """开始处理表"""
        self.current_table = table_name
        self.start_time = datetime.now()
        self.logger.info(f"{'='*60}")
        self.logger.info(f"开始处理表: {table_name}")
        self.logger.info(f"开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    def end_table(self, success: bool = True):
        """结束处理表"""
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()
            status = "成功" if success else "失败"
            self.logger.info(f"处理{status}，耗时: {duration:.2f}秒")
        self.logger.info(f"{'='*60}\n")
        self.current_table = None
        self.start_time = None
    
    def log_step(self, step_name: str, message: str = None):
        """记录处理步骤"""
        if message:
            self.logger.info(f"  [{step_name}] {message}")
        else:
            self.logger.info(f"  [{step_name}]")
    
    def log_warning(self, message: str):
        """记录警告"""
        self.logger.warning(f"  ⚠ {message}")
    
    def log_error(self, message: str):
        """记录错误"""
        self.logger.error(f"  ✗ {message}")