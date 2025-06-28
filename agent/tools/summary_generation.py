# agent/tools/summary_generation.py
from langchain.tools import tool
from typing import Dict, Any
import pandas as pd
from common.vanna_instance import get_vanna_instance
from core.logging import get_agent_logger

# Initialize logger
logger = get_agent_logger("SummaryGeneration")

@tool
def generate_summary(question: str, query_result: Dict[str, Any], sql: str) -> Dict[str, Any]:
    """
    为查询结果生成自然语言摘要。
    
    Args:
        question: 原始问题
        query_result: 查询结果数据
        sql: 执行的SQL语句
        
    Returns:
        包含摘要结果的字典，格式：
        {
            "success": bool,
            "summary": str,
            "error": str或None
        }
    """
    try:
        logger.info(f"开始生成摘要，问题: {question}")
        
        if not query_result or not query_result.get("rows"):
            return {
                "success": True,
                "summary": "查询执行完成，但没有找到符合条件的数据。",
                "message": "无数据摘要"
            }
        
        # 重构DataFrame用于摘要生成
        df = _reconstruct_dataframe(query_result)
        
        if df is None or df.empty:
            return {
                "success": True,
                "summary": "查询执行完成，但数据为空。",
                "message": "空数据摘要"
            }
        
        # 调用Vanna生成摘要（thinking内容已在base_llm_chat.py中统一处理）
        vn = get_vanna_instance()
        summary = vn.generate_summary(question=question, df=df)
        
        if summary is None:
            # 生成默认摘要
            summary = _generate_default_summary(question, query_result, sql)
        
        logger.info(f"摘要生成成功: {summary[:100]}...")
        
        return {
            "success": True,
            "summary": summary,
            "message": "摘要生成成功"
        }
        
    except Exception as e:
        logger.error(f"摘要生成异常: {str(e)}")
        
        # 生成备用摘要
        fallback_summary = _generate_fallback_summary(question, query_result, sql)
        
        return {
            "success": True,  # 即使异常也返回成功，因为有备用摘要
            "summary": fallback_summary,
            "message": f"使用备用摘要生成: {str(e)}"
        }

def _reconstruct_dataframe(query_result: Dict[str, Any]) -> pd.DataFrame:
    """从查询结果重构DataFrame"""
    try:
        rows = query_result.get("rows", [])
        columns = query_result.get("columns", [])
        
        if not rows or not columns:
            return pd.DataFrame()
        
        return pd.DataFrame(rows, columns=columns)
        
    except Exception as e:
        logger.warning(f"DataFrame重构失败: {str(e)}")
        return pd.DataFrame()

def _generate_default_summary(question: str, query_result: Dict[str, Any], sql: str) -> str:
    """生成默认摘要"""
    try:
        row_count = query_result.get("row_count", 0)
        columns = query_result.get("columns", [])
        
        if row_count == 0:
            return "查询执行完成，但没有找到符合条件的数据。"
        
        summary_parts = [f"根据您的问题「{question}」，查询返回了 {row_count} 条记录。"]
        
        if columns:
            summary_parts.append(f"数据包含以下字段：{', '.join(columns)}。")
        
        return ' '.join(summary_parts)
        
    except Exception:
        return f"查询执行完成，共返回 {query_result.get('row_count', 0)} 条记录。"

def _generate_fallback_summary(question: str, query_result: Dict[str, Any], sql: str) -> str:
    """生成备用摘要"""
    row_count = query_result.get("row_count", 0)
    
    if row_count == 0:
        return "查询执行完成，但没有找到符合条件的数据。请检查查询条件是否正确。"
    
    return f"查询执行成功，共返回 {row_count} 条记录。数据已准备完毕，您可以查看详细结果。"