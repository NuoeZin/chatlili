// ===== 全局变量 =====
let socket;
let oldestId = null;
let ip = localStorage.getItem("ip");
let port = localStorage.getItem("port");
let user = localStorage.getItem("user");
let uid = localStorage.getItem("uid");
let serverHttpPort = localStorage.getItem("serverHttpPort") || 5000;
let reconnectAttempts = 0;
const MAX_RECONNECT = 5;
let isLoadingHistory = false;
let hasMoreHistory = true;

// 图片懒加载
let imageObserver;

// ===== 初始化图片懒加载 =====
function initLazyLoading() {
    if ('IntersectionObserver' in window) {
        imageObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    if (img.dataset.src) {
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                        imageObserver.unobserve(img);
                    }
                }
            });
        }, {
            rootMargin: '50px 0px',
            threshold: 0.01
        });
    }
}

// ===== 工具函数 =====
function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, m => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;',
        '"': '&quot;', "'": '&#039;'
    })[m]);
}

function getAvatarUrl(username) {
    return `http://${ip}:${serverHttpPort}/avatar/${encodeURIComponent(username)}?t=${Date.now()}`;
}

function getFileIcon(filename) {
    const ext = filename.split('.').pop()?.toLowerCase() || '';
    const icons = {
        'mp4': '🎬', 'avi': '🎬', 'mov': '🎬', 'mkv': '🎬',
        'mp3': '🎵', 'wav': '🎵', 'flac': '🎵', 'm4a': '🎵',
        'jpg': '🖼️', 'jpeg': '🖼️', 'png': '🖼️', 'gif': '🖼️',
        'pdf': '📄', 'doc': '📝', 'docx': '📝', 'txt': '📄',
        'zip': '📦', 'rar': '📦', '7z': '📦'
    };
    return icons[ext] || '📎';
}

// ===== 显示消息 =====
function displayMessage(msg) {
    const chat = document.getElementById("chat");
    if (!chat) return;
    
    console.log("显示消息:", msg); // 打印完整消息对象
    
    const isSelf = msg.user === user;
    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${isSelf ? 'self' : 'other'}`;
    if (msg.id) msgDiv.setAttribute("data-message-id", msg.id);
    
    // 对方头像
    if (!isSelf) {
        const avatar = document.createElement("img");
        avatar.className = "avatar";
        avatar.src = getAvatarUrl(msg.user);
        avatar.onerror = function() {
            this.outerHTML = `<div class="avatar text-avatar">${msg.user.charAt(0)}</div>`;
        };
        msgDiv.appendChild(avatar);
    }
    
    // 气泡
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    
    // 对方名字
    if (!isSelf) {
        const name = document.createElement("div");
        name.className = "message-name";
        name.textContent = msg.user;
        bubble.appendChild(name);
    }
    
    // ===== 判断是否为文件 =====
    const content = msg.content || '';
    const hasFileExtension = content.includes('.') && 
        (content.endsWith('.mp3') || content.endsWith('.wav') || content.endsWith('.mp4') ||
         content.endsWith('.avi') || content.endsWith('.mov') || content.endsWith('.mkv') ||
         content.endsWith('.flac') || content.endsWith('.m4a') || content.endsWith('.ogg') ||
         content.endsWith('.jpg') || content.endsWith('.jpeg') || content.endsWith('.png') ||
         content.endsWith('.gif') || content.endsWith('.zip') || content.endsWith('.rar') ||
         content.endsWith('.pdf') || content.endsWith('.txt'));
    
    // ===== 内容区域 =====
    if (msg.type === 'image' || (hasFileExtension && content.match(/\.(jpg|jpeg|png|gif|webp|bmp)$/i))) {
        // 图片 - 直接显示
        const img = document.createElement("img");
        img.className = "chat-image lazy";
        img.dataset.src = `http://${ip}:${serverHttpPort}/file/${encodeURIComponent(content)}`;
        img.alt = content;
        img.style.maxWidth = "100%";
        img.style.maxHeight = "300px";
        img.style.borderRadius = "8px";
        img.style.cursor = "pointer";
        
        if (imageObserver) {
            img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"%3E%3C/svg%3E';
            imageObserver.observe(img);
        } else {
            img.src = img.dataset.src;
        }
        
        img.onclick = () => window.open(img.dataset.src || img.src);
        bubble.appendChild(img);
        
    } else if (msg.type === 'emoji') {
        // 表情
        const img = document.createElement("img");
        img.src = `http://${ip}:${serverHttpPort}/emoji/${encodeURIComponent(content)}`;
        img.style.width = "60px";
        bubble.appendChild(img);
        
    } else if (hasFileExtension) {
        // 任何包含文件扩展名的消息都显示为文件气泡
        const fileDiv = document.createElement("div");
        fileDiv.className = "file-bubble";
        fileDiv.onclick = () => {
            window.location.href = `preview.html?ip=${ip}&port=${serverHttpPort}&file=${encodeURIComponent(content)}&type=${msg.type || 'file'}`;
        };
        
        // 根据扩展名选择图标
        let icon = '📎';
        const ext = content.split('.').pop()?.toLowerCase() || '';
        
        if (['mp4', 'avi', 'mov', 'mkv', 'webm', 'flv', 'wmv'].includes(ext)) {
            icon = '🎬';
        } else if (['mp3', 'wav', 'flac', 'm4a', 'ogg', 'aac'].includes(ext)) {
            icon = '🎵';
        } else if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'].includes(ext)) {
            icon = '🖼️';
        } else if (['pdf'].includes(ext)) {
            icon = '📄';
        } else if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) {
            icon = '📦';
        } else if (['txt', 'md', 'log'].includes(ext)) {
            icon = '📝';
        }
        
        const iconSpan = document.createElement("span");
        iconSpan.className = "file-bubble-icon";
        iconSpan.innerHTML = icon;
        
        const nameSpan = document.createElement("span");
        nameSpan.className = "file-bubble-name";
        nameSpan.textContent = content;
        
        fileDiv.appendChild(iconSpan);
        fileDiv.appendChild(nameSpan);
        bubble.appendChild(fileDiv);
        
    } else {
        // 普通文本
        bubble.appendChild(document.createTextNode(content));
    }
    
    // 时间戳
    if (msg.time) {
        const time = new Date(msg.time);
        const timeStr = time.toLocaleTimeString('zh-CN', {hour12: false});
        const timeSpan = document.createElement("div");
        timeSpan.className = "message-time";
        timeSpan.textContent = timeStr;
        bubble.appendChild(timeSpan);
    }
    
    msgDiv.appendChild(bubble);
    
    // 自己头像
    if (isSelf) {
        const avatar = document.createElement("img");
        avatar.className = "avatar";
        avatar.src = getAvatarUrl(msg.user);
        avatar.onerror = function() {
            this.outerHTML = `<div class="avatar text-avatar">${msg.user.charAt(0)}</div>`;
        };
        msgDiv.appendChild(avatar);
    }
    
    chat.appendChild(msgDiv);
    chat.scrollTop = chat.scrollHeight;
}

