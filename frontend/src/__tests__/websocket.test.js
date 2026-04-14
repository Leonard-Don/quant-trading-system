import webSocketService from '../services/websocket';

describe('webSocketService', () => {
  const originalWebSocket = global.WebSocket;
  let consoleErrorSpy;
  let consoleLogSpy;
  let consoleWarnSpy;
  let mathRandomSpy;

  beforeEach(() => {
    webSocketService.disconnect({ resetSubscriptions: true });
    webSocketService.listeners = new Map();
    webSocketService.reconnectAttempts = 0;
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    consoleLogSpy = jest.spyOn(console, 'log').mockImplementation(() => {});
    consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
    mathRandomSpy = jest.spyOn(Math, 'random').mockReturnValue(0.5);
  });

  afterEach(() => {
    if (webSocketService.ws) {
      webSocketService.disconnect({ resetSubscriptions: true });
    }
    global.WebSocket = originalWebSocket;
    jest.useRealTimers();
    consoleErrorSpy.mockRestore();
    consoleLogSpy.mockRestore();
    consoleWarnSpy.mockRestore();
    mathRandomSpy.mockRestore();
  });

  test('rejects the connect promise when the initial websocket connection closes before opening', async () => {
    let socketInstance = null;

    global.WebSocket = jest.fn().mockImplementation(() => {
      socketInstance = {
        readyState: 0,
        close: jest.fn(),
        send: jest.fn(),
      };
      return socketInstance;
    });
    global.WebSocket.OPEN = 1;

    const connectPromise = webSocketService.connect();

    socketInstance.onerror?.({ message: 'boom' });
    socketInstance.onclose?.({ code: 1006, reason: 'connect failed' });

    await expect(connectPromise).rejects.toThrow('WebSocket connection failed');
  });

  test('sends heartbeat ping frames while connected and stops after disconnect', async () => {
    let socketInstance = null;
    jest.useFakeTimers();

    global.WebSocket = jest.fn().mockImplementation(() => {
      socketInstance = {
        readyState: 0,
        close: jest.fn(),
        send: jest.fn(),
      };
      return socketInstance;
    });
    global.WebSocket.OPEN = 1;

    const connectPromise = webSocketService.connect();
    socketInstance.readyState = 1;
    socketInstance.onopen?.();
    await connectPromise;

    jest.advanceTimersByTime(webSocketService.heartbeatIntervalMs);
    expect(socketInstance.send).toHaveBeenCalledWith(JSON.stringify({ action: 'ping' }));

    const sendCountAfterHeartbeat = socketInstance.send.mock.calls.length;
    webSocketService.disconnect({ resetSubscriptions: true });
    jest.advanceTimersByTime(webSocketService.heartbeatIntervalMs * 2);

    expect(socketInstance.send).toHaveBeenCalledTimes(sendCountAfterHeartbeat);
  });

  test('emits reconnect metadata after an established connection drops', async () => {
    let socketInstance = null;
    const connectionEvents = [];
    jest.useFakeTimers();

    global.WebSocket = jest.fn().mockImplementation(() => {
      socketInstance = {
        readyState: 0,
        close: jest.fn(),
        send: jest.fn(),
      };
      return socketInstance;
    });
    global.WebSocket.OPEN = 1;

    const removeListener = webSocketService.addListener('connection', (payload) => {
      connectionEvents.push(payload);
    });

    const connectPromise = webSocketService.connect();
    socketInstance.readyState = 1;
    socketInstance.onopen?.();
    await connectPromise;

    socketInstance.onclose?.({ code: 1006, reason: 'network lost' });

    expect(connectionEvents).toContainEqual(expect.objectContaining({
      status: 'connected',
      reconnectAttempts: 0,
    }));
    expect(connectionEvents).toContainEqual(expect.objectContaining({
      status: 'reconnecting',
      reconnectAttempts: 1,
      lastError: 'network lost',
      nextRetryInMs: webSocketService.getReconnectDelay(1),
    }));
    expect(webSocketService.getStatus()).toEqual(expect.objectContaining({
      reconnectAttempts: 1,
      lastErrorReason: 'network lost',
    }));

    removeListener();
  });

  test('uses exponential backoff for later reconnect attempts', () => {
    expect(webSocketService.getReconnectDelay(1)).toBe(3000);
    expect(webSocketService.getReconnectDelay(2)).toBe(6000);
    expect(webSocketService.getReconnectDelay(3)).toBe(12000);
    expect(webSocketService.getReconnectDelay(4)).toBe(24000);
    expect(webSocketService.getReconnectDelay(5)).toBe(48000);
  });

  test('swallows reconnect promise rejections from timer-driven retries', async () => {
    let sockets = [];
    jest.useFakeTimers();

    global.WebSocket = jest.fn().mockImplementation(() => {
      const socketInstance = {
        readyState: 0,
        close: jest.fn(),
        send: jest.fn(),
      };
      sockets.push(socketInstance);
      return socketInstance;
    });
    global.WebSocket.OPEN = 1;

    const connectPromise = webSocketService.connect();
    sockets[0].readyState = 1;
    sockets[0].onopen?.();
    await connectPromise;

    sockets[0].onclose?.({ code: 1006, reason: 'network lost' });
    jest.advanceTimersByTime(webSocketService.getReconnectDelay(1));

    expect(sockets).toHaveLength(2);

    sockets[1].onerror?.({ message: 'retry failed' });
    sockets[1].onclose?.({ code: 1006, reason: 'retry failed' });

    await Promise.resolve();
    expect(consoleErrorSpy).toHaveBeenCalled();
  });

  test('fans out snapshot payloads to quote listeners', () => {
    const quoteEvents = [];
    const snapshotEvents = [];
    const removeQuoteListener = webSocketService.addListener('quote', (payload) => {
      quoteEvents.push(payload);
    });
    const removeSnapshotListener = webSocketService.addListener('snapshot', (payload) => {
      snapshotEvents.push(payload);
    });

    webSocketService.handleMessage({
      type: 'snapshot',
      origin: 'subscribe',
      timestamp: '2026-03-20T10:00:00',
      data: {
        AAPL: { symbol: 'AAPL', price: 188.2 },
        MSFT: { symbol: 'MSFT', price: 412.6 },
      },
    });

    expect(snapshotEvents).toHaveLength(1);
    expect(quoteEvents).toEqual([
      expect.objectContaining({ symbol: 'AAPL', data: expect.objectContaining({ price: 188.2 }) }),
      expect.objectContaining({ symbol: 'MSFT', data: expect.objectContaining({ price: 412.6 }) }),
    ]);

    removeQuoteListener();
    removeSnapshotListener();
  });

  test('requests websocket snapshots for the current symbols when connected', async () => {
    let socketInstance = null;

    global.WebSocket = jest.fn().mockImplementation(() => {
      socketInstance = {
        readyState: 0,
        close: jest.fn(),
        send: jest.fn(),
      };
      return socketInstance;
    });
    global.WebSocket.OPEN = 1;

    webSocketService.subscribe(['AAPL', 'MSFT']);

    const connectPromise = webSocketService.connect();
    socketInstance.readyState = 1;
    socketInstance.onopen?.();
    await connectPromise;

    socketInstance.send.mockClear();

    expect(webSocketService.requestSnapshot(['AAPL', 'MSFT'])).toBe(true);
    expect(socketInstance.send).toHaveBeenCalledWith(JSON.stringify({
      action: 'snapshot',
      symbols: ['AAPL', 'MSFT'],
    }));
  });

  test('can force-resend subscriptions after the socket is already connected', async () => {
    let socketInstance = null;

    global.WebSocket = jest.fn().mockImplementation(() => {
      socketInstance = {
        readyState: 0,
        close: jest.fn(),
        send: jest.fn(),
      };
      return socketInstance;
    });
    global.WebSocket.OPEN = 1;

    webSocketService.subscribe(['AAPL', 'MSFT']);

    const connectPromise = webSocketService.connect();
    socketInstance.readyState = 1;
    socketInstance.onopen?.();
    await connectPromise;

    socketInstance.send.mockClear();

    webSocketService.subscribe(['AAPL', 'MSFT'], { forceResend: true });

    expect(socketInstance.send).toHaveBeenCalledWith(JSON.stringify({
      action: 'subscribe',
      symbols: ['AAPL', 'MSFT'],
    }));
  });

  test('appends the realtime websocket token when configured', () => {
    process.env.REACT_APP_REALTIME_WS_TOKEN = 'secret-token';

    expect(webSocketService.getWebSocketUrl()).toContain('token=secret-token');

    delete process.env.REACT_APP_REALTIME_WS_TOKEN;
  });
});
