"""
管理员系统插件
功能：
- 设置管理员（OP）
- 服主（owner）从配置文件读取
- 管理员可以执行管理命令
- 支持 *op 用户名/UID 命令
"""

import os
import json
import time
import asyncio
import sqlite3
import requests

class AdminSystemPlugin:
    def __init__(self):
        self.config_path = "config.json"
        self.owner_uids = []  # 服主UID列表
        self.admin_uids = {}  # 管理员UID字典 {uid: {"username": name, "added_by": owner_uid, "time": timestamp}}
        self.admin_list_file = "data/admins.json"
        self.api = None
        self.load_config()
        self.load_admins()
        print("[AdminSystem] 管理员系统插件已初始化")
    
    def load_config(self):
        """从配置文件加载服主UID"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    owner = config.get("owner_uid", "")
                    if owner:
                        # 支持多个服主，用逗号分隔
                        self.owner_uids = [uid.strip() for uid in owner.split(",") if uid.strip()]
                        print(f"[AdminSystem] 服主UID: {self.owner_uids}")
                    else:
                        self.owner_uids = []
                        print("[AdminSystem] 未设置服主UID")
            else:
                print("[AdminSystem] 配置文件不存在")
                self.owner_uids = []
        except Exception as e:
            print(f"[AdminSystem] 加载配置失败: {e}")
            self.owner_uids = []
    
    def load_admins(self):
        """加载已保存的管理员列表"""
        try:
            os.makedirs("data", exist_ok=True)
            if os.path.exists(self.admin_list_file):
                with open(self.admin_list_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.admin_uids = data.get("admins", {})
                print(f"[AdminSystem] 已加载 {len(self.admin_uids)} 个管理员")
            else:
                self.admin_uids = {}
                self.save_admins()
        except Exception as e:
            print(f"[AdminSystem] 加载管理员列表失败: {e}")
            self.admin_uids = {}
    
    def save_admins(self):
        """保存管理员列表"""
        try:
            with open(self.admin_list_file, "w", encoding="utf-8") as f:
                json.dump({"admins": self.admin_uids}, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[AdminSystem] 保存管理员列表失败: {e}")
    
    def on_load(self, api):
        """插件加载时调用"""
        self.api = api
        print("[AdminSystem] 插件加载成功")
    
    def on_server_start(self, api):
        """服务器启动时调用"""
        print(f"[AdminSystem] 服主数量: {len(self.owner_uids)}")
        print(f"[AdminSystem] 管理员数量: {len(self.admin_uids)}")
    
    async def on_message(self, api, msg):
        """处理消息事件 - 检查命令"""
        content = msg.get("content", "")
        if not content or not content.startswith("*"):
            return
        
        uid = msg.get("uid")
        username = msg.get("user")
        
        if not uid or not username:
            return
        
        # 解析命令
        parts = content.strip().split()
        command = parts[0].lower()
        
        # 处理 *op 命令
        if command == "*op":
            await self.handle_op_command(api, msg, uid, username, parts)
        
        # 处理 *deop 命令（移除管理员权限）
        elif command == "*deop":
            await self.handle_deop_command(api, msg, uid, username, parts)
        
        # 处理 *admins 命令（查看管理员列表）
        elif command == "*admins":
            await self.handle_admins_command(api, msg, uid)
    
    async def handle_op_command(self, api, msg, uid, username, parts):
        """处理 *op 命令"""
        # 检查权限：必须是服主
        if uid not in self.owner_uids:
            await api.send_system_message(f"{username}，你没有权限执行此命令")
            return
        
        # 检查是否已连接到服务器
        clients = api.ctx.get('clients', set())
        if len(clients) == 0:
            await api.send_system_message("当前没有用户在线")
            return
        
        if len(parts) < 2:
            await api.send_system_message(f"用法: *op [用户名或UID]")
            return
        
        target = parts[1]
        
        # 获取目标用户信息
        target_info = await self.get_user_info(target)
        if not target_info:
            await api.send_system_message(f"未找到用户: {target}")
            return
        
        target_uid = target_info.get("uid")
        target_name = target_info.get("username")
        
        if not target_uid or not target_name:
            await api.send_system_message(f"无法获取用户信息")
            return
        
        # 检查是否是服主
        if target_uid in self.owner_uids:
            await api.send_system_message(f"{target_name} 是服主，无需设置管理员")
            return
        
        # 添加管理员
        self.admin_uids[target_uid] = {
            "username": target_name,
            "added_by": uid,
            "added_by_name": username,
            "time": int(time.time())
        }
        self.save_admins()
        
        await api.send_system_message(f"{target_name} 已被设置为管理员")
        
        # 发送通知给目标用户
        await self.notify_user(api, target_uid, f"{target_name}被{username}设置为管理员")
    
    async def handle_deop_command(self, api, msg, uid, username, parts):
        """处理 *deop 命令"""
        # 检查权限：必须是服主
        if uid not in self.owner_uids:
            await api.send_system_message(f"{username}，你没有权限执行此命令")
            return
        
        if len(parts) < 2:
            await api.send_system_message(f"用法: *deop [用户名或UID]")
            return
        
        target = parts[1]
        
        # 获取目标用户信息
        target_info = await self.get_user_info(target)
        if not target_info:
            await api.send_system_message(f"未找到用户: {target}")
            return
        
        target_uid = target_info.get("uid")
        target_name = target_info.get("username")
        
        if not target_uid or not target_name:
            await api.send_system_message(f"无法获取用户信息")
            return
        
        # 检查是否是服主
        if target_uid in self.owner_uids:
            await api.send_system_message(f"{target_name} 是服主，无法移除权限")
            return
        
        # 检查是否是管理员
        if target_uid not in self.admin_uids:
            await api.send_system_message(f"{target_name} 不是管理员")
            return
        
        # 移除管理员
        del self.admin_uids[target_uid]
        self.save_admins()
        
        await api.send_system_message(f"已移除 {target_name} 的管理员权限")
        
        # 发送通知给目标用户
        await self.notify_user(api, target_uid, f"{target_name}被{username}移除管理员权限")
    
    async def handle_admins_command(self, api, msg, uid):
        """处理 *admins 命令 - 查看管理员列表"""
        if not self.admin_uids and not self.owner_uids:
            await api.send_system_message("当前没有管理员")
            return
        
        message = "管理员列表\n"
        
        # 显示服主
        if self.owner_uids:
            message += "服主:\n"
            for owner_uid in self.owner_uids:
                # 尝试获取服主用户名
                owner_info = await self.get_user_info(owner_uid)
                if owner_info:
                    message += f"{owner_info.get('username')} (UID: {owner_uid})\n"
                else:
                    message += f"UID: {owner_uid}\n"
        
        # 显示管理员
        if self.admin_uids:
            message += "管理员:\n"
            for admin_uid, admin_info in self.admin_uids.items():
                admin_name = admin_info.get("username", "未知")
                added_by = admin_info.get("added_by_name", "未知")
                time_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(admin_info.get("time", 0)))
                message += f"{admin_name} (UID: {admin_uid})\n由{added_by}于{time_str}任命\n"
        
        await api.send_system_message(message)
    
    async def get_user_info(self, identifier):
        """获取用户信息（通过UID或用户名）"""
        try:
            # 从本地数据库获取
            conn = sqlite3.connect("data/users.db")
            cursor = conn.cursor()
            
            # 尝试通过UID查询
            cursor.execute("SELECT uid, username FROM users WHERE uid=?", (identifier,))
            result = cursor.fetchone()
            
            if result:
                conn.close()
                return {"uid": result[0], "username": result[1]}
            
            # 尝试通过用户名查询
            cursor.execute("SELECT uid, username FROM users WHERE username=?", (identifier,))
            result = cursor.fetchone()
            
            if result:
                conn.close()
                return {"uid": result[0], "username": result[1]}
            
            conn.close()
            
            # 如果本地没有，从大厅获取
            config = self.api.get_config()
            lobby_url = config.get("lobby_url", "").replace('/register', '')
            
            if lobby_url:
                response = requests.get(f"{lobby_url}/api/user/{identifier}", timeout=3)
                if response.status_code == 200:
                    data = response.json()
                    return {"uid": data.get("uid"), "username": data.get("username")}
            
            return None
        except Exception as e:
            print(f"[AdminSystem] 获取用户信息失败: {e}")
            return None
    
    async def notify_user(self, api, uid, message):
        """发送私聊通知给指定用户"""
        # 这里需要遍历所有客户端发送私聊消息
        # 由于无法直接发送私聊，我们发送系统消息
        await api.send_system_message(message)
    
    def is_owner(self, uid):
        """检查是否是服主"""
        return uid in self.owner_uids
    
    def is_admin(self, uid):
        """检查是否是管理员（包括服主）"""
        return uid in self.owner_uids or uid in self.admin_uids

# 插件实例
plugin = AdminSystemPlugin()

# 导出插件接口
on_load = plugin.on_load
on_server_start = plugin.on_server_start
on_message = plugin.on_message

# 导出额外接口
is_owner = plugin.is_owner
is_admin = plugin.is_admin