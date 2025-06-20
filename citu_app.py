# 给dataops 对话助手返回结果
from vanna.flask import VannaFlaskApp
from core.vanna_llm_factory import create_vanna_instance
from flask import request, jsonify
import pandas as pd
import common.result as result
from datetime import datetime, timedelta
from common.session_aware_cache import WebSessionAwareMemoryCache
from app_config import API_MAX_RETURN_ROWS, DISPLAY_SUMMARY_THINKING
import re

# 设置默认的最大返回行数
DEFAULT_MAX_RETURN_ROWS = 200
MAX_RETURN_ROWS = API_MAX_RETURN_ROWS if API_MAX_RETURN_ROWS is not None else DEFAULT_MAX_RETURN_ROWS

vn = create_vanna_instance()

# 创建带时间戳的缓存
timestamped_cache = WebSessionAwareMemoryCache()

# 实例化 VannaFlaskApp，使用自定义缓存
app = VannaFlaskApp(
    vn,
    cache=timestamped_cache,  # 使用带时间戳的缓存
    title="辞图智能数据问答平台",
    logo = "https://www.citupro.com/img/logo-black-2.png",
    subtitle="让 AI 为你写 SQL",
    chart=False,
    allow_llm_to_see_data=True,
    ask_results_correct=True,
    followup_questions=True,
    debug=True
)


def _remove_thinking_content(text: str) -> str:
    """
    移除文本中的 <think></think> 标签及其内容
    复用自 base_llm_chat.py 中的同名方法
    
    Args:
        text (str): 包含可能的 thinking 标签的文本
        
    Returns:
        str: 移除 thinking 内容后的文本
    """
    if not text:
        return text
    
    # 移除 <think>...</think> 标签及其内容（支持多行）
    # 使用 re.DOTALL 标志使 . 匹配包括换行符在内的任何字符
    cleaned_text = re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # 移除可能的多余空行
    cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text)
    
    # 去除开头和结尾的空白字符
    cleaned_text = cleaned_text.strip()
    
    return cleaned_text


# 修改ask接口，支持前端传递session_id
@app.flask_app.route('/api/v0/ask', methods=['POST'])
def ask_full():
    req = request.get_json(force=True)
    question = req.get("question", None)
    browser_session_id = req.get("session_id", None)  # 前端传递的会话ID
    
    if not question:
        return jsonify(result.failed(message="未提供问题", code=400)), 400

    # 如果使用WebSessionAwareMemoryCache
    if hasattr(app.cache, 'generate_id_with_browser_session') and browser_session_id:
        # 这里需要修改vanna的ask方法来支持传递session_id
        # 或者预先调用generate_id来建立会话关联
        conversation_id = app.cache.generate_id_with_browser_session(
            question=question, 
            browser_session_id=browser_session_id
        )

    try:
        sql, df, _ = vn.ask(
            question=question,
            print_results=False,
            visualize=False,
            allow_llm_to_see_data=True
        )

        # 关键：检查是否有LLM解释性文本（无法生成SQL的情况）
        if sql is None and hasattr(vn, 'last_llm_explanation') and vn.last_llm_explanation:
            # 根据 DISPLAY_SUMMARY_THINKING 参数决定是否移除 thinking 内容
            explanation_message = vn.last_llm_explanation
            if not DISPLAY_SUMMARY_THINKING:
                explanation_message = _remove_thinking_content(explanation_message)
                print(f"[DEBUG] 隐藏thinking内容 - 原始长度: {len(vn.last_llm_explanation)}, 处理后长度: {len(explanation_message)}")
            
            # 在解释性文本末尾添加提示语
            explanation_message = explanation_message + "请尝试提问其它问题。"
            
            # 使用 result.failed 返回，success为false，但在message中包含LLM友好的解释
            return jsonify(result.failed(
                message=explanation_message,  # 处理后的解释性文本
                code=400,  # 业务逻辑错误，使用400
                data={
                    "sql": None,
                    "rows": [],
                    "columns": [],
                    "summary": None,
                    "conversation_id": conversation_id if 'conversation_id' in locals() else None,
                    "session_id": browser_session_id
                }
            )), 200  # HTTP状态码仍为200，因为请求本身成功处理了

        # 如果sql为None但没有解释性文本，返回通用错误
        if sql is None:
            return jsonify(result.failed(
                message="无法生成SQL查询，请检查问题描述或数据表结构",
                code=400,
                data={
                    "sql": None,
                    "rows": [],
                    "columns": [],
                    "summary": None,
                    "conversation_id": conversation_id if 'conversation_id' in locals() else None,
                    "session_id": browser_session_id
                }
            )), 200

        # 正常SQL流程
        rows, columns = [], []
        summary = None
        
        if isinstance(df, pd.DataFrame) and not df.empty:
            rows = df.head(MAX_RETURN_ROWS).to_dict(orient="records")
            columns = list(df.columns)
            
            # 生成数据摘要
            try:
                summary = vn.generate_summary(question=question, df=df)
                print(f"[INFO] 成功生成摘要: {summary}")
            except Exception as e:
                print(f"[WARNING] 生成摘要失败: {str(e)}")
                summary = None

        return jsonify(result.success(data={
            "sql": sql,
            "rows": rows,
            "columns": columns,
            "summary": summary,  # 添加摘要到返回结果
            "conversation_id": conversation_id if 'conversation_id' in locals() else None,
            "session_id": browser_session_id
        }))
        
    except Exception as e:
        print(f"[ERROR] ask_full执行失败: {str(e)}")
        
        # 即使发生异常，也检查是否有业务层面的解释
        if hasattr(vn, 'last_llm_explanation') and vn.last_llm_explanation:
            # 根据 DISPLAY_SUMMARY_THINKING 参数决定是否移除 thinking 内容
            explanation_message = vn.last_llm_explanation
            if not DISPLAY_SUMMARY_THINKING:
                explanation_message = _remove_thinking_content(explanation_message)
                print(f"[DEBUG] 异常处理中隐藏thinking内容 - 原始长度: {len(vn.last_llm_explanation)}, 处理后长度: {len(explanation_message)}")
            
            # 在解释性文本末尾添加提示语
            explanation_message = explanation_message + "请尝试提问其它问题。"
            
            return jsonify(result.failed(
                message=explanation_message,
                code=400,
                data={
                    "sql": None,
                    "rows": [],
                    "columns": [],
                    "summary": None,
                    "conversation_id": conversation_id if 'conversation_id' in locals() else None,
                    "session_id": browser_session_id
                }
            )), 200
        else:
            # 技术错误，使用500错误码
            return jsonify(result.failed(
                message=f"查询处理失败: {str(e)}", 
                code=500
            )), 500

