"""
重构后的 CustomReactAgent 的交互式命令行客户端
"""
# from __future__ import annotations

import asyncio
import logging
import sys
import os
import json
from typing import List, Dict, Any

# 将当前目录和项目根目录添加到 sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))
sys.path.insert(0, CURRENT_DIR)  # 当前目录优先
sys.path.insert(1, PROJECT_ROOT)  # 项目根目录

# 导入 Agent 和配置（简化版本）
from agent import CustomReactAgent
import config

# 配置日志
logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)

class CustomAgentShell:
    """新 Agent 的交互式 Shell 客户端"""

    def __init__(self, agent: CustomReactAgent):
        """私有构造函数，请使用 create() 类方法。"""
        self.agent = agent
        self.user_id: str = config.DEFAULT_USER_ID
        self.thread_id: str | None = None
        self.recent_conversations: List[Dict[str, Any]] = []  # 存储最近的对话列表

    @classmethod
    async def create(cls):
        """异步工厂方法，创建 Shell 实例。"""
        agent = await CustomReactAgent.create()
        return cls(agent)

    async def close(self):
        """关闭 Agent 资源。"""
        if self.agent:
            await self.agent.close()

    async def _fetch_recent_conversations(self, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """获取最近的对话列表"""
        try:
            logger.info(f"🔍 获取用户 {user_id} 的最近 {limit} 次对话...")
            conversations = await self.agent.get_user_recent_conversations(user_id, limit)
            logger.info(f"✅ 成功获取 {len(conversations)} 个对话")
            return conversations
        except Exception as e:
            logger.error(f"❌ 获取对话列表失败: {e}")
            print(f"⚠️ 获取历史对话失败: {e}")
            print("   将直接开始新对话...")
            return []

    def _display_conversation_list(self, conversations: List[Dict[str, Any]]) -> None:
        """显示对话列表"""
        if not conversations:
            print("📭 暂无历史对话，将开始新对话。")
            return
        
        print("\n📋 最近的对话记录:")
        print("-" * 60)
        
        for i, conv in enumerate(conversations, 1):
            thread_id = conv.get('thread_id', '')
            formatted_time = conv.get('formatted_time', '')
            preview = conv.get('conversation_preview', '无预览')
            message_count = conv.get('message_count', 0)
            
            print(f"[{i}] {formatted_time} - {preview}")
            print(f"    Thread ID: {thread_id} | 消息数: {message_count}")
            print()
        
        print("💡 选择方式:")
        print("   - 输入序号 (1-5): 选择对应的对话")
        print("   - 输入 Thread ID: 直接指定对话")
        print("   - 输入日期 (YYYY-MM-DD): 选择当天最新对话")
        print("   - 输入 'new': 开始新对话")
        print("   - 直接输入问题: 开始新对话")
        print("-" * 60)

    def _parse_conversation_selection(self, user_input: str) -> Dict[str, Any]:
        """解析用户的对话选择"""
        user_input = user_input.strip()
        
        # 检查是否是数字序号 (1-5)
        if user_input.isdigit():
            index = int(user_input)
            if 1 <= index <= len(self.recent_conversations):
                selected_conv = self.recent_conversations[index - 1]
                return {
                    "type": "select_by_index",
                    "thread_id": selected_conv["thread_id"],
                    "preview": selected_conv["conversation_preview"]
                }
            else:
                return {"type": "invalid_index", "message": f"序号 {index} 无效，请输入 1-{len(self.recent_conversations)}"}
        
        # 检查是否是 Thread ID 格式 (包含冒号)
        if ':' in user_input and len(user_input.split(':')) == 2:
            user_part, timestamp_part = user_input.split(':')
            # 简单验证格式
            if user_part == self.user_id and timestamp_part.isdigit():
                # 检查该Thread ID是否存在于历史对话中
                for conv in self.recent_conversations:
                    if conv["thread_id"] == user_input:
                        return {
                            "type": "select_by_thread_id",
                            "thread_id": user_input,
                            "preview": conv["conversation_preview"]
                        }
                return {"type": "thread_not_found", "message": f"Thread ID {user_input} 不存在于最近的对话中"}
        
        # 检查是否是日期格式 (YYYY-MM-DD)
        import re
        date_pattern = r'^\d{4}-\d{2}-\d{2}$'
        if re.match(date_pattern, user_input):
            # 查找该日期的最新对话
            target_date = user_input.replace('-', '')  # 转换为 YYYYMMDD 格式
            for conv in self.recent_conversations:
                timestamp = conv.get('timestamp', '')
                if timestamp.startswith(target_date):
                    return {
                        "type": "select_by_date",
                        "thread_id": conv["thread_id"],
                        "preview": f"日期 {user_input} 的对话: {conv['conversation_preview']}"
                    }
            return {"type": "no_date_match", "message": f"未找到 {user_input} 的对话"}
        
        # 检查是否是 'new' 命令
        if user_input.lower() == 'new':
            return {"type": "new_conversation"}
        
        # 其他情况当作新问题处理
        return {"type": "new_question", "question": user_input}

    async def start(self):
        """启动 Shell 界面。"""
        print("\n🚀 Custom React Agent Shell (StateGraph Version)")
        print("=" * 50)
        
        # 获取用户ID
        user_input = input(f"请输入您的用户ID (默认: {self.user_id}): ").strip()
        if user_input:
            self.user_id = user_input
        
        print(f"👤 当前用户: {self.user_id}")
        
        # 获取并显示最近的对话列表
        print("\n🔍 正在获取历史对话...")
        self.recent_conversations = await self._fetch_recent_conversations(self.user_id, 5)
        self._display_conversation_list(self.recent_conversations)
        
        print("\n💬 开始对话 (输入 'exit' 或 'quit' 退出)")
        print("-" * 50)
        
        await self._chat_loop()

    async def _chat_loop(self):
        """主要的聊天循环。"""
        while True:
            user_input = input(f"👤 [{self.user_id[:8]}]> ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit']:
                raise KeyboardInterrupt  # 优雅退出
            
            if user_input.lower() == 'new':
                self.thread_id = None
                print("🆕 已开始新会话。")
                continue

            if user_input.lower() == 'history':
                await self._show_current_history()
                continue
            
            # 如果还没有选择对话，且有历史对话，则处理对话选择
            if self.thread_id is None and self.recent_conversations:
                selection = self._parse_conversation_selection(user_input)
                
                if selection["type"] == "select_by_index":
                    self.thread_id = selection["thread_id"]
                    print(f"📖 已选择对话: {selection['preview']}")
                    print(f"💬 Thread ID: {self.thread_id}")
                    print("现在可以在此对话中继续聊天...\n")
                    continue
                
                elif selection["type"] == "select_by_thread_id":
                    self.thread_id = selection["thread_id"]
                    print(f"📖 已选择对话: {selection['preview']}")
                    print("现在可以在此对话中继续聊天...\n")
                    continue
                
                elif selection["type"] == "select_by_date":
                    self.thread_id = selection["thread_id"]
                    print(f"📖 已选择对话: {selection['preview']}")
                    print("现在可以在此对话中继续聊天...\n")
                    continue
                
                elif selection["type"] == "new_conversation":
                    self.thread_id = None
                    print("🆕 已开始新会话。")
                    continue
                
                elif selection["type"] == "new_question":
                    # 当作新问题处理，继续下面的正常对话流程
                    user_input = selection["question"]
                    self.thread_id = None
                    print("🆕 开始新对话...")
                
                elif selection["type"] in ["invalid_index", "no_date_match", "thread_not_found"]:
                    print(f"❌ {selection['message']}")
                    continue
            
            # 正常对话流程
            print("🤖 Agent 正在思考...")
            result = await self.agent.chat(user_input, self.user_id, self.thread_id)
            
            if result.get("success"):
                answer = result.get('answer', '')
                # 去除 [Formatted Output] 标记，只显示真正的回答
                if answer.startswith("[Formatted Output]\n"):
                    answer = answer.replace("[Formatted Output]\n", "")
                
                print(f"🤖 Agent: {answer}")
                
                # 如果包含 SQL 数据，也显示出来
                if 'sql_data' in result:
                    print(f"📊 SQL 查询结果: {result['sql_data']}")
                    
                # 更新 thread_id 以便在同一会话中继续
                self.thread_id = result.get("thread_id")
            else:
                error_msg = result.get('error', '未知错误')
                print(f"❌ 发生错误: {error_msg}")
                
                # 提供针对性的建议
                if "Connection error" in error_msg or "网络" in error_msg:
                    print("💡 建议:")
                    print("   - 检查网络连接是否正常")
                    print("   - 稍后重试该问题")
                    print("   - 如果问题持续，可以尝试重新启动程序")
                elif "timeout" in error_msg.lower():
                    print("💡 建议:")
                    print("   - 当前网络较慢，建议稍后重试")
                    print("   - 尝试简化问题复杂度")
                else:
                    print("💡 建议:")
                    print("   - 请检查问题格式是否正确")
                    print("   - 尝试重新描述您的问题")
                
                # 保持thread_id，用户可以继续对话
                if not self.thread_id and result.get("thread_id"):
                    self.thread_id = result.get("thread_id")

    async def _show_current_history(self):
        """显示当前会话的历史记录。"""
        if not self.thread_id:
            print("当前没有活跃的会话。请先开始对话。")
            return
        
        print(f"\n--- 对话历史: {self.thread_id} ---")
        history = await self.agent.get_conversation_history(self.thread_id)
        if not history:
            print("无法获取历史或历史为空。")
            return
            
        for msg in history:
            print(f"[{msg['type']}] {msg['content']}")
        print("--- 历史结束 ---")


async def main():
    """主函数入口"""
    shell = None
    try:
        shell = await CustomAgentShell.create()
        await shell.start()
    except KeyboardInterrupt:
        logger.info("\n👋 检测到退出指令，正在清理资源...")
    except Exception as e:
        logger.error(f"❌ 程序发生严重错误: {e}", exc_info=True)
    finally:
        if shell:
            await shell.close()
        print("✅ 程序已成功关闭。")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # 这个捕获是为了处理在 main 之外的 Ctrl+C
        print("\n👋 程序被强制退出。") 