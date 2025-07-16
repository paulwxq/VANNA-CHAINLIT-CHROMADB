"""
数据库查询相关的工具集
"""
import re
import json
import sys
import os
from pathlib import Path
from langchain_core.tools import tool
from pydantic.v1 import BaseModel, Field
from typing import List, Dict, Any
import pandas as pd

# 添加项目根目录到sys.path以解决common模块导入问题
try:
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
except Exception as e:
    print(f"Warning: Could not add project root to sys.path: {e}")

# 使用独立日志系统
try:
    # 尝试相对导入（当作为模块导入时）
    from .logger import get_react_agent_logger
except ImportError:
    # 如果相对导入失败，尝试绝对导入（直接运行时）
    from logger import get_react_agent_logger

logger = get_react_agent_logger("SQLTools")

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
    if history_messages:
        history_str = "\n".join([f"{msg['type']}: {msg.get('content', '') or ''}" for msg in history_messages])
        enriched_question = f"""Previous conversation context:
{history_str}

Current user question:
human: {question}

Please analyze the conversation history to understand any references (like "this service area", "that branch", etc.) in the current question, and generate the appropriate SQL query."""
    else:
        # If no history messages, use the original question directly
        enriched_question = question

    # 🎯 添加稳定的Vanna输入日志
    logger.info("📝 [Vanna Input] Complete question being sent to Vanna:")
    logger.info("--- BEGIN VANNA INPUT ---")
    logger.info(enriched_question)
    logger.info("--- END VANNA INPUT ---")

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

        logger.info(f"   ✅ SQL Generated Successfully:")
        logger.info(f"   {sql}")
        return sql

    except Exception as e:
        logger.error(f"   An exception occurred during SQL generation: {e}", exc_info=True)
        return f"SQL generation failed: {str(e)}"

def _check_basic_syntax(sql: str) -> bool:
    """规则1: 检查SQL是否包含基础查询关键词"""
    if not sql or sql.strip() == "":
        return False
    
    sql_upper = sql.upper().strip()
    return any(keyword in sql_upper for keyword in ['SELECT', 'WITH'])


def _check_security(sql: str) -> tuple[bool, str]:
    """规则2: 检查SQL是否包含危险操作
    
    Returns:
        tuple: (是否安全, 错误信息)
    """
    sql_upper = sql.upper().strip()
    dangerous_patterns = [r'\bDROP\b', r'\bDELETE\b', r'\bTRUNCATE\b', r'\bALTER\b', r'\bCREATE\b', r'\bUPDATE\b']
    
    for pattern in dangerous_patterns:
        if re.search(pattern, sql_upper):
            keyword = pattern.replace(r'\b', '').replace('\\', '')
            return False, f"包含危险操作 {keyword}"
    
    return True, ""


def _has_limit_clause(sql: str) -> bool:
    """检测SQL是否包含LIMIT子句"""
    # 使用正则表达式检测LIMIT关键词，支持多种格式
    # LIMIT n 或 LIMIT offset, count 格式
    limit_pattern = r'\bLIMIT\s+\d+(?:\s*,\s*\d+)?\s*(?:;|\s*$)'
    return bool(re.search(limit_pattern, sql, re.IGNORECASE))


def _validate_with_limit_zero(sql: str) -> str:
    """规则3: 使用LIMIT 0验证SQL（适用于无LIMIT子句的SQL）"""
    try:
        from common.vanna_instance import get_vanna_instance
        vn = get_vanna_instance()
        
        # 添加 LIMIT 0 避免返回大量数据，只验证SQL结构
        test_sql = sql.rstrip(';') + " LIMIT 0"
        logger.info(f"   执行LIMIT 0验证:")
        logger.info(f"   {test_sql}")
        vn.run_sql(test_sql)
        
        logger.info("   ✅ SQL验证通过：语法正确且字段/表存在")
        return "SQL验证通过：语法正确且字段存在"
        
    except Exception as e:
        return _format_validation_error(str(e))