@app.flask_app.route('/api/v0/citu_run_sql', methods=['POST'])
def citu_run_sql():
    req = request.get_json(force=True)
    sql = req.get('sql')
    
    if not sql:
        return jsonify(result.failed(message="未提供SQL查询", code=400)), 400
    
    try:
        df = vn.run_sql(sql)
        
        rows, columns = [], []
        
        if isinstance(df, pd.DataFrame) and not df.empty:
            rows = df.head(MAX_RETURN_ROWS).to_dict(orient="records")
            columns = list(df.columns)
        
        return jsonify(result.success(data={
            "sql": sql,
            "rows": rows,
            "columns": columns
        }))
        
    except Exception as e:
        print(f"[ERROR] citu_run_sql执行失败: {str(e)}")
        return jsonify(result.failed(
            message=f"SQL执行失败: {str(e)}", 
            code=500
        )), 500

@app.flask_app.route('/api/v0/ask_cached', methods=['POST'])
def ask_cached():
    """
    带缓存功能的智能查询接口
    支持会话管理和结果缓存，提高查询效率
    """
    req = request.get_json(force=True)
    question = req.get("question", None)
    browser_session_id = req.get("session_id", None)
    
    if not question:
        return jsonify(result.failed(message="未提供问题", code=400)), 400

    try:
        # 生成conversation_id
        # 调试：查看generate_id的实际行为
        print(f"[DEBUG] 输入问题: '{question}'")
        conversation_id = app.cache.generate_id(question=question)
        print(f"[DEBUG] 生成的conversation_id: {conversation_id}")
        
        # 再次用相同问题测试
        conversation_id2 = app.cache.generate_id(question=question)
        print(f"[DEBUG] 再次生成的conversation_id: {conversation_id2}")
        print(f"[DEBUG] 两次ID是否相同: {conversation_id == conversation_id2}")
        
        # 检查缓存
        cached_sql = app.cache.get(id=conversation_id, field="sql")
        
        if cached_sql is not None:
            # 缓存命中
            print(f"[CACHE HIT] 使用缓存结果: {conversation_id}")
            sql = cached_sql
            df = app.cache.get(id=conversation_id, field="df")
            summary = app.cache.get(id=conversation_id, field="summary")
        else:
            # 缓存未命中，执行新查询
            print(f"[CACHE MISS] 执行新查询: {conversation_id}")
            
            sql, df, _ = vn.ask(
                question=question,
                print_results=False,
                visualize=False,
                allow_llm_to_see_data=True
            )
            
            # 检查是否有LLM解释性文本（无法生成SQL的情况）
            if sql is None and hasattr(vn, 'last_llm_explanation') and vn.last_llm_explanation:
                # 根据 DISPLAY_SUMMARY_THINKING 参数决定是否移除 thinking 内容
                explanation_message = vn.last_llm_explanation
                if not DISPLAY_SUMMARY_THINKING:
                    explanation_message = _remove_thinking_content(explanation_message)
                    print(f"[DEBUG] ask_cached中隐藏thinking内容 - 原始长度: {len(vn.last_llm_explanation)}, 处理后长度: {len(explanation_message)}")
                
                # 在解释性文本末尾添加提示语
                explanation_message = explanation_message + "请尝试用其它方式提问。"
                
                return jsonify(result.failed(
                    message=explanation_message,
                    code=400,
                    data={
                        "sql": None,
                        "rows": [],
                        "columns": [],
                        "summary": None,
                        "conversation_id": conversation_id,
                        "session_id": browser_session_id,
                        "cached": False
                    }
                )), 200
            
            # 如果sql为None但没有解释性文本，返回通用错误
            if sql is None:
                return jsonify(result.failed(
                    message="无法生成SQL查询，请检查问题描述或数据表结构",
                    code=400,
                    data={
                        "sql": None,
                        "rows": [],
                        "columns": [],
                        "summary": None,
                        "conversation_id": conversation_id,
                        "session_id": browser_session_id,
                        "cached": False
                    }
                )), 200
            
            # 缓存结果
            app.cache.set(id=conversation_id, field="question", value=question)
            app.cache.set(id=conversation_id, field="sql", value=sql)
            app.cache.set(id=conversation_id, field="df", value=df)
            
            # 生成并缓存摘要
            summary = None
            if isinstance(df, pd.DataFrame) and not df.empty:
                try:
                    summary = vn.generate_summary(question=question, df=df)
                    print(f"[INFO] 成功生成摘要: {summary}")
                except Exception as e:
                    print(f"[WARNING] 生成摘要失败: {str(e)}")
                    summary = None
            
            app.cache.set(id=conversation_id, field="summary", value=summary)

        # 处理返回数据
        rows, columns = [], []
        
        if isinstance(df, pd.DataFrame) and not df.empty:
            rows = df.head(MAX_RETURN_ROWS).to_dict(orient="records")
            columns = list(df.columns)

        return jsonify(result.success(data={
            "sql": sql,
            "rows": rows,
            "columns": columns,
            "summary": summary,
            "conversation_id": conversation_id,
            "session_id": browser_session_id,
            "cached": cached_sql is not None  # 标识是否来自缓存
        }))
        
    except Exception as e:
        print(f"[ERROR] ask_cached执行失败: {str(e)}")
        return jsonify(result.failed(
            message=f"查询处理失败: {str(e)}", 
            code=500
        )), 500
    


