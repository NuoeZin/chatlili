"""
用户认证插件 - 管理全局用户注册和登录（中心化版本）
功能：
- 用户注册、登录
- 修改用户名（无需密码，只需会话令牌）
- 修改密码
- 修改邮箱
- 头像上传/获取
- 背景图片上传/获取
- 会话验证
- 用户信息查询（支持UID或用户名）
"""

import os
import sqlite3
import hashlib
import secrets
import time
import json
import uuid
import requests
from flask import request, jsonify, send_from_directory, make_response

class UserAuthPlugin:
    def __init__(self):
        self.db_path = "data/users.db"
        self.avatar_dir = "avatars"
        self.background_dir = "backgrounds"
        os.makedirs("data", exist_ok=True)
        os.makedirs(self.avatar_dir, exist_ok=True)
        os.makedirs(self.background_dir, exist_ok=True)
        
        # 确保数据库文件是有效的SQLite文件
        self._ensure_db_files()
        self._init_db()
        self._create_default_assets()
        print("[UserAuth] 用户认证插件已初始化")
    
    def _ensure_db_files(self):
        """确保数据库文件是有效的SQLite文件"""
        # 检查并修复 users.db
        if os.path.exists(self.db_path) and os.path.getsize(self.db_path) == 0:
            os.remove(self.db_path)
            print("[UserAuth] 移除空的 users.db 文件")
        
        # 如果文件存在但不是SQLite数据库，则删除
        if os.path.exists(self.db_path):
            try:
                conn = sqlite3.connect(self.db_path)
                conn.execute("SELECT 1")
                conn.close()
            except sqlite3.DatabaseError:
                os.remove(self.db_path)
                print(f"[UserAuth] 移除损坏的数据库文件: {self.db_path}")
    
    def _init_db(self):
        """初始化数据库"""
        # 用户数据库
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 用户表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users(
                    uid TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    email TEXT UNIQUE,
                    avatar TEXT DEFAULT 'default.png',
                    created_at INTEGER,
                    last_login INTEGER,
                    status TEXT DEFAULT 'active'
                )
            """)
            
            # 会话表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions(
                    token TEXT PRIMARY KEY,
                    uid TEXT,
                    created_at INTEGER,
                    expires_at INTEGER,
                    client_ip TEXT,
                    user_agent TEXT,
                    FOREIGN KEY(uid) REFERENCES users(uid)
                )
            """)
            
            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_uid ON sessions(uid)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
            
            conn.commit()
            conn.close()
            print("[UserAuth] 用户数据库初始化成功")
            
        except Exception as e:
            print(f"[UserAuth] 用户数据库初始化失败: {e}")
            # 如果失败，尝试删除重建
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE users(
                    uid TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    email TEXT UNIQUE,
                    avatar TEXT DEFAULT 'default.png',
                    created_at INTEGER,
                    last_login INTEGER,
                    status TEXT DEFAULT 'active'
                )
            """)
            cursor.execute("""
                CREATE TABLE sessions(
                    token TEXT PRIMARY KEY,
                    uid TEXT,
                    created_at INTEGER,
                    expires_at INTEGER,
                    client_ip TEXT,
                    user_agent TEXT,
                    FOREIGN KEY(uid) REFERENCES users(uid)
                )
            """)
            cursor.execute("CREATE INDEX idx_sessions_token ON sessions(token)")
            cursor.execute("CREATE INDEX idx_sessions_uid ON sessions(uid)")
            cursor.execute("CREATE INDEX idx_users_username ON users(username)")
            cursor.execute("CREATE INDEX idx_users_email ON users(email)")
            conn.commit()
            conn.close()
            print("[UserAuth] 用户数据库重建成功")
    
    def _create_default_assets(self):
        """创建默认头像和背景"""
        # 创建默认头像
        default_avatar = os.path.join(self.avatar_dir, "default.png")
        if not os.path.exists(default_avatar):
            try:
                # 尝试使用PIL创建头像
                from PIL import Image, ImageDraw
                img = Image.new('RGB', (128, 128), color='#5865f2')
                draw = ImageDraw.Draw(img)
                draw.ellipse([44, 44, 84, 84], fill='white')
                img.save(default_avatar)
                print("[UserAuth] 默认头像已创建 (PIL)")
            except ImportError:
                # 如果没有PIL，创建一个简单的PNG文件
                try:
                    # 创建一个简单的1x1像素PNG
                    import struct
                    with open(default_avatar, 'wb') as f:
                        # PNG文件头
                        f.write(struct.pack('>8B', 137, 80, 78, 71, 13, 10, 26, 10))
                        # IHDR块
                        f.write(struct.pack('>I', 13))
                        f.write(b'IHDR')
                        f.write(struct.pack('>II', 1, 1))
                        f.write(struct.pack('>B', 8))  # 位深
                        f.write(struct.pack('>B', 6))  # 颜色类型 (RGBA)
                        f.write(struct.pack('>B', 0))  # 压缩方法
                        f.write(struct.pack('>B', 0))  # 过滤方法
                        f.write(struct.pack('>B', 0))  # 隔行扫描
                        # CRC
                        f.write(struct.pack('>I', 0))
                        # IDAT块 (简单的1像素透明)
                        f.write(struct.pack('>I', 1))
                        f.write(b'IDAT')
                        f.write(struct.pack('>B', 0))
                        f.write(struct.pack('>I', 0))
                        # IEND块
                        f.write(struct.pack('>I', 0))
                        f.write(b'IEND')
                        f.write(struct.pack('>I', 0))
                    print("[UserAuth] 默认头像已创建 (简单PNG)")
                except:
                    # 实在不行就创建空文件
                    with open(default_avatar, 'wb') as f:
                        f.write(b'')
                    print("[UserAuth] 创建空白头像文件")
        
        # 创建默认背景（可选）
        default_background = os.path.join(self.background_dir, "default.jpg")
        if not os.path.exists(default_background):
            try:
                # 创建一个简单的渐变背景
                from PIL import Image, ImageDraw
                img = Image.new('RGB', (1920, 1080), color='#2f3136')
                draw = ImageDraw.Draw(img)
                for i in range(1080):
                    color = int(47 + (i / 1080) * 20)
                    draw.line([(0, i), (1920, i)], fill=(color, color, color))
                img.save(default_background)
                print("[UserAuth] 默认背景已创建")
            except:
                pass
    
    def on_load(self, api):
        """插件加载时调用"""
        self.api = api
        self._register_routes()
        print("[UserAuth] 插件加载成功")
    
    def _register_routes(self):
        """注册认证相关路由"""
        
        # ===== 用户注册 =====
        @self.api.app.route("/api/register", methods=["POST", "OPTIONS"], endpoint="api_user_register")
        def api_register():
            """全局用户注册"""
            if request.method == "OPTIONS":
                return "", 200
            
            data = request.json
            username = data.get("username", "").strip()
            password = data.get("password", "")
            email = data.get("email", "").strip()
            
            if not username or not password:
                return {"status": "fail", "error": "用户名和密码不能为空"}, 400
            
            if len(username) < 2:
                return {"status": "fail", "error": "用户名至少2个字符"}, 400
            
            if len(password) < 6:
                return {"status": "fail", "error": "密码至少6位"}, 400
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # 检查用户名是否已存在
                cursor.execute("SELECT uid FROM users WHERE username=?", (username,))
                if cursor.fetchone():
                    return {"status": "fail", "error": "用户名已存在"}, 400
                
                # 检查邮箱是否已存在（如果提供了邮箱）
                if email:
                    cursor.execute("SELECT uid FROM users WHERE email=?", (email,))
                    if cursor.fetchone():
                        return {"status": "fail", "error": "邮箱已被使用"}, 400
                
                # 生成UID（8位数字）
                uid = self._generate_uid(cursor)
                
                # 密码加盐哈希
                salt = secrets.token_hex(16)
                password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
                
                timestamp = int(time.time())
                
                cursor.execute("""
                    INSERT INTO users 
                    (uid, username, password_hash, salt, email, created_at, last_login)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (uid, username, password_hash, salt, email or None, timestamp, timestamp))
                
                conn.commit()
                
                # 创建会话令牌
                token = self._create_session(uid, request.remote_addr, request.user_agent.string)
                
                print(f"[UserAuth] 新用户注册: {username} (UID: {uid})")
                
                return {
                    "status": "ok",
                    "uid": uid,
                    "username": username,
                    "token": token
                }
                
            except Exception as e:
                print(f"[UserAuth] 注册失败: {e}")
                return {"status": "fail", "error": str(e)}, 500
            finally:
                conn.close()
        
        # ===== 用户登录 =====
        @self.api.app.route("/api/login", methods=["POST", "OPTIONS"], endpoint="api_user_login")
        def api_login():
            """全局用户登录"""
            if request.method == "OPTIONS":
                return "", 200
            
            data = request.json
            username = data.get("username", "").strip()
            password = data.get("password", "")
            
            if not username or not password:
                return {"status": "fail", "error": "用户名和密码不能为空"}, 400
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    SELECT uid, username, password_hash, salt, status, avatar
                    FROM users WHERE username=?
                """, (username,))
                user = cursor.fetchone()
                
                if not user:
                    return {"status": "fail", "error": "用户名或密码错误"}, 401
                
                uid, db_username, password_hash, salt, status, avatar = user
                
                # 检查账户状态
                if status != 'active':
                    return {"status": "fail", "error": f"账户已{status}"}, 403
                
                # 验证密码
                input_hash = hashlib.sha256((password + salt).encode()).hexdigest()
                if input_hash != password_hash:
                    return {"status": "fail", "error": "用户名或密码错误"}, 401
                
                # 更新最后登录时间
                cursor.execute("UPDATE users SET last_login=? WHERE uid=?", 
                              (int(time.time()), uid))
                conn.commit()
                
                # 创建会话令牌
                token = self._create_session(uid, request.remote_addr, request.user_agent.string)
                
                print(f"[UserAuth] 用户登录: {db_username} (UID: {uid})")
                
                return {
                    "status": "ok",
                    "uid": uid,
                    "username": db_username,
                    "avatar": avatar,
                    "token": token
                }
                
            except Exception as e:
                print(f"[UserAuth] 登录失败: {e}")
                return {"status": "fail", "error": str(e)}, 500
            finally:
                conn.close()
        
        # ===== 修改用户名（优化版：无需密码）=====
        @self.api.app.route("/api/change_username", methods=["POST", "OPTIONS"], endpoint="api_change_username")
        def api_change_username():
            """修改用户名（无需密码，只需会话令牌）"""
            if request.method == "OPTIONS":
                return "", 200
            
            data = request.json
            uid = data.get("uid")
            new_username = data.get("new_username", "").strip()
            session_token = data.get("session_token") or request.cookies.get('session_token')
            
            if not uid or not new_username or not session_token:
                return {"status": "fail", "error": "参数不完整"}, 400
            
            if len(new_username) < 2:
                return {"status": "fail", "error": "用户名至少2个字符"}, 400
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # 验证会话令牌
                cursor.execute("""
                    SELECT uid FROM sessions 
                    WHERE token=? AND uid=? AND expires_at > ?
                """, (session_token, uid, int(time.time())))
                
                if not cursor.fetchone():
                    return {"status": "fail", "error": "会话无效或已过期"}, 401
                
                # 检查新用户名是否已存在
                cursor.execute("SELECT uid FROM users WHERE username=?", (new_username,))
                if cursor.fetchone():
                    return {"status": "fail", "error": "用户名已存在"}, 400
                
                # 更新用户名
                cursor.execute("UPDATE users SET username=? WHERE uid=?", (new_username, uid))
                conn.commit()
                
                print(f"[UserAuth] 用户 {uid} 修改用户名为: {new_username}")
                
                return {"status": "ok", "message": "用户名修改成功"}
                
            except Exception as e:
                print(f"[UserAuth] 修改用户名失败: {e}")
                return {"status": "fail", "error": str(e)}, 500
            finally:
                conn.close()
        
        # ===== 修改邮箱 =====
        @self.api.app.route("/api/change_email", methods=["POST", "OPTIONS"], endpoint="api_change_email")
        def api_change_email():
            """修改邮箱"""
            if request.method == "OPTIONS":
                return "", 200
            
            data = request.json
            uid = data.get("uid")
            new_email = data.get("new_email", "").strip()
            session_token = data.get("session_token") or request.cookies.get('session_token')
            
            if not uid or not session_token:
                return {"status": "fail", "error": "参数不完整"}, 400
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # 验证会话令牌
                cursor.execute("""
                    SELECT uid FROM sessions 
                    WHERE token=? AND uid=? AND expires_at > ?
                """, (session_token, uid, int(time.time())))
                
                if not cursor.fetchone():
                    return {"status": "fail", "error": "会话无效或已过期"}, 401
                
                # 如果提供了新邮箱，检查是否已被使用
                if new_email:
                    cursor.execute("SELECT uid FROM users WHERE email=? AND uid!=?", (new_email, uid))
                    if cursor.fetchone():
                        return {"status": "fail", "error": "邮箱已被其他账号使用"}, 400
                
                # 更新邮箱
                cursor.execute("UPDATE users SET email=? WHERE uid=?", (new_email or None, uid))
                conn.commit()
                
                print(f"[UserAuth] 用户 {uid} 修改邮箱为: {new_email}")
                
                return {"status": "ok", "message": "邮箱修改成功"}
                
            except Exception as e:
                print(f"[UserAuth] 修改邮箱失败: {e}")
                return {"status": "fail", "error": str(e)}, 500
            finally:
                conn.close()
        
        # ===== 修改密码 =====
        @self.api.app.route("/api/change_password", methods=["POST", "OPTIONS"], endpoint="api_change_password")
        def api_change_password():
            """修改密码"""
            if request.method == "OPTIONS":
                return "", 200
            
            data = request.json
            uid = data.get("uid")
            old_password = data.get("old_password")
            new_password = data.get("new_password")
            
            if not uid or not old_password or not new_password:
                return {"status": "fail", "error": "参数不完整"}, 400
            
            if len(new_password) < 6:
                return {"status": "fail", "error": "新密码至少6位"}, 400
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # 获取用户信息
                cursor.execute("SELECT password_hash, salt FROM users WHERE uid=?", (uid,))
                user = cursor.fetchone()
                
                if not user:
                    return {"status": "fail", "error": "用户不存在"}, 404
                
                password_hash, salt = user
                
                # 验证原密码
                input_hash = hashlib.sha256((old_password + salt).encode()).hexdigest()
                if input_hash != password_hash:
                    return {"status": "fail", "error": "原密码错误"}, 401
                
                # 生成新密码哈希
                new_salt = secrets.token_hex(16)
                new_password_hash = hashlib.sha256((new_password + new_salt).encode()).hexdigest()
                
                # 更新密码
                cursor.execute("""
                    UPDATE users SET password_hash=?, salt=? WHERE uid=?
                """, (new_password_hash, new_salt, uid))
                
                conn.commit()
                
                print(f"[UserAuth] 用户 {uid} 密码修改成功")
                return {"status": "ok", "message": "密码修改成功"}
                
            except Exception as e:
                print(f"[UserAuth] 密码修改失败: {e}")
                return {"status": "fail", "error": str(e)}, 500
            finally:
                conn.close()
        
        # ===== 验证会话 =====
        @self.api.app.route("/api/verify_session", methods=["POST", "OPTIONS"], endpoint="api_verify_session")
        def api_verify_session():
            """验证用户会话（供聊天服务器调用）"""
            if request.method == "OPTIONS":
                return "", 200
            
            data = request.json
            session_token = data.get("session_token")
            
            if not session_token:
                return {"valid": False, "error": "缺少会话令牌"}, 400
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    SELECT s.uid, u.username, u.avatar, u.email
                    FROM sessions s
                    JOIN users u ON s.uid = u.uid
                    WHERE s.token=? AND s.expires_at > ?
                """, (session_token, int(time.time())))
                
                session = cursor.fetchone()
                
                if session:
                    uid, username, avatar, email = session
                    print(f"[UserAuth] 会话验证成功: {username} (UID: {uid})")
                    return {
                        "valid": True,
                        "uid": uid,
                        "username": username,
                        "avatar": avatar,
                        "email": email
                    }
                else:
                    print(f"[UserAuth] 会话无效或已过期")
                    return {"valid": False}
                    
            finally:
                conn.close()
        
        # ===== 获取用户信息（支持UID或用户名）=====
        @self.api.app.route("/api/user/<identifier>", methods=["GET"], endpoint="api_user_info")
        def api_user_info(identifier):
            """获取用户公开信息 - 支持通过UID或用户名查询"""
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # 先尝试作为UID查询
                cursor.execute("""
                    SELECT username, avatar, created_at, email, uid
                    FROM users WHERE uid=?
                """, (identifier,))
                user = cursor.fetchone()
                
                if user:
                    print(f"[UserAuth] 通过UID查询用户: {identifier} -> {user[0]}")
                    return {
                        "uid": user[4],
                        "username": user[0],
                        "avatar": user[1],
                        "created_at": user[2],
                        "email": user[3]
                    }
                
                # 如果没找到，尝试作为用户名查询
                cursor.execute("""
                    SELECT uid, username, avatar, created_at, email
                    FROM users WHERE username=?
                """, (identifier,))
                user = cursor.fetchone()
                
                if user:
                    print(f"[UserAuth] 通过用户名查询用户: {identifier} -> {user[0]}")
                    return {
                        "uid": user[0],
                        "username": user[1],
                        "avatar": user[2],
                        "created_at": user[3],
                        "email": user[4]
                    }
                
                print(f"[UserAuth] 用户不存在: {identifier}")
                return {"error": "用户不存在"}, 404
                    
            finally:
                conn.close()
        
        # ===== 获取头像 =====
        @self.api.app.route("/api/avatar/<uid>", endpoint="api_user_avatar")
        def api_avatar(uid):
            """获取用户头像"""
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT avatar FROM users WHERE uid=?", (uid,))
                result = cursor.fetchone()
                
                if result and result[0] and result[0] != "default.png":
                    avatar_path = os.path.join(self.avatar_dir, result[0])
                    if os.path.exists(avatar_path):
                        return send_from_directory(self.avatar_dir, result[0])
                
                # 返回默认头像
                default = os.path.join(self.avatar_dir, "default.png")
                if os.path.exists(default):
                    return send_from_directory(self.avatar_dir, "default.png")
                    
            finally:
                conn.close()
            
            return {"error": "头像不存在"}, 404
        
        # ===== 上传头像 =====
        @self.api.app.route("/api/upload_avatar", methods=["POST", "OPTIONS"], endpoint="api_upload_avatar")
        def api_upload_avatar():
            """上传头像"""
            print(f"[大厅] 收到头像上传请求")
            
            if request.method == "OPTIONS":
                response = make_response()
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')
                response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
                response.headers.add('Access-Control-Allow-Credentials', 'true')
                return response
            
            uid = request.form.get("uid")
            username = request.form.get("username")
            token = request.form.get("session_token") or request.cookies.get('session_token')
            
            print(f"[大厅] 参数: uid={uid}, username={username}, token存在?={token is not None}")
            
            if not uid or not token:
                print("[大厅] 错误: 缺少参数")
                return {"error": "缺少参数"}, 400
            
            # 验证令牌（支持通过UID或用户名）
            if not self._verify_session_token(uid, username, token):
                print(f"[大厅] 错误: 身份验证失败 - uid={uid}, username={username}")
                return {"error": "身份验证失败"}, 401
            
            if "avatar" not in request.files:
                print("[大厅] 错误: 没有文件")
                return {"error": "没有文件"}, 400
            
            file = request.files["avatar"]
            if file.filename == "":
                print("[大厅] 错误: 未选择文件")
                return {"error": "未选择文件"}, 400
            
            # 验证文件类型
            if not file.content_type or not file.content_type.startswith("image/"):
                print(f"[大厅] 错误: 不是图片 - {file.content_type}")
                return {"error": "只能上传图片文件"}, 400
            
            # 验证文件大小（2MB限制）
            file.seek(0, 2)
            size = file.tell()
            file.seek(0)
            if size > 2 * 1024 * 1024:
                print(f"[大厅] 错误: 文件太大 - {size}")
                return {"error": "头像不能超过2MB"}, 400
            
            # 生成文件名
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                print(f"[大厅] 错误: 不支持的文件格式 - {ext}")
                return {"error": "不支持的图片格式"}, 400
            
            filename = f"{uid}_avatar{ext}"
            save_path = os.path.join(self.avatar_dir, filename)
            
            print(f"[大厅] 保存头像到: {save_path}")
            
            # 删除旧头像
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT avatar FROM users WHERE uid=?", (uid,))
            old_avatar = cursor.fetchone()
            if old_avatar and old_avatar[0] and old_avatar[0] != "default.png":
                old_path = os.path.join(self.avatar_dir, old_avatar[0])
                if os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                        print(f"[大厅] 删除旧头像: {old_path}")
                    except:
                        pass
            
            # 保存新头像
            file.save(save_path)
            cursor.execute("UPDATE users SET avatar=? WHERE uid=?", (filename, uid))
            conn.commit()
            conn.close()
            
            print(f"[UserAuth] 用户 {uid} 头像更新: {filename}")
            
            return {"filename": filename, "status": "success"}
        
        # ===== 获取背景图片 =====
        @self.api.app.route("/api/background/<uid>", endpoint="api_user_background")
        def api_user_background(uid):
            """获取用户背景图片"""
            # 查找用户背景文件
            if os.path.exists(self.background_dir):
                for f in os.listdir(self.background_dir):
                    if f.startswith(f"{uid}_background."):
                        return send_from_directory(self.background_dir, f)
            
            # 返回默认背景
            default = os.path.join(self.background_dir, "default.jpg")
            if os.path.exists(default):
                return send_from_directory(self.background_dir, "default.jpg")
            
            return {"error": "背景图片不存在"}, 404
        
        # ===== 上传背景图片 =====
        @self.api.app.route("/api/upload_background", methods=["POST", "OPTIONS"], endpoint="api_upload_background")
        def api_upload_background():
            """上传背景图片"""
            print(f"[大厅] 收到背景上传请求")
            
            if request.method == "OPTIONS":
                response = make_response()
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')
                response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
                response.headers.add('Access-Control-Allow-Credentials', 'true')
                return response
            
            uid = request.form.get("uid")
            username = request.form.get("username")
            token = request.form.get("session_token") or request.cookies.get('session_token')
            
            print(f"[大厅] 背景上传参数: uid={uid}, username={username}, token存在?={token is not None}")
            
            if not uid or not token:
                print("[大厅] 错误: 缺少参数")
                return {"error": "缺少参数"}, 400
            
            # 验证令牌
            if not self._verify_session_token(uid, username, token):
                print(f"[大厅] 错误: 身份验证失败 - uid={uid}")
                return {"error": "身份验证失败"}, 401
            
            if "background" not in request.files:
                print("[大厅] 错误: 没有文件")
                return {"error": "没有文件"}, 400
            
            file = request.files["background"]
            if file.filename == "":
                print("[大厅] 错误: 未选择文件")
                return {"error": "未选择文件"}, 400
            
            # 验证文件类型
            if not file.content_type or not file.content_type.startswith("image/"):
                print(f"[大厅] 错误: 不是图片 - {file.content_type}")
                return {"error": "只能上传图片文件"}, 400
            
            # 验证文件大小（5MB限制）
            file.seek(0, 2)
            size = file.tell()
            file.seek(0)
            if size > 5 * 1024 * 1024:
                print(f"[大厅] 错误: 文件太大 - {size}")
                return {"error": "背景图片不能超过5MB"}, 400
            
            # 生成文件名
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                print(f"[大厅] 错误: 不支持的文件格式 - {ext}")
                return {"error": "不支持的图片格式"}, 400
            
            filename = f"{uid}_background{ext}"
            save_path = os.path.join(self.background_dir, filename)
            
            print(f"[大厅] 保存背景图片到: {save_path}")
            
            # 删除旧背景
            for f in os.listdir(self.background_dir):
                if f.startswith(f"{uid}_background."):
                    old_path = os.path.join(self.background_dir, f)
                    try:
                        os.remove(old_path)
                        print(f"[大厅] 删除旧背景: {old_path}")
                    except:
                        pass
            
            # 保存新背景
            file.save(save_path)
            
            print(f"[UserAuth] 用户 {uid} 背景图片更新: {filename}")
            
            return {"filename": filename, "status": "success"}
    
    def _verify_session_token(self, uid, username, token):
        """验证会话令牌（支持通过UID或用户名）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        current_time = int(time.time())
        
        try:
            # 方法1：通过UID验证
            cursor.execute("""
                SELECT s.uid FROM sessions s
                WHERE s.token=? AND s.uid=? AND s.expires_at > ?
            """, (token, uid, current_time))
            
            if cursor.fetchone():
                print(f"[大厅] 令牌验证成功 (通过UID): {uid}")
                return True
            
            # 方法2：如果提供了用户名，通过用户名查找UID
            if username:
                cursor.execute("""
                    SELECT u.uid FROM users u
                    JOIN sessions s ON u.uid = s.uid
                    WHERE u.username=? AND s.token=? AND s.expires_at > ?
                """, (username, token, current_time))
                
                result = cursor.fetchone()
                if result:
                    print(f"[大厅] 令牌验证成功 (通过用户名): {username} -> {result[0]}")
                    return True
            
            print(f"[大厅] 令牌验证失败: uid={uid}, username={username}")
            return False
        except Exception as e:
            print(f"[大厅] 令牌验证异常: {e}")
            return False
        finally:
            conn.close()
    
    def _generate_uid(self, cursor):
        """生成唯一8位数字UID"""
        import random
        while True:
            uid = str(random.randint(10000000, 99999999))
            cursor.execute("SELECT uid FROM users WHERE uid=?", (uid,))
            if not cursor.fetchone():
                return uid
    
    def _create_session(self, uid, ip, user_agent):
        """创建会话令牌"""
        token = secrets.token_urlsafe(32)
        created = int(time.time())
        expires = created + 30 * 24 * 3600  # 30天有效期
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sessions (token, uid, created_at, expires_at, client_ip, user_agent)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (token, uid, created, expires, ip, (user_agent or '')[:255]))
        conn.commit()
        conn.close()
        
        return token

# 插件实例
plugin = UserAuthPlugin()

# 导出插件接口
on_load = plugin.on_load