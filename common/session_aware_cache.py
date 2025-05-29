# 修正后的 custom_cache.py
from datetime import datetime
from vanna.flask import MemoryCache
import uuid

class SessionAwareMemoryCache(MemoryCache):
    """区分会话(Session)和对话(Conversation)的缓存实现"""
    
    def __init__(self):
        super().__init__()
        self.conversation_start_times = {}  # 每个对话的开始时间
        self.session_info = {}  # 会话信息: {session_id: {'start_time': datetime, 'conversations': []}}
        self.conversation_to_session = {}  # 对话ID到会话ID的映射
    
    def create_or_get_session_id(self, user_identifier=None):
        """
        创建或获取会话ID
        在实际应用中，这可以通过以下方式确定：
        1. HTTP请求中的session cookie
        2. JWT token中的session信息
        3. 前端传递的session_id
        4. IP地址 + User-Agent的组合
        """
        # 简化实现：使用时间窗口来判断是否为同一会话
        # 实际应用中应该从HTTP请求中获取session信息
        current_time = datetime.now()
        
        # 检查是否有近期的会话（比如30分钟内）
        for session_id, session_data in self.session_info.items():
            last_activity = session_data.get('last_activity', session_data['start_time'])
            if (current_time - last_activity).total_seconds() < 1800:  # 30分钟内
                # 更新最后活动时间
                session_data['last_activity'] = current_time
                return session_id
        
        # 创建新会话
        new_session_id = str(uuid.uuid4())
        self.session_info[new_session_id] = {
            'start_time': current_time,
            'last_activity': current_time,
            'conversations': []
        }
        return new_session_id
    
    def generate_id(self, question: str = None, session_id: str = None) -> str:
        """重载generate_id方法，关联会话和对话"""
        conversation_id = super().generate_id(question=question)
        
        # 确定会话ID
        if not session_id:
            session_id = self.create_or_get_session_id()
        
        # 记录对话开始时间
        conversation_start_time = datetime.now()
        self.conversation_start_times[conversation_id] = conversation_start_time
        
        # 建立对话与会话的关联
        self.conversation_to_session[conversation_id] = session_id
        self.session_info[session_id]['conversations'].append(conversation_id)
        self.session_info[session_id]['last_activity'] = conversation_start_time
        
        return conversation_id
    
    def set(self, id: str, field: str, value, session_id: str = None):
        """重载set方法，确保时间信息正确"""
        # 如果这是新对话，初始化时间信息
        if id not in self.conversation_start_times:
            if not session_id:
                session_id = self.create_or_get_session_id()
            
            conversation_start_time = datetime.now()
            self.conversation_start_times[id] = conversation_start_time
            self.conversation_to_session[id] = session_id
            self.session_info[session_id]['conversations'].append(id)
            self.session_info[session_id]['last_activity'] = conversation_start_time
        
        # 调用父类的set方法
        super().set(id=id, field=field, value=value)
        
        # 设置时间相关字段
        if field != 'conversation_start_time' and field != 'session_start_time':
            # 设置对话开始时间
            super().set(id=id, field='conversation_start_time', 
                       value=self.conversation_start_times[id])
            
            # 设置会话开始时间
            session_id = self.conversation_to_session.get(id)
            if session_id and session_id in self.session_info:
                super().set(id=id, field='session_start_time', 
                           value=self.session_info[session_id]['start_time'])
                super().set(id=id, field='session_id', value=session_id)
    
    def get_conversation_start_time(self, conversation_id: str) -> datetime:
        """获取对话开始时间"""
        return self.conversation_start_times.get(conversation_id)
    
    def get_session_start_time(self, conversation_id: str) -> datetime:
        """获取会话开始时间"""
        session_id = self.conversation_to_session.get(conversation_id)
        if session_id and session_id in self.session_info:
            return self.session_info[session_id]['start_time']
        return None
    
    def get_session_info(self, session_id: str = None, conversation_id: str = None):
        """获取会话信息"""
        if conversation_id:
            session_id = self.conversation_to_session.get(conversation_id)
        
        if session_id and session_id in self.session_info:
            session_data = self.session_info[session_id].copy()
            session_data['conversation_count'] = len(session_data['conversations'])
            if session_data['conversations']:
                # 计算会话持续时间
                duration = datetime.now() - session_data['start_time']
                session_data['session_duration_seconds'] = duration.total_seconds()
                session_data['session_duration_formatted'] = str(duration)
            return session_data
        return None
    
    def get_all_sessions(self):
        """获取所有会话信息"""
        result = {}
        for session_id, session_data in self.session_info.items():
            session_info = session_data.copy()
            session_info['conversation_count'] = len(session_data['conversations'])
            if session_data['conversations']:
                duration = datetime.now() - session_data['start_time']
                session_info['session_duration_seconds'] = duration.total_seconds()
                session_info['session_duration_formatted'] = str(duration)
            result[session_id] = session_info
        return result


# 升级版：支持前端传递会话ID
class WebSessionAwareMemoryCache(SessionAwareMemoryCache):
    """支持从前端获取会话ID的版本"""
    
    def __init__(self):
        super().__init__()
        self.browser_sessions = {}  # browser_session_id -> our_session_id
    
    def register_browser_session(self, browser_session_id: str, user_info: dict = None):
        """注册浏览器会话"""
        if browser_session_id not in self.browser_sessions:
            our_session_id = str(uuid.uuid4())
            self.browser_sessions[browser_session_id] = our_session_id
            
            self.session_info[our_session_id] = {
                'start_time': datetime.now(),
                'last_activity': datetime.now(),
                'conversations': [],
                'browser_session_id': browser_session_id,
                'user_info': user_info or {}
            }
        return self.browser_sessions[browser_session_id]
    
    def generate_id_with_browser_session(self, question: str = None, browser_session_id: str = None) -> str:
        """使用浏览器会话ID生成对话ID"""
        if browser_session_id:
            our_session_id = self.register_browser_session(browser_session_id)
        else:
            our_session_id = self.create_or_get_session_id()
        
        return super().generate_id(question=question, session_id=our_session_id)