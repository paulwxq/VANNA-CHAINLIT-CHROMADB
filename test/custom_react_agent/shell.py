"""
重构后的 CustomReactAgent 的交互式命令行客户端
"""
import asyncio
import logging
import sys
import os

# 动态地将项目根目录添加到 sys.path，以支持跨模块导入
# 这使得脚本更加健壮，无论从哪里执行
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

# 从新模块导入 Agent 和配置 (使用相对导入)
from .agent import CustomReactAgent
from . import config

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
                print(f"🤖 Agent: {result.get('answer')}")
                # 更新 thread_id 以便在同一会话中继续
                self.thread_id = result.get("thread_id")
            else:
                print(f"❌ 发生错误: {result.get('error')}")

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