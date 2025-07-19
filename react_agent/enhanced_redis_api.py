"""
enhanced_redis_api.py - 完整的Redis直接访问API
支持include_tools开关参数，可以控制是否包含工具调用信息
"""
import redis
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def get_conversation_detail_from_redis(thread_id: str, include_tools: bool = False) -> Dict[str, Any]:
    """
    直接从Redis获取对话详细信息
    
    Args:
        thread_id: 线程ID，格式为 user_id:timestamp
        include_tools: 是否包含工具调用信息
                      - True: 返回所有消息（human/ai/tool/system）
                      - False: 只返回human和ai消息，且清理ai消息中的工具调用信息
        
    Returns:
        包含对话详细信息的字典
    """
    try:
        # 创建Redis连接
        redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
        redis_client.ping()
        
        # 扫描该thread的所有checkpoint keys
        pattern = f"checkpoint:{thread_id}:*"
        logger.info(f"🔍 扫描模式: {pattern}, include_tools: {include_tools}")
        
        keys = []
        cursor = 0
        while True:
            cursor, batch = redis_client.scan(cursor=cursor, match=pattern, count=1000)
            keys.extend(batch)
            if cursor == 0:
                break
        
        logger.info(f"📋 找到 {len(keys)} 个keys")
        
        if not keys:
            redis_client.close()
            return {
                "success": False,
                "error": f"未找到对话 {thread_id}",
                "data": None
            }
        
        # 获取最新的checkpoint（按key排序，最大的是最新的）
        latest_key = max(keys)
        logger.info(f"🔍 使用最新key: {latest_key}")
        
        # 检查key类型并获取数据
        key_type = redis_client.type(latest_key)
        logger.info(f"🔍 Key类型: {key_type}")
        
        data = None
        if key_type == 'string':
            data = redis_client.get(latest_key)
        elif key_type == 'ReJSON-RL':
            # RedisJSON类型
            try:
                data = redis_client.execute_command('JSON.GET', latest_key)
            except Exception as json_error:
                logger.error(f"❌ JSON.GET 失败: {json_error}")
                redis_client.close()
                return {
                    "success": False,
                    "error": f"无法读取RedisJSON数据: {json_error}",
                    "data": None
                }
        else:
            redis_client.close()
            return {
                "success": False,
                "error": f"不支持的key类型: {key_type}",
                "data": None
            }
        
        if not data:
            redis_client.close()
            return {
                "success": False,
                "error": "没有找到有效数据",
                "data": None
            }
        
        # 解析JSON数据
        try:
            checkpoint_data = json.loads(data)
            logger.info(f"🔍 JSON顶级keys: {list(checkpoint_data.keys())}")
        except json.JSONDecodeError as e:
            redis_client.close()
            return {
                "success": False,
                "error": f"JSON解析失败: {e}",
                "data": None
            }
        
        # 提取消息数据
        messages = extract_messages_from_checkpoint(checkpoint_data)
        logger.info(f"🔍 找到 {len(messages)} 条原始消息")
        
        # 🔑 关键改进：构建消息ID到时间戳的映射（模仿LangGraph API）
        logger.info(f"🔍 开始构建消息时间戳映射...")
        message_timestamps = _build_message_timestamp_map_from_redis(redis_client, thread_id)
        
        # 提取最新checkpoint时间戳作为备用
        checkpoint_ts = None
        if ('checkpoint' in checkpoint_data and 
            isinstance(checkpoint_data['checkpoint'], dict) and 
            'ts' in checkpoint_data['checkpoint']):
            
            ts_value = checkpoint_data['checkpoint']['ts']
            if isinstance(ts_value, str):
                try:
                    # 转换为中国时区格式
                    from datetime import datetime
                    import pytz
                    dt = datetime.fromisoformat(ts_value.replace('Z', '+00:00'))
                    china_tz = pytz.timezone('Asia/Shanghai')
                    china_dt = dt.astimezone(china_tz)
                    checkpoint_ts = china_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    logger.info(f"🕒 备用checkpoint时间戳: {checkpoint_ts}")
                except Exception as e:
                    logger.warning(f"⚠️ 时间戳转换失败: {e}")
        
        # 解析并过滤消息 - 使用消息时间戳映射
        parsed_messages = parse_and_filter_messages(messages, include_tools, checkpoint_ts, message_timestamps)
        
        # 提取用户ID
        user_id = thread_id.split(':')[0] if ':' in thread_id else 'unknown'
        
        # 解析created_at时间（从thread_id中提取）
        created_at = None
        if ':' in thread_id:
            try:
                timestamp_str = thread_id.split(':')[1]
                # 转换为中国时区格式
                from datetime import datetime
                import pytz
                # 假设timestamp是YYYYMMDDHHmmssSSS格式
                dt = datetime.strptime(timestamp_str, '%Y%m%d%H%M%S%f')
                china_tz = pytz.timezone('Asia/Shanghai')
                china_dt = china_tz.localize(dt)
                created_at = china_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                logger.info(f"🕒 解析created_at: {created_at}")
            except Exception as e:
                logger.warning(f"⚠️ 解析created_at失败: {e}")
        
        # 生成对话统计信息
        stats = generate_conversation_stats(parsed_messages, include_tools)
        
        redis_client.close()
        
        return {
            "success": True,
            "data": {
                "thread_id": thread_id,
                "conversation_id": thread_id,  # 添加conversation_id字段
                "created_at": created_at,  # 添加created_at字段
                "user_id": user_id,
                "include_tools": include_tools,
                "message_count": len(parsed_messages),
                "messages": parsed_messages,
                "stats": stats,
                "metadata": {
                    "latest_checkpoint_key": latest_key,
                    "total_raw_messages": len(messages),
                    "filtered_message_count": len(parsed_messages),
                    "filter_mode": "full_conversation" if include_tools else "human_ai_only"
                }
            }
        }
        
    except Exception as e:
        logger.error(f"❌ 获取对话详情失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "data": None
        }

