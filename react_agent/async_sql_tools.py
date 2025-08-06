"""
异步版本的 SQL 工具 - 解决 Vector 搜索异步冲突
通过线程池执行同步操作，避免 LangGraph 事件循环冲突
"""
import json
import asyncio
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from core.logging import get_react_agent_logger

logger = get_react_agent_logger("AsyncSQLTools")

# 创建线程池执行器
_executor = ThreadPoolExecutor(max_workers=3)

class GenerateSqlArgs(BaseModel):
    question: str = Field(description="The user's question in natural language")
    history_messages: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="The conversation history messages for context."
    )

async def _run_in_executor(func, *args, **kwargs):
    """在线程池中运行同步函数，避免事件循环冲突"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, func, *args, **kwargs)

@tool(args_schema=GenerateSqlArgs)
async def generate_sql(question: str, history_messages: List[Dict[str, Any]] = None) -> str:
    """
    异步生成 SQL 查询 - 通过线程池调用同步的 Vanna
    Generates an SQL query based on the user's question and the conversation history.
    """
    logger.info(f"🔧 [Async Tool] generate_sql - Question: '{question}'")
    
    # 在线程池中执行，避免事件循环冲突
    def _sync_generate():
        from common.vanna_instance import get_vanna_instance
        
        if history_messages is None:
            history_messages_local = []
        else:
            history_messages_local = history_messages
        
        logger.info(f"   History contains {len(history_messages_local)} messages.")
        
        # 构建增强问题（与同步版本相同的逻辑）
        if history_messages_local:
            history_str = "\n".join([f"{msg['type']}: {msg.get('content', '') or ''}" for msg in history_messages_local])
            enriched_question = f"""Previous conversation context:
{history_str}

Current user question:
human: {question}

Please analyze the conversation history to understand any references (like "this service area", "that branch", etc.) in the current question, and generate the appropriate SQL query."""
        else:
            enriched_question = question
        
        # 记录 Vanna 输入
        logger.info("📝 [Async Vanna Input] Complete question being sent to Vanna:")
        logger.info("--- BEGIN VANNA INPUT ---")
        logger.info(enriched_question)
        logger.info("--- END VANNA INPUT ---")
        
        try:
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
    
    # 在线程池中执行
    return await _run_in_executor(_sync_generate)

# 导入同步版本的验证函数
def _import_validation_functions():
    """动态导入验证函数，避免循环导入"""
    from react_agent.sql_tools import _check_basic_syntax, _check_table_existence, _validate_with_limit_zero
    return _check_basic_syntax, _check_table_existence, _validate_with_limit_zero

@tool
async def valid_sql(sql: str) -> str:
    """
    异步验证 SQL 语句的有效性
    Validates the SQL statement by checking syntax and executing with LIMIT 0.
    """
    logger.info(f"🔧 [Async Tool] valid_sql - Validating SQL")
    
    def _sync_validate():
        # 导入验证函数
        _check_basic_syntax, _check_table_existence, _validate_with_limit_zero = _import_validation_functions()
        
        # 规则1：基本语法检查
        if not _check_basic_syntax(sql):
            logger.warning(f"   SQL基本语法检查失败: {sql[:100]}...")
            return json.dumps({
                "result": "invalid",
                "error": "SQL语句格式错误：必须是SELECT或WITH开头的查询语句"
            })
        
        # 规则2：表存在性检查
        if not _check_table_existence(sql):
            logger.warning(f"   SQL表存在性检查失败")
            return json.dumps({
                "result": "invalid",
                "error": "SQL中引用的表不存在于数据库中"
            })
        
        # 规则3：LIMIT 0执行测试
        return _validate_with_limit_zero(sql)
    
    return await _run_in_executor(_sync_validate)

@tool
async def run_sql(sql: str) -> str:
    """
    异步执行 SQL 查询并返回结果
    执行SQL查询并以JSON字符串格式返回结果。
    
    Args:
        sql: 待执行的SQL语句。
        
    Returns:
        JSON字符串格式的查询结果，或包含错误的JSON字符串。
    """
    logger.info(f"🔧 [Async Tool] run_sql - 待执行SQL:")
    logger.info(f"   {sql}")
    
    def _sync_run():
        from common.vanna_instance import get_vanna_instance
        
        try:
            vn = get_vanna_instance()
            df = vn.run_sql(sql)
            
            logger.debug(f"SQL执行结果：\n{df}")
            
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
    
    return await _run_in_executor(_sync_run)

# 将所有异步工具函数收集到一个列表中
async_sql_tools = [generate_sql, valid_sql, run_sql]

# 清理函数（可选）
def cleanup():
    """清理线程池资源"""
    global _executor
    if _executor:
        _executor.shutdown(wait=False)
        logger.info("异步SQL工具线程池已关闭")