@app.flask_app.route('/api/v0/citu_train_question_sql', methods=['POST'])
def citu_train_question_sql():
    """
    训练问题-SQL对接口
    
    此API将接收的question/sql pair写入到training库中，用于训练和改进AI模型。
    支持仅传入SQL或同时传入问题和SQL进行训练。
    
    Args:
        question (str, optional): 用户问题
        sql (str, required): 对应的SQL查询语句
    
    Returns:
        JSON: 包含训练ID和成功消息的响应
    """
    try:
        req = request.get_json(force=True)
        question = req.get('question')
        sql = req.get('sql')
        
        if not sql:
            return jsonify(result.failed(
                message="'sql' are required", 
                code=400
            )), 400
        
        # 正确的调用方式：同时传递question和sql
        if question:
            training_id = vn.train(question=question, sql=sql)
            print(f"训练成功，训练ID为：{training_id}，问题：{question}，SQL：{sql}")
        else:
            training_id = vn.train(sql=sql)
            print(f"训练成功，训练ID为：{training_id}，SQL：{sql}")

        return jsonify(result.success(data={
            "training_id": training_id,
            "message": "Question-SQL pair trained successfully"
        }))
        
    except Exception as e:
        return jsonify(result.failed(
            message=f"Training failed: {str(e)}", 
            code=500
        )), 500
    

# ============ LangGraph Agent 集成 ============

# 全局Agent实例（单例模式）
citu_langraph_agent = None

def get_citu_langraph_agent():
    """获取LangGraph Agent实例（懒加载）"""
    global citu_langraph_agent
    if citu_langraph_agent is None:
        try:
            from agent.citu_agent import CituLangGraphAgent
            print("[CITU_APP] 开始创建LangGraph Agent实例...")
            citu_langraph_agent = CituLangGraphAgent()
            print("[CITU_APP] LangGraph Agent实例创建成功")
        except ImportError as e:
            print(f"[CRITICAL] Agent模块导入失败: {str(e)}")
            print("[CRITICAL] 请检查agent模块是否存在以及依赖是否正确安装")
            raise Exception(f"Agent模块导入失败: {str(e)}")
        except Exception as e:
            print(f"[CRITICAL] LangGraph Agent实例创建失败: {str(e)}")
            print(f"[CRITICAL] 错误类型: {type(e).__name__}")
            # 提供更有用的错误信息
            if "config" in str(e).lower():
                print("[CRITICAL] 可能是配置文件问题，请检查配置")
            elif "llm" in str(e).lower():
                print("[CRITICAL] 可能是LLM连接问题，请检查LLM配置")
            elif "tool" in str(e).lower():
                print("[CRITICAL] 可能是工具加载问题，请检查工具模块")
            raise Exception(f"Agent初始化失败: {str(e)}")
    return citu_langraph_agent

@app.flask_app.route('/api/v0/ask_agent', methods=['POST'])
def ask_agent():
    """
    新的LangGraph Agent接口
    
    请求格式:
    {
        "question": "用户问题",
        "session_id": "会话ID（可选）"
    }
    
    响应格式:
    {
        "success": true/false,
        "code": 200,
        "message": "success" 或错误信息,
        "data": {
            "response": "最终回答",
            "type": "DATABASE/CHAT",
            "sql": "生成的SQL（如果是数据库查询）",
            "data_result": {
                "rows": [...],
                "columns": [...],
                "row_count": 数字
            },
            "summary": "数据摘要（如果是数据库查询）",
            "session_id": "会话ID",
            "execution_path": ["classify", "agent_database", "format_response"],
            "classification_info": {
                "confidence": 0.95,
                "reason": "分类原因",
                "method": "rule_based/llm_based"
            },
            "agent_version": "langgraph_v1"
        }
    }
    """
    req = request.get_json(force=True)
    question = req.get("question", None)
    browser_session_id = req.get("session_id", None)
    
    if not question:
        return jsonify(result.failed(message="未提供问题", code=400)), 400

    try:
        # 专门处理Agent初始化异常
        try:
            agent = get_citu_langraph_agent()
        except Exception as e:
            print(f"[CRITICAL] Agent初始化失败: {str(e)}")
            return jsonify(result.failed(
                message="AI服务暂时不可用，请稍后重试", 
                code=503,
                data={
                    "session_id": browser_session_id,
                    "execution_path": ["agent_init_error"],
                    "agent_version": "langgraph_v1",
                    "timestamp": datetime.now().isoformat(),
                    "error_type": "agent_initialization_failed"
                }
            )), 503
        
        # 调用Agent处理问题
        agent_result = agent.process_question(
            question=question,
            session_id=browser_session_id
        )
        
        # 统一返回格式
        if agent_result.get("success", False):
            return jsonify(result.success(data={
                "response": agent_result.get("response", ""),
                "type": agent_result.get("type", "UNKNOWN"),
                "sql": agent_result.get("sql"),
                "data_result": agent_result.get("data_result"),
                "summary": agent_result.get("summary"),
                "session_id": browser_session_id,
                "execution_path": agent_result.get("execution_path", []),
                "classification_info": agent_result.get("classification_info", {}),
                "agent_version": "langgraph_v1",
                "timestamp": datetime.now().isoformat()
            }))
        else:
            return jsonify(result.failed(
                message=agent_result.get("error", "Agent处理失败"),
                code=agent_result.get("error_code", 500),
                data={
                    "session_id": browser_session_id,
                    "execution_path": agent_result.get("execution_path", []),
                    "classification_info": agent_result.get("classification_info", {}),
                    "agent_version": "langgraph_v1",
                    "timestamp": datetime.now().isoformat()
                }
            )), 200  # HTTP 200但业务失败
            
    except Exception as e:
        print(f"[ERROR] ask_agent执行失败: {str(e)}")
        return jsonify(result.failed(
            message="请求处理异常，请稍后重试", 
            code=500,
            data={
                "session_id": browser_session_id,
                "execution_path": ["general_error"],
                "agent_version": "langgraph_v1",
                "timestamp": datetime.now().isoformat(),
                "error_type": "request_processing_failed"
            }
        )), 500