def extract_messages_from_checkpoint(checkpoint_data: Dict[str, Any]) -> List[Any]:
    """
    从checkpoint数据中提取消息列表
    """
    messages = []
    
    # 尝试不同的数据结构路径
    if 'checkpoint' in checkpoint_data:
        checkpoint = checkpoint_data['checkpoint']
        if isinstance(checkpoint, dict) and 'channel_values' in checkpoint:
            channel_values = checkpoint['channel_values']
            if isinstance(channel_values, dict) and 'messages' in channel_values:
                messages = channel_values['messages']
    
    # 如果没有找到，尝试直接路径
    if not messages and 'channel_values' in checkpoint_data:
        channel_values = checkpoint_data['channel_values']
        if isinstance(channel_values, dict) and 'messages' in channel_values:
            messages = channel_values['messages']
    
    return messages

def _build_message_timestamp_map_from_redis(redis_client, thread_id: str) -> Dict[str, str]:
    """
    构建消息ID到时间戳的映射，模仿LangGraph API的逻辑
    遍历所有历史checkpoint，为每条消息记录其首次出现的时间戳
    """
    message_timestamps = {}
    
    try:
        # 获取所有checkpoint keys
        pattern = f"checkpoint:{thread_id}:*"
        keys = []
        cursor = 0
        while True:
            cursor, batch = redis_client.scan(cursor=cursor, match=pattern, count=1000)
            keys.extend(batch)
            if cursor == 0:
                break
        
        if not keys:
            logger.warning(f"⚠️ 未找到任何checkpoint keys: {pattern}")
            return message_timestamps
        
        # 获取所有checkpoint数据并按时间戳排序
        checkpoints_with_ts = []
        
        for key in keys:
            try:
                # 检查key类型并获取数据
                key_type = redis_client.type(key)
                data = None
                
                if key_type == 'string':
                    data = redis_client.get(key)
                elif key_type == 'ReJSON-RL':
                    data = redis_client.execute_command('JSON.GET', key)
                else:
                    continue
                
                if not data:
                    continue
                
                # 解析checkpoint数据
                checkpoint_data = json.loads(data)
                
                # 提取时间戳
                checkpoint_ts = None
                if ('checkpoint' in checkpoint_data and 
                    isinstance(checkpoint_data['checkpoint'], dict) and 
                    'ts' in checkpoint_data['checkpoint']):
                    
                    ts_value = checkpoint_data['checkpoint']['ts']
                    if isinstance(ts_value, str):
                        try:
                            # 转换为中国时区格式
                            from datetime import datetime
                            import pytz
                            dt = datetime.fromisoformat(ts_value.replace('Z', '+00:00'))
                            china_tz = pytz.timezone('Asia/Shanghai')
                            china_dt = dt.astimezone(china_tz)
                            checkpoint_ts = china_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        except Exception as e:
                            logger.warning(f"⚠️ 解析时间戳失败 {key}: {e}")
                            continue
                
                if checkpoint_ts:
                    checkpoints_with_ts.append({
                        'key': key,
                        'timestamp': checkpoint_ts,
                        'data': checkpoint_data,
                        'raw_ts': ts_value  # 用于排序
                    })
                    
            except Exception as e:
                logger.warning(f"⚠️ 处理checkpoint失败 {key}: {e}")
                continue
        
        # 按时间戳排序（最早的在前）
        checkpoints_with_ts.sort(key=lambda x: x['raw_ts'])
        
        logger.info(f"🔍 找到 {len(checkpoints_with_ts)} 个有效checkpoint，按时间排序")
        
        # 遍历每个checkpoint，为新消息分配时间戳
        for checkpoint_info in checkpoints_with_ts:
            checkpoint_data = checkpoint_info['data']
            checkpoint_ts = checkpoint_info['timestamp']
            
            # 提取消息
            messages = extract_messages_from_checkpoint(checkpoint_data)
            
            # 为这个checkpoint中的新消息分配时间戳
            for msg in messages:
                if isinstance(msg, dict) and 'kwargs' in msg:
                    msg_id = msg['kwargs'].get('id')
                    if msg_id and msg_id not in message_timestamps:
                        message_timestamps[msg_id] = checkpoint_ts
                        logger.debug(f"🕒 消息 {msg_id} 分配时间戳: {checkpoint_ts}")
        
        logger.info(f"✅ 成功构建消息时间戳映射，包含 {len(message_timestamps)} 条消息")
        
    except Exception as e:
        logger.error(f"❌ 构建消息时间戳映射失败: {e}")
        import traceback
        traceback.print_exc()
    
    return message_timestamps

