# 给dataops对话助手返回结果
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