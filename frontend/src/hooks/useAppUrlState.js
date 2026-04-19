import { useEffect, useState } from 'react';

import {
  getAppUrlSnapshot,
  subscribeToAppUrlChanges,
} from '../utils/appUrlState';

export const useAppUrlState = () => {
  const [snapshot, setSnapshot] = useState(() => getAppUrlSnapshot());

  useEffect(() => subscribeToAppUrlChanges(() => {
    setSnapshot(getAppUrlSnapshot());
  }), []);

  return snapshot;
};
