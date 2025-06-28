# agent/tools/sql_generation.py
from langchain.tools import tool
from typing import Dict, Any
from common.vanna_instance import get_vanna_instance
from core.logging import get_agent_logger

# Initialize logger
logger = get_agent_logger("SQLGeneration")

@tool
def generate_sql(question: str, allow_llm_to_see_data: bool = True) -> Dict[str, Any]:
    """
    将自然语言问题转换为SQL查询。
    
    Args:
        question: 需要转换为SQL的自然语言问题
        allow_llm_to_see_data: 是否允许LLM查看数据，默认True
    
    Returns:
        包含SQL生成结果的字典，格式：
        {
            "success": bool,
            "sql": str或None,
            "error": str或None,
            "can_retry": bool
        }
    """
    try:
        logger.info(f"开始生成SQL: {question}")
        
        vn = get_vanna_instance()
        sql = vn.generate_sql(question=question, allow_llm_to_see_data=allow_llm_to_see_data)
        
        if sql is None:
            # 检查是否有LLM解释性文本（已在base_llm_chat.py中处理thinking内容）
            explanation = getattr(vn, 'last_llm_explanation', None)
            if explanation:
                return {
                    "success": False,
                    "sql": None,
                    "error": explanation,
                    "error_type": "generation_failed_with_explanation",
                    "can_retry": True
                }
            else:
                return {
                    "success": False,
                    "sql": None,
                    "error": "无法生成SQL查询，可能是问题描述不够明确或数据表结构不匹配",
                    "error_type": "generation_failed",
                    "can_retry": True
                }
        
        # 检查SQL质量
        sql_clean = sql.strip()
        if not sql_clean:
            return {
                "success": False,
                "sql": sql,
                "error": "生成的SQL为空",
                "error_type": "empty_sql",
                "can_retry": True
            }
        
        logger.info(f"成功生成SQL: {sql}")
        return {
            "success": True,
            "sql": sql,
            "error": None,
            "message": "SQL生成成功"
        }
        
    except Exception as e:
        logger.error(f"SQL生成异常: {str(e)}")
        return {
            "success": False,
            "sql": None,
            "error": f"SQL生成过程异常: {str(e)}",
            "error_type": "exception",
            "can_retry": True
        }