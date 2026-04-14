/**
 * WebSocket实时数据服务
 * 用于获取实时股票报价推送
 */

class WebSocketService {
    constructor() {
        this.ws = null;
        this.connectPromise = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = Infinity;
        this.reconnectDelay = 3000;
        this.maxReconnectDelay = 60000;
        this.reconnectJitterRatio = 0.2;
        this.reconnectTimer = null;
        this.heartbeatIntervalMs = 15000;
        this.heartbeatTimer = null;
        this.listeners = new Map();
        this.subscriptions = new Set();
        this.isConnected = false;
        this.manuallyDisconnected = false;
        this.lastErrorReason = null;
    }

    startHeartbeat() {
        this.stopHeartbeat();
        this.heartbeatTimer = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.sendMessage({ action: 'ping' });
            }
        }, this.heartbeatIntervalMs);
    }

    stopHeartbeat() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
    }

    scheduleReconnect(nextRetryInMs) {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
        }

        this.reconnectTimer = setTimeout(() => {
            this.connect().catch((error) => {
                console.warn('WebSocket reconnect failed:', error);
            });
        }, nextRetryInMs);
    }

    getReconnectDelay(attempt = this.reconnectAttempts) {
        const safeAttempt = Math.max(1, attempt);
        const exponentialDelay = Math.min(
            this.reconnectDelay * (2 ** (safeAttempt - 1)),
            this.maxReconnectDelay,
        );
        const jitterWindow = Math.round(exponentialDelay * this.reconnectJitterRatio);
        const jitterOffset = jitterWindow > 0
            ? Math.round((Math.random() * jitterWindow * 2) - jitterWindow)
            : 0;

        return Math.max(this.reconnectDelay, exponentialDelay + jitterOffset);
    }

    /**
     * 获取WebSocket URL
     */
    getWebSocketUrl() {
        const apiUrl = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000';
        const url = new URL(apiUrl.replace(/^http/, 'ws') + '/ws/quotes');
        const token = process.env.REACT_APP_REALTIME_WS_TOKEN;
        if (token) {
            url.searchParams.set('token', token);
        }
        return url.toString();
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
                let settled = false;

                const rejectIfPending = (error) => {
                    if (settled) {
                        return;
                    }
                    settled = true;
                    this.connectPromise = null;
                    reject(error);
                };

                const resolveIfPending = () => {
                    if (settled) {
                        return;
                    }
                    settled = true;
                    this.connectPromise = null;
                    resolve();
                };

                this.ws.onopen = () => {
                    if (this.ws !== socket) {
                        return;
                    }
                    console.log('WebSocket connected');
                    const recovered = this.reconnectAttempts > 0 || Boolean(this.lastErrorReason);
                    this.isConnected = true;
                    this.reconnectAttempts = 0;
                    this.lastErrorReason = null;
                    this.startHeartbeat();
                    if (this.reconnectTimer) {
                        clearTimeout(this.reconnectTimer);
                        this.reconnectTimer = null;
                    }

                    // 重新订阅之前的股票
                    if (this.subscriptions.size > 0) {
                        this.sendMessage({ action: 'subscribe', symbols: Array.from(this.subscriptions) });
                    }

                    this.notifyListeners('connection', {
                        status: 'connected',
                        reconnectAttempts: 0,
                        recovered,
                        lastError: null,
                    });
                    resolveIfPending();
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
                    const reason = error?.message || 'WebSocket connection failed';
                    this.lastErrorReason = reason;
                    this.notifyListeners('error', { error, reason });
                    if (!this.isConnected) {
                        rejectIfPending(new Error('WebSocket connection failed'));
                    }
                };

                this.ws.onclose = (event) => {
                    if (this.ws !== socket) {
                        return;
                    }
                    console.log('WebSocket closed:', event.code, event.reason);
                    const wasConnected = this.isConnected;
                    const closeReason = event?.reason || (event?.code ? `WebSocket closed (${event.code})` : 'WebSocket closed');
                    this.isConnected = false;
                    this.connectPromise = null;
                    this.stopHeartbeat();
                    this.ws = null;
                    this.lastErrorReason = this.lastErrorReason || closeReason;

                    if (!wasConnected && !this.manuallyDisconnected) {
                        const reasonSuffix = event?.reason ? `: ${event.reason}` : '';
                        rejectIfPending(new Error(`WebSocket connection failed${reasonSuffix}`));
                    }

                    // 尝试重连
                    if (!this.manuallyDisconnected && this.reconnectAttempts < this.maxReconnectAttempts) {
                        this.reconnectAttempts++;
                        const nextRetryInMs = this.getReconnectDelay(this.reconnectAttempts);
                        console.log(`Reconnecting... attempt ${this.reconnectAttempts}`);
                        this.notifyListeners('connection', {
                            status: 'reconnecting',
                            reconnectAttempts: this.reconnectAttempts,
                            lastError: this.lastErrorReason,
                            nextRetryInMs,
                        });
                        this.scheduleReconnect(nextRetryInMs);
                    } else {
                        this.notifyListeners('connection', {
                            status: 'disconnected',
                            reconnectAttempts: this.reconnectAttempts,
                            lastError: this.lastErrorReason,
                        });
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
    disconnect(options = {}) {
        const { resetSubscriptions = false } = options;
        this.manuallyDisconnected = true;
        this.connectPromise = null;
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        this.stopHeartbeat();
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.isConnected = false;
        this.lastErrorReason = null;

        if (resetSubscriptions) {
            this.subscriptions.clear();
        }
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
    subscribe(symbols, options = {}) {
        const { forceResend = false } = options;
        if (!Array.isArray(symbols)) {
            symbols = [symbols];
        }
        const normalizedSymbols = symbols
            .map(s => String(s).trim().toUpperCase())
            .filter(Boolean);
        const uniqueSymbols = Array.from(new Set(normalizedSymbols));
        const newSymbols = uniqueSymbols
            .filter(symbol => !this.subscriptions.has(symbol));

        newSymbols.forEach(symbol => this.subscriptions.add(symbol));

        if (this.isConnected) {
            const payloadSymbols = forceResend ? uniqueSymbols : newSymbols;
            if (payloadSymbols.length > 0) {
                this.sendMessage({ action: 'subscribe', symbols: payloadSymbols });
            }
        }

        return newSymbols;
    }

    requestSnapshot(symbols = Array.from(this.subscriptions)) {
        const normalizedSymbols = (Array.isArray(symbols) ? symbols : [symbols])
            .filter(Boolean)
            .map(symbol => String(symbol).trim().toUpperCase());

        if (!this.isConnected || normalizedSymbols.length === 0) {
            return false;
        }

        this.sendMessage({ action: 'snapshot', symbols: normalizedSymbols });
        return true;
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
            case 'snapshot':
                this.notifyListeners('snapshot', data);
                Object.entries(data.data || {}).forEach(([symbol, quote]) => {
                    const quoteEvent = {
                        type: 'quote',
                        symbol,
                        data: quote,
                        timestamp: data.timestamp,
                        origin: data.origin || 'snapshot',
                    };
                    this.notifyListeners('quote', quoteEvent);
                    this.notifyListeners(`quote:${symbol}`, quoteEvent);
                });
                break;
            case 'pong':
                // 心跳响应
                break;
            case 'error':
                console.error('WebSocket error message:', data.message);
                this.lastErrorReason = data.message || this.lastErrorReason;
                this.notifyListeners('error', { ...data, reason: data.message || this.lastErrorReason });
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
     * 手动重连 — 重置退避计数器后立即尝试连接
     */
    manualReconnect() {
        this.disconnect();
        this.manuallyDisconnected = false;
        this.reconnectAttempts = 0;
        this.lastErrorReason = null;
        return this.connect();
    }

    /**
     * 获取连接状态
     */
    getStatus() {
        return {
            isConnected: this.isConnected,
            subscriptions: Array.from(this.subscriptions),
            reconnectAttempts: this.reconnectAttempts,
            lastErrorReason: this.lastErrorReason
        };
    }
}

// 创建单例实例
const webSocketService = new WebSocketService();

export default webSocketService;
