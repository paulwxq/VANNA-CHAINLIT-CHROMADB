# 简化后的对话感知缓存
from datetime import datetime
from vanna.flask import MemoryCache
import uuid

class ConversationAwareMemoryCache(MemoryCache):
    """基于对话ID的简单时间感知缓存实现"""
    
    def __init__(self):
        super().__init__()
        self.conversation_start_times = {}  # 每个对话的开始时间: {conversation_id: datetime}
    
    def generate_id(self, question: str = None, user_id: str = None) -> str:
        """生成对话ID并记录时间，格式为 {user_id}:YYYYMMDDHHMMSSsss"""
        # 如果没有传递user_id，使用默认值
        if not user_id:
            user_id = "guest"
        
        # 生成时间戳：年月日时分秒毫秒格式
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}"
        
        # 生成对话ID：{user_id}:{timestamp}
        conversation_id = f"{user_id}:{timestamp}"
        
        # 记录对话开始时间
        self.conversation_start_times[conversation_id] = now
        
        return conversation_id
    
    def set(self, id: str, field: str, value, **kwargs):
        """重载set方法，确保时间信息正确"""
        # 如果这是新对话，初始化时间信息
        if id not in self.conversation_start_times:
            self.conversation_start_times[id] = datetime.now()
        
        # 调用父类的set方法
        super().set(id=id, field=field, value=value)
        
        # 自动设置对话开始时间字段
        if field != 'conversation_start_time':
            super().set(id=id, field='conversation_start_time', 
                       value=self.conversation_start_times[id])
    
    def get_conversation_start_time(self, conversation_id: str) -> datetime:
        """获取对话开始时间"""
        return self.conversation_start_times.get(conversation_id)
    
    def get_conversation_info(self, conversation_id: str):
        """获取对话信息"""
        start_time = self.get_conversation_start_time(conversation_id)
        if start_time:
            duration = datetime.now() - start_time
            
            # 从conversation_id解析user_id
            user_id = "unknown"
            if ":" in conversation_id:
                user_id = conversation_id.split(":")[0]
            
            return {
                'conversation_id': conversation_id,
                'user_id': user_id,
                'start_time': start_time,
                'duration_seconds': duration.total_seconds(),
                'duration_formatted': str(duration)
            }
        return None
    
    def get_all_conversations(self):
        """获取所有对话信息"""
        result = {}
        for conversation_id, start_time in self.conversation_start_times.items():
            duration = datetime.now() - start_time
            
            # 从conversation_id解析user_id
            user_id = "unknown"
            if ":" in conversation_id:
                user_id = conversation_id.split(":")[0]
                
            result[conversation_id] = {
                'user_id': user_id,
                'start_time': start_time,
                'duration_seconds': duration.total_seconds(),
                'duration_formatted': str(duration)
            }
        return result

    @staticmethod
    def parse_conversation_id(conversation_id: str):
        """解析conversation_id，返回user_id和timestamp"""
        if ":" not in conversation_id:
            return None, None
        
        parts = conversation_id.split(":", 1)
        user_id = parts[0]
        timestamp_str = parts[1]
        
        try:
            # 解析时间戳：YYYYMMDDHHMMSSsss
            if len(timestamp_str) == 17:  # 20250722204550155
                timestamp = datetime.strptime(timestamp_str[:14], "%Y%m%d%H%M%S")
                # 添加毫秒
                milliseconds = int(timestamp_str[14:])
                timestamp = timestamp.replace(microsecond=milliseconds * 1000)
                return user_id, timestamp
        except ValueError:
            pass
        
        return user_id, None

    @staticmethod
    def extract_user_id(conversation_id: str) -> str:
        """从conversation_id中提取user_id"""
        if ":" not in conversation_id:
            return "unknown"
        return conversation_id.split(":", 1)[0]

    @staticmethod
    def validate_user_id_consistency(conversation_id: str, provided_user_id: str) -> tuple[bool, str]:
        """
        校验conversation_id中的user_id与提供的user_id是否一致
        
        Returns:
            tuple: (is_valid, error_message)
        """
        if not conversation_id or not provided_user_id:
            return True, ""  # 如果任一为空，跳过校验
        
        extracted_user_id = ConversationAwareMemoryCache.extract_user_id(conversation_id)
        
        if extracted_user_id != provided_user_id:
            return False, f"用户ID不匹配：conversation_id中的用户ID '{extracted_user_id}' 与提供的用户ID '{provided_user_id}' 不一致"
        
        return True, ""


# 保持向后兼容的别名
WebSessionAwareMemoryCache = ConversationAwareMemoryCache
SessionAwareMemoryCache = ConversationAwareMemoryCache