"""
Redis对话管理功能演示脚本

这个脚本演示了如何使用Redis对话管理系统的各种功能：
1. 创建对话
2. 多轮对话（带上下文）
3. 缓存命中
4. 对话历史查询
5. 统计信息查看
"""

import requests
import json
import time
import sys
import os

class ConversationDemo:
    def __init__(self, base_url="http://localhost:8084/api/v0"):
        self.base_url = base_url
        self.session_id = f"demo_session_{int(time.time())}"
        self.conversation_id = None
        self.user_id = None
    
    def print_section(self, title):
        """打印分隔线"""
        print("\n" + "="*60)
        print(f" {title} ")
        print("="*60)
    
    def demo_basic_conversation(self):
        """演示基本对话功能"""
        self.print_section("1. 基本对话功能")
        
        # 第一个问题
        print("\n[DEMO] 发送第一个问题...")
        response = requests.post(
            f"{self.base_url}/ask_agent",
            json={
                "question": "高速公路服务区有多少个？",
                "session_id": self.session_id
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            self.conversation_id = data['data']['conversation_id']
            self.user_id = data['data']['user_id']
            
            print(f"[结果] 对话ID: {self.conversation_id}")
            print(f"[结果] 用户ID: {self.user_id}")
            print(f"[结果] 是否为Guest用户: {data['data'].get('is_guest_user')}")
            print(f"[结果] 回答: {data['data'].get('response', '')[:100]}...")
        else:
            print(f"[错误] 响应码: {response.status_code}")
    
    def demo_context_awareness(self):
        """演示上下文感知功能"""
        self.print_section("2. 上下文感知功能")
        
        if not self.conversation_id:
            print("[警告] 需要先运行基本对话演示")
            return
        
        # 第二个问题（依赖上下文）
        print("\n[DEMO] 发送依赖上下文的问题...")
        response = requests.post(
            f"{self.base_url}/ask_agent",
            json={
                "question": "这些服务区的经理都是谁？",
                "session_id": self.session_id,
                "conversation_id": self.conversation_id
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"[结果] 使用了上下文: {data['data'].get('context_used')}")
            print(f"[结果] 对话状态: {data['data'].get('conversation_status')}")
            print(f"[结果] 回答: {data['data'].get('response', '')[:100]}...")
        else:
            print(f"[错误] 响应码: {response.status_code}")
    
    def demo_cache_functionality(self):
        """演示缓存功能"""
        self.print_section("3. 缓存功能")
        
        # 问相同的问题
        question = "高速公路服务区的总数是多少？"
        
        print(f"\n[DEMO] 第一次询问: {question}")
        response1 = requests.post(
            f"{self.base_url}/ask_agent",
            json={
                "question": question,
                "session_id": self.session_id + "_cache",
            }
        )
        
        if response1.status_code == 200:
            data1 = response1.json()
            print(f"[结果] 来自缓存: {data1['data'].get('from_cache')}")
            conv_id = data1['data']['conversation_id']
            
            # 立即再问一次
            print(f"\n[DEMO] 第二次询问相同问题...")
            response2 = requests.post(
                f"{self.base_url}/ask_agent",
                json={
                    "question": question,
                    "session_id": self.session_id + "_cache",
                    "conversation_id": conv_id
                }
            )
            
            if response2.status_code == 200:
                data2 = response2.json()
                print(f"[结果] 来自缓存: {data2['data'].get('from_cache')}")
    
    def demo_conversation_history(self):
        """演示对话历史查询"""
        self.print_section("4. 对话历史查询")
        
        if not self.user_id:
            print("[警告] 需要先运行基本对话演示")
            return
        
        # 获取用户的对话列表
        print(f"\n[DEMO] 获取用户 {self.user_id} 的对话列表...")
        response = requests.get(
            f"{self.base_url}/user/{self.user_id}/conversations"
        )
        
        if response.status_code == 200:
            data = response.json()
            conversations = data['data']['conversations']
            print(f"[结果] 找到 {len(conversations)} 个对话")
            
            for i, conv in enumerate(conversations):
                print(f"\n  对话 {i+1}:")
                print(f"    ID: {conv['conversation_id']}")
                print(f"    创建时间: {conv['created_at']}")
                print(f"    消息数: {conv['message_count']}")
        
        # 获取特定对话的消息
        if self.conversation_id:
            print(f"\n[DEMO] 获取对话 {self.conversation_id} 的消息...")
            response = requests.get(
                f"{self.base_url}/conversation/{self.conversation_id}/messages"
            )
            
            if response.status_code == 200:
                data = response.json()
                messages = data['data']['messages']
                print(f"[结果] 找到 {len(messages)} 条消息")
                
                for msg in messages:
                    role = "用户" if msg['role'] == 'user' else "助手"
                    content = msg['content'][:50] + "..." if len(msg['content']) > 50 else msg['content']
                    print(f"\n  [{role}]: {content}")
    
    def demo_statistics(self):
        """演示统计信息"""
        self.print_section("5. 统计信息")
        
        print("\n[DEMO] 获取对话系统统计信息...")
        response = requests.get(f"{self.base_url}/conversation_stats")
        
        if response.status_code == 200:
            data = response.json()
            stats = data['data']
            
            print(f"\n[统计信息]")
            print(f"  Redis可用: {stats.get('available')}")
            print(f"  总用户数: {stats.get('total_users')}")
            print(f"  总对话数: {stats.get('total_conversations')}")
            print(f"  缓存的问答数: {stats.get('cached_qa_count')}")
            
            if stats.get('redis_info'):
                print(f"\n[Redis信息]")
                print(f"  内存使用: {stats['redis_info'].get('used_memory')}")
                print(f"  连接客户端数: {stats['redis_info'].get('connected_clients')}")
    
    def demo_invalid_conversation_id(self):
        """演示无效对话ID处理"""
        self.print_section("6. 无效对话ID处理")
        
        print("\n[DEMO] 使用无效的对话ID...")
        response = requests.post(
            f"{self.base_url}/ask_agent",
            json={
                "question": "测试无效ID",
                "session_id": self.session_id,
                "conversation_id": "invalid_conversation_xyz"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"[结果] 对话状态: {data['data'].get('conversation_status')}")
            print(f"[结果] 状态消息: {data['data'].get('conversation_message')}")
            print(f"[结果] 请求的ID: {data['data'].get('requested_conversation_id')}")
            print(f"[结果] 新创建的ID: {data['data'].get('conversation_id')}")
    
    def run_all_demos(self):
        """运行所有演示"""
        try:
            # 检查服务是否可用
            print("[DEMO] 检查服务可用性...")
            response = requests.get(f"{self.base_url}/agent_health", timeout=5)
            if response.status_code != 200:
                print("[错误] 服务不可用，请先启动Flask应用")
                return
            
            # 运行各个演示
            self.demo_basic_conversation()
            time.sleep(1)
            
            self.demo_context_awareness()
            time.sleep(1)
            
            self.demo_cache_functionality()
            time.sleep(1)
            
            self.demo_conversation_history()
            time.sleep(1)
            
            self.demo_statistics()
            time.sleep(1)
            
            self.demo_invalid_conversation_id()
            
            print("\n" + "="*60)
            print(" 演示完成 ")
            print("="*60)
            
        except Exception as e:
            print(f"\n[错误] 演示过程中出错: {str(e)}")
            print("请确保Flask应用正在运行 (python citu_app.py)")


if __name__ == "__main__":
    print("Redis对话管理功能演示")
    print("确保已经启动了Flask应用和Redis服务")
    print("-" * 60)
    
    demo = ConversationDemo()
    demo.run_all_demos() 