@app.flask_app.route('/api/v0/agent_health', methods=['GET'])
def agent_health():
    """
    Agent健康检查接口
    
    响应格式:
    {
        "success": true/false,
        "code": 200/503,
        "message": "healthy/degraded/unhealthy",
        "data": {
            "status": "healthy/degraded/unhealthy",
            "test_result": true/false,
            "workflow_compiled": true/false,
            "tools_count": 4,
            "message": "详细信息",
            "timestamp": "2024-01-01T12:00:00",
            "checks": {
                "agent_creation": true/false,
                "tools_import": true/false,
                "llm_connection": true/false,
                "classifier_ready": true/false
            }
        }
    }
    """
    try:
        # 基础健康检查
        health_data = {
            "status": "unknown",
            "test_result": False,
            "workflow_compiled": False,
            "tools_count": 0,
            "message": "",
            "timestamp": datetime.now().isoformat(),
            "checks": {
                "agent_creation": False,
                "tools_import": False,
                "llm_connection": False,
                "classifier_ready": False
            }
        }
        
        # 检查1: Agent创建
        try:
            agent = get_citu_langraph_agent()
            health_data["checks"]["agent_creation"] = True
            health_data["workflow_compiled"] = agent.workflow is not None
            health_data["tools_count"] = len(agent.tools) if hasattr(agent, 'tools') else 0
        except Exception as e:
            health_data["message"] = f"Agent创建失败: {str(e)}"
            return jsonify(result.failed(
                message="Agent状态: unhealthy", 
                data=health_data,
                code=503
            )), 503
        
        # 检查2: 工具导入
        try:
            from agent.tools import TOOLS
            health_data["checks"]["tools_import"] = len(TOOLS) > 0
        except Exception as e:
            health_data["message"] = f"工具导入失败: {str(e)}"
        
        # 检查3: LLM连接（简单测试）
        try:
            from agent.utils import get_compatible_llm
            llm = get_compatible_llm()
            health_data["checks"]["llm_connection"] = llm is not None
        except Exception as e:
            health_data["message"] = f"LLM连接失败: {str(e)}"
        
        # 检查4: 分类器准备
        try:
            from agent.classifier import QuestionClassifier
            classifier = QuestionClassifier()
            health_data["checks"]["classifier_ready"] = True
        except Exception as e:
            health_data["message"] = f"分类器失败: {str(e)}"
        
        # 检查5: 完整流程测试（可选）
        try:
            if all(health_data["checks"].values()):
                test_result = agent.health_check()
                health_data["test_result"] = test_result.get("status") == "healthy"
                health_data["status"] = test_result.get("status", "unknown")
                health_data["message"] = test_result.get("message", "健康检查完成")
            else:
                health_data["status"] = "degraded"
                health_data["message"] = "部分组件异常"
        except Exception as e:
            health_data["status"] = "degraded"
            health_data["message"] = f"完整测试失败: {str(e)}"
        
        # 根据状态返回相应的HTTP代码
        if health_data["status"] == "healthy":
            return jsonify(result.success(data=health_data))
        elif health_data["status"] == "degraded":
            return jsonify(result.failed(
                message="Agent状态: degraded", 
                data=health_data,
                code=503
            )), 503
        else:
            return jsonify(result.failed(
                message="Agent状态: unhealthy", 
                data=health_data,
                code=503
            )), 503
            
    except Exception as e:
        print(f"[ERROR] 健康检查异常: {str(e)}")
        return jsonify(result.failed(
            message=f"健康检查失败: {str(e)}", 
            code=500,
            data={
                "status": "error",
                "timestamp": datetime.now().isoformat()
            }
        )), 500



# ==================== 日常管理API ====================

@app.flask_app.route('/api/v0/cache_overview', methods=['GET'])
def cache_overview():
    """日常管理：轻量概览 - 合并原cache_inspect的核心功能"""
    try:
        cache = app.cache
        result_data = {
            'overview_summary': {
                'total_conversations': 0,
                'total_sessions': 0,
                'query_time': datetime.now().isoformat()
            },
            'recent_conversations': [],  # 最近的对话
            'session_summary': []       # 会话摘要
        }
        
        if hasattr(cache, 'cache') and isinstance(cache.cache, dict):
            result_data['overview_summary']['total_conversations'] = len(cache.cache)
            
            # 获取会话信息
            if hasattr(cache, 'get_all_sessions'):
                all_sessions = cache.get_all_sessions()
                result_data['overview_summary']['total_sessions'] = len(all_sessions)
                
                # 会话摘要（按最近活动排序）
                session_list = []
                for session_id, session_data in all_sessions.items():
                    session_summary = {
                        'session_id': session_id,
                        'start_time': session_data['start_time'].isoformat(),
                        'conversation_count': session_data.get('conversation_count', 0),
                        'duration_seconds': session_data.get('session_duration_seconds', 0),
                        'last_activity': session_data.get('last_activity', session_data['start_time']).isoformat(),
                        'is_active': (datetime.now() - session_data.get('last_activity', session_data['start_time'])).total_seconds() < 1800  # 30分钟内活跃
                    }
                    session_list.append(session_summary)
                
                # 按最后活动时间排序
                session_list.sort(key=lambda x: x['last_activity'], reverse=True)
                result_data['session_summary'] = session_list
            
            # 最近的对话（最多显示10个）
            conversation_list = []
            for conversation_id, conversation_data in cache.cache.items():
                conversation_start_time = cache.conversation_start_times.get(conversation_id)
                
                conversation_info = {
                    'conversation_id': conversation_id,
                    'conversation_start_time': conversation_start_time.isoformat() if conversation_start_time else None,
                    'session_id': cache.conversation_to_session.get(conversation_id),
                    'has_question': 'question' in conversation_data,
                    'has_sql': 'sql' in conversation_data,
                    'has_data': 'df' in conversation_data and conversation_data['df'] is not None,
                    'question_preview': conversation_data.get('question', '')[:80] + '...' if len(conversation_data.get('question', '')) > 80 else conversation_data.get('question', ''),
                }
                
                # 计算对话持续时间
                if conversation_start_time:
                    duration = datetime.now() - conversation_start_time
                    conversation_info['conversation_duration_seconds'] = duration.total_seconds()
                
                conversation_list.append(conversation_info)
            
            # 按对话开始时间排序，显示最新的10个
            conversation_list.sort(key=lambda x: x['conversation_start_time'] or '', reverse=True)
            result_data['recent_conversations'] = conversation_list[:10]
        
        return jsonify(result.success(data=result_data))
        
    except Exception as e:
        return jsonify(result.failed(
            message=f"获取缓存概览失败: {str(e)}", 
            code=500
        )), 500


