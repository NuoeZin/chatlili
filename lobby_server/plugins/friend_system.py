"""
好友系统插件
功能：
- 好友关系管理（双向好友）
- 关注者管理（单向关注）
- 用户搜索（支持UID和用户名）
- 临时会话缓存（速聊）
- 好友添加通知
- 实时在线状态（心跳机制）
- 2分钟无操作自动离线（前端控制）
"""

import os
import sqlite3
import time
import json
import hashlib
from flask import request, jsonify, make_response
from datetime import datetime, timedelta

class FriendSystemPlugin:
    def __init__(self):
        self.db_path = "data/friends.db"
        self.cache_dir = "chat_cache"
        self.online_users = {}  # 在线用户缓存 {uid: last_heartbeat}
        self.online_timeout = 300  # 5分钟超时（后端保底）
        
        os.makedirs("data", exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        
        self._init_db()
        self._start_cleanup_thread()
        self._start_online_cleanup_thread()
        print("[FriendSystem] 好友系统插件已初始化")
    
    def _init_db(self):
        """初始化数据库"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 好友关系表（双向好友）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS friendships(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_uid TEXT NOT NULL,
                    friend_uid TEXT NOT NULL,
                    status TEXT DEFAULT 'active',  -- active, blocked, deleted
                    created_at INTEGER,
                    updated_at INTEGER,
                    UNIQUE(user_uid, friend_uid)
                )
            """)
            
            # 关注者表（单向关注）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS followers(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    follower_uid TEXT NOT NULL,  -- 关注者
                    followed_uid TEXT NOT NULL,  -- 被关注者
                    status TEXT DEFAULT 'pending',  -- pending, accepted, rejected
                    created_at INTEGER,
                    updated_at INTEGER,
                    UNIQUE(follower_uid, followed_uid)
                )
            """)
            
            # 好友请求表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS friend_requests(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_uid TEXT NOT NULL,
                    to_uid TEXT NOT NULL,
                    message TEXT,
                    status TEXT DEFAULT 'pending',  -- pending, accepted, rejected
                    created_at INTEGER,
                    UNIQUE(from_uid, to_uid)
                )
            """)
            
            # 速聊会话索引表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS quick_chats(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user1_uid TEXT NOT NULL,
                    user2_uid TEXT NOT NULL,
                    chat_id TEXT UNIQUE NOT NULL,
                    created_at INTEGER,
                    last_active INTEGER,
                    UNIQUE(user1_uid, user2_uid)
                )
            """)
            
            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_friendships_user ON friendships(user_uid)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_friendships_friend ON friendships(friend_uid)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_followers_follower ON followers(follower_uid)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_followers_followed ON followers(followed_uid)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_requests_from ON friend_requests(from_uid)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_requests_to ON friend_requests(to_uid)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_quick_chats_users ON quick_chats(user1_uid, user2_uid)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_quick_chats_chat_id ON quick_chats(chat_id)")
            
            conn.commit()
            conn.close()
            print("[FriendSystem] 数据库初始化成功")
            
        except Exception as e:
            print(f"[FriendSystem] 数据库初始化失败: {e}")
    
    def _start_cleanup_thread(self):
        """启动缓存清理线程"""
        import threading
        
        def cleanup_loop():
            while True:
                time.sleep(3600)  # 每小时检查一次
                self._cleanup_expired_cache()
        
        thread = threading.Thread(target=cleanup_loop, daemon=True)
        thread.start()
        print("[FriendSystem] 缓存清理线程已启动")
    
    def _start_online_cleanup_thread(self):
        """启动在线状态清理线程"""
        import threading
        
        def online_cleanup_loop():
            while True:
                time.sleep(60)  # 每分钟清理一次
                self._cleanup_offline_users()
        
        thread = threading.Thread(target=online_cleanup_loop, daemon=True)
        thread.start()
        print("[FriendSystem] 在线状态清理线程已启动")
    
    def _cleanup_offline_users(self):
        """清理离线用户（超过5分钟没有心跳）"""
        now = time.time()
        expired = []
        for uid, last_seen in self.online_users.items():
            if now - last_seen > self.online_timeout:
                expired.append(uid)
        
        for uid in expired:
            del self.online_users[uid]
        
        if expired:
            print(f"[FriendSystem] 清理 {len(expired)} 个离线用户")
    
    def _update_online_status(self, uid):
        """更新用户在线状态"""
        self.online_users[uid] = time.time()
        print(f"[FriendSystem] 用户 {uid} 更新在线状态")
    
    def _remove_online_status(self, uid):
        """移除用户在线状态（主动离线）"""
        if uid in self.online_users:
            del self.online_users[uid]
            print(f"[FriendSystem] 用户 {uid} 主动离线")
            return True
        return False
    
    def _is_online(self, uid):
        """判断用户是否在线"""
        last_seen = self.online_users.get(uid)
        if last_seen:
            is_online = (time.time() - last_seen) < self.online_timeout
            return is_online
        return False
    
    def _cleanup_expired_cache(self):
        """清理过期的速聊缓存（超过24小时）"""
        try:
            now = time.time()
            expired_time = now - 24 * 3600  # 24小时前
            
            # 清理过期文件
            for filename in os.listdir(self.cache_dir):
                if filename.startswith("chat_") and filename.endswith(".json"):
                    filepath = os.path.join(self.cache_dir, filename)
                    stat = os.stat(filepath)
                    if stat.st_mtime < expired_time:
                        os.remove(filepath)
                        print(f"[FriendSystem] 清理过期缓存: {filename}")
            
            # 清理数据库中的过期记录
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM quick_chats WHERE last_active < ?", (expired_time,))
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted > 0:
                print(f"[FriendSystem] 清理 {deleted} 条过期会话记录")
                
        except Exception as e:
            print(f"[FriendSystem] 清理缓存失败: {e}")
    
    def on_load(self, api):
        """插件加载时调用"""
        self.api = api
        self._register_routes()
        print("[FriendSystem] 插件加载成功")
    
    def _register_routes(self):
        """注册好友系统相关路由"""
        
        # ===== 心跳开始/更新（用户活跃时调用）=====
        @self.api.app.route("/api/friends/heartbeat/start", methods=["POST", "OPTIONS"])
        def friends_heartbeat_start():
            """开始或更新心跳（用户在线）"""
            if request.method == "OPTIONS":
                response = make_response()
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')
                response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
                response.headers.add('Access-Control-Allow-Credentials', 'true')
                return response
            
            data = request.json
            uid = data.get("uid")
            token = data.get("session_token") or request.cookies.get('session_token')
            
            if not uid:
                return {"error": "参数不完整"}, 400
            
            # 验证令牌
            if not self._verify_token(uid, token):
                return {"error": "身份验证失败"}, 401
            
            self._update_online_status(uid)
            
            return jsonify({
                "status": "success",
                "message": "在线状态已更新",
                "online": True,
                "online_users": len(self.online_users)
            })
        
        # ===== 心跳停止（用户主动退出或超时）=====
        @self.api.app.route("/api/friends/heartbeat/stop", methods=["POST", "OPTIONS"])
        def friends_heartbeat_stop():
            """停止心跳（用户离线）"""
            if request.method == "OPTIONS":
                response = make_response()
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')
                response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
                response.headers.add('Access-Control-Allow-Credentials', 'true')
                return response
            
            data = request.json
            uid = data.get("uid")
            token = data.get("session_token") or request.cookies.get('session_token')
            
            if not uid:
                return {"error": "参数不完整"}, 400
            
            # 验证令牌
            if not self._verify_token(uid, token):
                return {"error": "身份验证失败"}, 401
            
            offline = self._remove_online_status(uid)
            
            return jsonify({
                "status": "success",
                "message": "已标记为离线",
                "offline": offline
            })
        
        # ===== 心跳状态查询 =====
        @self.api.app.route("/api/friends/heartbeat/status/<uid>", methods=["GET", "OPTIONS"])
        def friends_heartbeat_status(uid):
            """查询用户在线状态"""
            if request.method == "OPTIONS":
                response = make_response()
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')
                response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS')
                response.headers.add('Access-Control-Allow-Credentials', 'true')
                return response
            
            token = request.args.get("token") or request.cookies.get('session_token')
            
            if not uid:
                return {"error": "参数不完整"}, 400
            
            # 验证令牌
            if not self._verify_token(uid, token):
                return {"error": "身份验证失败"}, 401
            
            is_online = self._is_online(uid)
            last_seen = self.online_users.get(uid)
            
            return jsonify({
                "uid": uid,
                "is_online": is_online,
                "last_seen": last_seen,
                "timeout": self.online_timeout
            })
        
        # ===== 搜索用户 =====
        @self.api.app.route("/api/friends/search", methods=["POST", "OPTIONS"])
        def search_users():
            """搜索用户（支持UID或用户名）"""
            if request.method == "OPTIONS":
                response = make_response()
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')
                response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
                response.headers.add('Access-Control-Allow-Credentials', 'true')
                return response
            
            data = request.json
            query = data.get("query", "").strip()
            current_uid = data.get("uid")  # 当前用户UID
            token = data.get("session_token") or request.cookies.get('session_token')
            
            if not query or len(query) < 2:
                return {"error": "搜索关键词至少2个字符"}, 400
            
            if not current_uid or not token:
                return {"error": "未登录"}, 401
            
            # 验证令牌
            if not self._verify_token(current_uid, token):
                return {"error": "身份验证失败"}, 401
            
            # 更新当前用户在线状态
            self._update_online_status(current_uid)
            
            # 连接用户数据库进行搜索
            try:
                # 连接到用户数据库
                user_db = sqlite3.connect("data/users.db")
                user_cursor = user_db.cursor()
                
                # 判断查询是UID还是用户名
                results = []
                
                if query.isdigit() and len(query) == 8:
                    # 按UID精确搜索
                    user_cursor.execute("""
                        SELECT uid, username, avatar, email 
                        FROM users WHERE uid=?
                    """, (query,))
                    user = user_cursor.fetchone()
                    if user and user[0] != current_uid:  # 排除自己
                        is_online = self._is_online(user[0])
                        results.append({
                            "uid": user[0],
                            "username": user[1],
                            "avatar": user[2],
                            "email": user[3],
                            "is_online": is_online
                        })
                else:
                    # 按用户名模糊搜索
                    user_cursor.execute("""
                        SELECT uid, username, avatar, email 
                        FROM users WHERE username LIKE ? LIMIT 20
                    """, (f"%{query}%",))
                    
                    for user in user_cursor.fetchall():
                        if user[0] != current_uid:  # 排除自己
                            is_online = self._is_online(user[0])
                            results.append({
                                "uid": user[0],
                                "username": user[1],
                                "avatar": user[2],
                                "email": user[3],
                                "is_online": is_online
                            })
                
                user_db.close()
                
                # 为每个结果添加关系状态
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                for user in results:
                    # 检查是否是双向好友
                    cursor.execute("""
                        SELECT status FROM friendships 
                        WHERE user_uid=? AND friend_uid=?
                    """, (current_uid, user["uid"]))
                    friendship = cursor.fetchone()
                    
                    # 检查是否是关注者（对方关注了我）
                    cursor.execute("""
                        SELECT status FROM followers 
                        WHERE follower_uid=? AND followed_uid=?
                    """, (user["uid"], current_uid))
                    follower = cursor.fetchone()
                    
                    # 检查我是否关注了对方
                    cursor.execute("""
                        SELECT status FROM followers 
                        WHERE follower_uid=? AND followed_uid=?
                    """, (current_uid, user["uid"]))
                    following = cursor.fetchone()
                    
                    user["is_friend"] = friendship is not None and friendship[0] == 'active'
                    user["is_follower"] = follower is not None and follower[0] == 'pending'
                    user["is_following"] = following is not None and following[0] == 'pending'
                
                conn.close()
                
                return jsonify({
                    "results": results,
                    "total": len(results)
                })
                
            except Exception as e:
                print(f"[FriendSystem] 搜索用户失败: {e}")
                return {"error": str(e)}, 500
        
        # ===== 添加关注 =====
        @self.api.app.route("/api/friends/follow", methods=["POST", "OPTIONS"])
        def follow_user():
            """关注用户（单向）"""
            if request.method == "OPTIONS":
                response = make_response()
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')
                response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
                response.headers.add('Access-Control-Allow-Credentials', 'true')
                return response
            
            data = request.json
            follower_uid = data.get("uid")  # 关注者
            followed_uid = data.get("followed_uid")  # 被关注者
            token = data.get("session_token") or request.cookies.get('session_token')
            
            if not follower_uid or not followed_uid:
                return {"error": "参数不完整"}, 400
            
            if follower_uid == followed_uid:
                return {"error": "不能关注自己"}, 400
            
            # 验证令牌
            if not self._verify_token(follower_uid, token):
                return {"error": "身份验证失败"}, 401
            
            # 更新关注者在线状态
            self._update_online_status(follower_uid)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                timestamp = int(time.time())
                
                # 检查是否已存在关注关系
                cursor.execute("""
                    SELECT status FROM followers 
                    WHERE follower_uid=? AND followed_uid=?
                """, (follower_uid, followed_uid))
                existing = cursor.fetchone()
                
                if existing:
                    if existing[0] == 'rejected':
                        # 重新关注
                        cursor.execute("""
                            UPDATE followers SET status='pending', updated_at=?
                            WHERE follower_uid=? AND followed_uid=?
                        """, (timestamp, follower_uid, followed_uid))
                        message = "已重新关注"
                    else:
                        return {"error": "已关注"}, 400
                else:
                    # 新建关注关系
                    cursor.execute("""
                        INSERT INTO followers (follower_uid, followed_uid, status, created_at, updated_at)
                        VALUES (?, ?, 'pending', ?, ?)
                    """, (follower_uid, followed_uid, timestamp, timestamp))
                    message = "关注成功"
                
                conn.commit()
                
                # 检查是否形成双向好友（对方也关注了我）
                cursor.execute("""
                    SELECT status FROM followers 
                    WHERE follower_uid=? AND followed_uid=?
                """, (followed_uid, follower_uid))
                mutual = cursor.fetchone()
                
                # 如果双向关注，自动建立好友关系
                if mutual and mutual[0] == 'pending':
                    # 建立双向好友关系
                    cursor.execute("""
                        INSERT OR REPLACE INTO friendships (user_uid, friend_uid, status, created_at, updated_at)
                        VALUES (?, ?, 'active', ?, ?)
                    """, (follower_uid, followed_uid, timestamp, timestamp))
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO friendships (user_uid, friend_uid, status, created_at, updated_at)
                        VALUES (?, ?, 'active', ?, ?)
                    """, (followed_uid, follower_uid, timestamp, timestamp))
                    
                    conn.commit()
                    
                    print(f"[FriendSystem] 用户 {follower_uid} 和 {followed_uid} 已成为好友")
                
                # 获取被关注者信息
                user_db = sqlite3.connect("data/users.db")
                user_cursor = user_db.cursor()
                user_cursor.execute("SELECT username, avatar FROM users WHERE uid=?", (followed_uid,))
                followed_info = user_cursor.fetchone()
                user_db.close()
                
                return jsonify({
                    "status": "success",
                    "message": message,
                    "followed": {
                        "uid": followed_uid,
                        "username": followed_info[0] if followed_info else "未知用户",
                        "avatar": followed_info[1] if followed_info else "default.png",
                        "is_online": self._is_online(followed_uid)
                    }
                })
                
            except Exception as e:
                print(f"[FriendSystem] 关注失败: {e}")
                return {"error": str(e)}, 500
            finally:
                conn.close()
        
        # ===== 取消关注 =====
        @self.api.app.route("/api/friends/unfollow", methods=["POST", "OPTIONS"])
        def unfollow_user():
            """取消关注"""
            if request.method == "OPTIONS":
                response = make_response()
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')
                response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
                response.headers.add('Access-Control-Allow-Credentials', 'true')
                return response
            
            data = request.json
            follower_uid = data.get("uid")
            followed_uid = data.get("followed_uid")
            token = data.get("session_token") or request.cookies.get('session_token')
            
            if not follower_uid or not followed_uid:
                return {"error": "参数不完整"}, 400
            
            # 验证令牌
            if not self._verify_token(follower_uid, token):
                return {"error": "身份验证失败"}, 401
            
            # 更新用户在线状态
            self._update_online_status(follower_uid)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # 删除关注关系
                cursor.execute("""
                    DELETE FROM followers 
                    WHERE follower_uid=? AND followed_uid=?
                """, (follower_uid, followed_uid))
                
                # 检查是否还有双向好友关系，如果有，也删除
                cursor.execute("""
                    DELETE FROM friendships 
                    WHERE (user_uid=? AND friend_uid=?) OR (user_uid=? AND friend_uid=?)
                """, (follower_uid, followed_uid, followed_uid, follower_uid))
                
                conn.commit()
                
                return jsonify({"status": "success", "message": "已取消关注"})
                
            except Exception as e:
                print(f"[FriendSystem] 取消关注失败: {e}")
                return {"error": str(e)}, 500
            finally:
                conn.close()
        
        # ===== 获取关注者列表（谁关注了我）=====
        @self.api.app.route("/api/friends/followers", methods=["POST", "OPTIONS"])
        def get_followers():
            """获取关注者列表（单向关注我的人）"""
            if request.method == "OPTIONS":
                response = make_response()
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')
                response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
                response.headers.add('Access-Control-Allow-Credentials', 'true')
                return response
            
            data = request.json
            user_uid = data.get("uid")
            token = data.get("session_token") or request.cookies.get('session_token')
            
            if not user_uid:
                return {"error": "参数不完整"}, 400
            
            # 验证令牌
            if not self._verify_token(user_uid, token):
                return {"error": "身份验证失败"}, 401
            
            # 更新用户在线状态
            self._update_online_status(user_uid)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # 获取关注我的人（且我没有关注他们）
                cursor.execute("""
                    SELECT f.follower_uid, f.created_at 
                    FROM followers f
                    LEFT JOIN followers f2 ON f2.follower_uid=? AND f2.followed_uid=f.follower_uid
                    WHERE f.followed_uid=? AND f2.follower_uid IS NULL
                    ORDER BY f.created_at DESC
                """, (user_uid, user_uid))
                followers = cursor.fetchall()
                
                result = []
                user_db = sqlite3.connect("data/users.db")
                user_cursor = user_db.cursor()
                
                for follower_uid, created_at in followers:
                    user_cursor.execute("""
                        SELECT username, avatar, email 
                        FROM users WHERE uid=?
                    """, (follower_uid,))
                    user = user_cursor.fetchone()
                    
                    if user:
                        is_online = self._is_online(follower_uid)
                        result.append({
                            "uid": follower_uid,
                            "username": user[0],
                            "avatar": user[1] or "default.png",
                            "email": user[2],
                            "is_online": is_online,
                            "followed_since": created_at
                        })
                
                user_db.close()
                
                return jsonify({
                    "followers": result,
                    "total": len(result)
                })
                
            except Exception as e:
                print(f"[FriendSystem] 获取关注者失败: {e}")
                return {"error": str(e)}, 500
            finally:
                conn.close()
        
        # ===== 获取好友列表（双向）=====
        @self.api.app.route("/api/friends/list", methods=["POST", "OPTIONS"])
        def get_friends():
            """获取好友列表（双向互关）"""
            if request.method == "OPTIONS":
                response = make_response()
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')
                response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
                response.headers.add('Access-Control-Allow-Credentials', 'true')
                return response
            
            data = request.json
            user_uid = data.get("uid")
            token = data.get("session_token") or request.cookies.get('session_token')
            
            if not user_uid:
                return {"error": "参数不完整"}, 400
            
            # 验证令牌
            if not self._verify_token(user_uid, token):
                return {"error": "身份验证失败"}, 401
            
            # 更新用户在线状态
            self._update_online_status(user_uid)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # 获取所有好友（双向关系）
                cursor.execute("""
                    SELECT friend_uid, created_at FROM friendships 
                    WHERE user_uid=? AND status='active'
                    ORDER BY created_at DESC
                """, (user_uid,))
                friends = cursor.fetchall()
                
                result = []
                user_db = sqlite3.connect("data/users.db")
                user_cursor = user_db.cursor()
                
                for friend_uid, created_at in friends:
                    user_cursor.execute("""
                        SELECT username, avatar, email 
                        FROM users WHERE uid=?
                    """, (friend_uid,))
                    user = user_cursor.fetchone()
                    
                    if user:
                        is_online = self._is_online(friend_uid)
                        result.append({
                            "uid": friend_uid,
                            "username": user[0],
                            "avatar": user[1] or "default.png",
                            "email": user[2],
                            "is_online": is_online,
                            "friend_since": created_at
                        })
                
                user_db.close()
                
                return jsonify({
                    "friends": result,
                    "total": len(result)
                })
                
            except Exception as e:
                print(f"[FriendSystem] 获取好友列表失败: {e}")
                return {"error": str(e)}, 500
            finally:
                conn.close()
        
        # ===== 获取好友数量（用于个人主页）=====
        @self.api.app.route("/api/friends/count/<uid>", methods=["GET", "OPTIONS"])
        def get_friend_count(uid):
            """获取用户的好友数量和追随者数量"""
            if request.method == "OPTIONS":
                response = make_response()
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')
                response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS')
                response.headers.add('Access-Control-Allow-Credentials', 'true')
                return response
            
            token = request.args.get("token") or request.cookies.get('session_token')
            viewer_uid = request.args.get("viewer_uid")  # 查看者的UID
            
            if not uid:
                return {"error": "参数不完整"}, 400
            
            # 验证令牌 - 使用查看者的UID而不是目标用户的UID
            if not self._verify_token(viewer_uid or uid, token):
                return {"error": "身份验证失败"}, 401
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # 获取好友数量
                cursor.execute("""
                    SELECT COUNT(*) FROM friendships 
                    WHERE user_uid=? AND status='active'
                """, (uid,))
                friend_count = cursor.fetchone()[0]
                
                # 获取追随者数量（关注我的人）
                cursor.execute("""
                    SELECT COUNT(*) FROM followers 
                    WHERE followed_uid=? AND status='pending'
                """, (uid,))
                follower_count = cursor.fetchone()[0]
                
                return jsonify({
                    "uid": uid,
                    "friends": friend_count,
                    "followers": follower_count
                })
                
            except Exception as e:
                print(f"[FriendSystem] 获取数量失败: {e}")
                return {"error": str(e)}, 500
            finally:
                conn.close()
        
        # ===== 速聊（临时会话）- 修复版本 =====
        @self.api.app.route("/api/friends/quickchat", methods=["POST", "OPTIONS"])
        def quick_chat():
            """创建或获取速聊会话（缓存24小时）"""
            if request.method == "OPTIONS":
                response = make_response()
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')
                response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
                response.headers.add('Access-Control-Allow-Credentials', 'true')
                return response
            
            data = request.json
            from_uid = data.get("from_uid")
            to_uid = data.get("to_uid")
            message = data.get("message", "").strip()
            token = data.get("session_token") or request.cookies.get('session_token')
            
            if not from_uid or not to_uid:
                return {"error": "参数不完整"}, 400
            
            if from_uid == to_uid:
                return {"error": "不能给自己发消息"}, 400
            
            # 验证令牌
            if not self._verify_token(from_uid, token):
                return {"error": "身份验证失败"}, 401
            
            # 更新发送者在线状态
            self._update_online_status(from_uid)
            
            # 检查是否为好友（只有好友才能速聊）
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT status FROM friendships 
                WHERE user_uid=? AND friend_uid=?
            """, (from_uid, to_uid))
            friendship = cursor.fetchone()
            
            if not friendship or friendship[0] != 'active':
                conn.close()
                return {"error": "只有好友才能速聊"}, 403
            
            timestamp = int(time.time())
            expire_time = timestamp + 24 * 3600  # 24小时后过期
            
            try:
                # 检查是否已有会话（双向检查）
                cursor.execute("""
                    SELECT chat_id FROM quick_chats 
                    WHERE (user1_uid=? AND user2_uid=?) OR (user1_uid=? AND user2_uid=?)
                """, (from_uid, to_uid, to_uid, from_uid))
                
                existing = cursor.fetchone()
                
                if existing:
                    # 已有会话，使用现有chat_id
                    chat_id = existing[0]
                    print(f"[FriendSystem] 使用现有会话: {chat_id} between {from_uid} and {to_uid}")
                    
                    # 更新最后活动时间
                    cursor.execute("""
                        UPDATE quick_chats SET last_active=? WHERE chat_id=?
                    """, (timestamp, chat_id))
                    conn.commit()
                    
                    # 读取现有会话文件
                    filepath = os.path.join(self.cache_dir, f"chat_{chat_id}.json")
                    if os.path.exists(filepath):
                        with open(filepath, 'r', encoding='utf-8') as f:
                            chat_data = json.load(f)
                        
                        # 如果文件已过期，重新创建
                        if time.time() > chat_data.get("expires_at", 0):
                            os.remove(filepath)
                            # 继续执行下面的创建新会话逻辑
                        else:
                            # 如果有初始消息，添加到会话
                            if message:
                                message_id = len(chat_data["messages"]) + 1
                                new_message = {
                                    "id": message_id,
                                    "from_uid": from_uid,
                                    "content": message,
                                    "timestamp": timestamp,
                                    "read": False
                                }
                                chat_data["messages"].append(new_message)
                                chat_data["last_message"] = {
                                    "from_uid": from_uid,
                                    "content": message,
                                    "timestamp": timestamp
                                }
                                
                                # 保存回文件
                                with open(filepath, 'w', encoding='utf-8') as f:
                                    json.dump(chat_data, f, ensure_ascii=False, indent=2)
                            
                            # 获取对方信息
                            user_db = sqlite3.connect("data/users.db")
                            cursor2 = user_db.cursor()
                            cursor2.execute("SELECT username, avatar FROM users WHERE uid=?", (to_uid,))
                            to_user = cursor2.fetchone()
                            cursor2.execute("SELECT username, avatar FROM users WHERE uid=?", (from_uid,))
                            from_user = cursor2.fetchone()
                            user_db.close()
                            
                            conn.close()
                            
                            return jsonify({
                                "status": "success",
                                "chat_id": chat_id,
                                "expires_at": chat_data.get("expires_at", expire_time),
                                "to_user": {
                                    "uid": to_uid,
                                    "username": to_user[0] if to_user else "未知用户",
                                    "avatar": to_user[1] if to_user else "default.png",
                                    "is_online": self._is_online(to_uid)
                                },
                                "from_user": {
                                    "uid": from_uid,
                                    "username": from_user[0] if from_user else "未知用户",
                                    "avatar": from_user[1] if from_user else "default.png",
                                    "is_online": self._is_online(from_uid)
                                },
                                "message_sent": bool(message),
                                "existing": True
                            })
                
                # 没有现有会话，创建新会话
                # 生成会话ID（使用两个UID的哈希，确保相同两人总是相同ID）
                sorted_uids = sorted([from_uid, to_uid])
                chat_id = hashlib.md5(f"{sorted_uids[0]}:{sorted_uids[1]}:{int(time.time() / 86400)}".encode()).hexdigest()[:16]
                
                print(f"[FriendSystem] 创建新会话: {chat_id} between {from_uid} and {to_uid}")
                
                # 保存到索引表
                cursor.execute("""
                    INSERT OR REPLACE INTO quick_chats (user1_uid, user2_uid, chat_id, created_at, last_active)
                    VALUES (?, ?, ?, ?, ?)
                """, (sorted_uids[0], sorted_uids[1], chat_id, timestamp, timestamp))
                conn.commit()
                
                # 创建缓存文件
                chat_data = {
                    "chat_id": chat_id,
                    "participants": [from_uid, to_uid],
                    "messages": [],
                    "created_at": timestamp,
                    "expires_at": expire_time,
                    "last_message": None
                }
                
                if message:
                    chat_data["messages"].append({
                        "id": 1,
                        "from_uid": from_uid,
                        "content": message,
                        "timestamp": timestamp,
                        "read": False
                    })
                    chat_data["last_message"] = {
                        "from_uid": from_uid,
                        "content": message,
                        "timestamp": timestamp
                    }
                
                # 保存到文件
                filepath = os.path.join(self.cache_dir, f"chat_{chat_id}.json")
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(chat_data, f, ensure_ascii=False, indent=2)
                
                # 获取对方信息
                user_db = sqlite3.connect("data/users.db")
                cursor2 = user_db.cursor()
                cursor2.execute("SELECT username, avatar FROM users WHERE uid=?", (to_uid,))
                to_user = cursor2.fetchone()
                cursor2.execute("SELECT username, avatar FROM users WHERE uid=?", (from_uid,))
                from_user = cursor2.fetchone()
                user_db.close()
                
                conn.close()
                
                return jsonify({
                    "status": "success",
                    "chat_id": chat_id,
                    "expires_at": expire_time,
                    "to_user": {
                        "uid": to_uid,
                        "username": to_user[0] if to_user else "未知用户",
                        "avatar": to_user[1] if to_user else "default.png",
                        "is_online": self._is_online(to_uid)
                    },
                    "from_user": {
                        "uid": from_uid,
                        "username": from_user[0] if from_user else "未知用户",
                        "avatar": from_user[1] if from_user else "default.png",
                        "is_online": self._is_online(from_uid)
                    },
                    "message_sent": bool(message),
                    "existing": False
                })
                
            except Exception as e:
                print(f"[FriendSystem] 创建速聊失败: {e}")
                import traceback
                traceback.print_exc()
                return {"error": str(e)}, 500
            finally:
                if conn:
                    conn.close()
        
        # ===== 获取速聊会话 =====
        @self.api.app.route("/api/friends/quickchat/<chat_id>", methods=["GET", "OPTIONS"])
        def get_quick_chat(chat_id):
            """获取速聊会话内容"""
            if request.method == "OPTIONS":
                response = make_response()
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')
                response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS')
                response.headers.add('Access-Control-Allow-Credentials', 'true')
                return response
            
            uid = request.args.get("uid")
            token = request.args.get("token") or request.cookies.get('session_token')
            
            if not uid:
                return {"error": "未指定用户"}, 400
            
            # 验证令牌
            if not self._verify_token(uid, token):
                return {"error": "身份验证失败"}, 401
            
            # 更新用户在线状态
            self._update_online_status(uid)
            
            filepath = os.path.join(self.cache_dir, f"chat_{chat_id}.json")
            if not os.path.exists(filepath):
                return {"error": "会话不存在或已过期"}, 404
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    chat_data = json.load(f)
                
                # 验证用户是否参与会话
                if uid not in chat_data["participants"]:
                    return {"error": "无权限访问此会话"}, 403
                
                # 检查是否过期
                if time.time() > chat_data["expires_at"]:
                    os.remove(filepath)
                    # 同时删除索引
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM quick_chats WHERE chat_id=?", (chat_id,))
                    conn.commit()
                    conn.close()
                    return {"error": "会话已过期"}, 404
                
                # 更新最后活动时间
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE quick_chats SET last_active=? WHERE chat_id=?
                """, (int(time.time()), chat_id))
                conn.commit()
                conn.close()
                
                return jsonify(chat_data)
                
            except Exception as e:
                print(f"[FriendSystem] 获取会话失败: {e}")
                return {"error": str(e)}, 500
        
        # ===== 发送速聊消息 =====
        @self.api.app.route("/api/friends/quickchat/<chat_id>/send", methods=["POST", "OPTIONS"])
        def send_quick_message(chat_id):
            """发送速聊消息"""
            if request.method == "OPTIONS":
                response = make_response()
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')
                response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
                response.headers.add('Access-Control-Allow-Credentials', 'true')
                return response
            
            data = request.json
            from_uid = data.get("from_uid")
            content = data.get("content", "").strip()
            token = data.get("session_token") or request.cookies.get('session_token')
            
            if not from_uid or not content:
                return {"error": "参数不完整"}, 400
            
            # 验证令牌
            if not self._verify_token(from_uid, token):
                return {"error": "身份验证失败"}, 401
            
            # 更新发送者在线状态
            self._update_online_status(from_uid)
            
            filepath = os.path.join(self.cache_dir, f"chat_{chat_id}.json")
            if not os.path.exists(filepath):
                return {"error": "会话不存在或已过期"}, 404
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    chat_data = json.load(f)
                
                # 验证用户是否参与会话
                if from_uid not in chat_data["participants"]:
                    return {"error": "无权限发送消息"}, 403
                
                # 检查是否过期
                if time.time() > chat_data["expires_at"]:
                    os.remove(filepath)
                    return {"error": "会话已过期"}, 404
                
                # 添加消息
                message_id = len(chat_data["messages"]) + 1
                timestamp = int(time.time())
                
                message = {
                    "id": message_id,
                    "from_uid": from_uid,
                    "content": content,
                    "timestamp": timestamp,
                    "read": False
                }
                
                chat_data["messages"].append(message)
                chat_data["last_message"] = {
                    "from_uid": from_uid,
                    "content": content,
                    "timestamp": timestamp
                }
                
                # 保存回文件
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(chat_data, f, ensure_ascii=False, indent=2)
                
                # 更新最后活动时间
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE quick_chats SET last_active=? WHERE chat_id=?
                """, (timestamp, chat_id))
                conn.commit()
                conn.close()
                
                return jsonify({
                    "status": "success",
                    "message": message
                })
                
            except Exception as e:
                print(f"[FriendSystem] 发送消息失败: {e}")
                return {"error": str(e)}, 500
    
    def _verify_token(self, uid, token):
        """验证用户令牌"""
        try:
            conn = sqlite3.connect("data/users.db")
            cursor = conn.cursor()
            cursor.execute("""
                SELECT uid FROM sessions 
                WHERE token=? AND uid=? AND expires_at > ?
            """, (token, uid, int(time.time())))
            result = cursor.fetchone()
            conn.close()
            return result is not None
        except:
            return False

# 插件实例
plugin = FriendSystemPlugin()

# 导出插件接口
on_load = plugin.on_load