def parse_and_filter_messages(raw_messages: List[Any], include_tools: bool, checkpoint_ts: str = None, message_timestamps: Dict[str, str] = None) -> List[Dict[str, Any]]:
    """
    解析和过滤消息列表 - 关键的开关逻辑实现
    
    Args:
        raw_messages: 原始消息列表
        include_tools: 是否包含工具消息
                      - True: 返回所有消息类型
                      - False: 只返回human/ai，且清理ai消息中的工具信息
        
    Returns:
        解析后的消息列表
    """
    parsed_messages = []
    
    for msg in raw_messages:
        try:
            # 获取消息ID，用于查找其真实时间戳
            msg_id = None
            if isinstance(msg, dict) and 'kwargs' in msg:
                msg_id = msg['kwargs'].get('id')
            
            # 使用消息映射中的时间戳，如果没有则使用checkpoint时间戳
            msg_timestamp = checkpoint_ts
            if message_timestamps and msg_id and msg_id in message_timestamps:
                msg_timestamp = message_timestamps[msg_id]
                logger.debug(f"🕒 使用消息映射时间戳: {msg_id} -> {msg_timestamp}")
            
            parsed_msg = parse_single_message(msg, msg_timestamp)
            if not parsed_msg:
                continue
            
            msg_type = parsed_msg['role']  # 使用新的字段名
            
            if include_tools:
                # 完整模式：包含所有消息类型
                parsed_messages.append(parsed_msg)
                logger.debug(f"✅ [完整模式] 包含消息: {msg_type}")
                
            else:
                # 简化模式：只包含human和ai消息
                if msg_type == 'human':
                    parsed_messages.append(parsed_msg)
                    logger.debug(f"✅ [简化模式] 包含human消息")
                    
                elif msg_type == 'ai':
                    # 清理AI消息，移除工具调用信息
                    cleaned_msg = clean_ai_message_for_simple_mode(parsed_msg)
                    
                    # 只包含有实际内容的AI消息
                    if cleaned_msg['content'].strip() and not cleaned_msg.get('is_intermediate_step', False):
                        parsed_messages.append(cleaned_msg)
                        logger.debug(f"✅ [简化模式] 包含有内容的ai消息")
                    else:
                        logger.debug(f"⏭️ [简化模式] 跳过空的ai消息或中间步骤")
                
                else:
                    # 跳过tool、system等消息
                    logger.debug(f"⏭️ [简化模式] 跳过 {msg_type} 消息")
                    
        except Exception as e:
            logger.warning(f"⚠️ 解析消息失败: {e}")
            continue
    
    logger.info(f"📊 解析结果: {len(parsed_messages)} 条消息 (include_tools={include_tools})")
    return parsed_messages

