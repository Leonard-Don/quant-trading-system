/**
 * WebSocket实时数据服务
 * 用于获取实时股票报价推送
 */

class WebSocketService {
    constructor() {
        this.ws = null;
        this.connectPromise = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000;
        this.reconnectTimer = null;
        this.listeners = new Map();
        this.subscriptions = new Set();
        this.isConnected = false;
        this.manuallyDisconnected = false;
    }

    /**
     * 获取WebSocket URL
     */
    getWebSocketUrl() {
        const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000';
        // 将 http/https 替换为 ws/wss
        return apiUrl.replace(/^http/, 'ws') + '/ws/quotes';
    }

    /**
     * 连接WebSocket
     */
    connect() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            console.log('WebSocket already connected');
            return Promise.resolve();
        }

        if (this.ws && this.ws.readyState === WebSocket.CONNECTING && this.connectPromise) {
            return this.connectPromise;
        }

        this.manuallyDisconnected = false;
        this.connectPromise = new Promise((resolve, reject) => {
            try {
                const url = this.getWebSocketUrl();
                console.log('Connecting to WebSocket:', url);
                this.ws = new WebSocket(url);
                const socket = this.ws;

                this.ws.onopen = () => {
                    if (this.ws !== socket) {
                        return;
                    }
                    console.log('WebSocket connected');
                    this.isConnected = true;
                    this.reconnectAttempts = 0;
                    if (this.reconnectTimer) {
                        clearTimeout(this.reconnectTimer);
                        this.reconnectTimer = null;
                    }

                    // 重新订阅之前的股票
                    if (this.subscriptions.size > 0) {
                        this.sendMessage({ action: 'subscribe', symbols: Array.from(this.subscriptions) });
                    }

                    this.notifyListeners('connection', { status: 'connected' });
                    this.connectPromise = null;
                    resolve();
                };

                this.ws.onmessage = (event) => {
                    if (this.ws !== socket) {
                        return;
                    }
                    try {
                        const data = JSON.parse(event.data);
                        this.handleMessage(data);
                    } catch (e) {
                        console.error('Failed to parse WebSocket message:', e);
                    }
                };

                this.ws.onerror = (error) => {
                    if (this.ws !== socket) {
                        return;
                    }
                    console.error('WebSocket error:', error);
                    this.notifyListeners('error', { error });
                };

                this.ws.onclose = (event) => {
                    if (this.ws !== socket) {
                        return;
                    }
                    console.log('WebSocket closed:', event.code, event.reason);
                    this.isConnected = false;
                    this.connectPromise = null;
                    this.ws = null;
                    this.notifyListeners('connection', { status: 'disconnected' });

                    // 尝试重连
                    if (!this.manuallyDisconnected && this.reconnectAttempts < this.maxReconnectAttempts) {
                        this.reconnectAttempts++;
                        console.log(`Reconnecting... attempt ${this.reconnectAttempts}`);
                        this.reconnectTimer = setTimeout(() => this.connect(), this.reconnectDelay);
                    }
                };

            } catch (error) {
                this.connectPromise = null;
                reject(error);
            }
        });
        return this.connectPromise;
    }

    /**
     * 断开连接
     */
    disconnect() {
        this.manuallyDisconnected = true;
        this.connectPromise = null;
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.isConnected = false;
    }

    /**
     * 发送消息
     */
    sendMessage(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        }
    }

    /**
     * 订阅股票报价
     */
    subscribe(symbols) {
        if (!Array.isArray(symbols)) {
            symbols = [symbols];
        }
        const newSymbols = symbols
            .map(s => s.toUpperCase())
            .filter(symbol => !this.subscriptions.has(symbol));

        newSymbols.forEach(symbol => this.subscriptions.add(symbol));

        if (newSymbols.length > 0 && this.isConnected) {
            this.sendMessage({ action: 'subscribe', symbols: newSymbols });
        }

        return newSymbols;
    }

    /**
     * 取消订阅
     */
    unsubscribe(symbols) {
        if (!Array.isArray(symbols)) {
            symbols = [symbols];
        }
        const removedSymbols = symbols
            .map(s => s.toUpperCase())
            .filter(symbol => this.subscriptions.has(symbol));

        removedSymbols.forEach(symbol => this.subscriptions.delete(symbol));

        if (removedSymbols.length > 0 && this.isConnected) {
            this.sendMessage({ action: 'unsubscribe', symbols: removedSymbols });
        }

        return removedSymbols;
    }

    /**
     * 处理接收到的消息
     */
    handleMessage(data) {
        switch (data.type) {
            case 'connected':
                console.log('Server confirmed connection');
                break;
            case 'subscription':
                console.log(`${data.action}:`, data.symbol);
                break;
            case 'quote':
            case 'price_update':
                this.notifyListeners('quote', data);
                this.notifyListeners(`quote:${data.symbol}`, data);
                break;
            case 'pong':
                // 心跳响应
                break;
            case 'error':
                console.error('WebSocket error message:', data.message);
                this.notifyListeners('error', data);
                break;
            default:
                console.log('Unknown message type:', data.type);
        }

        if (data.type === 'subscription') {
            this.notifyListeners('subscription', data);
        }
    }

    /**
     * 添加事件监听器
     * @param {string} event - 事件类型: 'quote', 'connection', 'error', 'subscription'
     * @param {Function} callback - 回调函数
     */
    addListener(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, new Set());
        }
        this.listeners.get(event).add(callback);

        return () => this.removeListener(event, callback);
    }

    /**
     * 移除事件监听器
     */
    removeListener(event, callback) {
        if (this.listeners.has(event)) {
            this.listeners.get(event).delete(callback);
        }
    }

    /**
     * 通知所有监听器
     */
    notifyListeners(event, data) {
        if (this.listeners.has(event)) {
            this.listeners.get(event).forEach(callback => {
                try {
                    callback(data);
                } catch (e) {
                    console.error('Listener error:', e);
                }
            });
        }
    }

    /**
     * 发送心跳
     */
    ping() {
        this.sendMessage({ action: 'ping' });
    }

    /**
     * 获取连接状态
     */
    getStatus() {
        return {
            isConnected: this.isConnected,
            subscriptions: Array.from(this.subscriptions),
            reconnectAttempts: this.reconnectAttempts
        };
    }
}

// 创建单例实例
const webSocketService = new WebSocketService();

export default webSocketService;
