import redis
import json
import hashlib
import uuid
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from app_config import (
    REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD,
    CONVERSATION_CONTEXT_COUNT, CONVERSATION_MAX_LENGTH, USER_MAX_CONVERSATIONS,
    CONVERSATION_TTL, USER_CONVERSATIONS_TTL, QUESTION_ANSWER_TTL,
    ENABLE_CONVERSATION_CONTEXT, ENABLE_QUESTION_ANSWER_CACHE,
    DEFAULT_ANONYMOUS_USER_PREFIX, MAX_GUEST_CONVERSATIONS, MAX_REGISTERED_CONVERSATIONS,
    GUEST_USER_TTL
)

class RedisConversationManager:
    """Redis对话管理器 - 修正版"""
    
    def __init__(self):
        """初始化Redis连接"""
        try:
            self.redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # 测试连接
            self.redis_client.ping()
            print(f"[REDIS_CONV] Redis连接成功: {REDIS_HOST}:{REDIS_PORT}")
        except Exception as e:
            print(f"[ERROR] Redis连接失败: {str(e)}")
            self.redis_client = None
    
    def is_available(self) -> bool:
        """检查Redis是否可用"""
        try:
            return self.redis_client is not None and self.redis_client.ping()
        except:
            return False
    
    # ==================== 用户ID解析（修正版）====================
    
    def resolve_user_id(self, user_id_from_request: Optional[str], 
                       session_id: Optional[str], request_ip: str,
                       login_user_id: Optional[str] = None) -> str:
        """
        智能解析用户ID - 修正版
        
        Args:
            user_id_from_request: 请求参数中的user_id
            session_id: 浏览器session_id
            request_ip: 请求IP地址
            login_user_id: 从Flask session中获取的登录用户ID（在ask_agent中获取）
        """
        
        # 1. 优先使用登录用户ID
        if login_user_id:
            print(f"[REDIS_CONV] 使用登录用户ID: {login_user_id}")
            return login_user_id
        
        # 2. 如果没有登录，尝试从请求参数获取user_id
        if user_id_from_request:
            print(f"[REDIS_CONV] 使用请求参数user_id: {user_id_from_request}")
            return user_id_from_request
        
        # 3. 都没有则为匿名用户（guest）
        if session_id:
            guest_suffix = hashlib.md5(session_id.encode()).hexdigest()[:8]
            guest_id = f"{DEFAULT_ANONYMOUS_USER_PREFIX}_{guest_suffix}"
            print(f"[REDIS_CONV] 生成稳定guest用户: {guest_id}")
            return guest_id
        
        # 4. 最后基于IP的临时guest ID
        ip_suffix = hashlib.md5(request_ip.encode()).hexdigest()[:8]
        temp_guest_id = f"{DEFAULT_ANONYMOUS_USER_PREFIX}_temp_{ip_suffix}"
        print(f"[REDIS_CONV] 生成临时guest用户: {temp_guest_id}")
        return temp_guest_id
    
    def resolve_conversation_id(self, user_id: str, conversation_id_input: Optional[str], 
                              continue_conversation: bool) -> tuple[str, dict]:
        """
        智能解析对话ID - 改进版
        
        Returns:
            tuple: (conversation_id, status_info)
            status_info包含:
            - status: "existing" | "new" | "invalid_id_new"
            - message: 状态说明
            - requested_id: 原始请求的ID（如果有）
        """
        
        # 1. 如果指定了conversation_id，验证后使用
        if conversation_id_input:
            if self._is_valid_conversation(conversation_id_input, user_id):
                print(f"[REDIS_CONV] 使用指定对话: {conversation_id_input}")
                return conversation_id_input, {
                    "status": "existing",
                    "message": "继续已有对话"
                }
            else:
                print(f"[WARN] 无效的conversation_id: {conversation_id_input}，创建新对话")
                new_conversation_id = self.create_conversation(user_id)
                return new_conversation_id, {
                    "status": "invalid_id_new",
                    "message": "您请求的对话不存在或无权访问，已为您创建新对话",
                    "requested_id": conversation_id_input
                }
        
        # 2. 如果要继续最近对话
        if continue_conversation:
            recent_conversation = self._get_recent_conversation(user_id)
            if recent_conversation:
                print(f"[REDIS_CONV] 继续最近对话: {recent_conversation}")
                return recent_conversation, {
                    "status": "existing",
                    "message": "继续最近对话"
                }
        
        # 3. 创建新对话
        new_conversation_id = self.create_conversation(user_id)
        print(f"[REDIS_CONV] 创建新对话: {new_conversation_id}")
        return new_conversation_id, {
            "status": "new",
            "message": "创建新对话"
        }
    
    def _is_valid_conversation(self, conversation_id: str, user_id: str) -> bool:
        """验证对话是否存在且属于该用户"""
        if not self.is_available():
            return False
        
        try:
            # 检查对话元信息是否存在
            meta_data = self.redis_client.hgetall(f"conversation:{conversation_id}:meta")
            if not meta_data:
                return False
            
            # 检查是否属于该用户
            return meta_data.get('user_id') == user_id
            
        except Exception:
            return False
    
    def _get_recent_conversation(self, user_id: str) -> Optional[str]:
        """获取用户最近的对话ID"""
        if not self.is_available():
            return None
        
        try:
            conversations = self.redis_client.lrange(
                f"user:{user_id}:conversations", 0, 0
            )
            return conversations[0] if conversations else None
        except Exception:
            return None
    
    # ==================== 对话管理 ====================
    
    def create_conversation(self, user_id: str) -> str:
        """创建新对话"""
        # 生成包含时间戳的conversation_id
        timestamp = int(datetime.now().timestamp())
        conversation_id = f"conv_{timestamp}_{uuid.uuid4().hex[:8]}"
        
        if not self.is_available():
            return conversation_id  # Redis不可用时返回ID，但不存储
        
        try:
            # 创建对话元信息
            meta_data = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "message_count": "0"
            }
            
            # 保存对话元信息
            self.redis_client.hset(
                f"conversation:{conversation_id}:meta",
                mapping=meta_data
            )
            self.redis_client.expire(f"conversation:{conversation_id}:meta", CONVERSATION_TTL)
            
            # 添加到用户的对话列表
            self._add_conversation_to_user(user_id, conversation_id)
            
            print(f"[REDIS_CONV] 创建对话成功: {conversation_id}")
            return conversation_id
            
        except Exception as e:
            print(f"[ERROR] 创建对话失败: {str(e)}")
            return conversation_id  # 返回ID但可能未存储
    
    def save_message(self, conversation_id: str, role: str, content: str, 
                    metadata: Optional[Dict] = None) -> bool:
        """保存消息到对话历史"""
        if not self.is_available() or not conversation_id:
            return False
        
        try:
            message_data = {
                "message_id": str(uuid.uuid4()),
                "timestamp": datetime.now().isoformat(),
                "role": role,  # user, assistant
                "content": content,
                "metadata": metadata or {}
            }
            
            # 保存到消息列表（LPUSH添加到头部，最新消息在前）
            self.redis_client.lpush(
                f"conversation:{conversation_id}:messages",
                json.dumps(message_data)
            )
            
            # 设置TTL
            self.redis_client.expire(f"conversation:{conversation_id}:messages", CONVERSATION_TTL)
            
            # 限制消息数量
            self.redis_client.ltrim(
                f"conversation:{conversation_id}:messages",
                0, CONVERSATION_MAX_LENGTH - 1
            )
            
            # 更新元信息
            self._update_conversation_meta(conversation_id)
            
            return True
            
        except Exception as e:
            print(f"[ERROR] 保存消息失败: {str(e)}")
            return False
    
    def get_context(self, conversation_id: str, count: Optional[int] = None) -> str:
        """获取对话上下文，格式化为prompt"""
        if not self.is_available() or not ENABLE_CONVERSATION_CONTEXT:
            return ""
        
        try:
            if count is None:
                count = CONVERSATION_CONTEXT_COUNT
            
            # 获取最近的消息（count*2 因为包含用户和助手消息）
            message_count = count * 2
            messages = self.redis_client.lrange(
                f"conversation:{conversation_id}:messages",
                0, message_count - 1
            )
            
            if not messages:
                return ""
            
            # 解析消息并构建上下文（按时间正序）
            context_parts = []
            for msg_json in reversed(messages):  # Redis返回倒序，需要反转
                try:
                    msg_data = json.loads(msg_json)
                    role = msg_data.get("role", "")
                    content = msg_data.get("content", "")
                    
                    if role == "user":
                        context_parts.append(f"用户: {content}")
                    elif role == "assistant":
                        context_parts.append(f"助手: {content}")
                        
                except json.JSONDecodeError:
                    continue
            
            context = "\n".join(context_parts)
            print(f"[REDIS_CONV] 获取上下文成功: {len(context_parts)}条消息")
            return context
            
        except Exception as e:
            print(f"[ERROR] 获取上下文失败: {str(e)}")
            return ""
    
    def get_conversation_messages(self, conversation_id: str, limit: Optional[int] = None) -> List[Dict]:
        """获取对话的消息列表"""
        if not self.is_available():
            return []
        
        try:
            if limit:
                messages = self.redis_client.lrange(
                    f"conversation:{conversation_id}:messages", 0, limit - 1
                )
            else:
                messages = self.redis_client.lrange(
                    f"conversation:{conversation_id}:messages", 0, -1
                )
            
            # 解析并按时间正序返回
            parsed_messages = []
            for msg_json in reversed(messages):  # 反转为时间正序
                try:
                    parsed_messages.append(json.loads(msg_json))
                except json.JSONDecodeError:
                    continue
                    
            return parsed_messages
            
        except Exception as e:
            print(f"[ERROR] 获取对话消息失败: {str(e)}")
            return []
    
    def get_conversation_meta(self, conversation_id: str) -> Dict:
        """获取对话元信息"""
        if not self.is_available():
            return {}
        
        try:
            meta_data = self.redis_client.hgetall(f"conversation:{conversation_id}:meta")
            return meta_data if meta_data else {}
        except Exception as e:
            print(f"[ERROR] 获取对话元信息失败: {str(e)}")
            return {}
    
    def get_conversations(self, user_id: str, limit: int = None) -> List[Dict]:
        """获取用户的对话列表（按时间倒序）"""
        if not self.is_available():
            return []
        
        if limit is None:
            limit = USER_MAX_CONVERSATIONS
        
        try:
            # 获取对话ID列表（已经按时间倒序）
            conversation_ids = self.redis_client.lrange(
                f"user:{user_id}:conversations", 0, limit - 1
            )
            
            conversations = []
            for conv_id in conversation_ids:
                meta_data = self.get_conversation_meta(conv_id)
                if meta_data:  # 只返回仍然存在的对话
                    conversations.append(meta_data)
            
            return conversations
            
        except Exception as e:
            print(f"[ERROR] 获取用户对话列表失败: {str(e)}")
            return []
    
    # ==================== 智能缓存（修正版）====================
    
    def get_cached_answer(self, question: str, context: str = "") -> Optional[Dict]:
        """检查问答缓存 - 真正上下文感知版"""
        if not self.is_available() or not ENABLE_QUESTION_ANSWER_CACHE:
            return None
        
        try:
            cache_key = self._get_cache_key(question, context)
            cached_answer = self.redis_client.get(cache_key)  # 使用独立key而不是hash
            
            if cached_answer:
                print(f"[REDIS_CONV] 缓存命中: {cache_key}")
                return json.loads(cached_answer)
            
            return None
            
        except Exception as e:
            print(f"[ERROR] 获取缓存答案失败: {str(e)}")
            return None
    
    def cache_answer(self, question: str, answer: Dict, context: str = ""):
        """缓存问答结果 - 真正上下文感知版"""
        if not self.is_available() or not ENABLE_QUESTION_ANSWER_CACHE:
            return
        
        try:
            cache_key = self._get_cache_key(question, context)
            
            # 添加缓存时间戳和上下文哈希
            answer_with_meta = {
                **answer,
                "cached_at": datetime.now().isoformat(),
                "original_question": question,
                "context_hash": hashlib.md5(context.encode()).hexdigest()[:8] if context else ""
            }
            
            # 使用独立key，每个缓存项单独设置TTL
            self.redis_client.setex(
                cache_key, 
                QUESTION_ANSWER_TTL,
                json.dumps(answer_with_meta)
            )
            
            print(f"[REDIS_CONV] 缓存答案成功: {cache_key}")
            
        except Exception as e:
            print(f"[ERROR] 缓存答案失败: {str(e)}")
    
    def _get_cache_key(self, question: str, context: str = "") -> str:
        """生成真正包含上下文的缓存键"""
        if context and ENABLE_CONVERSATION_CONTEXT:
            # 使用上下文内容而不是conversation_id
            cache_input = f"context:{context}\nquestion:{question}"
        else:
            cache_input = question
        
        normalized = cache_input.strip().lower()
        question_hash = hashlib.md5(normalized.encode('utf-8')).hexdigest()[:16]
        return f"qa_cache:{question_hash}"
    
    # ==================== 私有方法 ====================
    
    def _add_conversation_to_user(self, user_id: str, conversation_id: str):
        """添加对话到用户列表，按时间自动排序"""
        try:
            # 获取用户类型配置
            config = self._get_user_type_config(user_id)
            
            # LPUSH添加到列表头部（最新的）
            self.redis_client.lpush(f"user:{user_id}:conversations", conversation_id)
            
            # 根据用户类型限制数量
            self.redis_client.ltrim(
                f"user:{user_id}:conversations", 
                0, config["max_conversations"] - 1
            )
            
            # 设置TTL
            self.redis_client.expire(
                f"user:{user_id}:conversations", 
                config["ttl"]
            )
            
        except Exception as e:
            print(f"[ERROR] 添加对话到用户列表失败: {str(e)}")
    
    def _get_user_type_config(self, user_id: str) -> Dict:
        """根据用户类型返回不同的配置 - 修正版"""
        if user_id.startswith(DEFAULT_ANONYMOUS_USER_PREFIX):
            return {
                "max_conversations": MAX_GUEST_CONVERSATIONS,
                "ttl": GUEST_USER_TTL  # 使用专门的guest TTL
            }
        else:
            return {
                "max_conversations": MAX_REGISTERED_CONVERSATIONS,
                "ttl": USER_CONVERSATIONS_TTL
            }
    
    def _update_conversation_meta(self, conversation_id: str):
        """更新对话元信息"""
        try:
            # 获取消息数量
            message_count = self.redis_client.llen(f"conversation:{conversation_id}:messages")
            
            # 更新元信息
            self.redis_client.hset(
                f"conversation:{conversation_id}:meta",
                mapping={
                    "updated_at": datetime.now().isoformat(),
                    "message_count": str(message_count)
                }
            )
            
        except Exception as e:
            print(f"[ERROR] 更新对话元信息失败: {str(e)}")
    
    # ==================== 管理方法 ====================
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        if not self.is_available():
            return {"available": False}
        
        try:
            stats = {
                "available": True,
                "total_users": len(self.redis_client.keys("user:*:conversations")),
                "total_conversations": len(self.redis_client.keys("conversation:*:meta")),
                "cached_qa_count": len(self.redis_client.keys("qa_cache:*")),  # 修正缓存统计
                "redis_info": {
                    "used_memory": self.redis_client.info().get("used_memory_human"),
                    "connected_clients": self.redis_client.info().get("connected_clients")
                }
            }
            
            return stats
            
        except Exception as e:
            print(f"[ERROR] 获取统计信息失败: {str(e)}")
            return {"available": False, "error": str(e)}
    
    def cleanup_expired_conversations(self):
        """清理过期对话（Redis TTL自动处理，这里可添加额外逻辑）"""
        if not self.is_available():
            return
        
        try:
            # 清理用户对话列表中的无效对话ID
            user_keys = self.redis_client.keys("user:*:conversations")
            cleaned_count = 0
            
            for user_key in user_keys:
                conversation_ids = self.redis_client.lrange(user_key, 0, -1)
                valid_ids = []
                
                for conv_id in conversation_ids:
                    # 检查对话是否仍然存在
                    if self.redis_client.exists(f"conversation:{conv_id}:meta"):
                        valid_ids.append(conv_id)
                    else:
                        cleaned_count += 1
                
                # 如果有无效ID，重建列表
                if len(valid_ids) != len(conversation_ids):
                    self.redis_client.delete(user_key)
                    if valid_ids:
                        self.redis_client.lpush(user_key, *reversed(valid_ids))
                        # 重新设置TTL
                        self.redis_client.expire(user_key, USER_CONVERSATIONS_TTL)
            
            print(f"[REDIS_CONV] 清理完成，移除了 {cleaned_count} 个无效对话引用")
            
        except Exception as e:
            print(f"[ERROR] 清理失败: {str(e)}") 