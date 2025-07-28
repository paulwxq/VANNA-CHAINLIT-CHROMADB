# Redis对话管理系统 - 无效conversation_id处理改进示例
# 这个文件展示了如何改进处理无效对话ID的逻辑

from typing import Optional, Tuple, Dict

class ImprovedRedisConversationManager:
    """改进版的Redis对话管理器 - 专注于无效ID处理"""
    
    def resolve_conversation_id(self, user_id: str, conversation_id_input: Optional[str], 
                              continue_conversation: bool) -> Tuple[str, Dict]:
        """
        智能解析对话ID - 改进版
        
        Args:
            user_id: 用户ID
            conversation_id_input: 用户请求的对话ID
            continue_conversation: 是否继续最近对话
            
        Returns:
            tuple: (conversation_id, status_info)
            status_info包含:
            - status: "continue" | "new" | "invalid_id_new" | "no_permission"
            - message: 状态说明
            - requested_id: 原始请求的ID（如果有）
        """
        
        # 1. 如果指定了conversation_id，验证后使用
        if conversation_id_input:
            validation_result = self._validate_conversation_access(conversation_id_input, user_id)
            
            if validation_result["valid"]:
                print(f"[REDIS_CONV] 使用指定对话: {conversation_id_input}")
                return conversation_id_input, {
                    "status": "continue",
                    "message": "继续已有对话"
                }
            else:
                # 根据不同的无效原因返回不同的状态
                if validation_result["reason"] == "not_found":
                    print(f"[WARN] 对话不存在: {conversation_id_input}，创建新对话")
                    new_conversation_id = self.create_conversation(user_id)
                    return new_conversation_id, {
                        "status": "invalid_id_new",
                        "message": "您请求的对话不存在或已过期，已为您创建新对话",
                        "requested_id": conversation_id_input,
                        "reason": "not_found"
                    }
                elif validation_result["reason"] == "no_permission":
                    print(f"[WARN] 无权访问对话: {conversation_id_input}，创建新对话")
                    new_conversation_id = self.create_conversation(user_id)
                    return new_conversation_id, {
                        "status": "no_permission",
                        "message": "您没有权限访问该对话，已为您创建新对话",
                        "requested_id": conversation_id_input,
                        "reason": "no_permission"
                    }
        
        # 2. 如果要继续最近对话
        if continue_conversation:
            recent_conversation = self._get_recent_conversation(user_id)
            if recent_conversation:
                        print(f"[REDIS_CONV] 继续最近对话: {recent_conversation}")
        return recent_conversation, {
            "status": "continue",
            "message": "继续最近对话"
        }
        
        # 3. 创建新对话
        new_conversation_id = self.create_conversation(user_id)
        print(f"[REDIS_CONV] 创建新对话: {new_conversation_id}")
        return new_conversation_id, {
            "status": "new",
            "message": "创建新对话"
        }
    
    def _validate_conversation_access(self, conversation_id: str, user_id: str) -> Dict:
        """
        验证对话访问权限
        
        Returns:
            dict: {
                "valid": bool,
                "reason": "not_found" | "no_permission" | None
            }
        """
        # 这里是示例实现
        # 实际实现需要查询Redis
        
        # 检查对话是否存在
        if not self._conversation_exists(conversation_id):
            return {"valid": False, "reason": "not_found"}
        
        # 检查用户权限
        if not self._user_has_permission(conversation_id, user_id):
            return {"valid": False, "reason": "no_permission"}
        
        return {"valid": True, "reason": None}
    
    def _conversation_exists(self, conversation_id: str) -> bool:
        """检查对话是否存在"""
        # 示例实现 - 根据ID模拟不同场景
        if "not_exist" in conversation_id:
            return False
        return True
    
    def _user_has_permission(self, conversation_id: str, user_id: str) -> bool:
        """检查用户是否有权限访问对话"""
        # 示例实现 - 根据ID模拟不同场景
        if "other_user" in conversation_id:
            return False
        return True
    
    def _get_recent_conversation(self, user_id: str) -> Optional[str]:
        """获取用户最近的对话"""
        # 示例实现
        return None
    
    def create_conversation(self, user_id: str) -> str:
        """创建新对话"""
        # 示例实现
        import uuid
        from datetime import datetime
        timestamp = int(datetime.now().timestamp())
        return f"conv_{timestamp}_{uuid.uuid4().hex[:8]}"


