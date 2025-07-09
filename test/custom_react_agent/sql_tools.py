"""
数据库查询相关的工具集
"""
import re
import json
import logging
from langchain_core.tools import tool
import pandas as pd

logger = logging.getLogger(__name__)

# --- 工具函数 ---

@tool
def generate_sql(question: str) -> str:
    """
    根据用户问题生成SQL查询语句。

    Args:
        question: 用户的原始问题。

    Returns:
        生成的SQL语句或错误信息。
    """
    logger.info(f"🔧 [Tool] generate_sql - 问题: '{question}'")

    try:
        from common.vanna_instance import get_vanna_instance
        vn = get_vanna_instance()
        sql = vn.generate_sql(question)

        if not sql or sql.strip() == "":
            if hasattr(vn, 'last_llm_explanation') and vn.last_llm_explanation:
                error_info = vn.last_llm_explanation
                logger.warning(f"   Vanna返回了错误解释: {error_info}")
                return f"数据库查询失败，具体原因：{error_info}"
            else:
                logger.warning("   Vanna未能生成SQL且无解释。")
                return "无法生成SQL：问题可能不适合数据库查询"

        sql_upper = sql.upper().strip()
        if not any(keyword in sql_upper for keyword in ['SELECT', 'WITH']):
            logger.warning(f"   Vanna返回了疑似错误信息而非SQL: {sql}")
            return f"数据库查询失败，具体原因：{sql}"

        logger.info(f"   ✅ 成功生成SQL: {sql}")
        return sql

    except Exception as e:
        logger.error(f"   SQL生成过程中发生异常: {e}", exc_info=True)
        return f"SQL生成失败: {str(e)}"

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