@app.flask_app.route('/api/v0/cache_stats', methods=['GET'])
def cache_stats():
    """日常管理：统计信息 - 合并原session_stats和cache_stats功能"""
    try:
        cache = app.cache
        current_time = datetime.now()
        
        stats = {
            'basic_stats': {
                'total_sessions': len(getattr(cache, 'session_info', {})),
                'total_conversations': len(getattr(cache, 'cache', {})),
                'active_sessions': 0,  # 最近30分钟有活动
                'average_conversations_per_session': 0
            },
            'time_distribution': {
                'sessions': {
                    'last_1_hour': 0,
                    'last_6_hours': 0, 
                    'last_24_hours': 0,
                    'last_7_days': 0,
                    'older': 0
                },
                'conversations': {
                    'last_1_hour': 0,
                    'last_6_hours': 0,
                    'last_24_hours': 0, 
                    'last_7_days': 0,
                    'older': 0
                }
            },
            'session_details': [],
            'time_ranges': {
                'oldest_session': None,
                'newest_session': None,
                'oldest_conversation': None,
                'newest_conversation': None
            }
        }
        
        # 会话统计
        if hasattr(cache, 'session_info'):
            session_times = []
            total_conversations = 0
            
            for session_id, session_data in cache.session_info.items():
                start_time = session_data['start_time']
                session_times.append(start_time)
                conversation_count = len(session_data.get('conversations', []))
                total_conversations += conversation_count
                
                # 检查活跃状态
                last_activity = session_data.get('last_activity', session_data['start_time'])
                if (current_time - last_activity).total_seconds() < 1800:
                    stats['basic_stats']['active_sessions'] += 1
                
                # 时间分布统计
                age_hours = (current_time - start_time).total_seconds() / 3600
                if age_hours <= 1:
                    stats['time_distribution']['sessions']['last_1_hour'] += 1
                elif age_hours <= 6:
                    stats['time_distribution']['sessions']['last_6_hours'] += 1
                elif age_hours <= 24:
                    stats['time_distribution']['sessions']['last_24_hours'] += 1
                elif age_hours <= 168:  # 7 days
                    stats['time_distribution']['sessions']['last_7_days'] += 1
                else:
                    stats['time_distribution']['sessions']['older'] += 1
                
                # 会话详细信息
                session_duration = current_time - start_time
                stats['session_details'].append({
                    'session_id': session_id,
                    'start_time': start_time.isoformat(),
                    'last_activity': last_activity.isoformat(),
                    'conversation_count': conversation_count,
                    'duration_seconds': session_duration.total_seconds(),
                    'duration_formatted': str(session_duration),
                    'is_active': (current_time - last_activity).total_seconds() < 1800,
                    'browser_session_id': session_data.get('browser_session_id')
                })
            
            # 计算平均值
            if len(cache.session_info) > 0:
                stats['basic_stats']['average_conversations_per_session'] = total_conversations / len(cache.session_info)
            
            # 时间范围
            if session_times:
                stats['time_ranges']['oldest_session'] = min(session_times).isoformat()
                stats['time_ranges']['newest_session'] = max(session_times).isoformat()
        
        # 对话统计
        if hasattr(cache, 'conversation_start_times'):
            conversation_times = []
            for conv_time in cache.conversation_start_times.values():
                conversation_times.append(conv_time)
                age_hours = (current_time - conv_time).total_seconds() / 3600
                
                if age_hours <= 1:
                    stats['time_distribution']['conversations']['last_1_hour'] += 1
                elif age_hours <= 6:
                    stats['time_distribution']['conversations']['last_6_hours'] += 1
                elif age_hours <= 24:
                    stats['time_distribution']['conversations']['last_24_hours'] += 1
                elif age_hours <= 168:
                    stats['time_distribution']['conversations']['last_7_days'] += 1
                else:
                    stats['time_distribution']['conversations']['older'] += 1
            
            if conversation_times:
                stats['time_ranges']['oldest_conversation'] = min(conversation_times).isoformat()
                stats['time_ranges']['newest_conversation'] = max(conversation_times).isoformat()
        
        # 按最近活动排序会话详情
        stats['session_details'].sort(key=lambda x: x['last_activity'], reverse=True)
        
        return jsonify(result.success(data=stats))
        
    except Exception as e:
        return jsonify(result.failed(
            message=f"获取缓存统计失败: {str(e)}", 
            code=500
        )), 500


# ==================== 高级功能API ====================

