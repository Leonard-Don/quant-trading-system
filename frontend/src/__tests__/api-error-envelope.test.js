const loadResponseErrorHandler = async () => {
  vi.resetModules();
  const { default: api } = await import('../services/api');
  const handler = api.interceptors.response.handlers.find(
    (entry) => typeof entry.rejected === 'function',
  );
  return handler.rejected;
};

const normalizeApiError = async (axiosError) => {
  const handleError = await loadResponseErrorHandler();
  try {
    await handleError(axiosError);
  } catch (error) {
    return error;
  }
  throw new Error('Expected response interceptor to reject');
};

describe('api response error envelope compatibility', () => {
  let consoleErrorSpy;

  beforeEach(() => {
    window.localStorage.clear();
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
    vi.resetModules();
  });

  test.each([401, 403, 429, 500, 502, 503])(
    'preserves structured backend error message and metadata for HTTP %s',
    async (status) => {
      const details = { field: 'risk_limit', status, retry_after_seconds: 30 };
      const backendMessage = `backend structured message for ${status}`;
      const backendError = {
        code: `APP_${status}`,
        message: backendMessage,
        details,
        request_id: `req-${status}`,
        timestamp: `2026-05-07T0${status % 10}:30:00Z`,
      };

      const error = await normalizeApiError({
        config: { url: `/example/${status}`, headers: {} },
        message: 'Request failed with status code',
        response: {
          status,
          data: {
            success: false,
            error: backendError,
          },
        },
      });

      expect(error.userMessage).toBe(backendMessage);
      expect(error.errorCode).toBe(backendError.code);
      expect(error.errorDetails).toBe(details);
      expect(error.requestId).toBe(backendError.request_id);
      expect(error.serverTimestamp).toBe(backendError.timestamp);
    },
  );

  test.each([
    [401, '请先登录'],
    [403, '没有权限访问'],
    [429, '请求过于频繁，请稍后再试'],
    [500, '服务器内部错误，请稍后重试'],
    [502, '服务暂时不可用，请稍后重试'],
    [503, '服务暂时不可用，请稍后重试'],
  ])('uses HTTP %s status fallback only when the structured message is missing', async (status, fallbackMessage) => {
    const details = { status, reason: 'missing message fixture' };

    const error = await normalizeApiError({
      config: { url: `/example/${status}`, headers: {} },
      message: 'Request failed with status code',
      response: {
        status,
        data: {
          success: false,
          error: {
            code: `APP_${status}`,
            details,
            request_id: `fallback-req-${status}`,
            timestamp: `2026-05-07T1${status % 10}:30:00Z`,
          },
        },
      },
    });

    expect(error.userMessage).toBe(fallbackMessage);
    expect(error.errorCode).toBe(`APP_${status}`);
    expect(error.errorDetails).toBe(details);
    expect(error.requestId).toBe(`fallback-req-${status}`);
    expect(error.serverTimestamp).toBe(`2026-05-07T1${status % 10}:30:00Z`);
  });

  test('preserves legacy string error response behavior', async () => {
    const error = await normalizeApiError({
      config: { url: '/legacy-string-error', headers: {} },
      message: 'Request failed with status code',
      response: {
        status: 400,
        data: 'legacy plain text failure',
      },
    });

    expect(error.userMessage).toBe('legacy plain text failure');
    expect(error.errorCode).toBe('UNKNOWN_ERROR');
    expect(error.errorDetails).toBeUndefined();
    expect(error.requestId).toBeUndefined();
    expect(error.serverTimestamp).toBeUndefined();
  });
});
