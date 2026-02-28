"""
消息加密存储插件（纯 Python 实现）
使用简单的 XOR 加密，无需外部依赖
"""

import json
import hashlib
import os

class SimpleCipher:
    """简单的 XOR 加密实现"""
    
    def __init__(self, key):
        self.key = hashlib.sha256(key.encode()).digest()
    
    def encrypt(self, data):
        """加密数据"""
        if isinstance(data, str):
            data = data.encode()
        
        # XOR 加密
        result = bytearray()
        for i, byte in enumerate(data):
            result.append(byte ^ self.key[i % len(self.key)])
        
        return result.hex()
    
    def decrypt(self, data):
        """解密数据"""
        try:
            data_bytes = bytes.fromhex(data)
            result = bytearray()
            for i, byte in enumerate(data_bytes):
                result.append(byte ^ self.key[i % len(self.key)])
            return result.decode()
        except:
            return data

class MessageEncryptPlugin:
    """消息加密存储插件（纯 Python 实现）"""
    
    def __init__(self):
        self.encryption_enabled = True
        # 从主机名生成密钥
        import socket
        hostname = socket.gethostname()
        self.cipher = SimpleCipher(hostname + "_salt_2024")
        print("[Encrypt] 消息加密存储插件已初始化（纯 Python 实现）")
    
    def on_load(self, api):
        """插件加载时调用"""
        self.api = api
        print("[Encrypt] 插件加载成功 - 使用 XOR 加密")
    
    def on_server_start(self, api):
        """服务器启动时调用"""
        print("[Encrypt] 消息将使用 XOR 加密存储")
    
    async def on_message(self, api, msg):
        """处理消息事件"""
        if msg.get("_storage_encrypted") is None:
            msg["_needs_encryption"] = True
    
    def encrypt_message(self, message_data):
        """加密消息"""
        try:
            if isinstance(message_data, dict):
                message_data = json.dumps(message_data)
            elif not isinstance(message_data, str):
                message_data = str(message_data)
            
            encrypted = self.cipher.encrypt(message_data)
            return f"xor:{encrypted}"
        except Exception as e:
            print(f"[Encrypt] 加密失败: {e}")
            return json.dumps(message_data) if isinstance(message_data, dict) else str(message_data)
    
    def decrypt_message(self, encrypted_data):
        """解密消息"""
        try:
            if isinstance(encrypted_data, str) and encrypted_data.startswith("xor:"):
                encrypted = encrypted_data[4:]
                decrypted = self.cipher.decrypt(encrypted)
                return decrypted
            return encrypted_data
        except Exception as e:
            print(f"[Encrypt] 解密失败: {e}")
            return encrypted_data

# 插件实例
plugin = MessageEncryptPlugin()

# 导出插件接口
on_load = plugin.on_load
on_server_start = plugin.on_server_start
on_message = plugin.on_message

# 导出加密函数
encrypt_message = plugin.encrypt_message
decrypt_message = plugin.decrypt_message