@app.flask_app.route('/api/v0/cache_export', methods=['GET'])
def cache_export():
    """高级功能：完整导出 - 保持原cache_raw_export的完整功能"""
    try:
        cache = app.cache
        
        # 验证缓存的实际结构
        if not hasattr(cache, 'cache'):
            return jsonify(result.failed(message="缓存对象没有cache属性", code=500)), 500
        
        if not isinstance(cache.cache, dict):
            return jsonify(result.failed(message="缓存不是字典类型", code=500)), 500
        
        # 定义JSON序列化辅助函数
        def make_json_serializable(obj):
            """将对象转换为JSON可序列化的格式"""
            if obj is None:
                return None
            elif isinstance(obj, (str, int, float, bool)):
                return obj
            elif isinstance(obj, (list, tuple)):
                return [make_json_serializable(item) for item in obj]
            elif isinstance(obj, dict):
                return {str(k): make_json_serializable(v) for k, v in obj.items()}
            elif hasattr(obj, 'isoformat'):  # datetime objects
                return obj.isoformat()
            elif hasattr(obj, 'item'):  # numpy scalars
                return obj.item()
            elif hasattr(obj, 'tolist'):  # numpy arrays
                return obj.tolist()
            elif hasattr(obj, '__dict__'):  # pandas dtypes and other objects
                return str(obj)
            else:
                return str(obj)
        
        # 获取完整的原始缓存数据
        raw_cache = cache.cache
        
        # 获取会话和对话时间信息
        conversation_times = getattr(cache, 'conversation_start_times', {})
        session_info = getattr(cache, 'session_info', {})
        conversation_to_session = getattr(cache, 'conversation_to_session', {})
        
        export_data = {
            'export_metadata': {
                'export_time': datetime.now().isoformat(),
                'total_conversations': len(raw_cache),
                'total_sessions': len(session_info),
                'cache_type': type(cache).__name__,
                'cache_object_info': str(cache),
                'has_session_times': bool(session_info),
                'has_conversation_times': bool(conversation_times)
            },
            'session_info': {
                session_id: {
                    'start_time': session_data['start_time'].isoformat(),
                    'last_activity': session_data.get('last_activity', session_data['start_time']).isoformat(),
                    'conversations': session_data['conversations'],
                    'conversation_count': len(session_data['conversations']),
                    'browser_session_id': session_data.get('browser_session_id'),
                    'user_info': session_data.get('user_info', {})
                }
                for session_id, session_data in session_info.items()
            },
            'conversation_times': {
                conversation_id: start_time.isoformat() 
                for conversation_id, start_time in conversation_times.items()
            },
            'conversation_to_session_mapping': conversation_to_session,
            'conversations': {}
        }
        
        # 处理每个对话的完整数据
        for conversation_id, conversation_data in raw_cache.items():
            # 获取时间信息
            conversation_start_time = conversation_times.get(conversation_id)
            session_id = conversation_to_session.get(conversation_id)
            session_start_time = None
            if session_id and session_id in session_info:
                session_start_time = session_info[session_id]['start_time']
            
            processed_conversation = {
                'conversation_id': conversation_id,
                'conversation_start_time': conversation_start_time.isoformat() if conversation_start_time else None,
                'session_id': session_id,
                'session_start_time': session_start_time.isoformat() if session_start_time else None,
                'field_count': len(conversation_data),
                'fields': {}
            }
            
            # 添加时间计算
            if conversation_start_time:
                conversation_duration = datetime.now() - conversation_start_time
                processed_conversation['conversation_duration_seconds'] = conversation_duration.total_seconds()
                processed_conversation['conversation_duration_formatted'] = str(conversation_duration)
            
            if session_start_time:
                session_duration = datetime.now() - session_start_time
                processed_conversation['session_duration_seconds'] = session_duration.total_seconds()
                processed_conversation['session_duration_formatted'] = str(session_duration)
            
            # 处理每个字段，确保JSON序列化安全
            for field_name, field_value in conversation_data.items():
                field_info = {
                    'field_name': field_name,
                    'data_type': type(field_value).__name__,
                    'is_none': field_value is None
                }
                
                try:
                    if field_value is None:
                        field_info['value'] = None
                        
                    elif field_name in ['conversation_start_time', 'session_start_time']:
                        # 处理时间字段
                        field_info['content'] = make_json_serializable(field_value)
                        
                    elif field_name == 'df' and field_value is not None:
                        # DataFrame的安全处理
                        if hasattr(field_value, 'to_dict'):
                            # 安全地处理dtypes
                            try:
                                dtypes_dict = {}
                                for col, dtype in field_value.dtypes.items():
                                    dtypes_dict[col] = str(dtype)
                            except Exception:
                                dtypes_dict = {"error": "无法序列化dtypes"}
                            
                            # 安全地处理内存使用
                            try:
                                memory_usage = field_value.memory_usage(deep=True)
                                memory_dict = {}
                                for idx, usage in memory_usage.items():
                                    memory_dict[str(idx)] = int(usage) if hasattr(usage, 'item') else int(usage)
                            except Exception:
                                memory_dict = {"error": "无法获取内存使用信息"}
                            
                            field_info.update({
                                'dataframe_info': {
                                    'shape': list(field_value.shape),
                                    'columns': list(field_value.columns),
                                    'dtypes': dtypes_dict,
                                    'index_info': {
                                        'type': type(field_value.index).__name__,
                                        'length': len(field_value.index)
                                    }
                                },
                                'data': make_json_serializable(field_value.to_dict('records')),
                                'memory_usage': memory_dict
                            })
                        else:
                            field_info['value'] = str(field_value)
                            field_info['note'] = 'not_standard_dataframe'
                    
                    elif field_name == 'fig_json':
                        # 图表JSON数据处理
                        if isinstance(field_value, str):
                            try:
                                import json
                                parsed_fig = json.loads(field_value)
                                field_info.update({
                                    'json_valid': True,
                                    'json_size_bytes': len(field_value),
                                    'plotly_structure': {
                                        'has_data': 'data' in parsed_fig,
                                        'has_layout': 'layout' in parsed_fig,
                                        'data_traces_count': len(parsed_fig.get('data', [])),
                                    },
                                    'raw_json': field_value
                                })
                            except json.JSONDecodeError:
                                field_info.update({
                                    'json_valid': False,
                                    'raw_content': str(field_value)
                                })
                        else:
                            field_info['value'] = make_json_serializable(field_value)
                    
                    elif field_name == 'followup_questions':
                        # 后续问题列表
                        field_info.update({
                            'content': make_json_serializable(field_value)
                        })
                    
                    elif field_name in ['question', 'sql', 'summary']:
                        # 文本字段
                        if isinstance(field_value, str):
                            field_info.update({
                                'text_length': len(field_value),
                                'content': field_value
                            })
                        else:
                            field_info['value'] = make_json_serializable(field_value)
                    
                    else:
                        # 未知字段的安全处理
                        field_info['content'] = make_json_serializable(field_value)
                
                except Exception as e:
                    field_info.update({
                        'processing_error': str(e),
                        'fallback_value': str(field_value)[:500] + '...' if len(str(field_value)) > 500 else str(field_value)
                    })
                
                processed_conversation['fields'][field_name] = field_info
            
            export_data['conversations'][conversation_id] = processed_conversation
        
        # 添加缓存统计信息
        field_frequency = {}
        data_types_found = set()
        total_dataframes = 0
        total_questions = 0
        
        for conv_data in export_data['conversations'].values():
            for field_name, field_info in conv_data['fields'].items():
                field_frequency[field_name] = field_frequency.get(field_name, 0) + 1
                data_types_found.add(field_info['data_type'])
                
                if field_name == 'df' and not field_info['is_none']:
                    total_dataframes += 1
                if field_name == 'question' and not field_info['is_none']:
                    total_questions += 1
        
        export_data['cache_statistics'] = {
            'field_frequency': field_frequency,
            'data_types_found': list(data_types_found),
            'total_dataframes': total_dataframes,
            'total_questions': total_questions,
            'has_session_timing': 'session_start_time' in field_frequency,
            'has_conversation_timing': 'conversation_start_time' in field_frequency
        }
        
        return jsonify(result.success(data=export_data))
        
    except Exception as e:
        import traceback
        error_details = {
            'error_message': str(e),
            'error_type': type(e).__name__,
            'traceback': traceback.format_exc()
        }
        return jsonify(result.failed(
            message=f"导出缓存失败: {str(e)}", 
            code=500,
            data=error_details
        )), 500


