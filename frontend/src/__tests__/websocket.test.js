import webSocketService from '../services/websocket';

describe('webSocketService', () => {
  const originalWebSocket = global.WebSocket;
  let consoleErrorSpy;
  let consoleLogSpy;

  beforeEach(() => {
    webSocketService.disconnect({ resetSubscriptions: true });
    webSocketService.listeners = new Map();
    webSocketService.reconnectAttempts = 0;
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    consoleLogSpy = jest.spyOn(console, 'log').mockImplementation(() => {});
  });

  afterEach(() => {
    if (webSocketService.ws) {
      webSocketService.disconnect({ resetSubscriptions: true });
    }
    global.WebSocket = originalWebSocket;
    jest.useRealTimers();
    consoleErrorSpy.mockRestore();
    consoleLogSpy.mockRestore();
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
      nextRetryInMs: webSocketService.reconnectDelay,
    }));
    expect(webSocketService.getStatus()).toEqual(expect.objectContaining({
      reconnectAttempts: 1,
      lastErrorReason: 'network lost',
    }));

    removeListener();
  });
});
