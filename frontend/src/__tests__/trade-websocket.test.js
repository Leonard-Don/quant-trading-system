import tradeWebSocketService from '../services/tradeWebsocket';

describe('tradeWebSocketService', () => {
  const originalWebSocket = global.WebSocket;
  let consoleErrorSpy;
  let mathRandomSpy;

  beforeEach(() => {
    tradeWebSocketService.disconnect();
    tradeWebSocketService.listeners = new Map();
    tradeWebSocketService.reconnectAttempts = 0;
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    mathRandomSpy = jest.spyOn(Math, 'random').mockReturnValue(0.5);
  });

  afterEach(() => {
    if (tradeWebSocketService.ws) {
      tradeWebSocketService.disconnect();
    }
    global.WebSocket = originalWebSocket;
    jest.useRealTimers();
    consoleErrorSpy.mockRestore();
    mathRandomSpy.mockRestore();
  });

  test('rejects the connect promise when the initial trade websocket connection closes before opening', async () => {
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

    const connectPromise = tradeWebSocketService.connect();

    socketInstance.onerror?.({ message: 'boom' });
    socketInstance.onclose?.({ code: 1006, reason: 'connect failed' });

    await expect(connectPromise).rejects.toThrow('Trade WebSocket connection failed');
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

    const connectPromise = tradeWebSocketService.connect();
    socketInstance.readyState = 1;
    socketInstance.onopen?.();
    await connectPromise;

    jest.advanceTimersByTime(tradeWebSocketService.heartbeatIntervalMs);
    expect(socketInstance.send).toHaveBeenCalledWith(JSON.stringify({ action: 'ping' }));

    const sendCountAfterHeartbeat = socketInstance.send.mock.calls.length;
    tradeWebSocketService.disconnect();
    jest.advanceTimersByTime(tradeWebSocketService.heartbeatIntervalMs * 2);

    expect(socketInstance.send).toHaveBeenCalledTimes(sendCountAfterHeartbeat);
  });

  test('emits reconnect metadata with exponential backoff after disconnect', async () => {
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

    const removeListener = tradeWebSocketService.addListener('connection', (payload) => {
      connectionEvents.push(payload);
    });

    const connectPromise = tradeWebSocketService.connect();
    socketInstance.readyState = 1;
    socketInstance.onopen?.();
    await connectPromise;

    socketInstance.onclose?.({ code: 1006, reason: 'trade network lost' });

    expect(connectionEvents).toContainEqual(expect.objectContaining({
      status: 'connected',
    }));
    expect(connectionEvents).toContainEqual(expect.objectContaining({
      status: 'reconnecting',
      reconnectAttempts: 1,
      lastError: 'trade network lost',
      nextRetryInMs: tradeWebSocketService.getReconnectDelay(1),
    }));
    expect(tradeWebSocketService.getStatus()).toEqual(expect.objectContaining({
      reconnectAttempts: 1,
      lastErrorReason: 'trade network lost',
    }));

    removeListener();
  });

  test('uses exponential backoff for later trade reconnect attempts', () => {
    expect(tradeWebSocketService.getReconnectDelay(1)).toBe(2000);
    expect(tradeWebSocketService.getReconnectDelay(2)).toBe(4000);
    expect(tradeWebSocketService.getReconnectDelay(3)).toBe(8000);
    expect(tradeWebSocketService.getReconnectDelay(4)).toBe(16000);
  });

  test('appends the realtime websocket token for trade streams when configured', () => {
    process.env.REACT_APP_REALTIME_WS_TOKEN = 'secret-token';

    expect(tradeWebSocketService.getWebSocketUrl()).toContain('token=secret-token');

    delete process.env.REACT_APP_REALTIME_WS_TOKEN;
  });
});
