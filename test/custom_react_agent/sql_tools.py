"""
数据库查询相关的工具集
"""
import re
import json
import logging
from langchain_core.tools import tool
from pydantic.v1 import BaseModel, Field
from typing import List, Dict, Any
import pandas as pd

logger = logging.getLogger(__name__)

# --- Pydantic Schema for Tool Arguments ---

class GenerateSqlArgs(BaseModel):
    """Input schema for the generate_sql tool."""
    question: str = Field(description="The user's question to be converted to SQL.")
    history_messages: List[Dict[str, Any]] = Field(
        default=[],
        description="The conversation history messages for context."
    )

# --- Tool Functions ---

@tool(args_schema=GenerateSqlArgs)
def generate_sql(question: str, history_messages: List[Dict[str, Any]] = None) -> str:
    """
    Generates an SQL query based on the user's question and the conversation history.
    """
    logger.info(f"🔧 [Tool] generate_sql - Question: '{question}'")
    
    if history_messages is None:
        history_messages = []
    
    logger.info(f"   History contains {len(history_messages)} messages.")

    # Combine history and the current question to form a rich prompt
    history_str = "\n".join([f"{msg['type']}: {msg.get('content', '') or ''}" for msg in history_messages])
    enriched_question = f"""Based on the following conversation history:
---
{history_str}
---

Please provide an SQL query that answers this specific question: {question}"""

    try:
        from common.vanna_instance import get_vanna_instance
        vn = get_vanna_instance()
        sql = vn.generate_sql(enriched_question)

        if not sql or sql.strip() == "":
            if hasattr(vn, 'last_llm_explanation') and vn.last_llm_explanation:
                error_info = vn.last_llm_explanation
                logger.warning(f"   Vanna returned an explanation instead of SQL: {error_info}")
                return f"Database query failed. Reason: {error_info}"
            else:
                logger.warning("   Vanna failed to generate SQL and provided no explanation.")
                return "Could not generate SQL: The question may not be suitable for a database query."

        sql_upper = sql.upper().strip()
        if not any(keyword in sql_upper for keyword in ['SELECT', 'WITH']):
            logger.warning(f"   Vanna returned a message that does not appear to be a valid SQL query: {sql}")
            return f"Database query failed. Reason: {sql}"

        logger.info(f"   ✅ SQL Generated Successfully: {sql}")
        return sql

    except Exception as e:
        logger.error(f"   An exception occurred during SQL generation: {e}", exc_info=True)
        return f"SQL generation failed: {str(e)}"

@tool
def valid_sql(sql: str) -> str:
    """
    验证SQL语句的正确性和安全性。

    Args:
        sql: 待验证的SQL语句。

    Returns:
        验证结果。
    """
    logger.info(f"🔧 [Tool] valid_sql - 待验证SQL (前100字符): {sql[:100]}...")

    if not sql or sql.strip() == "":
        logger.warning("   SQL验证失败：SQL语句为空。")
        return "SQL验证失败：SQL语句为空"

    sql_upper = sql.upper().strip()
    if not any(keyword in sql_upper for keyword in ['SELECT', 'WITH']):
         logger.warning(f"   SQL验证失败：不是有效的查询语句。SQL: {sql}")
         return "SQL验证失败：不是有效的查询语句"
    
    # 简单的安全检查
    dangerous_patterns = [r'\bDROP\b', r'\bDELETE\b', r'\bTRUNCATE\b', r'\bALTER\b', r'\bCREATE\b', r'\bUPDATE\b']
    for pattern in dangerous_patterns:
        if re.search(pattern, sql_upper):
            keyword = pattern.replace(r'\b', '').replace('\\', '')
            logger.error(f"   SQL验证失败：包含危险操作 {keyword}。SQL: {sql}")
            return f"SQL验证失败：包含危险操作 {keyword}"

    logger.info(f"   ✅ SQL验证通过。")
    return "SQL验证通过：语法正确"

@tool
def run_sql(sql: str) -> str:
    """
    执行SQL查询并以JSON字符串格式返回结果。

    Args:
        sql: 待执行的SQL语句。

    Returns:
        JSON字符串格式的查询结果，或包含错误的JSON字符串。
    """
    logger.info(f"🔧 [Tool] run_sql - 待执行SQL (前100字符): {sql[:100]}...")

    try:
        from common.vanna_instance import get_vanna_instance
        vn = get_vanna_instance()
        df = vn.run_sql(sql)

        if df is None:
            logger.warning("   SQL执行成功，但查询结果为空。")
            result = {"status": "success", "data": [], "message": "查询无结果"}
            return json.dumps(result, ensure_ascii=False)

        logger.info(f"   ✅ SQL执行成功，返回 {len(df)} 条记录。")
        # 将DataFrame转换为JSON，并妥善处理datetime等特殊类型
        return df.to_json(orient='records', date_format='iso')

    except Exception as e:
        logger.error(f"   SQL执行过程中发生异常: {e}", exc_info=True)
        error_result = {"status": "error", "error_message": str(e)}
        return json.dumps(error_result, ensure_ascii=False)

# 将所有工具函数收集到一个列表中，方便Agent导入和使用
sql_tools = [generate_sql, valid_sql, run_sql] 