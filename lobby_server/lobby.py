from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import threading
import time
import requests
from datetime import datetime
from plugin_loader import PluginLoader

app = Flask(__name__, static_folder="../client", static_url_path="")
CORS(app, supports_credentials=True)

# 服务器列表存储
servers = {}  # 使用字典，key为 (ip, port) 元组

# 配置
HEARTBEAT_INTERVAL = 30  # 心跳检测间隔（秒）
MAX_FAIL_COUNT = 3        # 最大失败次数

# 初始化插件加载器
plugin_loader = PluginLoader(app, servers)

# ===== 心跳检测线程 =====
def heartbeat_checker():
    """定期检查服务器存活状态"""
    while True:
        time.sleep(HEARTBEAT_INTERVAL)
        dead_servers = []
        
        for key, server in servers.items():
            try:
                # 发送心跳请求到服务器的 /info 接口
                url = f"http://{server['ip']}:{server['http_port']}/info"
                response = requests.get(url, timeout=3)
                
                if response.status_code == 200:
                    # 服务器存活，重置失败计数
                    server['fail_count'] = 0
                    server['last_seen'] = datetime.now().isoformat()
                    
                    # 触发心跳事件
                    plugin_loader.on_heartbeat(server['ip'], server['port'])
                    
                    print(f"心跳正常: {server['name']} ({server['ip']}:{server['port']})")
                else:
                    # 服务器响应但状态码错误
                    server['fail_count'] += 1
                    print(f"心跳异常 ({server['fail_count']}/{MAX_FAIL_COUNT}): {server['name']}")
                    
            except requests.exceptions.RequestException:
                # 连接失败
                server['fail_count'] += 1
                print(f"心跳超时 ({server['fail_count']}/{MAX_FAIL_COUNT}): {server['name']}")
            
            # 如果失败次数超限，标记为死亡
            if server['fail_count'] >= MAX_FAIL_COUNT:
                dead_servers.append(key)
                print(f"服务器已离线，将从列表移除: {server['name']}")
                
                # 触发离线事件
                plugin_loader.on_server_offline(server['ip'], server['port'], server)
        
        # 移除死亡的服务器
        for key in dead_servers:
            del servers[key]
        
        print(f"当前在线服务器: {len(servers)} 个")

# 启动心跳检测线程
heartbeat_thread = threading.Thread(target=heartbeat_checker, daemon=True)
heartbeat_thread.start()

# ===== 路由 =====

@app.route("/")
def index():
    """返回主页"""
    return send_from_directory(app.static_folder, "index.html")

@app.route("/<path:path>")
def serve_static(path):
    """提供静态文件"""
    return send_from_directory(app.static_folder, path)

@app.route("/favicon.ico")
def favicon():
    return "", 204

@app.route("/servers")
def get_servers():
    """获取服务器列表（用于前端显示房间卡）"""
    servers_list = []
    for key, server in servers.items():
        # 计算在线状态
        last_seen = datetime.fromisoformat(server.get('last_seen', datetime.now().isoformat()))
        time_diff = (datetime.now() - last_seen).total_seconds()
        is_online = time_diff < HEARTBEAT_INTERVAL * 2  # 两个心跳周期内算在线
        
        servers_list.append({
            "name": server["name"],
            "description": server.get("description", "一个普通的聊天室"),
            "ip": server["ip"],
            "port": server["port"],
            "http_port": server["http_port"],
            "server_id": server.get("server_id", ""),
            "last_seen": server.get("last_seen", ""),
            "is_online": is_online,
            "registered_at": server.get("registered_at", "")
        })
    
    # 按最后活跃时间排序
    servers_list.sort(key=lambda x: x.get('last_seen', ''), reverse=True)
    return jsonify(servers_list)

