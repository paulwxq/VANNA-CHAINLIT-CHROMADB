# agent/utils.py
"""
Agent相关的工具函数
"""
import functools
from typing import Dict, Any, Callable
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage

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
    """自定义LLM的LangChain兼容包装器"""
    
    def __init__(self, llm_instance):
        self.llm = llm_instance
        self._model_name = getattr(llm_instance, 'model', 'custom_llm')
    
    def invoke(self, input_data, **kwargs):
        """LangChain invoke接口"""
        try:
            if isinstance(input_data, str):
                messages = [HumanMessage(content=input_data)]
            elif isinstance(input_data, list):
                messages = input_data
            else:
                messages = [HumanMessage(content=str(input_data))]
            
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
            
        except Exception as e:
            print(f"[ERROR] LLM包装器调用失败: {str(e)}")
            return AIMessage(content=f"LLM调用失败: {str(e)}")
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    def bind_tools(self, tools):
        """绑定工具（用于支持工具调用）"""
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
                return ChatOpenAI(
                    base_url=llm_config.get("base_url"),
                    api_key=llm_config.get("api_key"),
                    model=llm_config.get("model"),
                    temperature=llm_config.get("temperature", 0.7)
                )
            except ImportError:
                print("[WARNING] langchain_openai 未安装，使用自定义包装器")
        
        # 使用自定义LLM包装器
        from customllm.qianwen_chat import QianWenChat
        custom_llm = QianWenChat(config=llm_config)
        return LLMWrapper(custom_llm)
        
    except Exception as e:
        print(f"[ERROR] 获取LLM失败: {str(e)}")
        # 返回基础包装器
        from common.utils import get_current_llm_config
        from customllm.qianwen_chat import QianWenChat
        
        llm_config = get_current_llm_config()
        custom_llm = QianWenChat(config=llm_config)
        return LLMWrapper(custom_llm)