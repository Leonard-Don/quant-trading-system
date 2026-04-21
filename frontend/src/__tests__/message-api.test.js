import { getApiErrorMessage } from '../utils/messageApi';

describe('getApiErrorMessage', () => {
  test('formats FastAPI validation detail arrays into a readable string', () => {
    expect(getApiErrorMessage({
      userMessage: [
        { loc: ['body', 'symbol'], msg: 'Field required' },
        { loc: ['body', 'strategy'], msg: 'Field required' },
      ],
    })).toBe('body.symbol: Field required；body.strategy: Field required');
  });

  test('falls back to nested message objects before using the default fallback', () => {
    expect(getApiErrorMessage({
      userMessage: { message: '保存失败' },
    })).toBe('保存失败');

    expect(getApiErrorMessage(null, '默认错误')).toBe('默认错误');
  });
});
