"""
用户基础指令插件
功能：提供 *list 显示在线人数，*time 显示当前网络时间，*help 显示所有可用命令
"""

import time
import json  # 添加这行
from datetime import datetime

class UserCommandsPlugin:
    """用户基础指令插件"""
    
    def __init__(self):
        print("[UserCommands] 用户指令插件已初始化")
    
    def on_load(self, api):
        """插件加载时调用"""
        self.api = api
        print("[UserCommands] 插件加载成功 - 支持指令: *list, *time, *help")
    
    def on_server_start(self, api):
        """服务器启动时调用"""
        print("[UserCommands] 用户指令服务已启动")
    
    def _get_admin_plugin(self):
        """获取管理员插件实例"""
        plugin_loader = self.api.ctx.get('plugin_loader')
        if plugin_loader and hasattr(plugin_loader, 'plugins'):
            for plugin in plugin_loader.plugins:
                if hasattr(plugin, 'is_admin'):
                    return plugin
        return None
    
    def _get_blacklist_plugin(self):
        """获取黑名单插件实例"""
        plugin_loader = self.api.ctx.get('plugin_loader')
        if plugin_loader and hasattr(plugin_loader, 'plugins'):
            for plugin in plugin_loader.plugins:
                if hasattr(plugin, 'is_banned'):
                    return plugin
        return None
    
    async def _send_private_message(self, api, target_username, message_data):
        """发送私聊消息给指定用户（像彩蛋那样）"""
        clients = api.ctx.get('clients', set())
        for client in clients:
            if hasattr(client, 'username') and client.username == target_username:
                try:
                    await client.send(json.dumps(message_data))
                    return True
                except Exception as e:
                    print(f"[UserCommands] 发送私聊消息失败: {e}")
        return False
    
    async def on_message(self, api, msg):
        """处理消息事件"""
        if msg.get("type") != "text":
            return
        
        content = msg.get("content", "")
        if not content or not content.startswith('*'):
            return
        
        command = content.lower().strip()
        sender = msg.get("user")
        uid = msg.get("uid")
        
        # 标记为指令消息，不存入数据库
        msg["_is_command"] = True
        msg["_no_store"] = True  # 确保不存储
        
        # ===== *help 指令：显示所有可用命令 =====
        if command == '*help':
            await self._handle_help_command(api, sender, uid)
            return True
        
        # ===== *list 指令：显示在线人数 =====
        elif command == '*list':
            await self._handle_list_command(api, sender, uid)
            return True
        
        # ===== *time 指令：显示当前网络时间 =====
        elif command == '*time':
            await self._handle_time_command(api, sender, uid)
            return True
    
    async def _handle_help_command(self, api, sender, uid):
        """处理 *help 指令 - 显示所有可用命令及其权限要求"""
        
        # 获取权限插件
        admin_plugin = self._get_admin_plugin()
        is_admin = admin_plugin and admin_plugin.is_admin(uid) if admin_plugin else False
        is_owner = admin_plugin and admin_plugin.is_owner(uid) if admin_plugin else False
        
        # 构建帮助信息
        help_lines = []
        help_lines.append("**命令帮助列表**\n")
        help_lines.append("")
        
        # 通用命令（所有人可用）
        help_lines.append("**通用命令** (所有人可用):\n")
        help_lines.append("  `*help` - 显示本帮助菜单\n")
        help_lines.append("  `*list` - 查看当前在线用户列表\n")
        help_lines.append("  `*time` - 显示当前网络时间\n")
        help_lines.append("  `*bug` - 触发？🤔（仅自己可见）\n")
        help_lines.append("  `*banlist` - 查看封禁列表\n")
        help_lines.append("\n\n")
        
        # 管理员命令
        help_lines.append("**管理员命令** (需要管理员权限):\n")
        help_lines.append("  `*ban [用户名/UID] [原因]` - 封禁用户\n")
        help_lines.append("  `*unban [用户名/UID]` - 解封用户\n")
        help_lines.append("\n\n")
        
        # 服主专属命令
        help_lines.append("**服主命令** (仅服主可用):\n")
        help_lines.append("  `*op [用户名/UID]` - 将用户设为管理员\n")
        help_lines.append("  `*deop [用户名/UID]` - 移除管理员权限\n")
        help_lines.append("  `*admins` - 查看管理员列表\n")
        help_lines.append("\n\n")
        
        # 当前用户权限状态
        help_lines.append("**你的权限状态**:\n")
        if is_owner:
            help_lines.append("  你是 **服主**，拥有所有权限\n")
        elif is_admin:
            help_lines.append("  你是 **管理员**，可以执行管理员命令\n")
        else:
            help_lines.append("  你是 **普通用户**，只能使用通用命令\n")
        
        help_lines.append("\n\n")
        help_lines.append("提示：命令前的 `*` 是必需的\n")
        
        # 创建气泡消息（模仿彩蛋的私聊格式）
        help_message = {
            "type": "text",
            "user": "help帮助",
            "content": "\n".join(help_lines),
            "time": int(time.time() * 1000),
            "avatar": "avatars/serverchat.png",  # 使用服务器头像
            "_command_help": True,
            "_private": True  # 标记为私聊消息
        }
        
        # 只发送给触发者（像彩蛋那样）
        await self._send_private_message(api, sender, help_message)
        print(f"[UserCommands] {sender} 查询了帮助菜单 (权限: {'服主' if is_owner else '管理员' if is_admin else '普通用户'})")
    
    async def _handle_list_command(self, api, sender, uid):
        """处理 *list 指令"""
        # 获取在线用户列表
        online_users = []
        for client in api.ctx.get('clients', set()):
            if hasattr(client, 'username') and client.username:
                online_users.append(client.username)
        
        online_count = len(online_users)
        
        # 构建显示消息
        if online_count == 0:
            message = "当前没有其他用户在线"
        else:
            user_list = ", ".join(online_users[:10])  # 最多显示10个
            if online_count > 10:
                user_list += f" 等{online_count}人"
            message = f"当前在线用户 ({online_count}人): {user_list}"
        
        # 发送系统消息（广播）
        await api.send_system_message(message)
        print(f"[UserCommands] {sender} 查询了在线列表")
    
    async def _handle_time_command(self, api, sender, uid):
        """处理 *time 指令"""
        # 获取当前时间
        now = datetime.now()
        
        # 格式化时间
        time_str = now.strftime("%Y年%m月%d日 %H:%M:%S")
        weekday = now.weekday()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday_str = weekdays[weekday]
        
        # 获取时间戳
        timestamp = int(time.time())
        
        message = f"当前网络时间: {time_str} {weekday_str} (时间戳: {timestamp})"
        
        # 发送系统消息（广播）
        await api.send_system_message(message)
        print(f"[UserCommands] {sender} 查询了当前时间")

# 插件实例
plugin = UserCommandsPlugin()

# 导出插件接口
on_load = plugin.on_load
on_server_start = plugin.on_server_start
on_message = plugin.on_message