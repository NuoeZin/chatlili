"""
大厅认证插件 - 简化版：直接验证用户登录状态
"""

import os
import sqlite3
import time
import requests
from flask import request, jsonify

class LobbyAuthPlugin:
    def __init__(self):
        self.lobby_url = None
        print("[LobbyAuth] 大厅认证插件已初始化")
    
    def on_load(self, api):
        """插件加载时调用"""
        self.api = api
        config = api.get_config()
        
        # 从配置读取大厅地址
        lobby_register_url = config.get("lobby_url", "http://localhost:8000/register")
        self.lobby_url = lobby_register_url.replace('/register', '')
        
        print(f"[LobbyAuth] 大厅地址: {self.lobby_url}")
        print("[LobbyAuth] 插件加载成功！")
    
    def on_server_start(self, api):
        """服务器启动时调用"""
        self._init_local_db()
        print("[LobbyAuth] 大厅认证模式已启动")
    
    def _init_local_db(self):
        """初始化本地用户映射表"""
        try:
            conn = sqlite3.connect("data/users.db")
            cursor = conn.cursor()
            
            # 检查是否需要添加新列
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if "lobby_uid" not in columns:
                try:
                    cursor.execute("ALTER TABLE users ADD COLUMN lobby_uid TEXT")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lobby_uid ON users(lobby_uid)")
                    print("[LobbyAuth] 已添加 lobby_uid 列")
                except Exception as e:
                    print(f"[LobbyAuth] 添加列失败: {e}")
            
            if "email" not in columns:
                try:
                    cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
                    print("[LobbyAuth] 已添加 email 列")
                except Exception as e:
                    print(f"[LobbyAuth] 添加列失败: {e}")
            
            conn.commit()
            conn.close()
            
            # 创建映射表
            conn = sqlite3.connect("data/users.db")
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_mapping(
                    lobby_uid TEXT PRIMARY KEY,
                    local_uid TEXT UNIQUE,
                    username TEXT,
                    avatar TEXT,
                    email TEXT,
                    first_seen INTEGER,
                    last_seen INTEGER
                )
            """)
            
            conn.commit()
            conn.close()
            print("[LobbyAuth] 数据库初始化成功")
        except Exception as e:
            print(f"[LobbyAuth] 数据库初始化失败: {e}")
    
    def verify_session(self, data):
        """验证用户会话（由 server.py 调用）"""
        print("[LobbyAuth] 收到会话验证请求")
        
        session_token = data.get("session_token")
        if not session_token:
            return {"status": "fail", "error": "缺少会话令牌"}, 400
        
        # 向大厅验证会话
        user_info = self._verify_session_with_lobby(session_token)
        if not user_info:
            print("[LobbyAuth] 会话无效")
            return {"status": "fail", "error": "会话无效或已过期"}, 401
        
        # 获取或创建本地用户
        local_user = self._get_or_create_local_user(user_info)
        
        print(f"[LobbyAuth] 用户验证成功: {local_user['username']} (大厅:{user_info['uid']} -> 本地:{local_user['local_uid']})")
        
        return {
            "status": "ok",
            "uid": local_user["local_uid"],
            "username": local_user["username"],
            "lobby_uid": user_info["uid"],
            "avatar": user_info.get("avatar", "default.png")
        }
    
    def _verify_session_with_lobby(self, session_token):
        """向大厅验证会话"""
        try:
            print(f"[LobbyAuth] 验证会话: {self.lobby_url}/api/verify_session")
            response = requests.post(
                f"{self.lobby_url}/api/verify_session",
                json={"session_token": session_token},
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("valid"):
                    return {
                        "uid": data["uid"],
                        "username": data["username"],
                        "avatar": data.get("avatar", "default.png"),
                        "email": data.get("email", "")
                    }
            return None
        except requests.exceptions.ConnectionError:
            print(f"[LobbyAuth] 无法连接到大厅服务器: {self.lobby_url}")
            return None
        except Exception as e:
            print(f"[LobbyAuth] 验证失败: {e}")
            return None
    
    def _get_or_create_local_user(self, user_info):
        """获取或创建本地用户"""
        lobby_uid = user_info["uid"]
        username = user_info["username"]
        avatar = user_info.get("avatar", "default.png")
        email = user_info.get("email", "")
        
        conn = sqlite3.connect("data/users.db")
        cursor = conn.cursor()
        
        # 查找是否已有映射
        cursor.execute("""
            SELECT local_uid, username FROM user_mapping WHERE lobby_uid=?
        """, (lobby_uid,))
        mapping = cursor.fetchone()
        
        timestamp = int(time.time())
        
        if mapping:
            local_uid, local_username = mapping
            
            # 更新最后访问时间
            cursor.execute("""
                UPDATE user_mapping SET last_seen=? WHERE lobby_uid=?
            """, (timestamp, lobby_uid))
            
            # 如果用户名变了，同步更新
            if local_username != username:
                cursor.execute("""
                    UPDATE users SET username=?, email=? WHERE uid=?
                """, (username, email, local_uid))
                cursor.execute("""
                    UPDATE user_mapping SET username=?, email=? WHERE lobby_uid=?
                """, (username, email, lobby_uid))
            
            conn.commit()
            conn.close()
            
            return {
                "local_uid": local_uid,
                "username": username,
                "existing": True
            }
        
        # 创建新用户
        import random
        while True:
            local_uid = str(random.randint(10000000, 99999999))
            cursor.execute("SELECT uid FROM users WHERE uid=?", (local_uid,))
            if not cursor.fetchone():
                break
        
        # 插入用户表
        cursor.execute("""
            INSERT INTO users (uid, username, avatar, lobby_uid, email, created_at, last_login)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (local_uid, username, avatar, lobby_uid, email, timestamp, timestamp))
        
        # 插入映射表
        cursor.execute("""
            INSERT INTO user_mapping (lobby_uid, local_uid, username, avatar, email, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (lobby_uid, local_uid, username, avatar, email, timestamp, timestamp))
        
        conn.commit()
        conn.close()
        
        print(f"[LobbyAuth] 新用户映射: {username} (大厅:{lobby_uid} -> 本地:{local_uid})")
        
        return {
            "local_uid": local_uid,
            "username": username,
            "existing": False
        }

# 插件实例
plugin = LobbyAuthPlugin()

# 导出插件接口
on_load = plugin.on_load
on_server_start = plugin.on_server_start
verify_session = plugin.verify_session