# ==================== 清理功能API ====================

@app.flask_app.route('/api/v0/cache_preview_cleanup', methods=['POST'])
def cache_preview_cleanup():
    """清理功能：预览删除操作 - 保持原功能"""
    try:
        req = request.get_json(force=True)
        
        # 时间条件 - 支持三种方式
        older_than_hours = req.get('older_than_hours')
        older_than_days = req.get('older_than_days') 
        before_timestamp = req.get('before_timestamp')  # YYYY-MM-DD HH:MM:SS 格式
        
        cache = app.cache
        
        # 计算截止时间
        cutoff_time = None
        time_condition = None
        
        if older_than_hours:
            cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
            time_condition = f"older_than_hours: {older_than_hours}"
        elif older_than_days:
            cutoff_time = datetime.now() - timedelta(days=older_than_days)
            time_condition = f"older_than_days: {older_than_days}"
        elif before_timestamp:
            try:
                # 支持 YYYY-MM-DD HH:MM:SS 格式
                cutoff_time = datetime.strptime(before_timestamp, '%Y-%m-%d %H:%M:%S')
                time_condition = f"before_timestamp: {before_timestamp}"
            except ValueError:
                return jsonify(result.failed(
                    message="before_timestamp格式错误，请使用 YYYY-MM-DD HH:MM:SS 格式", 
                    code=400
                )), 400
        else:
            return jsonify(result.failed(
                message="必须提供时间条件：older_than_hours, older_than_days 或 before_timestamp (YYYY-MM-DD HH:MM:SS)", 
                code=400
            )), 400
        
        preview = {
            'time_condition': time_condition,
            'cutoff_time': cutoff_time.isoformat(),
            'will_be_removed': {
                'sessions': []
            },
            'will_be_kept': {
                'sessions_count': 0,
                'conversations_count': 0
            },
            'summary': {
                'sessions_to_remove': 0,
                'conversations_to_remove': 0,
                'sessions_to_keep': 0,
                'conversations_to_keep': 0
            }
        }
        
        # 预览按session删除
        sessions_to_remove_count = 0
        conversations_to_remove_count = 0
        
        for session_id, session_data in cache.session_info.items():
            session_preview = {
                'session_id': session_id,
                'start_time': session_data['start_time'].isoformat(),
                'conversation_count': len(session_data['conversations']),
                'conversations': []
            }
            
            # 添加conversation详情
            for conv_id in session_data['conversations']:
                if conv_id in cache.cache:
                    conv_data = cache.cache[conv_id]
                    session_preview['conversations'].append({
                        'conversation_id': conv_id,
                        'question': conv_data.get('question', '')[:50] + '...' if conv_data.get('question') else '',
                        'start_time': cache.conversation_start_times.get(conv_id, '').isoformat() if cache.conversation_start_times.get(conv_id) else ''
                    })
            
            if session_data['start_time'] < cutoff_time:
                preview['will_be_removed']['sessions'].append(session_preview)
                sessions_to_remove_count += 1
                conversations_to_remove_count += len(session_data['conversations'])
            else:
                preview['will_be_kept']['sessions_count'] += 1
                preview['will_be_kept']['conversations_count'] += len(session_data['conversations'])
        
        # 更新摘要统计
        preview['summary'] = {
            'sessions_to_remove': sessions_to_remove_count,
            'conversations_to_remove': conversations_to_remove_count,
            'sessions_to_keep': preview['will_be_kept']['sessions_count'],
            'conversations_to_keep': preview['will_be_kept']['conversations_count']
        }
        
        return jsonify(result.success(data=preview))
        
    except Exception as e:
        return jsonify(result.failed(
            message=f"预览清理操作失败: {str(e)}", 
            code=500
        )), 500


