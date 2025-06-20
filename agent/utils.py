# agent/utils.py
"""
Agent相关的工具函数
"""
import functools
import json
from typing import Dict, Any, Callable, List, Optional
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

def handle_tool_errors(func: Callable) -> Callable:
    """
    工具函数错误处理装饰器
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Dict[str, Any]:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"[ERROR] 工具 {func.__name__} 执行失败: {str(e)}")
            return {
                "success": False,
                "error": f"工具执行异常: {str(e)}",
                "error_type": "tool_exception"
            }
    return wrapper

class LLMWrapper:
    """自定义LLM的LangChain兼容包装器，支持工具调用"""
    
    def __init__(self, llm_instance):
        self.llm = llm_instance
        self._model_name = getattr(llm_instance, 'model', 'custom_llm')
        self._bound_tools = []
    
    def invoke(self, input_data, **kwargs):
        """LangChain invoke接口"""
        try:
            if isinstance(input_data, str):
                messages = [HumanMessage(content=input_data)]
            elif isinstance(input_data, list):
                messages = input_data
            else:
                messages = [HumanMessage(content=str(input_data))]
            
            # 检查是否需要工具调用
            if self._bound_tools and self._should_use_tools(messages):
                return self._invoke_with_tools(messages, **kwargs)
            else:
                return self._invoke_without_tools(messages, **kwargs)
                
        except Exception as e:
            print(f"[ERROR] LLM包装器调用失败: {str(e)}")
            return AIMessage(content=f"LLM调用失败: {str(e)}")
    
    def _should_use_tools(self, messages: List[BaseMessage]) -> bool:
        """判断是否应该使用工具"""
        # 检查最后一条消息是否包含工具相关的指令
        if messages:
            last_message = messages[-1]
            if isinstance(last_message, HumanMessage):
                content = last_message.content.lower()
                # 检查是否包含工具相关的关键词
                tool_keywords = ["生成sql", "执行sql", "generate sql", "execute sql", "查询", "数据库"]
                return any(keyword in content for keyword in tool_keywords)
        return True  # 默认使用工具
    
    def _invoke_with_tools(self, messages: List[BaseMessage], **kwargs):
        """使用工具调用的方式"""
        try:
            # 构建工具调用提示
            tool_prompt = self._build_tool_prompt(messages)
            
            # 调用底层LLM
            response = self.llm.submit_prompt(tool_prompt, **kwargs)
            
            # 解析工具调用
            tool_calls = self._parse_tool_calls(response)
            
            if tool_calls:
                # 如果有工具调用，返回包含工具调用的AIMessage
                return AIMessage(
                    content=response,
                    tool_calls=tool_calls
                )
            else:
                # 没有工具调用，返回普通响应
                return AIMessage(content=response)
                
        except Exception as e:
            print(f"[ERROR] 工具调用失败: {str(e)}")
            return self._invoke_without_tools(messages, **kwargs)
    
    def _invoke_without_tools(self, messages: List[BaseMessage], **kwargs):
        """不使用工具的普通调用"""
        # 转换消息格式
        prompt = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                prompt.append(self.llm.system_message(msg.content))
            elif isinstance(msg, HumanMessage):
                prompt.append(self.llm.user_message(msg.content))
            elif isinstance(msg, AIMessage):
                prompt.append(self.llm.assistant_message(msg.content))
            else:
                prompt.append(self.llm.user_message(str(msg.content)))
        
        # 调用底层LLM
        response = self.llm.submit_prompt(prompt, **kwargs)
        
        # 返回LangChain格式的结果
        return AIMessage(content=response)
    
    def _build_tool_prompt(self, messages: List[BaseMessage]) -> List[Dict[str, str]]:
        """构建包含工具信息的提示"""
        prompt = []
        
        # 添加系统消息，包含工具定义
        system_content = self._get_system_message_with_tools(messages)
        prompt.append(self.llm.system_message(system_content))
        
        # 添加用户消息
        for msg in messages:
            if isinstance(msg, HumanMessage):
                prompt.append(self.llm.user_message(msg.content))
            elif isinstance(msg, AIMessage) and not isinstance(msg, SystemMessage):
                prompt.append(self.llm.assistant_message(msg.content))
        
        return prompt
    
    def _get_system_message_with_tools(self, messages: List[BaseMessage]) -> str:
        """获取包含工具定义的系统消息"""
        # 查找原始系统消息
        original_system = ""
        for msg in messages:
            if isinstance(msg, SystemMessage):
                original_system = msg.content
                break
        
        # 构建工具定义
        tool_definitions = []
        for tool in self._bound_tools:
            tool_def = {
                "name": tool.name,
                "description": tool.description,
                "parameters": getattr(tool, 'args_schema', {})
            }
            tool_definitions.append(f"- {tool.name}: {tool.description}")
        
        # 组合系统消息
        if tool_definitions:
            tools_text = "\n".join(tool_definitions)
            return f"""{original_system}