// ===== WebSocket连接 =====
function connectWebSocket() {
    const ws = new WebSocket(`ws://${ip}:${port}`);
    
    ws.onopen = () => {
        console.log("WebSocket已连接");
        reconnectAttempts = 0;
        loadHistory();
        loadEmojis();
    };
    
    ws.onmessage = (e) => {
        try {
            const msg = JSON.parse(e.data);
            
            if (msg.type === "system") {
                const chat = document.getElementById("chat");
                if (chat) {
                    const div = document.createElement("div");
                    div.className = "system-message";
                    div.textContent = `🔔 ${msg.content}`;
                    chat.appendChild(div);
                    chat.scrollTop = chat.scrollHeight;
                }
            } else if (msg.type === "recall_notice") {
                const el = document.querySelector(`[data-message-id="${msg.message_id}"]`);
                if (el) {
                    el.querySelector('.bubble').innerHTML = '<div class="recalled">⛔ 消息已撤回</div>';
                }
            } else {
                displayMessage(msg);
            }
        } catch (err) {
            console.error("解析失败:", err);
        }
    };
    
    ws.onclose = () => {
        if (reconnectAttempts++ < MAX_RECONNECT) {
            setTimeout(connectWebSocket, 3000);
        }
    };
    
    return ws;
}

// ===== 加载历史消息 =====
async function loadHistory() {
    isLoadingHistory = true;
    
    try {
        const res = await fetch(`http://${ip}:${serverHttpPort}/history`);
        const list = await res.json();
        
        const chat = document.getElementById("chat");
        chat.innerHTML = '';
        
        list.forEach(msg => displayMessage(msg));
        chat.scrollTop = chat.scrollHeight;
        
        if (list.length) oldestId = list[0].id;
    } catch (e) {
        console.error("历史消息加载失败");
    }
    
    isLoadingHistory = false;
}

// ===== 加载更多历史消息 =====
async function loadMoreHistory() {
    if (isLoadingHistory || !hasMoreHistory) return;
    
    isLoadingHistory = true;
    const chat = document.getElementById("chat");
    const oldHeight = chat.scrollHeight;
    
    try {
        const res = await fetch(`http://${ip}:${serverHttpPort}/history?before=${oldestId}`);
        const list = await res.json();
        
        if (!list.length) {
            hasMoreHistory = false;
            return;
        }
        
        oldestId = list[0].id;
        
        // 临时保存当前滚动位置
        for (let i = list.length - 1; i >= 0; i--) {
            const msgDiv = createMessageElement(list[i]);
            chat.insertBefore(msgDiv, chat.firstChild);
        }
        
        chat.scrollTop = chat.scrollHeight - oldHeight;
    } catch (e) {}
    
    isLoadingHistory = false;
}

