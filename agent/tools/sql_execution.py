# agent/tools/sql_execution.py
from langchain.tools import tool
from typing import Dict, Any
import pandas as pd
import time
import functools
from common.vanna_instance import get_vanna_instance
from app_config import API_MAX_RETURN_ROWS

def retry_on_failure(max_retries: int = 2, delay: float = 1.0, backoff_factor: float = 2.0):
    """
    重试装饰器
    
    Args:
        max_retries: 最大重试次数
        delay: 初始延迟时间（秒）
        backoff_factor: 退避因子（指数退避）
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries <= max_retries:
                try:
                    result = func(*args, **kwargs)
                    
                    # 如果函数返回结果包含 can_retry 标识，检查是否需要重试
                    if isinstance(result, dict) and result.get('can_retry', False) and not result.get('success', True):
                        if retries < max_retries:
                            retries += 1
                            wait_time = delay * (backoff_factor ** (retries - 1))
                            print(f"[RETRY] {func.__name__} 执行失败，等待 {wait_time:.1f} 秒后重试 ({retries}/{max_retries})")
                            time.sleep(wait_time)
                            continue
                    
                    return result
                    
                except Exception as e:
                    retries += 1
                    if retries <= max_retries:
                        wait_time = delay * (backoff_factor ** (retries - 1))
                        print(f"[RETRY] {func.__name__} 异常: {str(e)}, 等待 {wait_time:.1f} 秒后重试 ({retries}/{max_retries})")
                        time.sleep(wait_time)
                    else:
                        print(f"[RETRY] {func.__name__} 达到最大重试次数 ({max_retries})，抛出异常")
                        raise
            
            # 不应该到达这里，但为了安全性
            return result
            
        return wrapper
    return decorator

@tool
@retry_on_failure(max_retries=2)
def execute_sql(sql: str, max_rows: int = None) -> Dict[str, Any]:
    """
    执行SQL查询并返回结果。
    
    Args:
        sql: 要执行的SQL查询语句
        max_rows: 最大返回行数，默认使用API_MAX_RETURN_ROWS配置
        
    Returns:
        包含查询结果的字典，格式：
        {
            "success": bool,
            "data_result": dict或None,  # 注意：工具内部仍使用data_result，但会被Agent重命名为query_result
            "error": str或None,
            "can_retry": bool
        }
    """
    # 设置默认的最大返回行数，与ask()接口保持一致
    DEFAULT_MAX_RETURN_ROWS = 200
    if max_rows is None:
        max_rows = API_MAX_RETURN_ROWS if API_MAX_RETURN_ROWS is not None else DEFAULT_MAX_RETURN_ROWS
    try:
        print(f"[TOOL:execute_sql] 开始执行SQL: {sql[:100]}...")
        
        vn = get_vanna_instance()
        df = vn.run_sql(sql)
        
        if df is None:
            return {
                "success": False,
                "data_result": None,
                "error": "SQL执行返回空结果",
                "error_type": "no_result",
                "can_retry": False
            }
        
        if not isinstance(df, pd.DataFrame):
            return {
                "success": False,
                "data_result": None,
                "error": f"SQL执行返回非DataFrame类型: {type(df)}",
                "error_type": "invalid_result_type",
                "can_retry": False
            }
        
        if df.empty:
            return {
                "success": True,
                "data_result": {
                    "rows": [],
                    "columns": [],
                    "row_count": 0,
                    "message": "查询执行成功，但没有找到符合条件的数据"
                },
                "message": "查询无结果"
            }
        
        # 处理数据结果
        total_rows = len(df)
        limited_df = df.head(max_rows)
        
        # 转换为字典格式并处理数据类型
        rows = _process_dataframe_rows(limited_df.to_dict(orient="records"))
        columns = list(df.columns)
        
        print(f"[TOOL:execute_sql] 查询成功，返回 {len(rows)} 行数据")
        
        result = {
            "success": True,
            "data_result": {
                "rows": rows,
                "columns": columns,
                "row_count": len(rows),
                "total_row_count": total_rows,
                "is_limited": total_rows > max_rows
            },
            "message": f"查询成功，共 {total_rows} 行数据"
        }
        
        if total_rows > max_rows:
            result["message"] += f"，已限制显示前 {max_rows} 行"
        
        return result
        
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] SQL执行异常: {error_msg}")
        
        return {
            "success": False,
            "data_result": None,
            "error": f"SQL执行失败: {error_msg}",
            "error_type": _analyze_sql_error(error_msg),
            "can_retry": "timeout" in error_msg.lower() or "connection" in error_msg.lower(),
            "sql": sql
        }

def _process_dataframe_rows(rows: list) -> list:
    """处理DataFrame行数据，确保JSON序列化兼容"""
    processed_rows = []
    
    for row in rows:
        processed_row = {}
        for key, value in row.items():
            if pd.isna(value):
                processed_row[key] = None
            elif isinstance(value, (pd.Timestamp, pd.Timedelta)):
                processed_row[key] = str(value)
            elif isinstance(value, (int, float, str, bool)):
                processed_row[key] = value
            else:
                processed_row[key] = str(value)
        
        processed_rows.append(processed_row)
    
    return processed_rows

def _analyze_sql_error(error_msg: str) -> str:
    """分析SQL错误类型"""
    error_msg_lower = error_msg.lower()
    
    if "syntax error" in error_msg_lower or "syntaxerror" in error_msg_lower:
        return "syntax_error"
    elif "table" in error_msg_lower and ("not found" in error_msg_lower or "doesn't exist" in error_msg_lower):
        return "table_not_found"
    elif "column" in error_msg_lower and ("not found" in error_msg_lower or "unknown" in error_msg_lower):
        return "column_not_found"
    elif "timeout" in error_msg_lower:
        return "timeout"
    elif "connection" in error_msg_lower:
        return "connection_error"
    elif "permission" in error_msg_lower or "access denied" in error_msg_lower:
        return "permission_error"
    else:
        return "unknown_error"