你有以下工具可以使用：
{tools_text}

使用工具时，请明确说明你要调用哪个工具以及需要的参数。对于数据库查询问题，请按照以下步骤：
1. 使用 generate_sql 工具生成SQL查询
2. 使用 execute_sql 工具执行SQL查询
3. 使用 generate_summary 工具生成结果摘要

请直接开始执行工具调用，不要只是提供指导。"""
        else:
            return original_system
    
    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """解析LLM响应中的工具调用"""
        tool_calls = []
        
        # 简单的工具调用解析逻辑
        # 这里可以根据实际的LLM响应格式进行调整
        
        response_lower = response.lower()
        if "generate_sql" in response_lower:
            tool_calls.append({
                "name": "generate_sql",
                "args": {},
                "id": "generate_sql_call"
            })
        
        return tool_calls
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    def bind_tools(self, tools):
        """绑定工具（用于支持工具调用）"""
        self._bound_tools = tools if isinstance(tools, list) else [tools]
        return self

def get_compatible_llm():
    """获取兼容的LLM实例"""
    try:
        from common.utils import get_current_llm_config
        llm_config = get_current_llm_config()
        
        # 尝试使用标准的OpenAI兼容API
        if llm_config.get("base_url") and llm_config.get("api_key"):
            try:
                from langchain_openai import ChatOpenAI
                llm = ChatOpenAI(
                    base_url=llm_config.get("base_url"),
                    api_key=llm_config.get("api_key"),
                    model=llm_config.get("model"),
                    temperature=llm_config.get("temperature", 0.7)
                )
                print("[INFO] 使用标准OpenAI兼容API")
                return llm
            except ImportError:
                print("[WARNING] langchain_openai 未安装，使用 Vanna 实例包装器")
        
        # 优先使用统一的 Vanna 实例
        from common.vanna_instance import get_vanna_instance
        vn = get_vanna_instance()
        print("[INFO] 使用Vanna实例包装器")
        return LLMWrapper(vn)
        
    except Exception as e:
        print(f"[ERROR] 获取 Vanna 实例失败: {str(e)}")
        # 回退到原有逻辑
        from common.utils import get_current_llm_config
        from customllm.qianwen_chat import QianWenChat
        
        llm_config = get_current_llm_config()
        custom_llm = QianWenChat(config=llm_config)
        print("[INFO] 使用QianWen包装器")
        return LLMWrapper(custom_llm)

def _is_valid_sql_format(sql_text: str) -> bool:
    """验证文本是否为有效的SQL查询格式"""
    if not sql_text or not sql_text.strip():
        return False
    
    sql_clean = sql_text.strip().upper()
    
    # 检查是否以SQL关键字开头
    sql_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP', 'WITH']
    starts_with_sql = any(sql_clean.startswith(keyword) for keyword in sql_keywords)
    
    # 检查是否包含解释性语言
    explanation_phrases = [
        '无法', '不能', '抱歉', 'SORRY', 'UNABLE', 'CANNOT', 
        '需要更多信息', '请提供', '表不存在', '字段不存在',
        '不清楚', '不确定', '没有足够', '无法理解', '无法生成',
        '无法确定', '不支持', '不可用', '缺少', '未找到'
    ]
    contains_explanation = any(phrase in sql_clean for phrase in explanation_phrases)
    
    return starts_with_sql and not contains_explanation