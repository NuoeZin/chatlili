"""
用户@功能插件
功能：当用户被@时，向在线用户发送通知
"""

import os
import re
import time
import base64
import json

class UserMentionPlugin:
    """用户@功能插件"""
    
    def __init__(self):
        self.mentioned_users = {}
        self.mention_cooldown = 5
        self.sounds_dir = "sounds"
        self.notification_sound = None
        self.sound_name = "默认提示音"
        self._load_notification_sound()
        print("[UserMention] 用户@功能插件已初始化")
    
    def _load_notification_sound(self):
        """加载提示音"""
        if not os.path.exists(self.sounds_dir):
            os.makedirs(self.sounds_dir)
            print(f"[UserMention] 创建音频目录: {self.sounds_dir}")
            self._create_readme()
            self._use_default_sound()
            return
        
        sound_files = []
        for file in os.listdir(self.sounds_dir):
            if file.endswith(('.mp3', '.wav', '.ogg', '.m4a')):
                sound_files.append(file)
        
        if sound_files:
            sound_files.sort()
            selected_file = sound_files[0]
            file_path = os.path.join(self.sounds_dir, selected_file)
            
            try:
                with open(file_path, 'rb') as f:
                    audio_data = f.read()
                    ext = os.path.splitext(selected_file)[1].lower()
                    mime_type = {
                        '.mp3': 'audio/mpeg',
                        '.wav': 'audio/wav',
                        '.ogg': 'audio/ogg',
                        '.m4a': 'audio/mp4'
                    }.get(ext, 'audio/mpeg')
                    
                    self.notification_sound = {
                        'data': base64.b64encode(audio_data).decode(),
                        'mime': mime_type,
                        'name': selected_file
                    }
                    self.sound_name = selected_file
                    print(f"[UserMention] 使用提示音: {selected_file}")
            except Exception as e:
                print(f"[UserMention] 加载音频失败: {e}")
                self._use_default_sound()
        else:
            print(f"[UserMention] 未找到音频文件，使用默认提示音")
            self._use_default_sound()
    
    def _create_readme(self):
        """创建说明文件"""
        readme_path = os.path.join(self.sounds_dir, "README.txt")
        if not os.path.exists(readme_path):
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write("""@提示音设置说明
====================

将你的提示音文件放入此目录，支持以下格式：
- MP3 (.mp3)
- WAV (.wav)
- OGG (.ogg)
- M4A (.m4a)

插件会自动使用目录中的第一个音频文件作为提示音。
""")
    
    def _use_default_sound(self):
        """使用默认提示音"""
        self.notification_sound = {
            'data': self._get_default_sound(),
            'mime': 'audio/wav',
            'name': '默认提示音'
        }
        self.sound_name = "默认提示音"
        print("[UserMention] 使用内置默认提示音")
    
    def _get_default_sound(self):
        """生成默认提示音"""
        return base64.b64encode(bytes([
            0x52, 0x49, 0x46, 0x46, 0x2c, 0x00, 0x00, 0x00, 0x57, 0x41, 0x56, 0x45,
            0x66, 0x6d, 0x74, 0x20, 0x10, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
            0x44, 0xac, 0x00, 0x00, 0x44, 0xac, 0x00, 0x00, 0x01, 0x00, 0x08, 0x00,
            0x64, 0x61, 0x74, 0x61, 0x08, 0x00, 0x00, 0x00, 0x80, 0x86, 0x8c, 0x92,
            0x8c, 0x86, 0x80, 0x00
        ])).decode()
    
    def on_load(self, api):
        """插件加载时调用"""
        self.api = api
        self.online_users = api.ctx.get('clients', set())
        print(f"[UserMention] 插件加载成功 - 当前提示音: {self.sound_name}")
    
    def on_server_start(self, api):
        """服务器启动时调用"""
        print("[UserMention] @功能服务已启动")
    
    def _extract_mentions(self, text):
        """从文本中提取所有@的用户名"""
        if not text or not isinstance(text, str):
            return []
        pattern = r'@([\u4e00-\u9fa5a-zA-Z0-9_]+)'
        mentions = re.findall(pattern, text)
        return list(set(mentions))
    
    def _is_user_online(self, username):
        """检查用户是否在线"""
        for client in self.online_users:
            if hasattr(client, 'username') and client.username == username:
                return True
        return False
    
    def _check_mention_cooldown(self, username):
        """检查用户是否在冷却时间内"""
        current_time = time.time()
        if username in self.mentioned_users:
            if current_time - self.mentioned_users[username] < self.mention_cooldown:
                return False
        self.mentioned_users[username] = current_time
        return True
    
    # ===== 新增：获取在线用户列表的API =====
    def get_online_users(self):
        """获取所有在线用户的用户名列表"""
        online_usernames = []
        for client in self.online_users:
            if hasattr(client, 'username') and client.username:
                online_usernames.append(client.username)
        return list(set(online_usernames))  # 去重
    
    # ===== HTTP路由注册 =====
    def register_routes(self, app):
        """注册HTTP路由"""
        
        @app.route("/api/online-users", methods=["GET"])
        def get_online_users_api():
            """获取在线用户列表的API端点"""
            online_users = self.get_online_users()
            return jsonify({"users": online_users})
    
    async def on_message(self, api, msg):
        """处理消息事件"""
        if msg.get("type") != "text":
            return
        
        content = msg.get("content", "")
        if not content:
            return
        
        mentions = self._extract_mentions(content)
        if not mentions:
            return
        
        sender = msg.get("user")
        print(f"[UserMention] {sender} 提到了: {mentions}")
        
        online_mentions = []
        offline_mentions = []
        
        for username in mentions:
            if username == sender:
                continue
            
            if self._is_user_online(username):
                online_mentions.append(username)
            else:
                offline_mentions.append(username)
        
        # 给在线用户发送提醒
        for username in online_mentions:
            if not self._check_mention_cooldown(username):
                print(f"[UserMention] {username} 冷却中，跳过")
                continue
            
            await self._send_mention_notification(api, username, sender, content)
        
        # 提示离线用户
        if offline_mentions:
            offline_msg = f"用户 {', '.join(offline_mentions)} 当前不在线"
            await api.send_system_message(offline_msg)
            print(f"[UserMention] 离线用户: {offline_mentions}")
    
    async def _send_mention_notification(self, api, target_user, mentioned_by, message):
        """发送@提醒"""
        notification = {
            "type": "mention",
            "content": f" {mentioned_by} 在消息中提到了你",
            "mentioned_by": mentioned_by,
            "original_message": message,
            "time": int(time.time() * 1000),
            "sound": self.notification_sound
        }
        
        await self._send_to_user(api, target_user, notification)
        print(f"[UserMention] 已向在线用户 {target_user} 发送@提醒 (提示音: {self.sound_name})")
    
    async def _send_to_user(self, api, target_username, notification):
        """发送消息给指定用户"""
        for client in self.online_users:
            if hasattr(client, 'username') and client.username == target_username:
                try:
                    await client.send(json.dumps(notification))
                    print(f"[UserMention] 消息已发送给 {target_username}")
                except Exception as e:
                    print(f"[UserMention] 发送失败: {e}")
                break

# 插件实例
plugin = UserMentionPlugin()

# 导出插件接口
on_load = plugin.on_load
on_server_start = plugin.on_server_start
on_message = plugin.on_message

# 导出API函数
get_online_users = plugin.get_online_users
register_routes = plugin.register_routes