// ===== 加载表情 =====
async function loadEmojis() {
    const panel = document.getElementById("emojiPanel");
    if (!panel) return;
    
    try {
        const res = await fetch(`http://${ip}:${serverHttpPort}/emojis`);
        const list = await res.json();
        
        panel.innerHTML = list.map(name => 
            `<img src="http://${ip}:${serverHttpPort}/emoji/${name}" alt="${name}" class="emoji">`
        ).join('');
        
        panel.querySelectorAll('img').forEach(img => {
            img.onclick = () => {
                socket.send(JSON.stringify({
                    type: "emoji", user, uid,
                    content: img.alt,
                    time: Date.now()
                }));
            };
        });
    } catch (e) {
        panel.innerHTML = '<p>加载失败</p>';
    }
}

// ===== 发送文字 =====
function sendText() {
    const input = document.getElementById("input");
    if (!input?.value.trim()) return;
    
    socket.send(JSON.stringify({
        type: "text", user, uid,
        content: input.value,
        time: Date.now()
    }));
    
    input.value = "";
}

// ===== 上传文件 =====
async function sendFile() {
    const input = document.getElementById("fileInput");
    if (!input?.files[0]) return alert("请选择文件");
    
    const form = new FormData();
    form.append("file", input.files[0]);
    
    try {
        const res = await fetch(`http://${ip}:${serverHttpPort}/upload`, {
            method: "POST", body: form
        });
        const data = await res.json();
        
        socket.send(JSON.stringify({
            type: data.type, user, uid,
            content: data.filename,
            time: Date.now()
        }));
        
        input.value = "";
    } catch (e) {
        alert("上传失败");
    }
}

// ===== 登录页函数（保留向后兼容）=====
function connect() {
    const newIp = document.getElementById("ip")?.value.trim();
    const newPort = document.getElementById("port")?.value.trim();
    if (!newIp || !newPort) return alert("请输入IP和端口");
    
    fetch(`http://${newIp}:5000/info`)
        .then(res => res.json())
        .then(data => {
            localStorage.setItem("ip", newIp);
            localStorage.setItem("port", newPort);
            localStorage.setItem("serverName", data.name || "未命名");
            localStorage.setItem("serverHttpPort", data.http_port || 5000);
            window.location.href = "login.html";  // 跳转到新登录页
        })
        .catch(() => {
            localStorage.setItem("ip", newIp);
            localStorage.setItem("port", newPort);
            window.location.href = "login.html";  // 即使失败也跳转
        });
}

function selectServer(ip, port, name, httpPort) {
    localStorage.setItem("ip", ip);
    localStorage.setItem("port", port);
    localStorage.setItem("serverName", name || "未命名");
    localStorage.setItem("serverHttpPort", httpPort || 5000);
    window.location.href = "login.html";  // 跳转到新登录页
}

// 保留旧的登录函数用于向后兼容，但重定向到新登录页
async function login() {
    window.location.href = "login.html";
}

async function register() {
    window.location.href = "login.html";
}



async function loadServers() {
    const div = document.getElementById("servers");
    if (!div) return;
    
    try {
        const res = await fetch("/servers");
        const list = await res.json();
        
        div.innerHTML = list.length ? list.map(s => `
            <div class="server-item" onclick="selectServer('${s.ip}',${s.port},'${escapeHtml(s.name)}',${s.http_port})">
                <h3>${escapeHtml(s.name)}</h3>
                <p>${escapeHtml(s.description || '聊天室')}</p>
                <button>连接</button>
            </div>
        `).join('') : '<div class="empty">暂无服务器</div>';
    } catch (e) {
        div.innerHTML = '<div class="error">加载失败</div>';
    }
}

function detectDevice() {
    const ua = navigator.userAgent.toLowerCase();
    return ['mobile', 'android', 'iphone', 'ipad'].some(k => ua.includes(k));
}

// ===== 页面初始化 =====
document.addEventListener("DOMContentLoaded", () => {
    ip = localStorage.getItem("ip");
    port = localStorage.getItem("port");
    user = localStorage.getItem("user");
    uid = localStorage.getItem("uid");
    serverHttpPort = localStorage.getItem("serverHttpPort") || 5000;
    
    // 服务器列表页
    if (document.getElementById("servers")) {
        loadServers();
        setInterval(loadServers, 10000);
    }
    
    // 聊天页
    if (document.getElementById("chat")) {
        if (!ip || !port) window.location.href = "index.html";
        if (!user) window.location.href = "login.html";
        
        initLazyLoading();
        socket = connectWebSocket();
        loadEmojis();
        
        // 滚动加载更多历史消息
        const chat = document.getElementById("chat");
        chat.addEventListener('scroll', () => {
            if (chat.scrollTop < 100 && !isLoadingHistory && hasMoreHistory) {
                loadMoreHistory();
            }
        });
    }
    
    // 登录页
    if (document.getElementById("serverInfo")) {
        const name = localStorage.getItem("serverName") || "未知";
        document.getElementById("serverInfo").innerHTML = `
            <h3>${escapeHtml(name)}</h3>
            <p>请登录或注册</p>
        `;
    }
});

// ===== 暴露全局函数 =====
window.sendText = sendText;
window.sendFile = sendFile;
window.connect = connect;
window.selectServer = selectServer;
window.login = login;
window.register = register;