def parse_single_message(msg: Any, checkpoint_ts: str = None) -> Optional[Dict[str, Any]]:
    """
    解析单个消息，支持LangChain序列化格式
    
    Args:
        msg: 原始消息数据
        checkpoint_ts: checkpoint的时间戳，用作消息的真实时间（备用）
    """
    if isinstance(msg, dict):
        # LangChain序列化格式
        if (msg.get('lc') == 1 and 
            msg.get('type') == 'constructor' and 
            'id' in msg and 
            isinstance(msg['id'], list) and 
            'kwargs' in msg):
            
            kwargs = msg['kwargs']
            msg_class = msg['id'][-1] if msg['id'] else 'Unknown'
            
            # 确定消息类型
            if msg_class == 'HumanMessage':
                msg_type = 'human'
            elif msg_class == 'AIMessage':
                msg_type = 'ai'
            elif msg_class == 'ToolMessage':
                msg_type = 'tool'
            elif msg_class == 'SystemMessage':
                msg_type = 'system'
            else:
                msg_type = 'unknown'
            
            # 使用传入的时间戳（现在将通过消息ID映射获得）
            final_timestamp = checkpoint_ts or datetime.now().isoformat()
            
            # 构建基础消息对象 - 修改字段名称
            parsed_msg = {
                "role": msg_type,  # type -> role
                "content": kwargs.get('content', ''),
                "message_id": kwargs.get('id'),  # id -> message_id
                "timestamp": final_timestamp  # 使用消息自己的时间戳或备用时间戳
            }
            
            # 处理AI消息的特殊字段
            if msg_type == 'ai':
                # 工具调用信息
                tool_calls = kwargs.get('tool_calls', [])
                parsed_msg['tool_calls'] = tool_calls
                parsed_msg['has_tool_calls'] = len(tool_calls) > 0
                
                # 额外的AI消息元数据
                additional_kwargs = kwargs.get('additional_kwargs', {})
                if additional_kwargs:
                    parsed_msg['additional_kwargs'] = additional_kwargs
                
                response_metadata = kwargs.get('response_metadata', {})
                if response_metadata:
                    parsed_msg['response_metadata'] = response_metadata
            
            # 处理工具消息的特殊字段
            elif msg_type == 'tool':
                parsed_msg['tool_name'] = kwargs.get('name')
                parsed_msg['tool_call_id'] = kwargs.get('tool_call_id')
                parsed_msg['status'] = kwargs.get('status', 'unknown')
            
            return parsed_msg
            
        # 简单字典格式
        elif 'type' in msg:
            return {
                "role": msg.get('type', 'unknown'),  # type -> role
                "content": msg.get('content', ''),
                "message_id": msg.get('id'),  # id -> message_id
                "timestamp": checkpoint_ts or datetime.now().isoformat()  # 使用真实时间戳
            }
    
    return None

