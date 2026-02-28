"""
用户背景图片插件 - 存储和管理用户的自定义背景图片
"""

import os
import sqlite3
import time
import hashlib
import base64
from flask import request, jsonify, send_from_directory

class UserBackgroundPlugin:
    def __init__(self):
        self.db_path = "data/user_backgrounds.db"
        self.background_dir = "backgrounds"
        os.makedirs("data", exist_ok=True)
        os.makedirs(self.background_dir, exist_ok=True)
        
        self._init_db()
        print("[UserBackground] 用户背景图片插件已初始化")
    
    def _init_db(self):
        """初始化数据库"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_backgrounds(
                    uid TEXT PRIMARY KEY,
                    background_filename TEXT,
                    updated_at INTEGER,
                    FOREIGN KEY(uid) REFERENCES users(uid)
                )
            """)
            
            conn.commit()
            conn.close()
            print("[UserBackground] 数据库初始化成功")
        except Exception as e:
            print(f"[UserBackground] 数据库初始化失败: {e}")
    
    def on_load(self, api):
        """插件加载时调用"""
        self.api = api
        self._register_routes()
        print("[UserBackground] 插件加载成功")
    
    def _register_routes(self):
        """注册背景图片相关路由"""
        
        @self.api.app.route("/api/background/<uid>", methods=["GET"])
        def get_background(uid):
            """获取用户背景图片"""
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT background_filename FROM user_backgrounds WHERE uid=?", (uid,))
                result = cursor.fetchone()
                
                if result and result[0]:
                    background_path = os.path.join(self.background_dir, result[0])
                    if os.path.exists(background_path):
                        return send_from_directory(self.background_dir, result[0])
                
                # 返回默认背景
                default = os.path.join(self.background_dir, "default.jpg")
                if os.path.exists(default):
                    return send_from_directory(self.background_dir, "default.jpg")
                    
            finally:
                conn.close()
            
            return {"error": "背景图片不存在"}, 404
        
        @self.api.app.route("/api/background/upload", methods=["POST", "OPTIONS"])
        def upload_background():
            """上传背景图片"""
            if request.method == "OPTIONS":
                return "", 200
            
            uid = request.form.get("uid")
            token = request.form.get("token")
            
            if not uid or not token:
                return {"error": "缺少参数"}, 400
            
            # 验证令牌
            if not self._verify_user_token(uid, token):
                return {"error": "身份验证失败"}, 401
            
            if "background" not in request.files:
                return {"error": "没有文件"}, 400
            
            file = request.files["background"]
            if file.filename == "":
                return {"error": "未选择文件"}, 400
            
            # 验证文件类型
            if not file.content_type or not file.content_type.startswith("image/"):
                return {"error": "只能上传图片文件"}, 400
            
            # 验证文件大小（5MB限制）
            file.seek(0, 2)
            size = file.tell()
            file.seek(0)
            if size > 5 * 1024 * 1024:
                return {"error": "背景图片不能超过5MB"}, 400
            
            # 生成文件名
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                return {"error": "不支持的图片格式"}, 400
            
            filename = f"{uid}_background{ext}"
            save_path = os.path.join(self.background_dir, filename)
            
            # 删除旧背景
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT background_filename FROM user_backgrounds WHERE uid=?", (uid,))
            old_background = cursor.fetchone()
            if old_background and old_background[0]:
                old_path = os.path.join(self.background_dir, old_background[0])
                if os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except:
                        pass
            
            # 保存新背景
            file.save(save_path)
            
            # 更新数据库
            cursor.execute("""
                INSERT OR REPLACE INTO user_backgrounds (uid, background_filename, updated_at)
                VALUES (?, ?, ?)
            """, (uid, filename, int(time.time())))
            conn.commit()
            conn.close()
            
            print(f"[UserBackground] 用户 {uid} 背景图片更新: {filename}")
            
            return {"filename": filename, "status": "success"}
    
    def _verify_user_token(self, uid, token):
        """验证用户令牌（需要访问用户数据库）"""
        try:
            # 这里需要访问 users.db 验证令牌
            # 简单实现：从大厅的会话表验证
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
plugin = UserBackgroundPlugin()

# 导出插件接口
on_load = plugin.on_load