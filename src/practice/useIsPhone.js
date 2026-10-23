import { useSyncExternalStore } from 'react';

// 手机竖屏：iPad 竖屏最窄 744px，不会落进来
const PHONE_QUERY = '(max-width: 639px)';

const subscribe = (cb) => {
  const mql = window.matchMedia(PHONE_QUERY);
  mql.addEventListener('change', cb);
  return () => mql.removeEventListener('change', cb);
};

const getSnapshot = () => window.matchMedia(PHONE_QUERY).matches;

export const useIsPhone = () => useSyncExternalStore(subscribe, getSnapshot, () => false);