def clean_ai_message_for_simple_mode(ai_msg: Dict[str, Any]) -> Dict[str, Any]:
    """
    调试版本：清理AI消息用于简化模式
    """
    original_content = ai_msg.get("content", "")
    logger.info(f"🔍 清理AI消息，原始内容: '{original_content}', 长度: {len(original_content)}")
    
    cleaned_msg = {
        "role": ai_msg["role"],  # 使用新的字段名
        "content": original_content,
        "message_id": ai_msg.get("message_id"),  # 使用新的字段名
        "timestamp": ai_msg.get("timestamp")
    }
    
    # 处理内容格式化
    content = original_content.strip()
    
    # 注释掉 [Formatted Output] 清理逻辑 - 源头已不生成前缀
    # if '[Formatted Output]' in content:
    #     logger.info(f"🔍 发现 [Formatted Output] 标记")
    #     
    #     if content.startswith('[Formatted Output]\n'):
    #         # 去掉标记，保留后面的实际内容
    #         actual_content = content.replace('[Formatted Output]\n', '')
    #         logger.info(f"🔍 去除标记后的内容: '{actual_content}', 长度: {len(actual_content)}")
    #         cleaned_msg["content"] = actual_content
    #         content = actual_content
    #     elif content == '[Formatted Output]' or content == '[Formatted Output]\n':
    #         # 如果只有标记没有内容
    #         logger.info(f"🔍 只有标记没有实际内容")
    #         cleaned_msg["content"] = ""
    #         cleaned_msg["is_intermediate_step"] = True
    #         content = ""
    
    # 如果清理后内容为空或只有空白，标记为中间步骤
    if not content.strip():
        logger.info(f"🔍 内容为空，标记为中间步骤")
        cleaned_msg["is_intermediate_step"] = True
        cleaned_msg["content"] = ""
    
    # 添加简化模式标记
    cleaned_msg["simplified"] = True
    
    logger.info(f"🔍 清理结果: '{cleaned_msg['content']}', 是否中间步骤: {cleaned_msg.get('is_intermediate_step', False)}")
    
    return cleaned_msg

def generate_conversation_stats(messages: List[Dict[str, Any]], include_tools: bool) -> Dict[str, Any]:
    """
    生成对话统计信息
    
    Args:
        messages: 解析后的消息列表
        include_tools: 是否包含工具信息（影响统计内容）
        
    Returns:
        统计信息字典
    """
    stats = {
        "total_messages": len(messages),
        "human_messages": 0,
        "ai_messages": 0,
        "conversation_rounds": 0,
        "include_tools_mode": include_tools
    }
    
    # 添加工具相关统计（仅在include_tools=True时）
    if include_tools:
        stats.update({
            "tool_messages": 0,
            "system_messages": 0,
            "messages_with_tools": 0,
            "unique_tools_used": set()
        })
    
    for msg in messages:
        msg_type = msg.get('type', 'unknown')
        
        if msg_type == 'human':
            stats["human_messages"] += 1
        elif msg_type == 'ai':
            stats["ai_messages"] += 1
            
            # 工具相关统计
            if include_tools and msg.get('has_tool_calls', False):
                stats["messages_with_tools"] += 1
                
                # 统计使用的工具
                tool_calls = msg.get('tool_calls', [])
                for tool_call in tool_calls:
                    if isinstance(tool_call, dict) and 'name' in tool_call:
                        stats["unique_tools_used"].add(tool_call['name'])
                        
        elif include_tools:
            if msg_type == 'tool':
                stats["tool_messages"] += 1
                
                # 记录工具名称
                tool_name = msg.get('tool_name')
                if tool_name:
                    stats["unique_tools_used"].add(tool_name)
                    
            elif msg_type == 'system':
                stats["system_messages"] += 1
    
    # 计算对话轮次
    stats["conversation_rounds"] = stats["human_messages"]
    
    # 转换set为list（JSON序列化）
    if include_tools and "unique_tools_used" in stats:
        stats["unique_tools_used"] = list(stats["unique_tools_used"])
    
    return stats

