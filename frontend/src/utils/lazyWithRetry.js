import { lazy } from 'react';

const DEFAULT_RETRY_COUNT = 2;
const DEFAULT_RETRY_DELAY_MS = 350;

export const isRecoverableLazyLoadError = (error) => {
  const message = String(error?.message || error || '');
  return (
    message.includes('Load failed')
    || message.includes('ChunkLoadError')
    || message.includes('Loading chunk')
    || message.includes('dynamically imported module')
    || message.includes('Importing a module script failed')
  );
};

const wait = (delayMs) => new Promise((resolve) => {
  const schedule = typeof window !== 'undefined' ? window.setTimeout : setTimeout;
  schedule(resolve, delayMs);
});

export const importWithRetry = async (
  importer,
  {
    retries = DEFAULT_RETRY_COUNT,
    retryDelayMs = DEFAULT_RETRY_DELAY_MS,
  } = {},
) => {
  let lastError = null;

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      return await importer();
    } catch (error) {
      lastError = error;
      if (!isRecoverableLazyLoadError(error) || attempt >= retries) {
        throw error;
      }
      await wait(retryDelayMs * (attempt + 1));
    }
  }

  throw lastError;
};

const lazyWithRetry = (importer, options) => lazy(() => importWithRetry(importer, options));

export default lazyWithRetry;
