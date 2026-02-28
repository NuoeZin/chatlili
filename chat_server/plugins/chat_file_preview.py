"""
聊天服务器文件预览插件
功能：自动识别文件类型，修正消息类型
"""

import os

class ChatFilePreviewPlugin:
    """聊天服务器文件预览插件"""
    
    def __init__(self):
        # 支持的视频格式（完整列表）
        self.supported_video = [
            '.mp4', '.avi', '.mov', '.mkv', '.webm', 
            '.flv', '.wmv', '.m4v', '.3gp', '.mpg', '.mpeg',
            '.ts', '.mts', '.m2ts', '.vob', '.ogv', '.divx'
        ]
        # 支持的音频格式（完整列表）
        self.supported_audio = [
            '.mp3', '.wav', '.flac', '.m4a', '.ogg', 
            '.aac', '.wma', '.opus', '.mid', '.midi',
            '.ape', '.ac3', '.dts', '.cda'
        ]
        # 支持的图片格式（完整列表）
        self.supported_image = [
            '.jpg', '.jpeg', '.png', '.gif', '.webp', 
            '.bmp', '.svg', '.ico', '.tiff', '.tif',
            '.psd', '.raw', '.cr2', '.nef'
        ]
        print("[ChatFilePreview] 聊天文件预览插件已初始化")
        print(f"[ChatFilePreview] 支持视频: {', '.join(self.supported_video[:5])}... 共{len(self.supported_video)}种")
        print(f"[ChatFilePreview] 支持音频: {', '.join(self.supported_audio[:5])}... 共{len(self.supported_audio)}种")
        print(f"[ChatFilePreview] 支持图片: {', '.join(self.supported_image[:5])}... 共{len(self.supported_image)}种")
    
    def on_load(self, api):
        """插件加载时调用"""
        self.api = api
        print("[ChatFilePreview] 插件加载成功")
    
    def on_server_start(self, api):
        """服务器启动时调用"""
        print("[ChatFilePreview] 文件类型修正服务已启动")
    
    async def on_message(self, api, msg):
        """处理消息事件 - 修正文件类型"""
        # 只处理文件消息
        if msg.get("type") != "file":
            return
        
        filename = msg.get("content", "")
        if not filename:
            return
        
        # 获取文件扩展名
        ext = os.path.splitext(filename)[1].lower()
        
        # 根据扩展名修正类型
        if ext in self.supported_video:
            old_type = msg.get("type")
            msg["type"] = "video"
            print(f"[ChatFilePreview] 视频: {filename} ({old_type} -> video)")
        elif ext in self.supported_audio:
            old_type = msg.get("type")
            msg["type"] = "audio"
            print(f"[ChatFilePreview] 音频: {filename} ({old_type} -> audio)")
        elif ext in self.supported_image:
            old_type = msg.get("type")
            msg["type"] = "image"
            print(f"[ChatFilePreview] 图片: {filename} ({old_type} -> image)")

# 插件实例
plugin = ChatFilePreviewPlugin()

# 导出插件接口
on_load = plugin.on_load
on_server_start = plugin.on_server_start
on_message = plugin.on_message