# 使用示例
def demo_usage():
    """演示如何使用改进版的对话管理器"""
    
    manager = ImprovedRedisConversationManager()
    
    # 场景1：请求不存在的对话
    print("=== 场景1：请求不存在的对话 ===")
    conv_id, status = manager.resolve_conversation_id(
        user_id="user_123",
        conversation_id_input="conv_not_exist",
        continue_conversation=False
    )
    print(f"返回的对话ID: {conv_id}")
    print(f"状态信息: {status}")
    print()
    
    # 场景2：请求无权限的对话
    print("=== 场景2：请求无权限的对话 ===")
    conv_id, status = manager.resolve_conversation_id(
        user_id="user_456",
        conversation_id_input="conv_belongs_to_other_user",
        continue_conversation=False
    )
    print(f"返回的对话ID: {conv_id}")
    print(f"状态信息: {status}")
    print()
    
    # 场景3：创建新对话
    print("=== 场景3：创建新对话 ===")
    conv_id, status = manager.resolve_conversation_id(
        user_id="user_789",
        conversation_id_input=None,
        continue_conversation=False
    )
    print(f"返回的对话ID: {conv_id}")
    print(f"状态信息: {status}")


# API响应增强示例
def enhanced_ask_agent_response(conversation_status: Dict) -> Dict:
    """展示如何在API响应中包含对话状态信息"""
    
    # 基础响应
    response = {
        "success": True,
        "code": 200,
        "message": "操作成功",
        "data": {
            "response": "这是AI的回答...",
            "type": "DATABASE",
            "conversation_id": "conv_1234567890_abc123",
            "user_id": "user_123"
        }
    }
    
    # 添加对话状态信息
    response["data"].update({
        "conversation_status": conversation_status["status"],
        "requested_conversation_id": conversation_status.get("requested_id")
    })
    
    return response


# 前端处理示例（JavaScript风格的Python代码）
def frontend_handling_example():
    """展示前端如何处理不同的对话状态"""
    
    # 模拟API响应
    api_responses = [
        {
            "data": {
                "conversation_status": "invalid_id_new",
                "requested_conversation_id": "conv_old_123"
            }
        },
        {
            "data": {
                "conversation_status": "no_permission",
                "requested_conversation_id": "conv_other_user"
            }
        },
        {
            "data": {
                "conversation_status": "continue"
            }
        }
    ]
    
    # 状态消息映射（支持本地化）
    status_messages = {
        "invalid_id_new": "您请求的对话不存在或已过期，已为您创建新对话",
        "no_permission": "您没有权限访问该对话，已为您创建新对话", 
        "continue": "继续已有对话",
        "new": "创建新对话"
    }
    
    # 处理不同状态
    for response in api_responses:
        status = response["data"]["conversation_status"]
        message = status_messages.get(status, "未知状态")
        
        if status == "invalid_id_new":
            print(f"⚠️ 警告通知: {message}")
            print(f"  原请求ID: {response['data'].get('requested_conversation_id')}")
            print("  [更新本地conversation_id]")
            
        elif status == "no_permission":
            print(f"🚫 权限通知: {message}")
            print(f"  原请求ID: {response['data'].get('requested_conversation_id')}")
            print("  [清除本地无效的conversation_id]")
            
        elif status == "continue":
            print(f"✅ 成功: {message}")
            
        print()


if __name__ == "__main__":
    # 运行演示
    demo_usage()
    print("\n" + "="*50 + "\n")
    
    # 展示API响应增强
    print("=== API响应增强示例 ===")
    status_info = {
        "status": "invalid_id_new",
        "message": "您请求的对话不存在或已过期，已为您创建新对话",
        "requested_id": "conv_old_123"
    }
    enhanced_response = enhanced_ask_agent_response(status_info)
    import json
    print(json.dumps(enhanced_response, indent=2, ensure_ascii=False))
    
    print("\n" + "="*50 + "\n")
    
    # 展示前端处理
    print("=== 前端处理示例 ===")
    frontend_handling_example() 