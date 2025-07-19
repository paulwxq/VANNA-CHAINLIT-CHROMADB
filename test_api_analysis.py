#!/usr/bin/env python3
"""
测试当前API的真实输出，分析数据结构以确定是否能满足需求
"""
import requests
import json
from datetime import datetime

def test_current_api():
    """测试当前的对话历史API"""
    print("=" * 60)
    print("测试当前API的真实输出")
    print("=" * 60)
    
    # API URL
    api_url = "http://localhost:8084/api/v0/react/users/wang10/conversations/wang10:20250717211620915"
    
    try:
        print(f"📡 调用API: {api_url}")
        response = requests.get(api_url, timeout=30)
        
        print(f"📊 状态码: {response.status_code}")
        print(f"📄 响应头: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API调用成功")
            print(f"📋 响应数据结构分析:")
            analyze_response_structure(data)
            
            # 分析消息结构
            if 'data' in data and 'messages' in data['data']:
                analyze_messages(data['data']['messages'])
            
            # 保存完整响应到文件
            with open('api_response_full.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"💾 完整响应已保存到 api_response_full.json")
            
        else:
            print(f"❌ API调用失败: {response.status_code}")
            print(f"📄 错误响应: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求失败: {e}")
    except Exception as e:
        print(f"❌ 其他错误: {e}")

def analyze_response_structure(data):
    """分析响应数据结构"""
    print(f"   🔍 顶级键: {list(data.keys())}")
    
    if 'data' in data:
        data_section = data['data']
        print(f"   🔍 data部分键: {list(data_section.keys())}")
        
        if 'message_count' in data_section:
            print(f"   📊 消息总数: {data_section['message_count']}")
        
        if 'messages' in data_section:
            messages = data_section['messages']
            print(f"   📊 消息列表长度: {len(messages)}")

def analyze_messages(messages):
    """详细分析消息结构"""
    print(f"\n📨 消息详细分析:")
    print(f"   总消息数: {len(messages)}")
    
    # 统计消息类型
    message_types = {}
    has_id_count = 0
    has_timestamp_count = 0
    has_tool_calls_count = 0
    
    print(f"\n   前5条消息样例:")
    for i, msg in enumerate(messages[:5]):
        print(f"   消息 {i+1}:")
        print(f"     类型: {msg.get('type', 'unknown')}")
        print(f"     内容长度: {len(str(msg.get('content', '')))}")
        print(f"     是否有ID: {'id' in msg}")
        print(f"     是否有时间戳: {'timestamp' in msg}")
        print(f"     是否有工具调用: {'tool_calls' in msg}")
        
        if 'id' in msg:
            print(f"     ID值: {msg['id']}")
        if 'timestamp' in msg:
            print(f"     时间戳: {msg['timestamp']}")
        if 'tool_calls' in msg and msg['tool_calls']:
            print(f"     工具调用数量: {len(msg['tool_calls']) if isinstance(msg['tool_calls'], list) else 'non-list'}")
        
        print(f"     所有字段: {list(msg.keys())}")
        print()
    
    # 统计所有消息的类型和字段
    for msg in messages:
        msg_type = msg.get('type', 'unknown')
        message_types[msg_type] = message_types.get(msg_type, 0) + 1
        
        if 'id' in msg:
            has_id_count += 1
        if 'timestamp' in msg:
            has_timestamp_count += 1
        if 'tool_calls' in msg:
            has_tool_calls_count += 1
    
    print(f"   📊 消息类型统计: {message_types}")
    print(f"   📊 包含ID的消息数: {has_id_count}/{len(messages)}")
    print(f"   📊 包含时间戳的消息数: {has_timestamp_count}/{len(messages)}")
    print(f"   📊 包含工具调用的消息数: {has_tool_calls_count}/{len(messages)}")

def test_with_parameters():
    """测试带参数的API调用（虽然可能不支持）"""
    print("\n" + "=" * 60)
    print("测试带参数的API调用")
    print("=" * 60)
    
    base_url = "http://localhost:8084/api/v0/react/users/wang10/conversations/wang10:20250717211620915"
    
    test_params = [
        {},
        {"include_tools": "false"},
        {"simplified": "true"},
        {"include_tools": "false", "simplified": "true"}
    ]
    
    for i, params in enumerate(test_params):
        print(f"\n🧪 测试 {i+1}: 参数 = {params}")
        
        try:
            response = requests.get(base_url, params=params, timeout=10)
            print(f"   状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                message_count = data.get('data', {}).get('message_count', 0)
                print(f"   消息数量: {message_count}")
                
                # 检查是否有参数相关的字段
                data_section = data.get('data', {})
                if 'mode' in data_section:
                    print(f"   模式: {data_section['mode']}")
                if 'include_tools' in data_section:
                    print(f"   include_tools: {data_section['include_tools']}")
                if 'simplified' in data_section:
                    print(f"   simplified: {data_section['simplified']}")
            else:
                print(f"   失败: {response.text[:100]}")
                
        except Exception as e:
            print(f"   错误: {e}")

def analyze_feasibility():
    """基于实际数据分析可行性"""
    print("\n" + "=" * 60)
    print("需求可行性分析")
    print("=" * 60)
    
    try:
        with open('api_response_full.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        messages = data.get('data', {}).get('messages', [])
        
        print(f"📋 基于 {len(messages)} 条消息的分析:")
        
        # 需求1: 过滤消息类型
        human_messages = [msg for msg in messages if msg.get('type') == 'human']
        ai_messages = [msg for msg in messages if msg.get('type') == 'ai']
        tool_messages = [msg for msg in messages if msg.get('type') == 'tool']
        
        print(f"\n🎯 需求1 - 消息过滤:")
        print(f"   Human消息: {len(human_messages)} 条")
        print(f"   AI消息: {len(ai_messages)} 条")
        print(f"   Tool消息: {len(tool_messages)} 条")
        
        # 分析AI消息中哪些有实际内容
        ai_with_content = [msg for msg in ai_messages if msg.get('content', '').strip()]
        ai_with_tools = [msg for msg in ai_messages if msg.get('tool_calls')]
        
        print(f"   有内容的AI消息: {len(ai_with_content)} 条")
        print(f"   有工具调用的AI消息: {len(ai_with_tools)} 条")
        
        # 需求2: 时间戳分析
        print(f"\n🕐 需求2 - 时间戳分析:")
        messages_with_timestamp = [msg for msg in messages if 'timestamp' in msg]
        messages_with_id = [msg for msg in messages if 'id' in msg]
        
        print(f"   有时间戳的消息: {len(messages_with_timestamp)} 条")
        print(f"   有ID的消息: {len(messages_with_id)} 条")
        
        if messages_with_timestamp:
            sample_timestamp = messages_with_timestamp[0]['timestamp']
            print(f"   时间戳样例: {sample_timestamp}")
            
        if messages_with_id:
            sample_id = messages_with_id[0]['id']
            print(f"   ID样例: {sample_id}")
        
        # 可行性结论
        print(f"\n✅ 可行性结论:")
        print(f"   需求1 (消息过滤): {'✅ 可行' if human_messages and ai_with_content else '❌ 不可行'}")
        print(f"   需求2 (真实时间戳): {'✅ 可行' if messages_with_timestamp else '❌ 需要进一步分析'}")
        
    except FileNotFoundError:
        print("❌ 请先运行主测试获取数据")
    except Exception as e:
        print(f"❌ 分析失败: {e}")

if __name__ == "__main__":
    print(f"🚀 开始API分析测试 - {datetime.now()}")
    
    # 测试当前API
    test_current_api()
    
    # 测试参数支持
    test_with_parameters()
    
    # 分析可行性
    analyze_feasibility()
    
    print(f"\n🏁 测试完成 - {datetime.now()}") 