import tradeWebSocketService from '../services/tradeWebsocket';

describe('tradeWebSocketService', () => {
  const originalWebSocket = global.WebSocket;
  let consoleErrorSpy;
  let mathRandomSpy;

  beforeEach(() => {
    tradeWebSocketService.disconnect();
    tradeWebSocketService.listeners = new Map();
    tradeWebSocketService.reconnectAttempts = 0;
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    mathRandomSpy = vi.spyOn(Math, 'random').mockReturnValue(0.5);
  });

  afterEach(() => {
    if (tradeWebSocketService.ws) {
      tradeWebSocketService.disconnect();
    }
    global.WebSocket = originalWebSocket;
    vi.useRealTimers();
    consoleErrorSpy.mockRestore();
    mathRandomSpy.mockRestore();
  });

  test('rejects the connect promise when the initial trade websocket connection closes before opening', async () => {
    let socketInstance = null;

    global.WebSocket = vi.fn().mockImplementation(() => {
      socketInstance = {
        readyState: 0,
        close: vi.fn(),
        send: vi.fn(),
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
    vi.useFakeTimers();

    global.WebSocket = vi.fn().mockImplementation(() => {
      socketInstance = {
        readyState: 0,
        close: vi.fn(),
        send: vi.fn(),
      };
      return socketInstance;
    });
    global.WebSocket.OPEN = 1;

    const connectPromise = tradeWebSocketService.connect();
    socketInstance.readyState = 1;
    socketInstance.onopen?.();
    await connectPromise;

    vi.advanceTimersByTime(tradeWebSocketService.heartbeatIntervalMs);
    expect(socketInstance.send).toHaveBeenCalledWith(JSON.stringify({ action: 'ping' }));

    const sendCountAfterHeartbeat = socketInstance.send.mock.calls.length;
    tradeWebSocketService.disconnect();
    vi.advanceTimersByTime(tradeWebSocketService.heartbeatIntervalMs * 2);

    expect(socketInstance.send).toHaveBeenCalledTimes(sendCountAfterHeartbeat);
  });

  test('emits reconnect metadata with exponential backoff after disconnect', async () => {
    let socketInstance = null;
    const connectionEvents = [];
    vi.useFakeTimers();

    global.WebSocket = vi.fn().mockImplementation(() => {
      socketInstance = {
        readyState: 0,
        close: vi.fn(),
        send: vi.fn(),
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
    vi.stubEnv('VITE_REALTIME_WS_TOKEN', 'secret-token');

    expect(tradeWebSocketService.getWebSocketUrl()).toContain('token=secret-token');

    vi.unstubAllEnvs();
  });
});
