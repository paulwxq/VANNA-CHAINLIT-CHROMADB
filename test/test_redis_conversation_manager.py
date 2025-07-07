import unittest
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.redis_conversation_manager import RedisConversationManager
from datetime import datetime
import time

class TestRedisConversationManager(unittest.TestCase):
    """Redis对话管理器单元测试"""
    
    def setUp(self):
        """测试前准备"""
        self.manager = RedisConversationManager()
        # 清理测试数据
        self.test_user_id = "test_user_123"
        self.test_guest_id = "guest_test_456"
        
    def tearDown(self):
        """测试后清理"""
        # 清理测试创建的数据
        if self.manager.is_available():
            # 清理测试用户的对话
            try:
                conversations = self.manager.get_conversations(self.test_user_id)
                for conv in conversations:
                    conv_id = conv.get('conversation_id')
                    if conv_id:
                        self.manager.redis_client.delete(f"conversation:{conv_id}:meta")
                        self.manager.redis_client.delete(f"conversation:{conv_id}:messages")
                self.manager.redis_client.delete(f"user:{self.test_user_id}:conversations")
                
                # 清理guest用户
                conversations = self.manager.get_conversations(self.test_guest_id)
                for conv in conversations:
                    conv_id = conv.get('conversation_id')
                    if conv_id:
                        self.manager.redis_client.delete(f"conversation:{conv_id}:meta")
                        self.manager.redis_client.delete(f"conversation:{conv_id}:messages")
                self.manager.redis_client.delete(f"user:{self.test_guest_id}:conversations")
            except:
                pass
    
    def test_redis_connection(self):
        """测试Redis连接"""
        is_available = self.manager.is_available()
        print(f"[TEST] Redis可用状态: {is_available}")
        if not is_available:
            self.skipTest("Redis不可用，跳过测试")
    
    def test_user_id_resolution(self):
        """测试用户ID解析逻辑"""
        # 测试登录用户ID优先
        user_id = self.manager.resolve_user_id(
            "request_user", "session_123", "127.0.0.1", "login_user"
        )
        self.assertEqual(user_id, "login_user")
        
        # 测试请求参数用户ID
        user_id = self.manager.resolve_user_id(
            "request_user", "session_123", "127.0.0.1", None
        )
        self.assertEqual(user_id, "request_user")
        
        # 测试guest用户生成
        user_id = self.manager.resolve_user_id(
            None, "session_123", "127.0.0.1", None
        )
        self.assertTrue(user_id.startswith("guest_"))
        
        # 测试基于IP的临时guest
        user_id = self.manager.resolve_user_id(
            None, None, "127.0.0.1", None
        )
        self.assertTrue(user_id.startswith("guest_temp_"))
    
    def test_conversation_creation(self):
        """测试对话创建"""
        if not self.manager.is_available():
            self.skipTest("Redis不可用")
        
        conv_id = self.manager.create_conversation(self.test_user_id)
        print(f"[TEST] 创建的对话ID: {conv_id}")
        
        # 验证对话ID格式
        self.assertTrue(conv_id.startswith("conv_"))
        self.assertIn("_", conv_id)
        
        # 验证对话元信息
        meta = self.manager.get_conversation_meta(conv_id)
        self.assertEqual(meta.get('user_id'), self.test_user_id)
        self.assertEqual(meta.get('conversation_id'), conv_id)
        self.assertIn('created_at', meta)
    
    def test_message_saving_and_retrieval(self):
        """测试消息保存和获取"""
        if not self.manager.is_available():
            self.skipTest("Redis不可用")
        
        # 创建对话
        conv_id = self.manager.create_conversation(self.test_user_id)
        
        # 保存消息
        self.manager.save_message(conv_id, "user", "测试问题")
        self.manager.save_message(conv_id, "assistant", "测试回答")
        
        # 获取消息列表
        messages = self.manager.get_conversation_messages(conv_id)
        self.assertEqual(len(messages), 2)
        
        # 验证消息顺序（时间正序）
        self.assertEqual(messages[0]['role'], 'user')
        self.assertEqual(messages[0]['content'], '测试问题')
        self.assertEqual(messages[1]['role'], 'assistant')
        self.assertEqual(messages[1]['content'], '测试回答')
    
    def test_context_generation(self):
        """测试上下文生成"""
        if not self.manager.is_available():
            self.skipTest("Redis不可用")
        
        # 创建对话并添加多条消息
        conv_id = self.manager.create_conversation(self.test_user_id)
        
        self.manager.save_message(conv_id, "user", "问题1")
        self.manager.save_message(conv_id, "assistant", "回答1")
        self.manager.save_message(conv_id, "user", "问题2")
        self.manager.save_message(conv_id, "assistant", "回答2")
        
        # 获取上下文
        context = self.manager.get_context(conv_id, count=2)
        print(f"[TEST] 生成的上下文:\n{context}")
        
        # 验证上下文格式
        self.assertIn("用户: 问题1", context)
        self.assertIn("助手: 回答1", context)
        self.assertIn("用户: 问题2", context)
        self.assertIn("助手: 回答2", context)
    
    def test_conversation_list(self):
        """测试用户对话列表"""
        if not self.manager.is_available():
            self.skipTest("Redis不可用")
        
        # 创建多个对话
        conv_ids = []
        for i in range(3):
            conv_id = self.manager.create_conversation(self.test_user_id)
            conv_ids.append(conv_id)
            time.sleep(0.1)  # 确保时间戳不同
        
        # 获取对话列表
        conversations = self.manager.get_conversations(self.test_user_id)
        self.assertEqual(len(conversations), 3)
        
        # 验证顺序（最新的在前）
        self.assertEqual(conversations[0]['conversation_id'], conv_ids[2])
        self.assertEqual(conversations[1]['conversation_id'], conv_ids[1])
        self.assertEqual(conversations[2]['conversation_id'], conv_ids[0])
    
    def test_cache_functionality(self):
        """测试缓存功能"""
        if not self.manager.is_available():
            self.skipTest("Redis不可用")
        
        question = "测试缓存问题"
        context = "用户: 之前的问题\n助手: 之前的回答"
        
        # 测试缓存未命中
        cached = self.manager.get_cached_answer(question, context)
        self.assertIsNone(cached)
        
        # 缓存答案
        answer = {
            "success": True,
            "data": {
                "response": "测试答案",
                "type": "CHAT"
            }
        }
        self.manager.cache_answer(question, answer, context)
        
        # 测试缓存命中
        cached = self.manager.get_cached_answer(question, context)
        self.assertIsNotNone(cached)
        self.assertEqual(cached['data']['response'], '测试答案')
        
        # 测试不同上下文的缓存
        different_context = "用户: 不同的问题\n助手: 不同的回答"
        cached = self.manager.get_cached_answer(question, different_context)
        self.assertIsNone(cached)  # 不同上下文应该缓存未命中
    
    def test_conversation_id_resolution(self):
        """测试对话ID解析"""
        if not self.manager.is_available():
            self.skipTest("Redis不可用")
        
        # 测试创建新对话
        conv_id, status = self.manager.resolve_conversation_id(
            self.test_user_id, None, False
        )
        self.assertTrue(conv_id.startswith("conv_"))
        self.assertEqual(status['status'], 'new')
        
        # 测试使用已存在的对话
        conv_id2, status2 = self.manager.resolve_conversation_id(
            self.test_user_id, conv_id, False
        )
        self.assertEqual(conv_id2, conv_id)
        self.assertEqual(status2['status'], 'existing')
        
        # 测试无效的对话ID
        conv_id3, status3 = self.manager.resolve_conversation_id(
            self.test_user_id, "invalid_conv_id", False
        )
        self.assertNotEqual(conv_id3, "invalid_conv_id")
        self.assertEqual(status3['status'], 'invalid_id_new')
        self.assertEqual(status3['requested_id'], 'invalid_conv_id')
    
    def test_statistics(self):
        """测试统计功能"""
        if not self.manager.is_available():
            self.skipTest("Redis不可用")
        
        # 创建测试数据
        conv_id = self.manager.create_conversation(self.test_user_id)
        self.manager.save_message(conv_id, "user", "统计测试")
        
        # 获取统计信息
        stats = self.manager.get_stats()
        print(f"[TEST] 统计信息: {stats}")
        
        self.assertTrue(stats['available'])
        self.assertIn('total_users', stats)
        self.assertIn('total_conversations', stats)
        self.assertIn('cached_qa_count', stats)
        
    def test_guest_user_limit(self):
        """测试guest用户对话数量限制"""
        if not self.manager.is_available():
            self.skipTest("Redis不可用")
        
        # 创建多个对话，超过guest用户限制
        from app_config import MAX_GUEST_CONVERSATIONS
        
        conv_ids = []
        for i in range(MAX_GUEST_CONVERSATIONS + 2):
            conv_id = self.manager.create_conversation(self.test_guest_id)
            conv_ids.append(conv_id)
            time.sleep(0.05)
        
        # 验证只保留了限制数量的对话
        conversations = self.manager.get_conversations(self.test_guest_id)
        self.assertEqual(len(conversations), MAX_GUEST_CONVERSATIONS)
        
        # 验证保留的是最新的对话
        retained_ids = [conv['conversation_id'] for conv in conversations]
        for i in range(MAX_GUEST_CONVERSATIONS):
            self.assertIn(conv_ids[-(i+1)], retained_ids)
    
    def test_cleanup_functionality(self):
        """测试清理功能"""
        if not self.manager.is_available():
            self.skipTest("Redis不可用")
        
        # 创建对话
        conv_id = self.manager.create_conversation(self.test_user_id)
        
        # 手动删除对话元信息，模拟过期
        self.manager.redis_client.delete(f"conversation:{conv_id}:meta")
        
        # 执行清理
        self.manager.cleanup_expired_conversations()
        
        # 验证对话已从用户列表中移除
        conversations = self.manager.get_conversations(self.test_user_id)
        conv_ids = [conv['conversation_id'] for conv in conversations]
        self.assertNotIn(conv_id, conv_ids)


if __name__ == '__main__':
    unittest.main() 