# agent/tools/general_chat.py
from langchain.tools import tool
from typing import Dict, Any, Optional
from common.utils import get_current_llm_config
from customllm.qianwen_chat import QianWenChat

@tool
def general_chat(question: str, context: Optional[str] = None) -> Dict[str, Any]:
    """
    处理一般性对话和咨询。
    
    Args:
        question: 用户的问题或对话内容
        context: 上下文信息，可选
        
    Returns:
        包含聊天响应的字典，格式：
        {
            "success": bool,
            "response": str,
            "error": str或None
        }
    """
    try:
        print(f"[TOOL:general_chat] 处理聊天问题: {question}")
        
        system_prompt = """
你是Cito智能数据问答平台的AI助手，专门为用户提供帮助和支持。

你的职责包括：
1. 回答关于平台功能和使用方法的问题
2. 解释数据分析相关的概念和术语
3. 提供操作指导和建议
4. 进行友好的日常对话

回答原则：
- 保持友好、专业的语调
- 提供准确、有用的信息
- 如果不确定某个问题，诚实地表达不确定性
- 鼓励用户尝试数据查询功能
- 回答要简洁明了，避免过于冗长
- 保持中文回答，语言自然流畅
"""
        
        # 生成聊天响应
        llm_config = get_current_llm_config()
        llm = QianWenChat(config=llm_config)
        
        messages = [llm.system_message(system_prompt)]
        
        if context:
            messages.append(llm.user_message(f"上下文信息：{context}"))
        
        messages.append(llm.user_message(question))
        
        response = llm.submit_prompt(messages)
        
        if response:
            print(f"[TOOL:general_chat] 聊天响应生成成功: {response[:100]}...")
            return {
                "success": True,
                "response": response.strip(),
                "message": "聊天响应生成成功"
            }
        else:
            return {
                "success": False,
                "response": _get_fallback_response(question),
                "error": "无法生成聊天响应"
            }
            
    except Exception as e:
        print(f"[ERROR] 通用聊天异常: {str(e)}")
        return {
            "success": False,
            "response": _get_fallback_response(question),
            "error": f"聊天服务异常: {str(e)}"
        }

def _get_fallback_response(question: str) -> str:
    """获取备用响应"""
    question_lower = question.lower()
    
    if any(keyword in question_lower for keyword in ["你好", "hello", "hi"]):
        return "您好！我是Cito智能数据问答平台的AI助手。我可以帮助您进行数据查询和分析，也可以回答关于平台使用的问题。有什么可以帮助您的吗？"
    
    elif any(keyword in question_lower for keyword in ["谢谢", "thank"]):
        return "不客气！如果您还有其他问题，随时可以问我。我可以帮您查询数据或解答疑问。"
    
    elif any(keyword in question_lower for keyword in ["再见", "bye"]):
        return "再见！期待下次为您服务。如果需要数据查询或其他帮助，随时欢迎回来！"
    
    elif any(keyword in question_lower for keyword in ["怎么", "如何", "怎样"]):
        return "我理解您想了解使用方法。Cito平台支持自然语言数据查询，您可以直接用中文描述您想要查询的数据，比如'查询本月销售额'或'统计各部门人数'等。有具体问题欢迎继续询问！"
    
    elif any(keyword in question_lower for keyword in ["功能", "作用", "能做"]):
        return "我主要可以帮助您：\n1. 进行数据库查询和分析\n2. 解答平台使用问题\n3. 解释数据相关概念\n4. 提供操作指导\n\n您可以用自然语言描述数据需求，我会帮您生成相应的查询。"
    
    else:
        return "抱歉，我暂时无法理解您的问题。您可以：\n1. 尝试用更具体的方式描述问题\n2. 询问平台使用方法\n3. 进行数据查询（如'查询销售数据'）\n\n我会尽力为您提供帮助！"