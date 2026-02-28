"""
大厅服务器插件加载器
"""

import os
import importlib
import traceback

PLUGIN_FOLDER = "plugins"

class PluginAPI:
    """
    提供给插件调用的统一接口
    """

    def __init__(self, app, servers):
        self.app = app
        self.servers = servers

    def add_route(self, rule, endpoint=None, view_func=None, methods=None):
        """添加路由"""
        if methods is None:
            methods = ['GET']
        self.app.add_url_rule(rule, endpoint, view_func, methods=methods)
        print(f"[PluginAPI] 添加路由: {rule}")

    def get_servers(self):
        """获取服务器列表"""
        return self.servers

    def add_server(self, key, server_info):
        """添加服务器"""
        self.servers[key] = server_info

    def remove_server(self, key):
        """移除服务器"""
        if key in self.servers:
            del self.servers[key]

    def get_server_count(self):
        """获取服务器数量"""
        return len(self.servers)

    def log(self, message):
        """记录日志"""
        print(f"[Plugin] {message}")

class PluginLoader:
    def __init__(self, app, servers):
        self.plugins = []
        self.app = app
        self.servers = servers
        self.api = PluginAPI(app, servers)

    def load_plugins(self):
        """加载所有插件"""
        if not os.path.exists(PLUGIN_FOLDER):
            os.makedirs(PLUGIN_FOLDER)
            print(f"创建插件文件夹: {PLUGIN_FOLDER}")

        for file in os.listdir(PLUGIN_FOLDER):
            if not file.endswith(".py") or file.startswith("__"):
                continue

            name = file[:-3]
            try:
                module = importlib.import_module(f"{PLUGIN_FOLDER}.{name}")
                self.plugins.append(module)

                if hasattr(module, "on_load"):
                    module.on_load(self.api)

                print(f"[插件加载成功] {name}")

            except Exception as e:
                print(f"[插件加载失败] {name}")
                traceback.print_exc()

    def on_server_start(self):
        """服务器启动事件"""
        for plugin in self.plugins:
            if hasattr(plugin, "on_server_start"):
                try:
                    plugin.on_server_start(self.api)
                except Exception as e:
                    print(f"[插件错误] on_server_start: {e}")
                    traceback.print_exc()

    def on_heartbeat(self, ip, port):
        """心跳事件"""
        for plugin in self.plugins:
            if hasattr(plugin, "on_heartbeat"):
                try:
                    plugin.on_heartbeat(self.api, ip, port)
                except Exception as e:
                    print(f"[插件错误] on_heartbeat: {e}")

    def on_server_register(self, ip, port, server_info):
        """服务器注册事件"""
        for plugin in self.plugins:
            if hasattr(plugin, "on_server_register"):
                try:
                    plugin.on_server_register(self.api, ip, port, server_info)
                except Exception as e:
                    print(f"[插件错误] on_server_register: {e}")

    def on_server_unregister(self, ip, port):
        """服务器注销事件"""
        for plugin in self.plugins:
            if hasattr(plugin, "on_server_unregister"):
                try:
                    plugin.on_server_unregister(self.api, ip, port)
                except Exception as e:
                    print(f"[插件错误] on_server_unregister: {e}")

    def on_server_offline(self, ip, port, server_info):
        """服务器离线事件"""
        for plugin in self.plugins:
            if hasattr(plugin, "on_server_offline"):
                try:
                    plugin.on_server_offline(self.api, ip, port, server_info)
                except Exception as e:
                    print(f"[插件错误] on_server_offline: {e}")