@app.flask_app.route('/api/v0/cache_cleanup', methods=['POST'])
def cache_cleanup():
    """清理功能：实际删除缓存 - 保持原功能"""
    try:
        req = request.get_json(force=True)
        
        # 时间条件 - 支持三种方式
        older_than_hours = req.get('older_than_hours')
        older_than_days = req.get('older_than_days') 
        before_timestamp = req.get('before_timestamp')  # YYYY-MM-DD HH:MM:SS 格式
        
        cache = app.cache
        
        if not hasattr(cache, 'session_info'):
            return jsonify(result.failed(
                message="缓存不支持会话功能", 
                code=400
            )), 400
        
        # 计算截止时间
        cutoff_time = None
        time_condition = None
        
        if older_than_hours:
            cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
            time_condition = f"older_than_hours: {older_than_hours}"
        elif older_than_days:
            cutoff_time = datetime.now() - timedelta(days=older_than_days)
            time_condition = f"older_than_days: {older_than_days}"
        elif before_timestamp:
            try:
                # 支持 YYYY-MM-DD HH:MM:SS 格式
                cutoff_time = datetime.strptime(before_timestamp, '%Y-%m-%d %H:%M:%S')
                time_condition = f"before_timestamp: {before_timestamp}"
            except ValueError:
                return jsonify(result.failed(
                    message="before_timestamp格式错误，请使用 YYYY-MM-DD HH:MM:SS 格式", 
                    code=400
                )), 400
        else:
            return jsonify(result.failed(
                message="必须提供时间条件：older_than_hours, older_than_days 或 before_timestamp (YYYY-MM-DD HH:MM:SS)", 
                code=400
            )), 400
        
        cleanup_stats = {
            'time_condition': time_condition,
            'cutoff_time': cutoff_time.isoformat(),
            'sessions_removed': 0,
            'conversations_removed': 0,
            'sessions_kept': 0,
            'conversations_kept': 0,
            'removed_session_ids': [],
            'removed_conversation_ids': []
        }
        
        # 按session删除
        sessions_to_remove = []
        
        for session_id, session_data in cache.session_info.items():
            if session_data['start_time'] < cutoff_time:
                sessions_to_remove.append(session_id)
        
        # 删除符合条件的sessions及其所有conversations
        for session_id in sessions_to_remove:
            session_data = cache.session_info[session_id]
            conversations_in_session = session_data['conversations'].copy()
            
            # 删除session中的所有conversations
            for conv_id in conversations_in_session:
                if conv_id in cache.cache:
                    del cache.cache[conv_id]
                    cleanup_stats['conversations_removed'] += 1
                    cleanup_stats['removed_conversation_ids'].append(conv_id)
                
                # 清理conversation相关的时间记录
                if hasattr(cache, 'conversation_start_times') and conv_id in cache.conversation_start_times:
                    del cache.conversation_start_times[conv_id]
                
                if hasattr(cache, 'conversation_to_session') and conv_id in cache.conversation_to_session:
                    del cache.conversation_to_session[conv_id]
            
            # 删除session记录
            del cache.session_info[session_id]
            cleanup_stats['sessions_removed'] += 1
            cleanup_stats['removed_session_ids'].append(session_id)
        
        # 统计保留的sessions和conversations
        cleanup_stats['sessions_kept'] = len(cache.session_info)
        cleanup_stats['conversations_kept'] = len(cache.cache)
        
        return jsonify(result.success(data=cleanup_stats))
        
    except Exception as e:
        return jsonify(result.failed(
            message=f"清理缓存失败: {str(e)}", 
            code=500
        )), 500
    

@app.flask_app.route('/api/v0/training_error_question_sql', methods=['POST'])
def training_error_question_sql():
    """
    存储错误的question-sql对到error_sql集合中
    
    此API将接收的错误question/sql pair写入到error_sql集合中，用于记录和分析错误的SQL查询。
    
    Args:
        question (str, required): 用户问题
        sql (str, required): 对应的错误SQL查询语句
    
    Returns:
        JSON: 包含训练ID和成功消息的响应
    """
    try:
        data = request.get_json()
        question = data.get('question')
        sql = data.get('sql')
        
        print(f"[DEBUG] 接收到错误SQL训练请求: question={question}, sql={sql}")
        
        if not question or not sql:
            return jsonify(result.failed(
                message="question和sql参数都是必需的", 
                code=400
            )), 400
        
        # 使用vn实例的train_error_sql方法存储错误SQL
        id = vn.train_error_sql(question=question, sql=sql)
        
        print(f"[INFO] 成功存储错误SQL，ID: {id}")
        
        return jsonify(result.success(data={
            "id": id,
            "message": "错误SQL对已成功存储到error_sql集合"
        }))
        
    except Exception as e:
        print(f"[ERROR] 存储错误SQL失败: {str(e)}")
        return jsonify(result.failed(
            message=f"存储错误SQL失败: {str(e)}", 
            code=500
        )), 500



# 前端JavaScript示例 - 如何维持会话
"""
// 前端需要维护一个会话ID
class ChatSession {
    constructor() {
        // 从localStorage获取或创建新的会话ID
        this.sessionId = localStorage.getItem('chat_session_id') || this.generateSessionId();
        localStorage.setItem('chat_session_id', this.sessionId);
    }
    
    generateSessionId() {
        return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }
    
    async askQuestion(question) {
        const response = await fetch('/api/v0/ask', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                question: question,
                session_id: this.sessionId  // 关键：传递会话ID
            })
        });
        return await response.json();
    }
    
    // 开始新会话
    startNewSession() {
        this.sessionId = this.generateSessionId();
        localStorage.setItem('chat_session_id', this.sessionId);
    }
}

// 使用示例
const chatSession = new ChatSession();
chatSession.askQuestion("各年龄段客户的流失率如何？");
"""

print("正在启动Flask应用: http://localhost:8084")
app.run(host="0.0.0.0", port=8084, debug=True)