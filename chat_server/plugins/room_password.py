"""
房间密码插件
功能：
- 从配置文件读取房间密码
- 用户进入聊天室时需要输入密码
- 密码验证通过后才能加入聊天
- 密码为空时不启用验证
- 使用文件持久化存储验证记录
"""

import os
import json
import time
import threading
from flask import request, jsonify

class RoomPasswordPlugin:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self.password = None
        self.config_path = "config.json"
        self.data_file = "data/room_password.json"
        self.verified_users = {}
        self.session_timeout = 3600
        self.api = None
        
        os.makedirs("data", exist_ok=True)
        self.load_password()
        self.load_verified_users()
        
        print(f"[RoomPassword] 房间密码插件已初始化，当前已验证用户: {list(self.verified_users.keys())}")
    
    def load_password(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self.password = config.get("room_password", "")
                    
                if self.password:
                    print(f"[RoomPassword] 房间密码已启用 (长度: {len(self.password)}位)")
                else:
                    print("[RoomPassword] 房间密码未设置，所有人可进入")
            else:
                print("[RoomPassword] 配置文件不存在，使用默认空密码")
                self.password = ""
        except Exception as e:
            print(f"[RoomPassword] 加载密码失败: {e}")
            self.password = ""
    
    def load_verified_users(self):
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    current_time = time.time()
                    for uid, timestamp in data.items():
                        if current_time - timestamp < self.session_timeout:
                            self.verified_users[uid] = timestamp
                        else:
                            print(f"[RoomPassword] 加载时发现用户 {uid} 验证已过期")
                    print(f"[RoomPassword] 已加载 {len(self.verified_users)} 个已验证用户: {list(self.verified_users.keys())}")
            else:
                print(f"[RoomPassword] 验证记录文件不存在，将创建新文件")
                self.save_verified_users()
        except Exception as e:
            print(f"[RoomPassword] 加载验证记录失败: {e}")
    
    def save_verified_users(self):
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self.verified_users, f, indent=2, ensure_ascii=False)
            print(f"[RoomPassword] 已保存验证记录到文件: {list(self.verified_users.keys())}")
            return True
        except Exception as e:
            print(f"[RoomPassword] 保存验证记录失败: {e}")
            return False
    
    def on_load(self, api):
        self.api = api
        if hasattr(api, 'app') and api.app:
            self._register_routes()
            print(f"[RoomPassword] 插件加载成功，当前已验证用户: {list(self.verified_users.keys())}")
        else:
            print("[RoomPassword] 警告: API 中没有 app 属性，路由注册失败")
    
    def on_server_start(self, api):
        print(f"[RoomPassword] 房间密码状态: {'已启用' if self.password else '未启用'}")
        print(f"[RoomPassword] 启动时已验证用户: {list(self.verified_users.keys())}")
        threading.Thread(target=self._cleanup_loop, daemon=True).start()
        print("[RoomPassword] 清理线程已启动")
    
    def _cleanup_loop(self):
        while True:
            time.sleep(60)
            self._clean_expired()
    
    def _clean_expired(self):
        current_time = time.time()
        changed = False
        
        expired = []
        for uid, timestamp in self.verified_users.items():
            if current_time - timestamp > self.session_timeout:
                expired.append(uid)
        
        for uid in expired:
            del self.verified_users[uid]
            changed = True
            print(f"[RoomPassword] 用户 {uid} 验证已过期")
        
        if changed:
            self.save_verified_users()
    
    def _register_routes(self):
        
        @self.api.app.route("/api/room/password/check", methods=["POST", "OPTIONS"])
        def check_password():
            if request.method == "OPTIONS":
                return "", 200
            
            if not self.password:
                return jsonify({
                    "status": "success",
                    "requires_password": False
                })
            
            data = request.json
            input_password = data.get("password", "")
            uid = data.get("uid")
            
            if not uid:
                return {"error": "缺少用户ID"}, 400
            
            print(f"[RoomPassword] ===== 收到密码验证请求 =====")
            print(f"[RoomPassword] 用户UID: {uid}")
            print(f"[RoomPassword] 验证前 verified_users: {list(self.verified_users.keys())}")
            
            if input_password == self.password:
                # 记录已验证用户
                self.verified_users[uid] = time.time()
                print(f"[RoomPassword] 用户 {uid} 密码验证成功")
                
                # 立即保存到文件
                save_success = self.save_verified_users()
                if save_success:
                    print(f"[RoomPassword] 验证后 verified_users: {list(self.verified_users.keys())}")
                    
                    # 双重确认：从文件重新读取，确保保存成功
                    try:
                        with open(self.data_file, "r", encoding="utf-8") as f:
                            saved_data = json.load(f)
                        print(f"[RoomPassword] 文件中的验证记录: {list(saved_data.keys())}")
                        if uid in saved_data:
                            print(f"[RoomPassword] 用户 {uid} 的验证记录已成功写入文件")
                        else:
                            print(f"[RoomPassword] 用户 {uid} 的验证记录未写入文件！")
                    except Exception as e:
                        print(f"[RoomPassword] 读取文件确认失败: {e}")
                else:
                    print(f"[RoomPassword] 警告：验证记录保存失败！")
                
                return jsonify({
                    "status": "success",
                    "requires_password": True,
                    "verified": True
                })
            else:
                print(f"[RoomPassword] 用户 {uid} 密码错误")
                return jsonify({
                    "status": "fail",
                    "requires_password": True,
                    "verified": False,
                    "error": "密码错误"
                })
        
        @self.api.app.route("/api/room/password/status", methods=["GET", "OPTIONS"])
        def password_status():
            if request.method == "OPTIONS":
                return "", 200
            
            return jsonify({
                "requires_password": bool(self.password)
            })
    
    def is_verified(self, uid):
        """检查用户是否已验证（供WebSocket使用）"""
        if not self.password:
            return True  # 无密码，直接通过
        
        print(f"[RoomPassword] ===== is_verified 被调用 =====")
        print(f"[RoomPassword] 检查用户: uid={uid}")
        print(f"[RoomPassword] 当前 verified_users: {list(self.verified_users.keys())}")
        
        # 检查是否已验证
        if uid in self.verified_users:
            # 检查是否过期
            time_diff = time.time() - self.verified_users[uid]
            if time_diff < self.session_timeout:
                remaining = self.session_timeout - time_diff
                print(f"[RoomPassword] 用户 {uid} 已验证，剩余时间: {remaining:.0f}秒")
                return True
            else:
                # 过期了，删除记录
                print(f"[RoomPassword] 用户 {uid} 验证已过期")
                del self.verified_users[uid]
                self.save_verified_users()
        else:
            print(f"[RoomPassword] 用户 {uid} 不在 verified_users 中")
            
            # 尝试从文件重新加载，防止内存和文件不同步
            try:
                if os.path.exists(self.data_file):
                    with open(self.data_file, "r", encoding="utf-8") as f:
                        saved_data = json.load(f)
                    print(f"[RoomPassword] 文件中的验证记录: {list(saved_data.keys())}")
                    
                    if uid in saved_data:
                        # 如果文件中有但内存中没有，重新加载
                        print(f"[RoomPassword] 发现用户 {uid} 在文件中但不在内存中，重新加载")
                        self.verified_users = saved_data
                        return self.is_verified(uid)  # 递归调用
            except Exception as e:
                print(f"[RoomPassword] 从文件重新加载失败: {e}")
        
        print(f"[RoomPassword] 用户 {uid} 未验证")
        return False
    
    def on_message(self, api, msg):
        """处理消息事件 - 拦截未验证用户的消息"""
        if not self.password:
            return
        
        uid = msg.get("uid")
        if not uid:
            return
        
        # 检查是否已验证
        if not self.is_verified(uid):
            # 未验证，阻止消息
            msg["_blocked"] = True
            print(f"[RoomPassword] 阻止用户 {uid} 的消息")

# 创建全局插件实例
plugin = RoomPasswordPlugin()

# 导出插件接口
def on_load(api):
    return plugin.on_load(api)

def on_server_start(api):
    return plugin.on_server_start(api)

def on_message(api, msg):
    return plugin.on_message(api, msg)

def is_verified(uid):
    return plugin.is_verified(uid)

# 显式导出
__all__ = ['on_load', 'on_server_start', 'on_message', 'is_verified']