"""
消息频率限制插件
功能：限制用户发送消息的频率，防止刷屏
规则：每个用户每秒最多发送3条消息
"""

import time
from collections import defaultdict, deque

class RateLimitPlugin:
    """消息频率限制插件"""
    
    def __init__(self):
        self.message_history = defaultdict(lambda: deque(maxlen=10))  # 存储每个用户最近的消息时间戳
        self.warning_cooldown = {}  # 警告冷却，避免重复警告
        print("[RateLimit] 消息频率限制插件已初始化")
    
    def on_load(self, api):
        """插件加载时调用"""
        self.api = api
        print("[RateLimit] 插件加载成功 - 限制: 3条/秒")
    
    def on_server_start(self, api):
        """服务器启动时调用"""
        print("[RateLimit] 消息频率限制已生效")
    
    async def on_message(self, api, msg):
        """处理消息事件"""
        # 只处理用户发送的消息，不处理系统消息
        if msg.get("type") not in ["text", "emoji", "image", "file"]:
            return
        
        # 获取用户标识（优先使用UID，否则使用用户名）
        user_id = msg.get("uid") or msg.get("user")
        if not user_id:
            return
        
        current_time = time.time()
        
        # 获取用户的消息历史
        user_history = self.message_history[user_id]
        
        # 清理超过1秒的历史记录
        while user_history and user_history[0] < current_time - 1:
            user_history.popleft()
        
        # 检查频率
        if len(user_history) >= 3:  # 1秒内超过3条
            # 检查是否在警告冷却期
            if user_id not in self.warning_cooldown or current_time - self.warning_cooldown[user_id] > 5:
                # 发送警告消息
                await api.send_system_message(f"发送消息过快，请稍后再试 (限制: 3条/秒)")
                self.warning_cooldown[user_id] = current_time
            
            # 阻止消息（通过设置已处理标志）
            msg["_rate_limited"] = True
            print(f"[RateLimit] 阻止刷屏: {user_id} ({len(user_history)}条/秒)")
            return
        
        # 记录这条消息
        user_history.append(current_time)
        print(f"[RateLimit] 消息通过: {user_id} ({len(user_history)}条/秒)")

# 插件实例
plugin = RateLimitPlugin()

# 导出插件接口
on_load = plugin.on_load
on_server_start = plugin.on_server_start
on_message = plugin.on_message