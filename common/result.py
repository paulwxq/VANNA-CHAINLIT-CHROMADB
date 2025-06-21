# 给dataops对话助手返回结果
from datetime import datetime
from .messages import MessageTemplate, ErrorType

def success(data=None, message="操作成功", code=200):
    """
    Return a standardized success response
    
    Args:
        data: The data to return
        message: A success message
        code: HTTP status code
        
    Returns:
        dict: A standardized success response
    """
    return {
        "code": code,
        "success": True,
        "message": message,
        "data": data
    }

def failed(message="操作失败", code=500, data=None):
    """
    Return a standardized error response
    
    Args:
        message: An error message
        code: HTTP status code
        data: Optional data to return
        
    Returns:
        dict: A standardized error response
    """
    return {
        "code": code,
        "success": False,
        "message": message,
        "data": data
    }

# ===== 标准化响应方法 =====

def success_response(response_text=None, data=None, message=MessageTemplate.SUCCESS, code=200):
    """
    标准化成功响应，将具体内容放在data.response中
    
    Args:
        response_text: 用户看到的具体内容
        data: 其他业务数据
        message: 高层级描述信息
        code: HTTP状态码
        
    Returns:
        dict: 标准化成功响应
    """
    response_data = data or {}
    if response_text is not None:
        response_data["response"] = response_text
    
    return {
        "code": code,
        "success": True,
        "message": message,
        "data": response_data
    }

def error_response(response_text, error_type=None, message=MessageTemplate.PROCESSING_FAILED, 
                  code=500, data=None, can_retry=None):
    """
    标准化错误响应，将具体错误信息放在data.response中
    
    Args:
        response_text: 用户看到的具体错误信息
        error_type: 错误类型标识
        message: 高层级描述信息
        code: HTTP状态码
        data: 其他业务数据
        can_retry: 是否可以重试
        
    Returns:
        dict: 标准化错误响应
    """
    response_data = data or {}
    response_data["response"] = response_text
    response_data["timestamp"] = datetime.now().isoformat()
    
    if error_type:
        response_data["error_type"] = error_type
    if can_retry is not None:
        response_data["can_retry"] = can_retry
    
    return {
        "code": code,
        "success": False,
        "message": message,
        "data": response_data
    }

# ===== Ask Agent API 专用响应方法 =====

def agent_success_response(response_type, session_id=None, execution_path=None, 
                          classification_info=None, agent_version="langgraph_v1", **kwargs):
    """
    Ask Agent API 成功响应格式
    
    Args:
        response_type: 响应类型 ("DATABASE" 或 "CHAT")
        session_id: 会话ID
        execution_path: 执行路径
        classification_info: 分类信息
        agent_version: Agent版本
        **kwargs: 其他字段 (response, sql, query_result, summary等)
        
    Returns:
        dict: Ask Agent API 标准成功响应
    """
    data = {
        "type": response_type,
        "session_id": session_id,
        "execution_path": execution_path or [],
        "classification_info": classification_info or {},
        "agent_version": agent_version,
        "timestamp": datetime.now().isoformat()
    }
    
    # 添加其他字段
    for key, value in kwargs.items():
        if value is not None:  # 只添加非None值
            data[key] = value
    
    return {
        "code": 200,
        "success": True,
        "message": MessageTemplate.SUCCESS,
        "data": data
    }

def agent_error_response(response_text, error_type=None, message=MessageTemplate.PROCESSING_FAILED,
                        code=500, session_id=None, execution_path=None, 
                        classification_info=None, agent_version="langgraph_v1", **kwargs):
    """
    Ask Agent API 错误响应格式
    
    Args:
        response_text: 用户看到的具体错误信息
        error_type: 错误类型标识
        message: 高层级描述信息
        code: HTTP状态码
        session_id: 会话ID
        execution_path: 执行路径
        classification_info: 分类信息
        agent_version: Agent版本
        **kwargs: 其他错误相关字段
        
    Returns:
        dict: Ask Agent API 标准错误响应
    """
    data = {
        "response": response_text,
        "session_id": session_id,
        "execution_path": execution_path or [],
        "classification_info": classification_info or {},
        "agent_version": agent_version,
        "timestamp": datetime.now().isoformat()
    }
    
    if error_type:
        data["error_type"] = error_type
    
    # 添加其他错误相关字段
    for key, value in kwargs.items():
        if value is not None:
            data[key] = value
    
    return {
        "code": code,
        "success": False,
        "message": message,
        "data": data
    }

# ===== 健康检查专用响应方法 =====

def health_success_response(status="healthy", test_result=True, **kwargs):
    """
    健康检查成功响应格式
    
    Args:
        status: 健康状态
        test_result: 测试结果
        **kwargs: 其他健康检查数据
        
    Returns:
        dict: 健康检查成功响应
    """
    data = {
        "status": status,
        "test_result": test_result,
        "response": "Agent健康检查完成",
        "timestamp": datetime.now().isoformat()
    }
    
    # 添加其他字段
    for key, value in kwargs.items():
        if value is not None:
            data[key] = value
    
    return {
        "code": 200,
        "success": True,
        "message": MessageTemplate.SUCCESS,
        "data": data
    }

def health_error_response(status="unhealthy", test_result=False, message=MessageTemplate.SERVICE_UNAVAILABLE, **kwargs):
    """
    健康检查错误响应格式
    
    Args:
        status: 健康状态
        test_result: 测试结果
        message: 高层级错误描述
        **kwargs: 其他健康检查数据
        
    Returns:
        dict: 健康检查错误响应
    """
    data = {
        "status": status,
        "test_result": test_result,
        "response": "部分组件异常" if status == "degraded" else "Agent健康检查失败",
        "timestamp": datetime.now().isoformat()
    }
    
    # 添加其他字段
    for key, value in kwargs.items():
        if value is not None:
            data[key] = value
    
    return {
        "code": 503,
        "success": False,
        "message": message,
        "data": data
    }

# ===== 便捷方法 =====

def bad_request_response(response_text, missing_params=None):
    """请求参数错误响应"""
    data = {}
    if missing_params:
        data["missing_params"] = missing_params
    
    return error_response(
        response_text=response_text,
        error_type=ErrorType.MISSING_REQUIRED_PARAMS,
        message=MessageTemplate.BAD_REQUEST,
        code=400,
        data=data
    )

def validation_failed_response(response_text):
    """参数验证失败响应"""
    return error_response(
        response_text=response_text,
        error_type=ErrorType.INVALID_PARAMS,
        message=MessageTemplate.VALIDATION_FAILED,
        code=422
    )

def internal_error_response(response_text, can_retry=True):
    """系统内部错误响应"""
    return error_response(
        response_text=response_text,
        error_type=ErrorType.DATABASE_ERROR,
        message=MessageTemplate.INTERNAL_ERROR,
        code=500,
        can_retry=can_retry
    )

def service_unavailable_response(response_text, can_retry=True):
    """服务不可用响应"""
    return error_response(
        response_text=response_text,
        error_type=ErrorType.AGENT_INITIALIZATION_FAILED,
        message=MessageTemplate.SERVICE_UNAVAILABLE,
        code=503,
        can_retry=can_retry
    ) 