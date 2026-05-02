const APP_URL_CHANGE_EVENT = 'quant-research:urlchange';

const SERVER_SNAPSHOT = Object.freeze({
  href: '',
  pathname: '',
  search: '',
  hash: '',
  revision: 0,
});

let cachedSnapshot = SERVER_SNAPSHOT;
let urlRevision = 0;

export const getCurrentAppUrl = () => {
  if (typeof window === 'undefined') {
    return '';
  }

  return `${window.location.pathname}${window.location.search}${window.location.hash || ''}`;
};

const refreshSnapshot = ({ forceRevision = false } = {}) => {
  if (typeof window === 'undefined') {
    return SERVER_SNAPSHOT;
  }

  const href = getCurrentAppUrl();
  const { pathname, search, hash } = window.location;
  const locationChanged = cachedSnapshot.href !== href;

  if (locationChanged || forceRevision) {
    urlRevision += 1;
  }

  if (
    locationChanged
    || forceRevision
    || cachedSnapshot.pathname !== pathname
    || cachedSnapshot.search !== search
    || cachedSnapshot.hash !== hash
  ) {
    cachedSnapshot = {
      href,
      pathname,
      search,
      hash,
      revision: urlRevision,
    };
  }

  return cachedSnapshot;
};

const notifyUrlChange = ({ forceRevision = false } = {}) => {
  if (typeof window === 'undefined') {
    return;
  }

  refreshSnapshot({ forceRevision });
  window.dispatchEvent(new CustomEvent(APP_URL_CHANGE_EVENT, { detail: { forceRevision } }));
  window.dispatchEvent(new PopStateEvent('popstate'));
};

export const subscribeToAppUrlChanges = (onStoreChange) => {
  if (typeof window === 'undefined') {
    return () => {};
  }

  const handleUrlChange = (event) => {
    refreshSnapshot({ forceRevision: Boolean(event?.detail?.forceRevision) });
    onStoreChange();
  };

  const handlePopState = () => {
    refreshSnapshot();
    onStoreChange();
  };

  window.addEventListener(APP_URL_CHANGE_EVENT, handleUrlChange);
  window.addEventListener('popstate', handlePopState);

  return () => {
    window.removeEventListener(APP_URL_CHANGE_EVENT, handleUrlChange);
    window.removeEventListener('popstate', handlePopState);
  };
};

export const getAppUrlSnapshot = () => refreshSnapshot();

export const getServerAppUrlSnapshot = () => SERVER_SNAPSHOT;

export const pushAppUrl = (url, { notifyOnUnchanged = true } = {}) => {
  if (typeof window === 'undefined') {
    return;
  }

  const currentUrl = getCurrentAppUrl();
  if (url !== currentUrl) {
    window.history.pushState(null, '', url);
    notifyUrlChange();
    return;
  }

  if (notifyOnUnchanged) {
    notifyUrlChange({ forceRevision: true });
  }
};

export const replaceAppUrl = (url, { notifyOnUnchanged = false } = {}) => {
  if (typeof window === 'undefined') {
    return;
  }

  const currentUrl = getCurrentAppUrl();
  if (url !== currentUrl) {
    window.history.replaceState(null, '', url);
    notifyUrlChange();
    return;
  }

  if (notifyOnUnchanged) {
    notifyUrlChange({ forceRevision: true });
  }
};
