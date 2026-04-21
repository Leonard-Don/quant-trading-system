import { useMemo } from 'react';
import { App as AntdApp } from 'antd';

const noop = () => undefined;

const normalizeErrorMessage = (value) => {
  if (typeof value === 'string') {
    return value.trim();
  }

  if (Array.isArray(value)) {
    return value
      .map((item) => normalizeErrorMessage(item))
      .filter(Boolean)
      .join('；');
  }

  if (value && typeof value === 'object') {
    if (typeof value.message === 'string' && value.message.trim()) {
      return value.message.trim();
    }
    if (typeof value.msg === 'string' && value.msg.trim()) {
      const location = Array.isArray(value.loc)
        ? value.loc.filter(Boolean).join('.')
        : '';
      return location ? `${location}: ${value.msg.trim()}` : value.msg.trim();
    }

    try {
      return JSON.stringify(value);
    } catch (error) {
      return String(value);
    }
  }

  return '';
};

export const getApiErrorMessage = (error, fallback = '请求失败，请稍后重试') => {
  if (!error) return fallback;
  return normalizeErrorMessage(error.userMessage) || normalizeErrorMessage(error.message) || fallback;
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
