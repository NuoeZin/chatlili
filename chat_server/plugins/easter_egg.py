"""
彩蛋插件
功能：当用户输入 *bug 时，随机触发彩蛋（仅触发者可见，不存储）
"""

import os
import random
import json
import time
import base64
import asyncio
import shutil
import hashlib
from datetime import datetime

class EasterEggPlugin:
    """彩蛋插件"""
    
    def __init__(self):
        self.eggs_dir = "eggs"
        self.photos_dir = os.path.join(self.eggs_dir, "photos")
        self.docs_dir = os.path.join(self.eggs_dir, "documents")
        self.urls_file = os.path.join(self.eggs_dir, "urls.txt")
        self.config_file = os.path.join(self.eggs_dir, "config.json")
        
        # 上传目录
        self.upload_dir = "uploads"
        
        # 服务器头像路径
        self.server_avatar = "avatars/serverchat.png"
        
        # 用户临时文件记录 {username: [file1, file2, ...]}
        self.user_temp_files = {}
        
        # 彩蛋配置
        self.config = self._load_config()
        
        # 彩蛋类型权重
        self.egg_weights = self.config.get("weights", {
            "image": 30,
            "text": 40,
            "redirect": 20,
            "special": 10
        })
        
        print("[EasterEgg] 彩蛋插件已初始化")
        self._print_stats()
    
    def _load_config(self):
        """加载配置文件"""
        default_config = {
            "weights": {
                "image": 30,
                "text": 40,
                "redirect": 20,
                "special": 10
            },
            "messages": {
                "trigger": "彩蛋触发！",
                "no_eggs": "今天没有彩蛋，明天再来吧~"
            },
            "cooldown": 60,
            "enabled": True
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    print(f"[EasterEgg] 已加载配置文件: {self.config_file}")
                    
                    # 合并配置，确保所有必要的键都存在
                    merged_config = default_config.copy()
                    
                    # 深度合并 weights
                    if "weights" in config:
                        for key in default_config["weights"]:
                            if key in config["weights"]:
                                merged_config["weights"][key] = config["weights"][key]
                    
                    # 合并其他配置
                    for key in config:
                        if key != "weights":
                            merged_config[key] = config[key]
                    
                    return merged_config
            except Exception as e:
                print(f"[EasterEgg] 加载配置文件失败: {e}")
        
        return default_config
    
    def _print_stats(self):
        """打印统计信息"""
        # 检查图片
        photo_count = 0
        if os.path.exists(self.photos_dir):
            photo_count = len([f for f in os.listdir(self.photos_dir) 
                              if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))])
        
        # 检查文档
        doc_count = 0
        if os.path.exists(self.docs_dir):
            doc_count = len([f for f in os.listdir(self.docs_dir) 
                            if f.lower().endswith('.txt')])
        
        # 检查网址
        url_count = 0
        if os.path.exists(self.urls_file):
            try:
                with open(self.urls_file, 'r', encoding='utf-8') as f:
                    url_count = len([line for line in f.readlines() if line.strip()])
            except:
                pass
        
        print(f"[EasterEgg] 彩蛋资源: {photo_count}张图片, {doc_count}个文本, {url_count}个网址")
        print(f"[EasterEgg] 彩蛋权重: 图片{self.egg_weights.get('image', 0)}% 文本{self.egg_weights.get('text', 0)}% 跳转{self.egg_weights.get('redirect', 0)}% 特殊{self.egg_weights.get('special', 0)}%")
    
    def on_load(self, api):
        """插件加载时调用"""
        self.api = api
        self.user_cooldown = {}  # 用户冷却记录
        
        # 清理旧的临时文件
        self._cleanup_temp_files()
        
        print("[EasterEgg] 插件加载成功 - 输入 *bug 触发彩蛋（仅自己可见）")
    
    def on_server_start(self, api):
        """服务器启动时调用"""
        print("[EasterEgg] 彩蛋服务已启动 - 彩蛋消息不会存入数据库")
    
    def _cleanup_temp_files(self, username=None):
        """清理临时文件"""
        if username:
            # 清理特定用户的临时文件
            if username in self.user_temp_files:
                for file_path in self.user_temp_files[username]:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            print(f"[EasterEgg] 已清理用户临时文件: {file_path}")
                    except Exception as e:
                        print(f"[EasterEgg] 清理文件失败: {e}")
                del self.user_temp_files[username]
        else:
            # 清理所有 egg_ 开头的临时文件（启动时）
            if os.path.exists(self.upload_dir):
                for f in os.listdir(self.upload_dir):
                    if f.startswith("egg_"):
                        try:
                            os.remove(os.path.join(self.upload_dir, f))
                            print(f"[EasterEgg] 已清理临时文件: {f}")
                        except Exception as e:
                            print(f"[EasterEgg] 清理文件失败: {e}")
    
    def _check_cooldown(self, user_id):
        """检查冷却时间"""
        if not self.config.get("cooldown"):
            return True
        
        current_time = time.time()
        if user_id in self.user_cooldown:
            if current_time - self.user_cooldown[user_id] < self.config["cooldown"]:
                return False
        self.user_cooldown[user_id] = current_time
        return True
    
    async def _send_to_user(self, api, target_username, message):
        """发送消息给指定用户"""
        clients = api.ctx.get('clients', set())
        for client in clients:
            if hasattr(client, 'username') and client.username == target_username:
                try:
                    await client.send(json.dumps(message))
                    return True
                except Exception as e:
                    print(f"[EasterEgg] 发送失败: {e}")
        return False
    
    async def on_user_leave(self, api, username):
        """用户离开时清理其临时文件"""
        self._cleanup_temp_files(username)
        print(f"[EasterEgg] 用户 {username} 离开，已清理临时文件")
    
    async def on_message(self, api, msg):
        """处理消息事件"""
        if not self.config.get("enabled", True):
            return
        
        if msg.get("type") != "text":
            return
        
        content = msg.get("content", "")
        if not content or content.lower().strip() != '*bug':
            return
        
        # 标记为指令消息，不存入数据库
        msg["_is_command"] = True
        msg["_no_store"] = True  # 额外标记确保不存储
        
        sender = msg.get("user")
        uid = msg.get("uid")
        user_id = uid or sender
        
        # 检查冷却
        if not self._check_cooldown(user_id):
            await api.send_system_message(f"{sender} 彩蛋冷却中，请稍后再试")
            return
        
        print(f"[EasterEgg] {sender} 触发了彩蛋（仅自己可见）")
        
        # 随机选择彩蛋类型
        egg_type = self._choose_egg_type()
        
        egg_message = None
        if egg_type == "image":
            egg_message = await self._create_image_egg(sender)
        elif egg_type == "text":
            egg_message = await self._create_text_egg(sender)
        elif egg_type == "redirect":
            egg_message = await self._create_redirect_egg(sender)
        else:
            egg_message = await self._create_special_egg(sender)
        
        # 只发送给触发者
        if egg_message:
            await self._send_to_user(api, sender, egg_message)
            print(f"[EasterEgg] 彩蛋已发送给 {sender}")
    
    def _choose_egg_type(self):
        """根据权重选择彩蛋类型"""
        total = sum(self.egg_weights.values())
        r = random.randint(1, total)
        
        cumulative = 0
        for egg_type, weight in self.egg_weights.items():
            cumulative += weight
            if r <= cumulative:
                return egg_type
        return "text"
    
    async def _create_image_egg(self, sender):
        """创建图片彩蛋（直接保存到 uploads 根目录）"""
        if not os.path.exists(self.photos_dir):
            return None
        
        # 获取所有图片
        images = []
        for f in os.listdir(self.photos_dir):
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                images.append(f)
        
        if not images:
            return None
        
        # 随机选择一张图片
        chosen_image = random.choice(images)
        image_path = os.path.join(self.photos_dir, chosen_image)
        
        try:
            # 生成唯一的临时文件名
            file_hash = hashlib.md5(f"{sender}_{time.time()}_{chosen_image}".encode()).hexdigest()[:8]
            ext = os.path.splitext(chosen_image)[1]
            temp_filename = f"egg_{sender}_{file_hash}{ext}"
            
            # 直接保存到 uploads 根目录
            temp_path = os.path.join(self.upload_dir, temp_filename)
            
            # 复制图片到上传目录
            shutil.copy2(image_path, temp_path)
            os.chmod(temp_path, 0o644)  # 确保可读
            
            # 记录用户的临时文件
            if sender not in self.user_temp_files:
                self.user_temp_files[sender] = []
            self.user_temp_files[sender].append(temp_path)
            
            print(f"[EasterEgg] 图片已保存到: {temp_path}")
            
            # 创建图片消息
            image_msg = {
                "type": "image",
                "user": "🎲 彩蛋",
                "content": temp_filename,
                "time": int(time.time() * 1000),
                "avatar": self.server_avatar,
                "_egg": True,
                "_private": True,
                "_temp_file": True
            }
            
            print(f"[EasterEgg] 已创建图片彩蛋: {chosen_image} -> {temp_filename}")
            return image_msg
            
        except Exception as e:
            print(f"[EasterEgg] 创建图片彩蛋失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def _create_text_egg(self, sender):
        """创建文字彩蛋"""
        if not os.path.exists(self.docs_dir):
            return None
        
        # 获取所有txt文件
        text_files = []
        for f in os.listdir(self.docs_dir):
            if f.lower().endswith('.txt'):
                text_files.append(f)
        
        if not text_files:
            return None
        
        # 随机选择一个文件
        chosen_file = random.choice(text_files)
        file_path = os.path.join(self.docs_dir, chosen_file)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text_content = f.read().strip()
            
            # 创建文字消息
            text_msg = {
                "type": "text",
                "user": "🎲 彩蛋",
                "content": text_content,
                "time": int(time.time() * 1000),
                "avatar": self.server_avatar,
                "_egg": True,
                "_private": True
            }
            
            print(f"[EasterEgg] 已创建文字彩蛋: {chosen_file}")
            return text_msg
            
        except Exception as e:
            print(f"[EasterEgg] 创建文字彩蛋失败: {e}")
            return None
    
    async def _create_redirect_egg(self, sender):
        """创建跳转彩蛋"""
        if not os.path.exists(self.urls_file):
            return None
        
        try:
            with open(self.urls_file, 'r', encoding='utf-8') as f:
                urls = [line.strip() for line in f.readlines() if line.strip()]
            
            if not urls:
                return None
            
            # 随机选择一个网址
            chosen_url = random.choice(urls)
            
            # 创建跳转消息
            redirect_msg = {
                "type": "redirect",
                "user": "🎲 彩蛋",
                "content": chosen_url,
                "time": int(time.time() * 1000),
                "avatar": self.server_avatar,
                "message": f"你触发了跳转彩蛋！3秒后跳转到：",
                "_egg": True,
                "_private": True
            }
            
            print(f"[EasterEgg] 已创建跳转彩蛋: {chosen_url}")
            return redirect_msg
            
        except Exception as e:
            print(f"[EasterEgg] 创建跳转彩蛋失败: {e}")
            return None
    
    async def _create_special_egg(self, sender):
        """创建特殊彩蛋"""
        special_eggs = [
            "恭喜你发现了隐藏彩蛋！（仅你可见）",
            "你获得了七彩祥云！",
            "一只独角兽飘过...",
            "你解锁了隐藏成就：彩蛋猎人",
            "幸运值 +100！",
            "四叶草祝福你",
            "群星为你闪耀",
            "命中注定今天有好运",
            "此甚诡谲之，汝知否？",
            "学会自己爱自己，迷失自我的孩子无法成长",
            "资本的尽头是无尽的劳动",
            "妈妈慈祥的微笑十分痛苦",
            "镜子里的我是死去的我",
            "孤独的人给自己写信",
            "孩子们，不要再让手中的竹蜻蜓飞走了哦"
        ]
        
        chosen_text = random.choice(special_eggs)
        
        special_msg = {
            "type": "text",
            "user": "🎲 彩蛋",
            "content": chosen_text,
            "time": int(time.time() * 1000),
            "avatar": self.server_avatar,
            "_egg": True,
            "_private": True
        }
        
        return special_msg

# 插件实例
plugin = EasterEggPlugin()

# 导出插件接口
on_load = plugin.on_load
on_server_start = plugin.on_server_start
on_message = plugin.on_message
on_user_leave = plugin.on_user_leave