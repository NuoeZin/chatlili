import os
import importlib
import traceback

PLUGIN_FOLDER = "plugins"

class PluginAPI:
    """
    提供给插件调用的统一接口
    """

    def __init__(self, server_context):
        self.ctx = server_context
        # 添加 app 属性，从 server_context 中获取
        self.app = server_context.get("flask_app")

    # ===== 发送系统消息 =====
    async def send_system_message(self, text):
        msg = {
            "type": "system",
            "content": text,
            "time": self.ctx["time_func"]()
        }
        await self.ctx["broadcast"](msg)

    # ===== 获取在线用户 =====
    def get_online_count(self):
        return len(self.ctx["clients"])

    # ===== 获取服务器配置 =====
    def get_config(self):
        return self.ctx["config"]


class PluginLoader:

    def __init__(self, server_context):
        self.plugins = []
        self.ctx = server_context
        self.api = PluginAPI(server_context)

    # ===== 加载插件 =====
    def load_plugins(self):

        if not os.path.exists(PLUGIN_FOLDER):
            os.makedirs(PLUGIN_FOLDER)

        for file in os.listdir(PLUGIN_FOLDER):

            if not file.endswith(".py") or file.startswith("__"):
                continue

            name = file[:-3]

            try:
                module = importlib.import_module(f"{PLUGIN_FOLDER}.{name}")
                self.plugins.append(module)

                if hasattr(module, "on_load"):
                    # 确保 on_load 是同步函数
                    result = module.on_load(self.api)
                    # 如果是协程，等待它完成
                    if hasattr(result, '__await__'):
                        import asyncio
                        asyncio.create_task(result)

                print(f"[插件加载成功] {name}")

            except Exception:
                print(f"[插件加载失败] {name}")
                traceback.print_exc()

    # ===== 服务器启动事件 =====
    def emit_server_start(self):
        for p in self.plugins:
            if hasattr(p, "on_server_start"):
                try:
                    result = p.on_server_start(self.api)
                    if hasattr(result, '__await__'):
                        import asyncio
                        asyncio.create_task(result)
                except:
                    traceback.print_exc()

    # ===== 消息事件 =====
    async def emit_message(self, msg):
        for p in self.plugins:
            if hasattr(p, "on_message"):
                try:
                    # 检查 on_message 是否是协程函数
                    if hasattr(p.on_message, '__await__'):
                        await p.on_message(self.api, msg)
                    else:
                        # 如果是普通函数，直接调用
                        result = p.on_message(self.api, msg)
                        # 如果返回了协程，等待它
                        if hasattr(result, '__await__'):
                            await result
                except Exception as e:
                    print(f"[插件错误] {p.__name__ if hasattr(p, '__name__') else 'unknown'}: {e}")
                    traceback.print_exc()

    # ===== 用户加入 =====
    async def emit_user_join(self, username):
        for p in self.plugins:
            if hasattr(p, "on_user_join"):
                try:
                    if hasattr(p.on_user_join, '__await__'):
                        await p.on_user_join(self.api, username)
                    else:
                        result = p.on_user_join(self.api, username)
                        if hasattr(result, '__await__'):
                            await result
                except:
                    traceback.print_exc()

    # ===== 用户离开 =====
    async def emit_user_leave(self, username):
        for p in self.plugins:
            if hasattr(p, "on_user_leave"):
                try:
                    if hasattr(p.on_user_leave, '__await__'):
                        await p.on_user_leave(self.api, username)
                    else:
                        result = p.on_user_leave(self.api, username)
                        if hasattr(result, '__await__'):
                            await result
                except:
                    traceback.print_exc()