def _validate_with_prepare(sql: str) -> str:
    """规则4: 使用PREPARE/DEALLOCATE验证SQL（适用于包含LIMIT子句的SQL）"""
    import time
    
    try:
        from common.vanna_instance import get_vanna_instance
        vn = get_vanna_instance()
        
        # 生成唯一的语句名，避免并发冲突
        stmt_name = f"validation_stmt_{int(time.time() * 1000)}"
        prepare_executed = False
        
        try:
            # 执行PREPARE验证
            prepare_sql = f"PREPARE {stmt_name} AS {sql.rstrip(';')}"
            logger.info(f"   执行PREPARE验证:")
            logger.info(f"   {prepare_sql}")
            
            vn.run_sql(prepare_sql)
            prepare_executed = True
            
            # 如果执行到这里没有异常，说明PREPARE成功
            logger.info("   ✅ PREPARE执行成功，SQL验证通过")
            return "SQL验证通过：语法正确且字段存在"
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # PostgreSQL中PREPARE不返回结果集是正常行为
            if "no results to fetch" in error_msg:
                prepare_executed = True  # 标记为成功执行
                logger.info("   ✅ PREPARE执行成功（无结果集），SQL验证通过")
                return "SQL验证通过：语法正确且字段存在"
            else:
                # 真正的错误（语法错误、字段不存在等）
                raise e
                
        finally:
            # 只有在PREPARE成功执行时才尝试清理资源
            if prepare_executed:
                try:
                    deallocate_sql = f"DEALLOCATE {stmt_name}"
                    logger.info(f"   清理PREPARE资源: {deallocate_sql}")
                    vn.run_sql(deallocate_sql)
                except Exception as cleanup_error:
                    # 清理失败不影响验证结果，只记录警告
                    logger.warning(f"   清理PREPARE资源失败: {cleanup_error}")
                    
    except Exception as e:
        return _format_validation_error(str(e))


def _format_validation_error(error_msg: str) -> str:
    """格式化验证错误信息"""
    logger.warning(f"   SQL验证失败：执行测试时出错 - {error_msg}")
    
    # 提供更详细的错误信息供LLM理解和处理
    if "column" in error_msg.lower() and ("does not exist" in error_msg.lower() or "不存在" in error_msg):
        return f"SQL验证失败：字段不存在。详细错误：{error_msg}"
    elif "table" in error_msg.lower() and ("does not exist" in error_msg.lower() or "不存在" in error_msg):
        return f"SQL验证失败：表不存在。详细错误：{error_msg}"
    elif "syntax error" in error_msg.lower() or "语法错误" in error_msg:
        return f"SQL验证失败：语法错误。详细错误：{error_msg}"
    else:
        return f"SQL验证失败：执行失败。详细错误：{error_msg}"


@tool
def valid_sql(sql: str) -> str:
    """
    验证SQL语句的正确性和安全性，使用四规则递进验证：
    1. 基础语法检查（SELECT/WITH关键词）
    2. 安全检查（无危险操作）
    3. 语义验证：无LIMIT时使用LIMIT 0验证
    4. 语义验证：有LIMIT时使用PREPARE/DEALLOCATE验证

    Args:
        sql: 待验证的SQL语句。

    Returns:
        验证结果。
    """
    logger.info(f"🔧 [Tool] valid_sql - 待验证SQL:")
    logger.info(f"   {sql}")

    # 规则1: 基础语法检查
    if not _check_basic_syntax(sql):
        logger.warning("   SQL验证失败：SQL语句为空或不是有效的查询语句")
        return "SQL验证失败：SQL语句为空或不是有效的查询语句"

    # 规则2: 安全检查
    is_safe, security_error = _check_security(sql)
    if not is_safe:
        logger.error(f"   SQL验证失败：{security_error}")
        return f"SQL验证失败：{security_error}"

    # 规则3/4: 语义验证（二选一）
    if _has_limit_clause(sql):
        logger.info("   检测到LIMIT子句，使用PREPARE验证")
        return _validate_with_prepare(sql)
    else:
        logger.info("   未检测到LIMIT子句，使用LIMIT 0验证")
        return _validate_with_limit_zero(sql)

@tool
def run_sql(sql: str) -> str:
    """
    执行SQL查询并以JSON字符串格式返回结果。

    Args:
        sql: 待执行的SQL语句。

    Returns:
        JSON字符串格式的查询结果，或包含错误的JSON字符串。
    """
    logger.info(f"🔧 [Tool] run_sql - 待执行SQL:")
    logger.info(f"   {sql}")

    try:
        from common.vanna_instance import get_vanna_instance
        vn = get_vanna_instance()
        df = vn.run_sql(sql)

        print("-------------run_sql() df -------------------")
        print(df)
        print("--------------------------------")

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