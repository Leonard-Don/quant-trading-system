import { useMemo } from 'react';
import { App as AntdApp } from 'antd';

const noop = () => undefined;

export const getApiErrorMessage = (error, fallback = '请求失败，请稍后重试') => {
  if (!error) return fallback;
  return error.userMessage || error.message || fallback;
};

export const useSafeMessageApi = () => {
  const appContext = AntdApp.useApp();
  const appMessage = appContext?.message;

  return useMemo(() => ({
    success: (...args) => appMessage?.success?.(...args) ?? noop(),
    error: (...args) => appMessage?.error?.(...args) ?? noop(),
    warning: (...args) => appMessage?.warning?.(...args) ?? noop(),
    info: (...args) => appMessage?.info?.(...args) ?? noop(),
    loading: (...args) => appMessage?.loading?.(...args) ?? noop(),
    open: (...args) => appMessage?.open?.(...args) ?? noop(),
    destroy: (...args) => appMessage?.destroy?.(...args) ?? noop(),
  }), [appMessage]);
};
