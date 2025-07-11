"""
重构后的 CustomReactAgent 的交互式命令行客户端
"""
# from __future__ import annotations

import asyncio
import logging
import sys
import os
import json

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

    @classmethod
    async def create(cls):
        """异步工厂方法，创建 Shell 实例。"""
        agent = await CustomReactAgent.create()
        return cls(agent)

    async def close(self):
        """关闭 Agent 资源。"""
        if self.agent:
            await self.agent.close()

    async def start(self):
        """启动 Shell 界面。"""
        print("\n🚀 Custom React Agent Shell (StateGraph Version)")
        print("=" * 50)
        
        # 获取用户ID
        user_input = input(f"请输入您的用户ID (默认: {self.user_id}): ").strip()
        if user_input:
            self.user_id = user_input
        
        print(f"👤 当前用户: {self.user_id}")
        # 这里可以加入显示历史会话的逻辑
        
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
            
            # 正常对话
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