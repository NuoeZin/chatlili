"""
文件预览插件
为聊天服务器提供文件预览功能
"""

import os
import json
import time
from flask import jsonify, request, send_file
import mimetypes

class FilePreviewPlugin:
    def __init__(self):
        self.preview_cache = {}
        self.supported_video = ['.mp4', '.webm', '.ogg', '.mov']
        self.supported_audio = ['.mp3', '.wav', '.ogg', '.m4a']
        self.supported_image = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        print("[FilePreview] 文件预览插件已初始化")

    def on_load(self, api):
        """插件加载时调用"""
        self.api = api
        
        # 添加预览路由
        api.add_rule = self.add_preview_routes
        api.get_file_info = self.get_file_info
        api.generate_thumbnail = self.generate_thumbnail
        
        print("[FilePreview] 插件加载成功 - 支持视频/音频/图片预览")

    def add_preview_routes(self):
        """添加预览相关路由"""
        self.api.add_route('/preview/<path:filename>', 'preview_file', self.preview_file, methods=['GET'])
        self.api.add_route('/file_info', 'file_info', self.file_info, methods=['POST'])
        self.api.add_route('/thumbnail/<path:filename>', 'thumbnail', self.generate_thumbnail_route, methods=['GET'])
        print("[FilePreview] 预览路由添加成功")

    def preview_file(self, filename):
        """文件预览接口"""
        try:
            # 这里需要从聊天服务器获取文件
            # 实际应用中可能需要代理请求到聊天服务器
            file_ext = os.path.splitext(filename)[1].lower()
            
            if file_ext in self.supported_video:
                return self._video_preview(filename)
            elif file_ext in self.supported_audio:
                return self._audio_preview(filename)
            elif file_ext in self.supported_image:
                return self._image_preview(filename)
            else:
                return jsonify({
                    "type": "file",
                    "filename": filename,
                    "size": "未知",
                    "url": f"/file/{filename}"
                })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    def _video_preview(self, filename):
        """视频预览"""
        return jsonify({
            "type": "video",
            "filename": filename,
            "url": f"/file/{filename}",
            "thumbnail": f"/thumbnail/{filename}",
            "controls": True,
            "autoplay": False
        })

    def _audio_preview(self, filename):
        """音频预览"""
        return jsonify({
            "type": "audio",
            "filename": filename,
            "url": f"/file/{filename}",
            "controls": True,
            "autoplay": False
        })

    def _image_preview(self, filename):
        """图片预览"""
        return jsonify({
            "type": "image",
            "filename": filename,
            "url": f"/file/{filename}",
            "thumbnail": f"/thumbnail/{filename}"
        })

    def file_info(self):
        """获取文件信息"""
        data = request.json
        filename = data.get('filename')
        
        if not filename:
            return jsonify({"error": "文件名不能为空"}), 400
        
        file_ext = os.path.splitext(filename)[1].lower()
        
        file_type = "file"
        if file_ext in self.supported_video:
            file_type = "video"
        elif file_ext in self.supported_audio:
            file_type = "audio"
        elif file_ext in self.supported_image:
            file_type = "image"
        
        return jsonify({
            "filename": filename,
            "type": file_type,
            "ext": file_ext,
            "preview_url": f"/preview/{filename}"
        })

    def generate_thumbnail_route(self, filename):
        """生成缩略图"""
        # 这里可以调用 FFmpeg 或其他库生成视频缩略图
        # 简单实现：返回一个默认图片
        return jsonify({"thumbnail": "/static/default_thumbnail.png"})

    def generate_thumbnail(self, filename):
        """生成缩略图（供其他插件调用）"""
        return self.generate_thumbnail_route(filename)

    def get_file_info(self, filename):
        """获取文件信息（供其他插件调用）"""
        return self.file_info()

    def on_server_start(self, api):
        """服务器启动时调用"""
        self.add_preview_routes()
        print("[FilePreview] 文件预览服务已启动")

    def on_server_register(self, api, ip, port, server_info):
        """服务器注册时调用"""
        # 可以在这里收集服务器的文件信息
        pass

# 插件实例
plugin = FilePreviewPlugin()

# 导出插件接口
on_load = plugin.on_load
on_server_start = plugin.on_server_start
on_server_register = plugin.on_server_register