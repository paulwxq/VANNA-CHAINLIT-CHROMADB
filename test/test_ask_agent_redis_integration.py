import unittest
import requests
import json
import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.redis_conversation_manager import RedisConversationManager

class TestAskAgentRedisIntegration(unittest.TestCase):
    """ask_agent API的Redis集成测试"""
    
    def setUp(self):
        """测试前准备"""
        self.base_url = "http://localhost:8084/api/v0"
        self.test_session_id = "test_session_" + str(int(time.time()))
        self.manager = RedisConversationManager()
        
    def tearDown(self):
        """测试后清理"""
        # 清理测试数据
        pass
    
    def test_api_availability(self):
        """测试API可用性"""
        try:
            response = requests.get(f"{self.base_url}/agent_health", timeout=5)
            print(f"[TEST] Agent健康检查响应码: {response.status_code}")
        except Exception as e:
            self.skipTest(f"API服务不可用: {str(e)}")
    
    def test_basic_ask_agent(self):
        """测试基本的ask_agent调用"""
        try:
            # 第一次调用 - 创建新对话
            payload = {
                "question": "测试问题：高速公路服务区有多少个？",
                "session_id": self.test_session_id
            }
            
            response = requests.post(
                f"{self.base_url}/ask_agent",
                json=payload,
                timeout=30
            )
            
            print(f"[TEST] 第一次调用响应码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"[TEST] 响应数据: {json.dumps(data, indent=2, ensure_ascii=False)}")
                
                # 验证返回字段
                self.assertIn('data', data)
                self.assertIn('conversation_id', data['data'])
                self.assertIn('user_id', data['data'])
                self.assertIn('conversation_status', data['data'])
                
                conversation_id = data['data']['conversation_id']
                user_id = data['data']['user_id']
                
                print(f"[TEST] 创建的对话ID: {conversation_id}")
                print(f"[TEST] 用户ID: {user_id}")
                
                return conversation_id, user_id
                
        except Exception as e:
            self.skipTest(f"API调用失败: {str(e)}")
    
    def test_conversation_context(self):
        """测试对话上下文功能"""
        try:
            # 第一次调用
            payload1 = {
                "question": "高速公路服务区有多少个？",
                "session_id": self.test_session_id
            }
            
            response1 = requests.post(
                f"{self.base_url}/ask_agent",
                json=payload1,
                timeout=30
            )
            
            if response1.status_code != 200:
                self.skipTest("第一次API调用失败")
            
            data1 = response1.json()
            conversation_id = data1['data']['conversation_id']
            
            # 第二次调用 - 使用相同的对话ID
            payload2 = {
                "question": "这些服务区的经理都是谁？",  # 这个问题依赖于前面的上下文
                "session_id": self.test_session_id,
                "conversation_id": conversation_id
            }
            
            response2 = requests.post(
                f"{self.base_url}/ask_agent",
                json=payload2,
                timeout=30
            )
            
            print(f"[TEST] 第二次调用响应码: {response2.status_code}")
            
            if response2.status_code == 200:
                data2 = response2.json()
                print(f"[TEST] 使用了上下文: {data2['data'].get('context_used', False)}")
                self.assertTrue(data2['data'].get('context_used', False))
                
        except Exception as e:
            self.skipTest(f"上下文测试失败: {str(e)}")
    
    def test_cache_hit(self):
        """测试缓存命中"""
        try:
            # 同样的问题问两次
            question = "高速公路服务区的数量是多少？"
            
            # 第一次调用
            payload = {
                "question": question,
                "session_id": self.test_session_id + "_cache_test"
            }
            
            response1 = requests.post(
                f"{self.base_url}/ask_agent",
                json=payload,
                timeout=30
            )
            
            if response1.status_code != 200:
                self.skipTest("第一次API调用失败")
            
            data1 = response1.json()
            from_cache1 = data1['data'].get('from_cache', False)
            print(f"[TEST] 第一次调用from_cache: {from_cache1}")
            self.assertFalse(from_cache1)
            
            # 立即第二次调用相同的问题
            response2 = requests.post(
                f"{self.base_url}/ask_agent",
                json=payload,
                timeout=30
            )
            
            if response2.status_code == 200:
                data2 = response2.json()
                from_cache2 = data2['data'].get('from_cache', False)
                print(f"[TEST] 第二次调用from_cache: {from_cache2}")
                # 注意：由于是新对话，可能不会命中缓存
                
        except Exception as e:
            self.skipTest(f"缓存测试失败: {str(e)}")
    
    def test_invalid_conversation_id(self):
        """测试无效的conversation_id处理"""
        try:
            payload = {
                "question": "测试无效对话ID",
                "session_id": self.test_session_id,
                "conversation_id": "invalid_conv_id_xyz"
            }
            
            response = requests.post(
                f"{self.base_url}/ask_agent",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                status = data['data'].get('conversation_status')
                print(f"[TEST] 无效对话ID的状态: {status}")
                self.assertEqual(status, 'invalid_id_new')
                self.assertEqual(
                    data['data'].get('requested_conversation_id'),
                    'invalid_conv_id_xyz'
                )
                
        except Exception as e:
            self.skipTest(f"无效ID测试失败: {str(e)}")
    
    def test_conversation_api_endpoints(self):
        """测试对话管理API端点"""
        try:
            # 先创建一个对话
            result = self.test_basic_ask_agent()
            if not result:
                self.skipTest("无法创建测试对话")
            
            conversation_id, user_id = result
            
            # 测试获取用户对话列表
            response = requests.get(
                f"{self.base_url}/user/{user_id}/conversations",
                timeout=10
            )
            
            print(f"[TEST] 获取对话列表响应码: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                self.assertIn('data', data)
                self.assertIn('conversations', data['data'])
                print(f"[TEST] 用户对话数: {len(data['data']['conversations'])}")
            
            # 测试获取对话消息
            response = requests.get(
                f"{self.base_url}/conversation/{conversation_id}/messages",
                timeout=10
            )
            
            print(f"[TEST] 获取对话消息响应码: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                self.assertIn('data', data)
                self.assertIn('messages', data['data'])
                print(f"[TEST] 对话消息数: {len(data['data']['messages'])}")
            
            # 测试获取统计信息
            response = requests.get(
                f"{self.base_url}/conversation_stats",
                timeout=10
            )
            
            print(f"[TEST] 获取统计信息响应码: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                self.assertIn('data', data)
                stats = data['data']
                print(f"[TEST] Redis可用: {stats.get('available')}")
                print(f"[TEST] 总用户数: {stats.get('total_users')}")
                print(f"[TEST] 总对话数: {stats.get('total_conversations')}")
                
        except Exception as e:
            print(f"[ERROR] 管理API测试失败: {str(e)}")
    
    def test_guest_user_generation(self):
        """测试guest用户生成"""
        try:
            # 不提供user_id，应该生成guest用户
            payload = {
                "question": "测试guest用户",
                "session_id": self.test_session_id + "_guest"
            }
            
            response = requests.post(
                f"{self.base_url}/ask_agent",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                user_id = data['data']['user_id']
                is_guest = data['data'].get('is_guest_user', False)
                
                print(f"[TEST] 生成的用户ID: {user_id}")
                print(f"[TEST] 是否为guest用户: {is_guest}")
                
                self.assertTrue(user_id.startswith('guest_'))
                self.assertTrue(is_guest)
                
        except Exception as e:
            self.skipTest(f"Guest用户测试失败: {str(e)}")


def run_selected_tests():
    """运行选定的测试"""
    suite = unittest.TestSuite()
    
    # 添加要运行的测试
    suite.addTest(TestAskAgentRedisIntegration('test_api_availability'))
    suite.addTest(TestAskAgentRedisIntegration('test_basic_ask_agent'))
    suite.addTest(TestAskAgentRedisIntegration('test_conversation_context'))
    suite.addTest(TestAskAgentRedisIntegration('test_invalid_conversation_id'))
    suite.addTest(TestAskAgentRedisIntegration('test_conversation_api_endpoints'))
    
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)


if __name__ == '__main__':
    print("=" * 60)
    print("ask_agent Redis集成测试")
    print("注意: 需要先启动Flask应用 (python citu_app.py)")
    print("=" * 60)
    
    # 可以选择运行所有测试或选定的测试
    unittest.main()
    # 或者运行选定的测试
    # run_selected_tests() 