def format_timestamp_readable(timestamp: str) -> str:
    """格式化时间戳为可读格式"""
    try:
        if len(timestamp) >= 14:
            year = timestamp[:4]
            month = timestamp[4:6]
            day = timestamp[6:8]
            hour = timestamp[8:10]
            minute = timestamp[10:12]
            second = timestamp[12:14]
            return f"{year}-{month}-{day} {hour}:{minute}:{second}"
    except Exception:
        pass
    return timestamp


# =================== 测试函数 ===================

def test_conversation_detail_with_switch():
    """
    测试对话详情获取功能，重点测试include_tools开关
    """
    print("🧪 测试对话详情获取（开关参数测试）...")
    
    # 测试thread_id（请替换为实际存在的thread_id）
    test_thread_id = "wang:20250709195048728323"
    
    print(f"\n1. 测试完整模式（include_tools=True）...")
    result_full = get_conversation_detail_from_redis(test_thread_id, include_tools=True)
    
    if result_full['success']:
        data = result_full['data']
        print(f"   ✅ 成功获取完整对话")
        print(f"   📊 消息数量: {data['message_count']}")
        print(f"   📈 统计信息: {data['stats']}")
        print(f"   🔧 包含工具: {data['stats'].get('tool_messages', 0)} 条工具消息")
        
        # 显示消息类型分布
        message_types = {}
        for msg in data['messages']:
            msg_type = msg['type']
            message_types[msg_type] = message_types.get(msg_type, 0) + 1
        print(f"   📋 消息类型分布: {message_types}")
        
    else:
        print(f"   ❌ 获取失败: {result_full['error']}")
    
    print(f"\n2. 测试简化模式（include_tools=False）...")
    result_simple = get_conversation_detail_from_redis(test_thread_id, include_tools=False)
    
    if result_simple['success']:
        data = result_simple['data']
        print(f"   ✅ 成功获取简化对话")
        print(f"   📊 消息数量: {data['message_count']}")
        print(f"   📈 统计信息: {data['stats']}")
        
        # 显示消息类型分布
        message_types = {}
        for msg in data['messages']:
            msg_type = msg['type']
            message_types[msg_type] = message_types.get(msg_type, 0) + 1
        print(f"   📋 消息类型分布: {message_types}")
        
        # 显示前几条消息示例
        print(f"   💬 消息示例:")
        for i, msg in enumerate(data['messages'][:4]):
            content_preview = str(msg['content'])[:50] + "..." if len(str(msg['content'])) > 50 else str(msg['content'])
            simplified_mark = " [简化]" if msg.get('simplified') else ""
            print(f"      [{i+1}] {msg['type']}: {content_preview}{simplified_mark}")
            
    else:
        print(f"   ❌ 获取失败: {result_simple['error']}")
    
    # 比较两种模式
    if result_full['success'] and result_simple['success']:
        full_count = result_full['data']['message_count']
        simple_count = result_simple['data']['message_count']
        difference = full_count - simple_count
        
        print(f"\n3. 模式比较:")
        print(f"   📊 完整模式消息数: {full_count}")
        print(f"   📊 简化模式消息数: {simple_count}")
        print(f"   📊 过滤掉的消息数: {difference}")
        print(f"   🎯 过滤效果: {'有效' if difference > 0 else '无差异'}")

if __name__ == "__main__":
    test_conversation_detail_with_switch()