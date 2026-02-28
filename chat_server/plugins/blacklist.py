"""
黑名单插件
功能：
- *ban [用户名或UID] - 将用户加入黑名单并踢出（管理员可用）
- *unban [用户名或UID] - 从黑名单移除（管理员可用）
- *banlist - 查看黑名单列表（所有人可用）
- 黑名单用户无法进入聊天室
- 已在房间内的黑名单用户会被立即踢出
"""

import os
import sqlite3
import time
import json
import asyncio
from datetime import datetime

class BlacklistPlugin:
    def __init__(self):
        self.db_path = "data/blacklist.db"
        self.banned_users = {}  # 内存缓存 {uid: {"username": xxx, "reason": "xxx", "banned_at": timestamp}}
        self.banned_ips = {}     # IP黑名单（可选）
        self._init_db()
        self._load_banned_users()
        print("[Blacklist] 黑名单插件已初始化")
    
    def _init_db(self):
        """初始化数据库"""
        os.makedirs("data", exist_ok=True)
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 黑名单表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS blacklist(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid TEXT UNIQUE,
                    username TEXT,
                    reason TEXT,
                    banned_by TEXT,
                    banned_at INTEGER,
                    expires_at INTEGER DEFAULT 0
                )
            """)
            
            # IP黑名单表（可选）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ip_blacklist(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip TEXT UNIQUE,
                    reason TEXT,
                    banned_by TEXT,
                    banned_at INTEGER
                )
            """)
            
            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_blacklist_uid ON blacklist(uid)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_blacklist_username ON blacklist(username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ip_blacklist_ip ON ip_blacklist(ip)")
            
            conn.commit()
            conn.close()
            print("[Blacklist] 数据库初始化成功")
        except Exception as e:
            print(f"[Blacklist] 数据库初始化失败: {e}")
    
    def _load_banned_users(self):
        """加载黑名单用户到内存"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT uid, username, reason, banned_at, expires_at FROM blacklist")
            rows = cursor.fetchall()
            
            current_time = int(time.time())
            for row in rows:
                uid, username, reason, banned_at, expires_at = row
                # 检查是否过期
                if expires_at and expires_at < current_time:
                    # 过期了，自动删除
                    cursor.execute("DELETE FROM blacklist WHERE uid=?", (uid,))
                else:
                    self.banned_users[uid] = {
                        "username": username,
                        "reason": reason,
                        "banned_at": banned_at,
                        "expires_at": expires_at
                    }
            
            conn.commit()
            conn.close()
            print(f"[Blacklist] 已加载 {len(self.banned_users)} 个黑名单用户")
        except Exception as e:
            print(f"[Blacklist] 加载黑名单失败: {e}")
    
    def on_load(self, api):
        """插件加载时调用"""
        self.api = api
        self.clients = api.ctx.get('clients', set())
        print("[Blacklist] 插件加载成功 - 支持命令: *ban, *unban, *banlist")
    
    def on_server_start(self, api):
        """服务器启动时调用"""
        print("[Blacklist] 黑名单服务已启动")
    
    async def on_message(self, api, msg):
        """处理消息事件"""
        if msg.get("type") != "text":
            return
        
        content = msg.get("content", "")
        if not content or not content.startswith('*'):
            return
        
        parts = content.lower().strip().split()
        command = parts[0]
        sender = msg.get("user")
        uid = msg.get("uid")
        
        # 检查发送者是否在黑名单中（不应该发生，但以防万一）
        if uid in self.banned_users:
            msg["_blocked"] = True
            return
        
        # ===== *ban 命令：封禁用户（需要管理员权限）=====
        if command == '*ban' and len(parts) >= 2:
            target = ' '.join(parts[1:]).strip()
            await self._handle_ban(api, sender, uid, target)
            msg["_is_command"] = True
            return True
        
        # ===== *unban 命令：解封用户（需要管理员权限）=====
        elif command == '*unban' and len(parts) >= 2:
            target = ' '.join(parts[1:]).strip()
            await self._handle_unban(api, sender, uid, target)
            msg["_is_command"] = True
            return True
        
        # ===== *banlist 命令：查看黑名单（所有人可用）=====
        elif command == '*banlist':
            await self._handle_banlist(api, sender, uid)
            msg["_is_command"] = True
            return True
    
    async def _handle_ban(self, api, operator, operator_uid, target):
        """处理封禁命令"""
        try:
            # ===== 检查管理员权限 =====
            admin_plugin = None
            for plugin in self.api.ctx["plugin_loader"].plugins:
                if hasattr(plugin, 'is_admin'):
                    admin_plugin = plugin
                    break
            
            if not admin_plugin or not admin_plugin.is_admin(operator_uid):
                await api.send_system_message("你没有权限执行此命令（需要管理员权限）")
                return
            
            # 获取目标用户信息
            target_info = await self._find_user(target)
            if not target_info:
                await api.send_system_message(f"未找到用户 '{target}'")
                return
            
            target_uid = target_info["uid"]
            target_username = target_info["username"]
            
            # 检查目标是否是管理员或服主
            if admin_plugin.is_owner(target_uid):
                await api.send_system_message(f"不能封禁服主")
                return
            
            if admin_plugin.is_admin(target_uid) and not admin_plugin.is_owner(operator_uid):
                await api.send_system_message(f"你不能封禁其他管理员")
                return
            
            # 检查是否已在黑名单
            if target_uid in self.banned_users:
                await api.send_system_message(f"用户 {target_username} 已在黑名单中")
                return
            
            # 添加到数据库
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            banned_at = int(time.time())
            
            cursor.execute("""
                INSERT INTO blacklist (uid, username, reason, banned_by, banned_at)
                VALUES (?, ?, ?, ?, ?)
            """, (target_uid, target_username, f"被 {operator} 封禁", operator_uid, banned_at))
            conn.commit()
            conn.close()
            
            # 更新内存缓存
            self.banned_users[target_uid] = {
                "username": target_username,
                "reason": f"被 {operator} 封禁",
                "banned_at": banned_at,
                "expires_at": 0
            }
            
            # 踢出用户（如果在线）
            kicked = await self._kick_user(target_uid, target_username)
            
            await api.send_system_message(
                f"用户 {target_username} 已被封禁{'并踢出房间' if kicked else ''}"
            )
            print(f"[Blacklist] {operator} 封禁了 {target_username} ({target_uid})")
            
        except Exception as e:
            print(f"[Blacklist] 封禁失败: {e}")
            await api.send_system_message("封禁失败，请稍后重试")
    
    async def _handle_unban(self, api, operator, operator_uid, target):
        """处理解封命令"""
        try:
            # ===== 检查管理员权限 =====
            admin_plugin = None
            for plugin in self.api.ctx["plugin_loader"].plugins:
                if hasattr(plugin, 'is_admin'):
                    admin_plugin = plugin
                    break
            
            if not admin_plugin or not admin_plugin.is_admin(operator_uid):
                await api.send_system_message("你没有权限执行此命令（需要管理员权限）")
                return
            
            # 查找目标用户（可能在黑名单中）
            target_uid = None
            target_username = target
            
            # 先检查是否在黑名单缓存中
            for uid, info in self.banned_users.items():
                if info["username"] == target or uid == target:
                    target_uid = uid
                    target_username = info["username"]
                    break
            
            if not target_uid:
                await api.send_system_message(f"未在黑名单中找到用户 '{target}'")
                return
            
            # 从数据库删除
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM blacklist WHERE uid=?", (target_uid,))
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted > 0:
                # 从内存缓存删除
                if target_uid in self.banned_users:
                    del self.banned_users[target_uid]
                
                await api.send_system_message(f"用户 {target_username} 已解封")
                print(f"[Blacklist] {operator} 解封了 {target_username} ({target_uid})")
            else:
                await api.send_system_message(f"解封失败，用户 {target} 不在黑名单中")
                
        except Exception as e:
            print(f"[Blacklist] 解封失败: {e}")
            await api.send_system_message("解封失败，请稍后重试")
    
    async def _handle_banlist(self, api, operator, operator_uid):
        """显示黑名单列表（所有人可用）"""
        if not self.banned_users:
            await api.send_system_message("黑名单为空")
            return
        
        # 格式化显示
        lines = ["黑名单列表:"]
        for i, (uid, info) in enumerate(self.banned_users.items(), 1):
            banned_time = datetime.fromtimestamp(info["banned_at"]).strftime("%m-%d %H:%M")
            lines.append(f"{i}. {info['username']} (UID: {uid}) - {info['reason']} - {banned_time}")
        
        # 分页显示（最多10条）
        if len(lines) > 11:
            lines = lines[:11]
            lines.append(f"...等{len(self.banned_users)}个")
        
        await api.send_system_message("\n".join(lines))
    
    async def _find_user(self, identifier):
        """查找用户（通过UID或用户名）"""
        # 先检查在线用户
        for client in self.clients:
            if hasattr(client, 'username') and client.username:
                if client.username == identifier or (hasattr(client, 'uid') and client.uid == identifier):
                    return {
                        "uid": client.uid if hasattr(client, 'uid') else "unknown",
                        "username": client.username
                    }
        
        # 如果没找到，尝试从数据库查询
        try:
            conn = sqlite3.connect("data/users.db")
            cursor = conn.cursor()
            
            # 尝试作为UID查询
            cursor.execute("SELECT uid, username FROM users WHERE uid=?", (identifier,))
            user = cursor.fetchone()
            if user:
                conn.close()
                return {"uid": user[0], "username": user[1]}
            
            # 尝试作为用户名查询
            cursor.execute("SELECT uid, username FROM users WHERE username=?", (identifier,))
            user = cursor.fetchone()
            conn.close()
            
            if user:
                return {"uid": user[0], "username": user[1]}
            
        except Exception as e:
            print(f"[Blacklist] 查询用户失败: {e}")
        
        return None
    
    async def _kick_user(self, target_uid, target_username):
        """踢出用户（断开WebSocket连接）"""
        kicked = False
        dead = set()
        
        for client in self.clients:
            if hasattr(client, 'uid') and client.uid == target_uid:
                try:
                    # 发送封禁通知
                    await client.send(json.dumps({
                        "type": "system",
                        "content": "你已被管理员封禁",
                        "time": time.time() * 1000
                    }))
                    # 关闭连接
                    await client.close()
                    dead.add(client)
                    kicked = True
                except:
                    dead.add(client)
        
        # 清理断开的连接
        for d in dead:
            self.clients.remove(d)
        
        return kicked
    
    def is_banned(self, uid):
        """检查用户是否被封禁（供WebSocket使用）"""
        return uid in self.banned_users

# 插件实例
plugin = BlacklistPlugin()

# 导出插件接口
on_load = plugin.on_load
on_server_start = plugin.on_server_start
on_message = plugin.on_message

# 导出额外接口供其他插件使用
is_banned = plugin.is_banned