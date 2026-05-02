import { importWithRetry, isRecoverableLazyLoadError } from '../utils/lazyWithRetry';

describe('lazyWithRetry', () => {
  test('recognizes Safari and chunk-load transient failures', () => {
    expect(isRecoverableLazyLoadError(new TypeError('Load failed'))).toBe(true);
    expect(isRecoverableLazyLoadError(new Error('Loading chunk 12 failed'))).toBe(true);
    expect(isRecoverableLazyLoadError(new Error('Importing a module script failed'))).toBe(true);
    expect(isRecoverableLazyLoadError(new Error('business logic failed'))).toBe(false);
  });

  test('retries recoverable lazy import failures before resolving', async () => {
    const module = { default: () => null };
    const importer = jest.fn()
      .mockRejectedValueOnce(new TypeError('Load failed'))
      .mockResolvedValueOnce(module);

    await expect(importWithRetry(importer, { retries: 1, retryDelayMs: 0 })).resolves.toBe(module);
    expect(importer).toHaveBeenCalledTimes(2);
  });

  test('does not retry non-recoverable lazy import failures', async () => {
    const importer = jest.fn()
      .mockRejectedValueOnce(new Error('business logic failed'));

    await expect(importWithRetry(importer, { retries: 2, retryDelayMs: 0 })).rejects.toThrow('business logic failed');
    expect(importer).toHaveBeenCalledTimes(1);
  });
});