@app.route("/register", methods=["POST", "OPTIONS"])
def register():
    """服务器注册接口 - 接收聊天服务器注册"""
    if request.method == "OPTIONS":
        return "", 200
        
    data = request.json
    ip = data.get("ip")
    port = data.get("port")
    
    if not ip or not port:
        return jsonify({"error": "IP和端口不能为空"}), 400
    
    key = (ip, port)
    
    # 获取完整服务器信息
    server_name = data.get("name", "未命名服务器")
    description = data.get("description", "一个普通的聊天室")
    http_port = data.get("http_port", 5000)
    server_id = data.get("server_id", "auto")
    secret_key = data.get("secret_key", "auto")
    
    server_info = {
        "name": server_name,
        "description": description,
        "ip": ip,
        "port": port,
        "http_port": http_port,
        "server_id": server_id,
        "secret_key": secret_key,
        "last_seen": datetime.now().isoformat(),
        "registered_at": datetime.now().isoformat() if key not in servers else servers[key].get("registered_at", datetime.now().isoformat()),
        "fail_count": 0
    }
    
    # 触发注册事件
    plugin_loader.on_server_register(ip, port, server_info)
    
    if key in servers:
        print(f"服务器重新注册: {server_name} ({ip}:{port}) - ID: {server_id}")
    else:
        print(f"新服务器注册: {server_name} ({ip}:{port}) - ID: {server_id}")
    
    servers[key] = server_info
    print(f"当前在线服务器: {len(servers)} 个")
    
    # 返回server_id和secret_key确认
    return jsonify({
        "status": "ok", 
        "message": "注册成功",
        "server_id": server_id,
        "secret_key": secret_key
    })

@app.route("/unregister", methods=["POST", "OPTIONS"])
def unregister():
    """服务器注销接口"""
    if request.method == "OPTIONS":
        return "", 200
        
    data = request.json
    ip = data.get("ip")
    port = data.get("port")
    
    if not ip or not port:
        return jsonify({"error": "IP和端口不能为空"}), 400
    
    key = (ip, port)
    
    if key in servers:
        server_name = servers[key]["name"]
        
        # 触发注销事件
        plugin_loader.on_server_unregister(ip, port)
        
        del servers[key]
        print(f"服务器主动注销: {server_name}")
        print(f"当前在线服务器: {len(servers)} 个")
        return jsonify({"status": "ok", "message": "注销成功"})
    else:
        return jsonify({"status": "ok", "message": "服务器不在列表中"})

@app.route("/heartbeat", methods=["POST", "OPTIONS"])
def heartbeat():
    """服务器心跳接口"""
    if request.method == "OPTIONS":
        return "", 200
        
    data = request.json
    ip = data.get("ip")
    port = data.get("port")
    
    if not ip or not port:
        return jsonify({"error": "IP和端口不能为空"}), 400
    
    key = (ip, port)
    
    if key in servers:
        servers[key]["last_seen"] = datetime.now().isoformat()
        servers[key]["fail_count"] = 0
        
        # 触发心跳事件
        plugin_loader.on_heartbeat(ip, port)
        
        return jsonify({"status": "ok", "message": "心跳更新成功"})
    else:
        return jsonify({"error": "服务器未注册"}), 404

# ===== 获取单个服务器信息 =====
@app.route("/api/server/<ip>/<port>")
def get_server_info(ip, port):
    """获取单个服务器详细信息"""
    key = (ip, int(port))
    if key in servers:
        return jsonify(servers[key])
    return jsonify({"error": "服务器不存在"}), 404

if __name__ == "__main__":
    print("=" * 60)
    print("大厅服务器启动")
    print("=" * 60)
    
    # 加载插件
    plugin_loader.load_plugins()
    plugin_loader.on_server_start()
    
    print(f"静态文件目录: {app.static_folder}")
    print(f"服务器列表API: http://localhost:8000/servers")
    print(f"心跳检测间隔: {HEARTBEAT_INTERVAL}秒")
    print(f"最大失败次数: {MAX_FAIL_COUNT}")
    print("=" * 60)
    
    app.run(host="0.0.0.0", port=8000, debug=True)