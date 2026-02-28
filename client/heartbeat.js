/**
 * 统一心跳管理模块
 * 功能：
 * - 用户在线时每30秒发送心跳
 * - 2分钟无操作自动标记离线
 * - 退出登录时立即标记离线
 * - 登录成功后立即发送心跳
 */

(function() {
    // ===== 配置 =====
    const HEARTBEAT_INTERVAL = 30000; // 30秒发送一次心跳
    const INACTIVE_TIMEOUT = 120000;  // 2分钟无操作标记离线
    const LOBBY_URL = window.location.origin;
    
    // ===== 状态变量 =====
    let heartbeatInterval = null;
    let inactiveTimer = null;
    let isActive = true;
    let currentUid = null;
    let currentToken = null;
    let isInitialized = false;
    let lastActivity = Date.now();
    
    // ===== 工具函数 =====
    function getCookie(name) {
        const cookieName = name + "=";
        const cookies = document.cookie.split(';');
        for(let i = 0; i < cookies.length; i++) {
            let cookie = cookies[i].trim();
            if (cookie.indexOf(cookieName) === 0) {
                return cookie.substring(cookieName.length, cookie.length);
            }
        }
        return null;
    }
    
    function getCurrentUser() {
        const uid = localStorage.getItem('uid') || getCookie('uid');
        const token = localStorage.getItem('session_token') || getCookie('session_token');
        
        if (uid && token) {
            return { uid, token };
        }
        return null;
    }
    
    function clearUserData() {
        // 清除所有登录相关的数据
        localStorage.removeItem('uid');
        localStorage.removeItem('user');
        localStorage.removeItem('session_token');
        
        const cookies = ['uid', 'username', 'session_token'];
        cookies.forEach(name => {
            document.cookie = name + "=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
        });
    }
    
    // ===== 心跳核心功能 =====
    async function sendHeartbeat() {
        if (!isActive) return; // 页面隐藏时不发送
        
        const user = getCurrentUser();
        if (!user) return;
        
        // 更新最后活动时间
        lastActivity = Date.now();
        
        // 如果用户没变，继续使用
        if (currentUid !== user.uid || currentToken !== user.token) {
            currentUid = user.uid;
            currentToken = user.token;
        }
        
        try {
            const res = await fetch(`${LOBBY_URL}/api/friends/heartbeat/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    uid: currentUid,
                    session_token: currentToken
                }),
                credentials: 'include'
            });
            
            if (res.ok) {
                console.log(`[Heartbeat] 心跳已发送 - ${currentUid}`);
            } else if (res.status === 401) {
                // 令牌失效，清除登录状态
                console.log('[Heartbeat] 令牌失效，用户已退出登录');
                clearUserData();
                stopHeartbeat();
            }
        } catch (e) {
            console.log('[Heartbeat] 发送失败', e);
        }
    }
    
    async function stopHeartbeat() {
        const user = getCurrentUser();
        if (!user) return;
        
        try {
            // 使用 keepalive 确保请求能发送完成
            await fetch(`${LOBBY_URL}/api/friends/heartbeat/stop`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    uid: user.uid,
                    session_token: user.token
                }),
                credentials: 'include',
                keepalive: true
            });
            console.log(`[Heartbeat] 心跳已停止 - ${user.uid}`);
        } catch (e) {
            console.log('[Heartbeat] 停止失败', e);
        }
    }
    
    // ===== 无操作检测 =====
    function resetInactiveTimer() {
        // 更新最后活动时间
        lastActivity = Date.now();
        
        // 清除旧的定时器
        if (inactiveTimer) {
            clearTimeout(inactiveTimer);
        }
        
        // 设置新的定时器
        inactiveTimer = setTimeout(() => {
            const now = Date.now();
            if (now - lastActivity >= INACTIVE_TIMEOUT) {
                console.log('[Heartbeat] 用户2分钟无操作，标记离线');
                stopHeartbeat();
            }
        }, INACTIVE_TIMEOUT);
    }
    
    // ===== 监听用户操作 =====
    function setupActivityListeners() {
        const events = ['mousedown', 'mousemove', 'keydown', 'scroll', 'touchstart', 'click'];
        
        events.forEach(eventName => {
            document.addEventListener(eventName, () => {
                resetInactiveTimer();
                // 如果有心跳定时器且用户在线，立即发送心跳表示活跃
                if (heartbeatInterval && getCurrentUser()) {
                    sendHeartbeat();
                }
            }, { passive: true });
        });
    }
    
    // ===== 心跳定时器管理 =====
    function startHeartbeatInterval() {
        if (heartbeatInterval) {
            clearInterval(heartbeatInterval);
        }
        
        // 立即发送一次
        sendHeartbeat();
        resetInactiveTimer();
        
        // 定时发送
        heartbeatInterval = setInterval(() => {
            sendHeartbeat();
        }, HEARTBEAT_INTERVAL);
        
        console.log('[Heartbeat] 心跳定时器已启动');
    }
    
    function stopHeartbeatInterval() {
        if (heartbeatInterval) {
            clearInterval(heartbeatInterval);
            heartbeatInterval = null;
            console.log('[Heartbeat] 心跳定时器已停止');
        }
        
        if (inactiveTimer) {
            clearTimeout(inactiveTimer);
            inactiveTimer = null;
        }
    }
    
    // ===== 登录状态变化监听 =====
    function watchLoginStatus() {
        // 监听 localStorage 变化
        window.addEventListener('storage', (e) => {
            if (e.key === 'uid' || e.key === 'session_token' || e.key === 'user') {
                console.log('[Heartbeat] 登录状态变化', e.key, e.newValue);
                
                const newUser = getCurrentUser();
                
                if (newUser) {
                    // 用户登录了
                    console.log('[Heartbeat] 检测到用户登录');
                    currentUid = newUser.uid;
                    currentToken = newUser.token;
                    startHeartbeatInterval();
                } else {
                    // 用户登出了
                    console.log('[Heartbeat] 检测到用户登出');
                    stopHeartbeatInterval();
                }
            }
        });
        
        // 定期检查登录状态（防止某些情况下的状态不一致）
        setInterval(() => {
            const user = getCurrentUser();
            const hadUser = currentUid !== null;
            
            if (user && !hadUser) {
                // 之前没有用户，现在有了 - 登录
                console.log('[Heartbeat] 检测到用户登录（定期检查）');
                currentUid = user.uid;
                currentToken = user.token;
                startHeartbeatInterval();
            } else if (!user && hadUser) {
                // 之前有用户，现在没了 - 登出
                console.log('[Heartbeat] 检测到用户登出（定期检查）');
                currentUid = null;
                currentToken = null;
                stopHeartbeatInterval();
            }
        }, 5000); // 每5秒检查一次
    }
    
    // ===== 页面可见性处理 =====
    function setupVisibilityListener() {
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                console.log('[Heartbeat] 页面隐藏，暂停心跳');
                isActive = false;
                // 不清除定时器，只是暂停发送
            } else {
                console.log('[Heartbeat] 页面可见，恢复心跳');
                isActive = true;
                sendHeartbeat(); // 立即发送一次
                resetInactiveTimer(); // 重置无操作计时器
            }
        });
    }
    
    // ===== 页面关闭处理 =====
    function setupUnloadListeners() {
        window.addEventListener('beforeunload', () => {
            stopHeartbeat();
        });
        
        window.addEventListener('pagehide', () => {
            stopHeartbeat();
        });
    }
    
    // ===== 初始化 =====
    function initHeartbeat() {
        if (isInitialized) return;
        
        const user = getCurrentUser();
        if (!user) {
            console.log('[Heartbeat] 用户未登录，不启动心跳');
            // 仍然监听登录状态变化
            watchLoginStatus();
            return;
        }
        
        currentUid = user.uid;
        currentToken = user.token;
        
        // 启动心跳
        startHeartbeatInterval();
        
        // 设置各种监听器
        setupActivityListeners();
        setupVisibilityListener();
        setupUnloadListeners();
        watchLoginStatus();
        
        isInitialized = true;
        console.log('[Heartbeat] 初始化完成');
    }
    
    // ===== 导出全局接口 =====
    window.HeartbeatManager = {
        init: initHeartbeat,
        send: sendHeartbeat,
        stop: stopHeartbeat,
        getStatus: () => ({
            isActive,
            currentUid,
            hasInterval: heartbeatInterval !== null,
            isInitialized,
            lastActivity,
            inactiveRemaining: Math.max(0, INACTIVE_TIMEOUT - (Date.now() - lastActivity))
        }),
        forceActive: () => {
            // 手动标记用户活跃
            resetInactiveTimer();
            sendHeartbeat();
        }
    };
    
    // ===== 自动初始化 =====
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initHeartbeat);
    } else {
        initHeartbeat();
    }
})();