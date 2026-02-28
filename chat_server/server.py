#注释大王
import asyncio
import websockets
import sqlite3
import json
import os
import socket
import threading
import requests
import webbrowser
import sys
import time
import atexit
import random
import re
import mimetypes
from flask import Flask, request, jsonify, send_from_directory, redirect, make_response
from datetime import datetime
from plugin_loader import PluginLoader

# 尝试导入CORS
try:
    from flask_cors import CORS
    CORS_AVAILABLE = True
except ImportError:
    CORS_AVAILABLE = False
    print("警告: flask_cors 未安装，建议运行: pip install flask-cors")

# ===== 配置 =====
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB限制（支持视频）
MAX_AVATAR_SIZE = 2 * 1024 * 1024  # 头像2MB限制
UID_LENGTH = 8  # UID长度，例如 12345678

# ===== 优化后的心跳配置 =====
HEARTBEAT_INTERVAL = 5  # 心跳间隔从25秒改为5秒
HEARTBEAT_TIMEOUT = 3   # 心跳超时时间（秒）
MAX_HEARTBEAT_FAILURES = 2  # 连续失败2次就重新注册（之前是3次）
REGISTER_RETRY_INTERVAL = 5  # 注册重试间隔从10秒改为5秒

# ===== 用户名到UID的缓存 =====
username_to_uid_cache = {}  # 缓存用户名到UID的映射
cache_timestamp = {}  # 缓存时间戳
CACHE_TTL = 3600  # 缓存1小时

# 首先读取配置文件
try:
    with open("config.json", "r", encoding="utf-8") as f:
        CONFIG = json.load(f)
except Exception as e:
    print(f"读取配置文件失败: {e}")
    print("请确保 config.json 文件存在且格式正确")
    sys.exit(1)

# 从配置中读取各项设置
SERVER_NAME = CONFIG.get("server_name", "我的聊天室")
SERVER_DESCRIPTION = CONFIG.get("description", "一个热闹的聊天室")
WS_PORT = CONFIG.get("ws_port", 8765)
HTTP_PORT = CONFIG.get("http_port", 5000)
LOBBY_URL = CONFIG.get("lobby_url", "http://localhost:8000/register")
LOBBY_BASE_URL = LOBBY_URL.replace('/register', '')

# 大厅认证相关配置
SERVER_ID = CONFIG.get("server_id", "auto")
SECRET_KEY = CONFIG.get("secret_key", "auto")
AUTH_MODE = CONFIG.get("auth_mode", "lobby")  # 强制使用lobby模式

# ===== 目录 =====
os.makedirs("data", exist_ok=True)
os.makedirs("uploads", exist_ok=True)
os.makedirs("emojis", exist_ok=True)
os.makedirs("avatars", exist_ok=True)  # 作为缓存目录
os.makedirs("logs", exist_ok=True)

# 确保默认头像存在
default_avatar_path = os.path.join("avatars", "default.png")
if not os.path.exists(default_avatar_path):
    try:
        with open(default_avatar_path, 'wb') as f:
            f.write(b'')  # 空文件，实际使用时会被替换
        print("已创建默认头像占位符")
    except Exception as e:
        print(f"创建默认头像失败: {e}")

# ===== 获取IP（智能检测）=====
def get_local_ip():
    """智能获取本机公网IP，优先从配置读取，其次自动检测"""
    if CONFIG.get("public_ip"):
        return CONFIG.get("public_ip")
    
    try:
        ip = requests.get('http://api.ipify.org', timeout=3).text
        return ip
    except:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(3)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"

SERVER_IP = get_local_ip()

