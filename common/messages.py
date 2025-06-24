class MessageTemplate:
    """标准化消息模板常量"""
    
    # 成功场景
    SUCCESS = "操作成功"
    
    # 客户端错误场景 (4xx)
    BAD_REQUEST = "请求参数错误"
    VALIDATION_FAILED = "参数验证失败"
    NOT_FOUND = "资源未找到"
    
    # 服务端错误场景 (5xx)
    INTERNAL_ERROR = "系统内部错误"
    SERVICE_UNAVAILABLE = "服务暂时不可用"
    
    # 业务处理场景
    QUERY_FAILED = "查询失败"
    GENERATION_FAILED = "生成失败"
    PROCESSING_FAILED = "处理失败"

class ErrorType:
    """错误类型标识常量"""
    
    # Agent相关错误
    AGENT_INITIALIZATION_FAILED = "agent_initialization_failed"
    REQUEST_PROCESSING_FAILED = "request_processing_failed"
    
    # SQL相关错误
    SQL_GENERATION_FAILED = "sql_generation_failed"
    SQL_EXECUTION_FAILED = "sql_execution_failed"
    
    # 参数相关错误
    MISSING_REQUIRED_PARAMS = "missing_required_params"
    INVALID_PARAMS = "invalid_params"
    
    # 资源相关错误
    RESOURCE_NOT_FOUND = "resource_not_found"
    
    # 系统错误
    DATABASE_ERROR = "database_error"
    NETWORK_ERROR = "network_error" 