"""
服务器监控插件
监控在线服务器的状态和性能
"""

import time
from datetime import datetime
import requests
from collections import defaultdict

class ServerMonitorPlugin:
    def __init__(self):
        self.server_stats = defaultdict(dict)
        self.stats_history = defaultdict(list)
        self.max_history = 100  # 保存最近100条记录
        print("[ServerMonitor] 服务器监控插件已初始化")

    def on_load(self, api):
        """插件加载时调用"""
        self.api = api
        
        # 添加监控API
        api.add_route('/stats', 'server_stats', self.get_server_stats, methods=['GET'])
        api.add_route('/stats/<ip>/<port>', 'server_detail', self.get_server_detail, methods=['GET'])
        
        api.get_online_count = self.get_online_count
        api.get_server_uptime = self.get_server_uptime
        
        print("[ServerMonitor] 插件加载成功 - 监控API已添加")

    def on_server_start(self, api):
        """服务器启动时调用"""
        # 启动监控线程
        import threading
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        print("[ServerMonitor] 监控线程已启动")

    def _monitor_loop(self):
        """监控循环"""
        while True:
            time.sleep(10)  # 每10秒检查一次
            self._check_all_servers()

    def _check_all_servers(self):
        """检查所有服务器状态"""
        servers = self.api.get_servers()
        current_time = time.time()
        
        for key, server in servers.items():
            ip = server['ip']
            port = server['http_port']
            
            try:
                # 获取服务器信息
                start_time = time.time()
                response = requests.get(f"http://{ip}:{port}/info", timeout=2)
                response_time = int((time.time() - start_time) * 1000)  # 毫秒
                
                if response.status_code == 200:
                    info = response.json()
                    
                    # 更新统计
                    stats = {
                        'timestamp': current_time,
                        'response_time': response_time,
                        'status': 'online',
                        'name': info.get('name', server['name']),
                        'ws_port': info.get('ws_port', server['port'])
                    }
                    
                    self.server_stats[key] = stats
                    self.stats_history[key].append(stats)
                    
                    # 限制历史记录数量
                    if len(self.stats_history[key]) > self.max_history:
                        self.stats_history[key] = self.stats_history[key][-self.max_history:]
                    
                    print(f"[Monitor] {server['name']} - 响应时间: {response_time}ms")
                else:
                    self._record_offline(key, server, 'http_error')
                    
            except requests.exceptions.RequestException:
                self._record_offline(key, server, 'timeout')

    def _record_offline(self, key, server, reason):
        """记录服务器离线"""
        stats = {
            'timestamp': time.time(),
            'response_time': None,
            'status': 'offline',
            'reason': reason,
            'name': server['name']
        }
        
        self.server_stats[key] = stats
        self.stats_history[key].append(stats)
        
        print(f"[Monitor] {server['name']} - 离线: {reason}")

    def get_server_stats(self):
        """获取所有服务器统计"""
        result = []
        servers = self.api.get_servers()
        
        for key, server in servers.items():
            stats = self.server_stats.get(key, {})
            result.append({
                'name': server['name'],
                'ip': server['ip'],
                'port': server['port'],
                'http_port': server['http_port'],
                'status': stats.get('status', 'unknown'),
                'response_time': stats.get('response_time'),
                'last_seen': server.get('last_seen')
            })
        
        return result

    def get_server_detail(self, ip, port):
        """获取特定服务器详情"""
        key = (ip, int(port))
        servers = self.api.get_servers()
        
        if key not in servers:
            return {"error": "服务器不存在"}, 404
        
        server = servers[key]
        stats = self.server_stats.get(key, {})
        history = self.stats_history.get(key, [])
        
        # 计算平均响应时间
        online_records = [h for h in history if h.get('status') == 'online']
        avg_response = None
        if online_records:
            avg_response = sum(h['response_time'] for h in online_records) / len(online_records)
        
        return {
            'server': {
                'name': server['name'],
                'description': server.get('description', ''),
                'ip': server['ip'],
                'port': server['port'],
                'http_port': server['http_port']
            },
            'current_stats': stats,
            'history': history[-20:],  # 最近20条记录
            'avg_response_time': avg_response,
            'online_rate': len(online_records) / len(history) if history else 0
        }

    def get_online_count(self):
        """获取在线服务器数量"""
        servers = self.api.get_servers()
        online = 0
        
        for key in servers:
            stats = self.server_stats.get(key, {})
            if stats.get('status') == 'online':
                online += 1
        
        return online

    def get_server_uptime(self, ip, port):
        """获取服务器在线时长"""
        key = (ip, port)
        history = self.stats_history.get(key, [])
        
        if not history:
            return 0
        
        # 计算连续在线时间
        online_time = 0
        last_online = None
        
        for record in reversed(history):
            if record.get('status') == 'online':
                if last_online is None:
                    last_online = record['timestamp']
            else:
                if last_online is not None:
                    online_time += last_online - record['timestamp']
                    last_online = None
        
        return online_time

    def on_server_register(self, api, ip, port, server_info):
        """服务器注册时调用"""
        print(f"[Monitor] 新服务器加入监控: {server_info['name']} ({ip}:{port})")

    def on_server_unregister(self, api, ip, port):
        """服务器注销时调用"""
        key = (ip, port)
        if key in self.server_stats:
            del self.server_stats[key]
        if key in self.stats_history:
            del self.stats_history[key]
        print(f"[Monitor] 服务器移除监控: {ip}:{port}")

    def on_server_offline(self, api, ip, port, server_info):
        """服务器离线时调用"""
        print(f"[Monitor] 服务器离线: {server_info['name']} ({ip}:{port})")

# 插件实例
plugin = ServerMonitorPlugin()

# 导出插件接口
on_load = plugin.on_load
on_server_start = plugin.on_server_start
on_server_register = plugin.on_server_register
on_server_unregister = plugin.on_server_unregister
on_server_offline = plugin.on_server_offline