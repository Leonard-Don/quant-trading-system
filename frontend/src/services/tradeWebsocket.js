class TradeWebSocketService {
  constructor() {
    this.ws = null;
    this.connectPromise = null;
    this.listeners = new Map();
    this.isConnected = false;
    this.manuallyDisconnected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 3;
    this.reconnectDelay = 2000;
    this.reconnectTimer = null;
    this.heartbeatIntervalMs = 15000;
    this.heartbeatTimer = null;
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

  getWebSocketUrl() {
    const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000';
    return apiUrl.replace(/^http/, 'ws') + '/ws/trades';
  }

  connect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return Promise.resolve();
    }

    if (this.ws && this.ws.readyState === WebSocket.CONNECTING && this.connectPromise) {
      return this.connectPromise;
    }

    this.manuallyDisconnected = false;
    this.connectPromise = new Promise((resolve, reject) => {
      try {
        const socket = new WebSocket(this.getWebSocketUrl());
        this.ws = socket;
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

        socket.onopen = () => {
          if (this.ws !== socket) {
            return;
          }

          this.isConnected = true;
          this.reconnectAttempts = 0;
          this.startHeartbeat();
          if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
          }
          this.notifyListeners('connection', { status: 'connected' });
          resolveIfPending();
        };

        socket.onmessage = (event) => {
          if (this.ws !== socket) {
            return;
          }

          try {
            const payload = JSON.parse(event.data);
            this.handleMessage(payload);
          } catch (error) {
            this.notifyListeners('error', { error });
          }
        };

        socket.onerror = (error) => {
          if (this.ws !== socket) {
            return;
          }

          this.notifyListeners('error', { error });
          if (!this.isConnected) {
            rejectIfPending(new Error('Trade WebSocket connection failed'));
          }
        };

        socket.onclose = (event) => {
          if (this.ws !== socket) {
            return;
          }

          const wasConnected = this.isConnected;
          this.ws = null;
          this.isConnected = false;
          this.connectPromise = null;
          this.stopHeartbeat();
          this.notifyListeners('connection', { status: 'disconnected' });

          if (!wasConnected && !this.manuallyDisconnected) {
            const closeReason = event?.reason ? `: ${event.reason}` : '';
            rejectIfPending(new Error(`Trade WebSocket connection failed${closeReason}`));
          }

          if (!this.manuallyDisconnected && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts += 1;
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

  disconnect() {
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
  }

  sendMessage(message) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  handleMessage(message) {
    if (message?.type) {
      this.notifyListeners(message.type, message);
    }

    if (message?.type === 'error') {
      this.notifyListeners('error', message);
    }
  }

  addListener(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }

    this.listeners.get(event).add(callback);
    return () => this.removeListener(event, callback);
  }

  removeListener(event, callback) {
    if (this.listeners.has(event)) {
      this.listeners.get(event).delete(callback);
    }
  }

  notifyListeners(event, payload) {
    if (!this.listeners.has(event)) {
      return;
    }

    this.listeners.get(event).forEach((listener) => {
      try {
        listener(payload);
      } catch (error) {
        console.error('Trade WebSocket listener error:', error);
      }
    });
  }

  getStatus() {
    return {
      isConnected: this.isConnected,
      reconnectAttempts: this.reconnectAttempts,
    };
  }
}

const tradeWebSocketService = new TradeWebSocketService();

export default tradeWebSocketService;