# ===== 数据库管理器 =====
class DatabaseManager:
    def __init__(self):
        self.init_users_db()
        self.init_messages_db()
    
    def init_users_db(self):
        conn = sqlite3.connect("data/users.db", check_same_thread=False)
        cursor = conn.cursor()
        
        # 简化用户表，password字段不再需要
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users(
            uid TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            avatar TEXT,
            lobby_uid TEXT,
            email TEXT,
            created_at INTEGER,
            last_login INTEGER
        )
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS username_history(
            uid TEXT,
            old_username TEXT,
            new_username TEXT,
            changed_at INTEGER,
            FOREIGN KEY(uid) REFERENCES users(uid)
        )
        """)
        
        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lobby_uid ON users(lobby_uid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_username ON users(username)")
        
        conn.commit()
        conn.close()
        print("用户数据库初始化成功")
    
    def init_messages_db(self):
        conn = sqlite3.connect("data/messages.db", check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='messages'
        """)
        table_exists = cursor.fetchone()
        
        if not table_exists:
            cursor.execute("""
            CREATE TABLE messages(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT,
                username TEXT,
                data TEXT,
                timestamp INTEGER,
                encrypted INTEGER DEFAULT 0
            )
            """)
            print("消息数据库表创建成功")
        else:
            cursor.execute("PRAGMA table_info(messages)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if "encrypted" not in columns:
                try:
                    cursor.execute("ALTER TABLE messages ADD COLUMN encrypted INTEGER DEFAULT 0")
                    conn.commit()
                    print("已添加 encrypted 列到消息表")
                except Exception as e:
                    print(f"添加 encrypted 列失败: {e}")
        
        conn.commit()
        conn.close()
        print("消息数据库初始化成功")
    
    def get_users_connection(self):
        conn = sqlite3.connect("data/users.db", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_messages_connection(self):
        conn = sqlite3.connect("data/messages.db", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

db_manager = DatabaseManager()

# ===== 缓存清理函数 =====
def cleanup_cache():
    """定期清理过期的用户名缓存"""
    while True:
        time.sleep(300)  # 每5分钟检查一次
        current_time = time.time()
        expired = [username for username, ts in cache_timestamp.items() 
                  if current_time - ts > CACHE_TTL]
        for username in expired:
            if username in username_to_uid_cache:
                del username_to_uid_cache[username]
            if username in cache_timestamp:
                del cache_timestamp[username]
        if expired:
            print(f"[缓存] 已清理 {len(expired)} 个过期用户名映射")

# ===== 用户同步函数 =====
def sync_user_from_lobby(identifier):
    """从大厅同步用户信息到本地数据库"""
    try:
        print(f"[用户同步] 尝试从大厅获取用户: {identifier}")
        
        # 从大厅获取用户信息 - 使用 identifier（可能是UID或用户名）
        response = requests.get(f"{LOBBY_BASE_URL}/api/user/{identifier}", timeout=5)
        
        if response.status_code == 200:
            user_data = response.json()
            print(f"[用户同步] 从大厅获取到用户: {user_data}")
            
            uid = user_data.get('uid')  # 大厅返回的UID
            username = user_data.get('username')
            email = user_data.get('email', '')
            avatar = user_data.get('avatar', 'default.png')
            created_at = user_data.get('created_at', int(time.time()))
            
            if not uid or not username:
                print("[用户同步] 用户数据不完整")
                return None
            
            conn = db_manager.get_users_connection()
            cursor = conn.cursor()
            
            # 检查是否已存在（通过UID或用户名）
            cursor.execute("SELECT uid FROM users WHERE uid=? OR username=?", (uid, username))
            existing = cursor.fetchone()
            
            timestamp = int(time.time())
            
            if existing:
                existing_uid = existing[0]
                print(f"[用户同步] 用户已存在: {existing_uid}，更新信息")
                # 更新用户信息
                cursor.execute("""
                    UPDATE users SET 
                    username=?, email=?, avatar=?, lobby_uid=?, last_login=?
                    WHERE uid=?
                """, (username, email, avatar, uid, timestamp, existing_uid))
                conn.commit()
                final_uid = existing_uid
            else:
                print(f"[用户同步] 创建新用户: {username} (UID: {uid})")
                # 插入新用户
                cursor.execute("""
                    INSERT INTO users 
                    (uid, username, avatar, lobby_uid, email, created_at, last_login)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (uid, username, avatar, uid, email, created_at, timestamp))
                conn.commit()
                final_uid = uid
            
            conn.close()
            
            # 异步同步头像
            threading.Thread(
                target=sync_avatar_from_lobby,
                args=(uid, final_uid, username),
                daemon=True
            ).start()
            
            print(f"[用户同步] 用户 {username} (UID: {final_uid}) 同步成功")
            
            return {
                "uid": final_uid,
                "username": username,
                "avatar": avatar,
                "email": email,
                "lobby_uid": uid
            }
        else:
            print(f"[用户同步] 从大厅获取用户失败: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"[用户同步] 同步用户异常: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_or_create_user(identifier):
    """获取或创建用户，返回用户信息（带缓存）"""
    print(f"[用户检查] 检查用户: {identifier}")
    
    # 检查是否是数字（可能是UID）
    is_uid = identifier.isdigit() and len(identifier) == 8
    
    conn = db_manager.get_users_connection()
    cursor = conn.cursor()
    
    try:
        # 先查询本地数据库（支持通过UID或用户名）
        cursor.execute("SELECT uid, username, avatar, lobby_uid, email FROM users WHERE uid=? OR username=?", 
                      (identifier, identifier))
        user = cursor.fetchone()
        
        if user:
            print(f"[用户检查] 本地找到用户: {user[1]} (UID: {user[0]})")
            # 更新缓存
            username_to_uid_cache[user[1]] = user[0]
            cache_timestamp[user[1]] = time.time()
            return {
                "uid": user[0],
                "username": user[1],
                "avatar": user[2],
                "lobby_uid": user[3] or user[0],
                "email": user[4],
                "source": "local"
            }
        
        # 用户不存在，从大厅同步
        print(f"[用户检查] 本地不存在用户 {identifier}，尝试从大厅同步")
        user_data = sync_user_from_lobby(identifier)
        
        if user_data:
            print(f"[用户检查] 从大厅同步成功: {user_data['username']}")
            # 更新缓存
            username_to_uid_cache[user_data['username']] = user_data['uid']
            cache_timestamp[user_data['username']] = time.time()
            return user_data
        
        print(f"[用户检查] 无法同步用户 {identifier}")
        return None
        
    finally:
        conn.close()

# ===== 大厅注册状态管理 =====
lobby_connected = False
heartbeat_failures = 0
register_lock = threading.Lock()
last_successful_heartbeat = 0  # 记录最后一次成功心跳的时间

def register_lobby():
    """注册到大厅服务器，失败时返回False"""
    global SERVER_ID, SECRET_KEY, lobby_connected, heartbeat_failures
    
    try:
        print(f"正在注册到大厅: {LOBBY_URL}")
        
        # 准备注册数据 - 发送完整信息
        register_data = {
            "name": SERVER_NAME,
            "description": SERVER_DESCRIPTION,
            "ip": SERVER_IP,
            "port": WS_PORT,
            "http_port": HTTP_PORT,
            "server_id": SERVER_ID,
            "secret_key": SECRET_KEY
        }
        
        print(f"发送注册数据: {register_data}")
        response = requests.post(LOBBY_URL, json=register_data, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"注册大厅成功: {data}")
            
            # 重置心跳失败计数和最后一次成功时间
            with register_lock:
                lobby_connected = True
                heartbeat_failures = 0
                global last_successful_heartbeat
                last_successful_heartbeat = time.time()
            
            # 如果大厅返回了server_id和secret_key，保存到配置
            if data.get("server_id") and data.get("secret_key"):
                # 更新内存中的值
                SERVER_ID = data["server_id"]
                SECRET_KEY = data["secret_key"]
                
                # 更新配置文件
                try:
                    with open("config.json", "r", encoding="utf-8") as f:
                        config = json.load(f)
                    config["server_id"] = SERVER_ID
                    config["secret_key"] = SECRET_KEY
                    with open("config.json", "w", encoding="utf-8") as f:
                        json.dump(config, f, indent=4, ensure_ascii=False)
                    print(f"已保存服务器ID: {SERVER_ID}")
                    print(f"已保存密钥: {SECRET_KEY[:10]}...")
                except Exception as e:
                    print(f"保存配置失败: {e}")
                
                return {
                    "success": True,
                    "server_id": SERVER_ID,
                    "secret_key": SECRET_KEY
                }
            elif data.get("message"):
                # 可能只是成功消息
                return {"success": True}
            else:
                print("大厅未返回服务器凭证")
                return {"success": True}
        else:
            print(f"注册大厅失败: {response.status_code} - {response.text}")
            with register_lock:
                lobby_connected = False
            return {"success": False}
    except requests.exceptions.ConnectionError:
        print(f"无法连接到大厅服务器: {LOBBY_URL}")
        with register_lock:
            lobby_connected = False
        return {"success": False}
    except Exception as e:
        print(f"注册大厅异常: {e}")
        import traceback
        traceback.print_exc()
        with register_lock:
            lobby_connected = False
        return {"success": False}

def register_loop():
    """持续尝试注册，直到成功"""
    global SERVER_ID, SECRET_KEY, lobby_connected
    
    while True:
        # 如果已经连接，只进行心跳检测
        with register_lock:
            if lobby_connected:
                time.sleep(HEARTBEAT_INTERVAL)
                continue
        
        # 未连接，尝试注册
        result = register_lobby()
        
        if isinstance(result, dict) and result.get("success"):
            # 注册成功后启动心跳线程（如果未启动）
            with register_lock:
                if not lobby_connected:
                    lobby_connected = True
                    # 心跳线程已经在主程序中启动，这里不需要重复启动
            print("已连接到大厅服务器")
        else:
            print(f"{REGISTER_RETRY_INTERVAL}秒后重试注册...")
            time.sleep(REGISTER_RETRY_INTERVAL)

def heartbeat_loop():
    """定期向大厅发送心跳，失败时累计计数，超过阈值重新注册（优化版）"""
    global heartbeat_failures, lobby_connected, last_successful_heartbeat
    
    # 修改这里：使用正确的 URL
    heartbeat_url = LOBBY_BASE_URL + '/heartbeat'  # 改成 /heartbeat 而不是 /register/heartbeat
    
    while True:
        time.sleep(HEARTBEAT_INTERVAL)
        
        # 如果已经断开连接，跳过心跳（由注册线程处理）
        with register_lock:
            if not lobby_connected:
                continue
        
        start_time = time.time()
        success = False
        error_msg = ""
        
        try:
            response = requests.post(
                heartbeat_url, 
                json={"ip": SERVER_IP, "port": WS_PORT}, 
                timeout=HEARTBEAT_TIMEOUT
            )
            
            if response.status_code == 200:
                success = True
                # 重置失败计数
                with register_lock:
                    heartbeat_failures = 0
                    last_successful_heartbeat = time.time()
                print(f"心跳发送成功 (延迟: {int((time.time() - start_time)*1000)}ms)")
            else:
                error_msg = f"HTTP {response.status_code}"
                with register_lock:
                    heartbeat_failures += 1
                    
        except requests.exceptions.Timeout:
            error_msg = "超时"
            with register_lock:
                heartbeat_failures += 1
        except requests.exceptions.ConnectionError:
            error_msg = "连接失败"
            with register_lock:
                heartbeat_failures += 1
        except Exception as e:
            error_msg = str(e)[:30]
            with register_lock:
                heartbeat_failures += 1
        
        # 检查心跳状态
        with register_lock:
            current_failures = heartbeat_failures
            
            if current_failures > 0:
                print(f"心跳{error_msg} ({current_failures}/{MAX_HEARTBEAT_FAILURES})")
            
            # 检查是否需要重新注册
            if current_failures >= MAX_HEARTBEAT_FAILURES:
                # 额外检查：如果连续失败，立即尝试重新注册，不等下一次循环
                print(f"心跳连续失败，立即重新注册...")
                lobby_connected = False
                heartbeat_failures = 0
                
                # 立即尝试重新注册（不等待下次循环）
                threading.Thread(target=force_reconnect, daemon=True).start()

def force_reconnect():
    """强制立即重新连接"""
    time.sleep(1)  # 稍微等待一下
    result = register_lobby()
    if result and result.get("success"):
        print("快速重连成功")
    else:
        print("快速重连失败，等待下次尝试")

def unregister_from_lobby():
    """从大厅注销"""
    try:
        unregister_url = LOBBY_BASE_URL + '/unregister'  # 使用正确的 URL
        response = requests.post(unregister_url, 
                                json={"ip": SERVER_IP, "port": WS_PORT}, 
                                timeout=3)
        if response.status_code == 200:
            print("已从大厅注销")
    except Exception as e:
        print(f"注销失败: {e}")

# 注册退出时的注销函数
atexit.register(unregister_from_lobby)

# ===== 头像同步函数 =====
def sync_avatar_from_lobby(identifier, local_uid, username):
    """从大厅同步用户头像到本地缓存"""
    try:
        lobby_base_url = LOBBY_URL.replace('/register', '')
        avatar_url = f"{lobby_base_url}/api/avatar/{identifier}"
        
        response = requests.get(avatar_url, timeout=5)
        if response.status_code == 200:
            # 获取文件扩展名
            content_type = response.headers.get('content-type', '')
            ext = '.png'
            if 'jpeg' in content_type or 'jpg' in content_type:
                ext = '.jpg'
            elif 'png' in content_type:
                ext = '.png'
            elif 'gif' in content_type:
                ext = '.gif'
            elif 'webp' in content_type:
                ext = '.webp'
            
            # 保存头像到本地缓存
            filename = f"{local_uid}_avatar{ext}"
            save_path = os.path.join("avatars", filename)
            
            with open(save_path, 'wb') as f:
                f.write(response.content)
            
            # 更新数据库中的头像记录
            conn = db_manager.get_users_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET avatar=? WHERE uid=?", (filename, local_uid))
            conn.commit()
            conn.close()
            
            print(f"已从大厅同步头像: {username} -> {filename}")
            return True
    except Exception as e:
        print(f"同步头像失败: {e}")
    return False

# ===== Flask =====
app = Flask(__name__)

# 配置CORS
if CORS_AVAILABLE:
    CORS(app, supports_credentials=True, origins="*")
else:
    @app.after_request
    def after_request(response):
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')
        response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response

# 打印所有注册的路由（调试用）
print("=" * 50)
print("已注册的路由:")
for rule in app.url_map.iter_rules():
    print(f"  {rule.endpoint}: {rule}")
print("=" * 50)

# 创建默认头像
def create_default_avatar():
    default_avatar_path = os.path.join("avatars", "default.png")
    if not os.path.exists(default_avatar_path):
        try:
            from PIL import Image, ImageDraw
            img = Image.new('RGB', (128, 128), color='#5865f2')
            draw = ImageDraw.Draw(img)
            draw.ellipse([44, 44, 84, 84], fill='white')
            img.save(default_avatar_path)
            print("默认头像已创建")
        except ImportError:
            print("PIL未安装，创建空白头像")
            with open(default_avatar_path, 'wb') as f:
                f.write(b'')
        except Exception as e:
            print(f"创建默认头像失败: {e}")

create_default_avatar()

# ===== Flask 路由 =====
@app.route("/chat")
def chat_redirect():
    user_agent = request.headers.get('User-Agent', '').lower()
    mobile_keywords = ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'phone', 'tablet']
    is_mobile = any(keyword in user_agent for keyword in mobile_keywords)
    
    if is_mobile:
        return redirect("/mobile.html")
    else:
        return redirect("/chat.html")

@app.route("/info")
def server_info():
    return jsonify({
        "name": SERVER_NAME,
        "description": SERVER_DESCRIPTION,
        "ip": SERVER_IP,
        "ws_port": WS_PORT,
        "http_port": HTTP_PORT,
        "server_id": SERVER_ID,
        "auth_mode": "lobby",
        "lobby_connected": lobby_connected
    })

# ===== 大厅认证路由 =====
@app.route("/auth/lobby", methods=["POST", "OPTIONS"])
def auth_lobby():
    """大厅认证登录 - 验证用户会话"""
    if request.method == "OPTIONS":
        return "", 200
    
    print("[Server] 收到大厅登录请求")
    
    # 交给插件处理
    for plugin in plugin_loader.plugins:
        if hasattr(plugin, 'verify_session'):
            result = plugin.verify_session(request.json)
            
            if isinstance(result, tuple):
                response_data, status_code = result
                return (response_data, status_code)
            else:
                if isinstance(result, dict) and result.get('status') == 'ok':
                    uid = result.get('uid')
                    username = result.get('username')
                    lobby_uid = result.get('lobby_uid')
                    
                    print(f"[Server] 用户登录成功: {username} (本地UID: {uid}, 大厅UID: {lobby_uid})")
                    
                    if uid and username and lobby_uid:
                        threading.Thread(
                            target=sync_avatar_from_lobby,
                            args=(lobby_uid, uid, username),
                            daemon=True
                        ).start()
                
                return jsonify(result)
    
    return {"status": "fail", "error": "认证插件未加载"}, 404

@app.route("/auth/refresh", methods=["POST"])
def auth_refresh():
    """刷新用户信息"""
    for plugin in plugin_loader.plugins:
        if hasattr(plugin, 'refresh_user_info'):
            return plugin.refresh_user_info(request.json)
    
    return {"error": "认证插件未加载"}, 404

@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    """退出登录"""
    for plugin in plugin_loader.plugins:
        if hasattr(plugin, 'logout'):
            return plugin.logout(request.json)
    
    return {"status": "ok"}

# ===== 原有用户认证路由（全部移除，只保留提示）=====
@app.route("/register", methods=["POST", "OPTIONS"])
def register():
    """本地注册 - 已禁用，请使用大厅注册"""
    return {"status": "fail", "error": "请通过大厅服务器注册 (http://localhost:8000/register.html)"}, 403

@app.route("/login", methods=["POST", "OPTIONS"])
def login():
    """本地登录 - 已禁用，请使用大厅认证"""
    return {"status": "fail", "error": "请通过大厅服务器登录"}, 403

@app.route("/change_username", methods=["POST", "OPTIONS"])
def change_username():
    """修改用户名 - 暂不支持"""
    return {"status": "fail", "error": "用户名修改功能暂不支持"}, 403

@app.route("/change_password", methods=["POST", "OPTIONS"])
def change_password():
    """修改密码 - 请在大厅服务器操作"""
    return {"status": "fail", "error": "请在大厅服务器修改密码"}, 403

# ===== 头像相关路由 =====
@app.route("/avatar/<identifier>")
def get_avatar(identifier):
    """获取用户头像 - 优先从本地缓存，否则从大厅获取"""
    print(f"[头像获取] 请求头像: {identifier}")
    
    user_info = get_or_create_user(identifier)
    
    if not user_info:
        print(f"[头像获取] 无法获取用户信息: {identifier}")
        default_path = os.path.join("avatars", "default.png")
        if os.path.exists(default_path):
            return send_from_directory("avatars", "default.png")
        return {"error": "用户不存在"}, 404
    
    uid = user_info["uid"]
    
    conn = db_manager.get_users_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT avatar FROM users WHERE uid=?", (uid,))
        result = cursor.fetchone()
        
        if result and result[0]:
            avatar_path = os.path.join("avatars", result[0])
            if os.path.exists(avatar_path):
                print(f"[头像获取] 从本地缓存返回: {result[0]}")
                return send_from_directory("avatars", result[0])
        
        # 本地没有，从大厅获取
        lobby_base_url = LOBBY_URL.replace('/register', '')
        target_id = user_info.get("lobby_uid") or uid
        avatar_url = f"{lobby_base_url}/api/avatar/{target_id}"
        
        print(f"[头像获取] 从大厅获取: {avatar_url}")
        
        try:
            response = requests.get(avatar_url, timeout=5)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                ext = '.png'
                if 'jpeg' in content_type or 'jpg' in content_type:
                    ext = '.jpg'
                elif 'png' in content_type:
                    ext = '.png'
                elif 'gif' in content_type:
                    ext = '.gif'
                elif 'webp' in content_type:
                    ext = '.webp'
                
                filename = f"{uid}_avatar{ext}"
                save_path = os.path.join("avatars", filename)
                
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                
                cursor.execute("UPDATE users SET avatar=? WHERE uid=?", (filename, uid))
                conn.commit()
                
                print(f"[头像获取] 已缓存并返回: {filename}")
                return send_from_directory("avatars", filename)
        except Exception as e:
            print(f"[头像获取] 从大厅获取失败: {e}")
        
        default_path = os.path.join("avatars", "default.png")
        if os.path.exists(default_path):
            return send_from_directory("avatars", "default.png")
        
    except Exception as e:
        print(f"[头像获取] 异常: {e}")
    finally:
        conn.close()
    
    return {"error": "头像不存在"}, 404

@app.route("/upload_avatar", methods=["POST", "OPTIONS"])
def upload_avatar():
    """上传头像 - 转发到大厅服务器（修复版本）"""
    print(f"[头像上传] 收到请求, method={request.method}")
    
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response
    
    identifier = request.form.get("username")
    if not identifier:
        print("[头像上传] 错误: 未指定用户")
        return {"error": "未指定用户"}, 400
    
    print(f"[头像上传] 接收到的用户名: {identifier}")
    
    # 获取用户信息（优先使用缓存）
    user_info = get_or_create_user(identifier)
    
    if not user_info:
        print(f"[头像上传] 无法获取用户信息: {identifier}")
        return {"error": "用户不存在"}, 404
    
    uid = user_info["uid"]  # 本地UID
    username = user_info["username"]
    lobby_uid = user_info.get("lobby_uid") or uid  # 大厅UID
    
    print(f"[头像上传] 找到用户: uid={uid}, username={username}, lobby_uid={lobby_uid}")
    
    # 获取会话令牌（从cookie或表单）
    session_token = request.cookies.get('session_token')
    if not session_token:
        session_token = request.form.get('session_token')
        if not session_token:
            print("[头像上传] 错误: 未登录")
            return {"error": "未登录"}, 401
    
    if "avatar" not in request.files:
        print("[头像上传] 错误: 没有文件")
        return {"error": "没有文件"}, 400
    
    file = request.files["avatar"]
    if file.filename == "":
        print("[头像上传] 错误: 未选择文件")
        return {"error": "未选择文件"}, 400
    
    # 验证文件类型
    if not file.content_type or not file.content_type.startswith("image/"):
        return {"error": "只能上传图片文件"}, 400
    
    # 验证文件大小
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_AVATAR_SIZE:
        return {"error": f"头像不能超过{MAX_AVATAR_SIZE//1024//1024}MB"}, 400
    
    # 验证文件扩展名
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        return {"error": "不支持的图片格式"}, 400
    
    # 先保存到本地作为备份
    local_filename = f"{uid}_local_{int(time.time())}{ext}"
    local_path = os.path.join("avatars", local_filename)
    file.save(local_path)
    print(f"[头像上传] 已保存本地备份: {local_path}")
    
    # 重新打开文件流用于转发
    file.stream.seek(0)
    
    # 转发到大厅 - 发送完整参数
    form_data = {
        'uid': lobby_uid,  # 大厅UID
        'username': username,  # 用户名，用于验证
        'session_token': session_token  # 会话令牌
    }
    
    files = {
        'avatar': (file.filename, file.stream, file.content_type)
    }
    
    target_url = f"{LOBBY_BASE_URL}/api/upload_avatar"
    
    # 准备cookies
    cookies = {'session_token': session_token}
    
    try:
        print(f"[头像上传] 转发到大厅: {target_url}")
        print(f"[头像上传] 表单数据: uid={lobby_uid}, username={username}")
        
        response = requests.post(
            target_url,
            data=form_data,
            files=files,
            cookies=cookies,
            timeout=10
        )
        
        print(f"[头像上传] 大厅响应状态: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"[头像上传] 大厅响应成功: {result}")
            
            # 异步同步头像
            threading.Thread(
                target=sync_avatar_from_lobby,
                args=(lobby_uid, uid, username),
                daemon=True
            ).start()
            
            return jsonify({"status": "success", "message": "头像上传成功"})
        else:
            try:
                error_data = response.json()
                error_msg = error_data.get('error', '上传失败')
                print(f"[头像上传] 大厅返回错误: {error_msg}")
                return {"error": error_msg}, response.status_code
            except:
                print(f"[头像上传] 大厅返回错误状态: {response.status_code}")
                return {"error": "上传失败"}, response.status_code
                
    except requests.exceptions.ConnectionError as e:
        print(f"[头像上传] 无法连接到大厅服务器，使用本地备份")
        conn = db_manager.get_users_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET avatar=? WHERE uid=?", (local_filename, uid))
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success", "message": "头像已保存到本地（大厅离线）"})
    except Exception as e:
        print(f"[头像上传] 转发请求异常: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}, 500

# ===== 其他路由保持不变 =====
@app.route("/history")
def history():
    conn = db_manager.get_messages_connection()
    cursor = conn.cursor()
    try:
        before = request.args.get("before", type=int)
        
        if before:
            cursor.execute("""
                SELECT * FROM messages WHERE id < ? 
                ORDER BY id DESC LIMIT 50
            """, (before,))
        else:
            cursor.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 50")
        
        rows = cursor.fetchall()
        
        result = []
        for r in reversed(rows):
            try:
                data = r[3]
                encrypted = r[5] if len(r) > 5 else 0
                
                if encrypted == 1:
                    for plugin in plugin_loader.plugins:
                        if hasattr(plugin, 'decrypt_message'):
                            try:
                                data = plugin.decrypt_message(data)
                                break
                            except:
                                pass
                
                msg = json.loads(data)
                msg["id"] = r[0]
                msg["uid"] = r[1]
                msg["username"] = r[2]
                result.append(msg)
            except Exception as e:
                print(f"解析消息 {r[0]} 失败: {e}")
                continue
        
        return jsonify(result)
    except Exception as e:
        print(f"获取历史消息失败: {e}")
        return jsonify([])
    finally:
        conn.close()

@app.route("/emojis")
def emoji_list():
    try:
        emojis = os.listdir("emojis")
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
        emojis = [f for f in emojis if os.path.splitext(f)[1].lower() in image_extensions]
        return jsonify(emojis)
    except Exception as e:
        print(f"加载表情失败: {e}")
        return jsonify([])

@app.route("/emoji/<name>")
def emoji_file(name):
    return send_from_directory("emojis", name)

@app.route("/upload", methods=["POST", "OPTIONS"])
def upload():
    if request.method == "OPTIONS":
        return "", 200
        
    try:
        if "file" not in request.files:
            return {"error": "没有文件"}, 400
            
        file = request.files["file"]
        
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
        
        if size > MAX_FILE_SIZE:
            return {"error": f"文件不能超过{MAX_FILE_SIZE//1024//1024}MB"}, 400
        
        filename = file.filename
        name, ext = os.path.splitext(filename)
        ext = ext.lower()
        
        content_type = file.content_type or ''
        file_type = 'file'
        
        video_exts = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v']
        audio_exts = ['.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac', '.wma']
        image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg']
        
        if ext in video_exts:
            file_type = 'video'
        elif ext in audio_exts:
            file_type = 'audio'
        elif ext in image_exts:
            file_type = 'image'
        elif content_type.startswith('video/'):
            file_type = 'video'
        elif content_type.startswith('audio/'):
            file_type = 'audio'
        elif content_type.startswith('image/'):
            file_type = 'image'
        
        counter = 1
        base_filename = filename
        while os.path.exists(os.path.join("uploads", base_filename)):
            base_filename = f"{name}_{counter}{ext}"
            counter += 1
        
        save_path = os.path.join("uploads", base_filename)
        file.save(save_path)
        print(f"文件上传成功: {base_filename} ({size} bytes)")
        
        return jsonify({
            "filename": base_filename,
            "type": file_type,
            "size": size,
            "ext": ext
        })
        
    except Exception as e:
        print(f"上传文件失败: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/file/<path:filename>")
def serve_file(filename):
    path = os.path.join("uploads", filename)
    if not os.path.exists(path):
        return {"error": "文件不存在"}, 404
    
    range_header = request.headers.get('Range', None)
    if not range_header:
        response = send_from_directory("uploads", filename)
        response.headers.add('Accept-Ranges', 'bytes')
        return response
    
    size = os.path.getsize(path)
    byte1, byte2 = 0, None
    
    m = re.search(r'(\d+)-(\d*)', range_header)
    if m:
        byte1 = int(m.group(1))
        if m.group(2):
            byte2 = int(m.group(2))
    
    if byte2 is None or byte2 >= size:
        byte2 = size - 1
    
    length = byte2 - byte1 + 1
    
    with open(path, 'rb') as f:
        f.seek(byte1)
        data = f.read(length)
    
    response = app.response_class(
        data,
        206,
        mimetype=mimetypes.guess_type(filename)[0] or 'application/octet-stream',
        direct_passthrough=True,
    )
    response.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{size}')
    response.headers.add('Accept-Ranges', 'bytes')
    response.headers.add('Content-Length', str(length))
    response.headers.add('Cache-Control', 'no-cache')
    
    return response

@app.route("/thumbnail/<path:filename>")
def generate_thumbnail(filename):
    default_thumb = os.path.join("avatars", "default.png")
    if os.path.exists(default_thumb):
        return send_from_directory("avatars", "default.png")
    return {"error": "缩略图不存在"}, 404

# ===== 获取在线用户API路由 =====
@app.route("/api/online-users", methods=["GET", "OPTIONS"])
def get_online_users():
    if request.method == "OPTIONS":
        return "", 200
    
    mention_plugin = None
    for plugin in plugin_loader.plugins:
        if hasattr(plugin, 'get_online_users'):
            mention_plugin = plugin
            break
    
    if not mention_plugin:
        return {"error": "@插件未加载"}, 404
    
    online_users = mention_plugin.get_online_users()
    return jsonify({"users": online_users})

# ===== WebSocket =====
clients = set()

def current_time():
    return time.time() * 1000

# ===== 修改这里：在 server_context 中添加 flask_app =====
server_context = {
    "clients": clients,
    "broadcast": None,
    "config": CONFIG,
    "time_func": current_time,
    "flask_app": app,  # 添加 Flask 应用实例
    "plugin_loader": None  # 将在后面设置
}

plugin_loader = PluginLoader(server_context)
server_context["plugin_loader"] = plugin_loader  # 设置 plugin_loader 引用

async def broadcast(msg):
    dead = set()
    for c in clients:
        try:
            await c.send(json.dumps(msg))
        except:
            dead.add(c)
    for d in dead:
        clients.remove(d)

server_context["broadcast"] = broadcast

async def chat(websocket):
    websocket.username = None
    websocket.uid = None
    websocket.authenticated = False
    websocket.password_verified = False  # 标记是否已通过密码验证
    
    # 等待第一条消息（包含用户信息）
    try:
        first_message = await asyncio.wait_for(websocket.recv(), timeout=5)
        msg = json.loads(first_message)
        
        uid = msg.get("uid")
        username = msg.get("user")
        
        if not uid or not username:
            await websocket.close(1008, "缺少用户信息")
            return
        
        websocket.uid = uid
        websocket.username = username
        websocket.authenticated = True
        
        # ===== 黑名单检查 =====
        blacklist_plugin = None
        for plugin in plugin_loader.plugins:
            if hasattr(plugin, 'is_banned'):
                blacklist_plugin = plugin
                break
        
        if blacklist_plugin and blacklist_plugin.is_banned(uid):
            await websocket.send(json.dumps({
                "type": "system",
                "content": "你已被封禁，无法进入聊天室",
                "time": datetime.now().timestamp() * 1000
            }))
            await asyncio.sleep(1)
            await websocket.close(1008, "已被封禁")
            return
        
        # ===== 房间密码检查 =====
        password_plugin = None
        for plugin in plugin_loader.plugins:
            if hasattr(plugin, 'is_verified'):
                password_plugin = plugin
                break

        # 如果密码插件存在，检查用户是否已验证
        if password_plugin:
            if password_plugin.is_verified(uid):
                websocket.password_verified = True
                print(f"[Server] 用户 {username}({uid}) 已通过密码验证")
            else:
                # 未验证，发送提示但不立即关闭
                await websocket.send(json.dumps({
                    "type": "system",
                    "content": "请先输入房间密码",
                    "time": datetime.now().timestamp() * 1000
                }))
                print(f"[Server] 用户 {username}({uid}) 未通过密码验证，等待验证")
        
    except asyncio.TimeoutError:
        await websocket.close(1008, "连接超时")
        return
    except Exception as e:
        print(f"连接验证失败: {e}")
        await websocket.close(1008, "验证失败")
        return
    
    clients.add(websocket)
    await plugin_loader.emit_user_join(username)
    print(f"新客户端连接，当前在线: {len(clients)}")
    
    users_conn = db_manager.get_users_connection()
    msgs_conn = db_manager.get_messages_connection()
    msgs_cursor = msgs_conn.cursor()
    
    try:
        # 如果已经验证，发送欢迎消息
        if websocket.password_verified:
            welcome_msg = {
                "type": "system",
                "content": "欢迎加入聊天室",
                "time": datetime.now().timestamp() * 1000
            }
            await websocket.send(json.dumps(welcome_msg))
        
        async for message in websocket:
            try:
                if not message or message.strip() == "":
                    continue
                
                msg = json.loads(message)
                
                if not isinstance(msg, dict):
                    continue
                
                uid = msg.get("uid")
                username = msg.get("user")
                msg_type = msg.get("type")
                
                if not username:
                    continue
                
                websocket.username = username
                
                if not uid:
                    user_info = get_or_create_user(username)
                    if user_info:
                        uid = user_info["uid"]
                    else:
                        uid = "unknown"
                
                # ===== 密码验证处理 =====
                password_plugin = None
                for plugin in plugin_loader.plugins:
                    if hasattr(plugin, 'is_verified'):
                        password_plugin = plugin
                        break
                
                if password_plugin:
                    # 每次收到消息都重新检查验证状态，以防用户在连接后验证
                    if not websocket.password_verified:
                        if password_plugin.is_verified(uid):
                            websocket.password_verified = True
                            await websocket.send(json.dumps({
                                "type": "system",
                                "content": "密码验证通过，欢迎加入聊天室",
                                "time": datetime.now().timestamp() * 1000
                            }))
                            print(f"[Server] 用户 {username}({uid}) 密码验证通过")
                        else:
                            # 未验证用户不能发送消息
                            await websocket.send(json.dumps({
                                "type": "system",
                                "content": "请先输入房间密码",
                                "time": datetime.now().timestamp() * 1000
                            }))
                            continue
                
                print(f"收到消息: 来自={username}, 内容={msg.get('content')}")
                
                await plugin_loader.emit_message(msg)
                
                if msg.get("_rate_limited"):
                    continue
                
                if msg.get("_is_command"):
                    msg["id"] = -1
                    msg["uid"] = uid
                    await broadcast(msg)
                else:
                    data_to_store = json.dumps(msg)
                    encrypted = 0
                    
                    for plugin in plugin_loader.plugins:
                        if hasattr(plugin, 'encrypt_message'):
                            try:
                                data_to_store = plugin.encrypt_message(msg)
                                encrypted = 1
                            except:
                                pass
                    
                    # 确保数据库连接正常
                    try:
                        msgs_cursor.execute("""
                            INSERT INTO messages (uid, username, data, timestamp, encrypted) 
                            VALUES (?, ?, ?, ?, ?)
                        """, (uid, username, data_to_store, int(time.time()), encrypted))
                        msgs_conn.commit()
                        
                        msg["id"] = msgs_cursor.lastrowid
                        msg["uid"] = uid
                        
                        await broadcast(msg)
                    except Exception as e:
                        print(f"存储消息失败: {e}")
                        # 即使存储失败，仍然广播消息
                        msg["id"] = -1
                        msg["uid"] = uid
                        await broadcast(msg)
                    
            except json.JSONDecodeError as e:
                error_msg = {
                    "type": "system",
                    "content": "消息格式错误",
                    "time": datetime.now().timestamp() * 1000
                }
                await websocket.send(json.dumps(error_msg))
            except Exception as e:
                print(f"处理消息失败: {e}")
                    
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        users_conn.close()
        msgs_conn.close()
        if websocket in clients:
            clients.remove(websocket)
        await plugin_loader.emit_user_leave(websocket.username or "unknown")
        print(f"客户端断开，当前在线: {len(clients)}")

# ===== 启动HTTP服务器 =====
def run_http():
    try:
        print(f"HTTP服务器启动在 http://{SERVER_IP}:{HTTP_PORT}")
        app.run(host="0.0.0.0", port=HTTP_PORT, debug=False, use_reloader=False)
    except Exception as e:
        print(f"HTTP服务器启动失败: {e}")

# ===== 启动WebSocket服务器 =====
async def run_ws():
    try:
        print(f"WebSocket服务器启动在 ws://{SERVER_IP}:{WS_PORT}")
        async with websockets.serve(chat, "0.0.0.0", WS_PORT):
            await asyncio.Future()
    except Exception as e:
        print(f"WebSocket服务器启动失败: {e}")

# ===== 主程序入口 =====
if __name__ == "__main__":
    plugin_loader.load_plugins()
    plugin_loader.emit_server_start()
    
    # 启动缓存清理线程
    cache_cleanup_thread = threading.Thread(target=cleanup_cache, daemon=True)
    cache_cleanup_thread.start()
    
    print("=" * 50)
    print(f"  聊天服务器 {SERVER_NAME} 启动")
    print("=" * 50)
    print(f"HTTP端口: {HTTP_PORT}")
    print(f"WebSocket端口: {WS_PORT}")
    print(f"本机IP: {SERVER_IP}")
    print(f"大厅地址: {LOBBY_URL}")
    print(f"服务器ID: {SERVER_ID}")
    print(f"认证模式: 仅大厅认证")
    print(f"心跳间隔: {HEARTBEAT_INTERVAL}秒 (优化版)")
    print(f"最大失败次数: {MAX_HEARTBEAT_FAILURES}")
    print("=" * 50)
    
    register_thread = threading.Thread(target=register_loop, daemon=True)
    register_thread.start()
    
    heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    heartbeat_thread.start()
    
    from multiprocessing import Process
    
    def run_http_wrapper():
        run_http()
    
    http_process = Process(target=run_http_wrapper, daemon=True)
    http_process.start()
    print(f"HTTP服务进程已启动，PID: {http_process.pid}")
    time.sleep(1)
    
    try:
        asyncio.run(run_ws())
    except KeyboardInterrupt:
        print("\n服务器关闭")
        unregister_from_lobby()
        if 'http_process' in locals():
            http_process.terminate()
            http_process.join()