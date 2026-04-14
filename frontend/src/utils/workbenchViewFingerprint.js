const normalize = (value = '') => String(value || '').trim();

const buildCanonicalWorkbenchView = (context = {}) => ({
  source_view: normalize(context.source_view || 'workbench') || 'workbench',
  refresh: normalize(context.refresh || context.workbenchRefresh),
  type: normalize(context.type || context.workbenchType),
  source_filter: normalize(context.source_filter || context.workbenchSource),
  reason: normalize(context.reason || context.workbenchReason),
  snapshot_view: normalize(context.snapshot_view || context.workbenchSnapshotView),
  keyword: normalize(context.keyword || context.workbenchKeyword),
  task_id: normalize(context.task_id || context.task),
});

export const buildWorkbenchViewFingerprint = (context = {}) => {
  const canonical = buildCanonicalWorkbenchView(context);
  const hasSignal = Object.entries(canonical).some(([key, value]) => key !== 'source_view' && Boolean(value));

  if (!hasSignal) {
    return '';
  }

  const serialized = JSON.stringify(canonical);
  let hash = 2166136261;
  for (let index = 0; index < serialized.length; index += 1) {
    hash ^= serialized.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }

  return `wv_${(hash >>> 0).toString(36)}`;
};

export const extractWorkbenchViewFingerprint = (viewContext = {}) =>
  normalize(viewContext?.view_fingerprint || viewContext?.snapshot_fingerprint) || buildWorkbenchViewFingerprint(viewContext);

