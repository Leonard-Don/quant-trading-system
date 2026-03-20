import tradeWebSocketService from '../services/tradeWebsocket';

describe('tradeWebSocketService', () => {
  const originalWebSocket = global.WebSocket;
  let consoleErrorSpy;

  beforeEach(() => {
    tradeWebSocketService.disconnect();
    tradeWebSocketService.listeners = new Map();
    tradeWebSocketService.reconnectAttempts = 0;
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    if (tradeWebSocketService.ws) {
      tradeWebSocketService.disconnect();
    }
    global.WebSocket = originalWebSocket;
    jest.useRealTimers();
    consoleErrorSpy.mockRestore();
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
});
