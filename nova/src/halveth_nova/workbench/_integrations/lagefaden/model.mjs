// SPDX-License-Identifier: MIT
// Offline review of DECLARED message provenance. No sensor or identity authentication.
const findings = new Set(['possible_object', 'alternative_explanation', 'unresolved']);
const exact = (value, fields) => value && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).length === fields.length
  && fields.every(field => Object.hasOwn(value, field));
const fail = code => { throw new Error(code); };
const label = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,48}$/.test(value);
const timestamp = value => typeof value === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(value)
  && Number.isFinite(Date.parse(value));

export function evaluatePacket(packet) {
  if (!exact(packet, ['caseId', 'referenceTime', 'freshnessMinutes', 'reports'])) fail('INVALID_PACKET');
  if (!label(packet.caseId) || !timestamp(packet.referenceTime)) fail('INVALID_HEADER');
  if (!Number.isInteger(packet.freshnessMinutes) || packet.freshnessMinutes < 1 || packet.freshnessMinutes > 1440) fail('INVALID_WINDOW');
  if (!Array.isArray(packet.reports) || packet.reports.length < 1 || packet.reports.length > 64) fail('INVALID_REPORT_COUNT');
  const now = Date.parse(packet.referenceTime);
  const byId = new Map();
  for (const report of packet.reports) {
    if (!exact(report, ['id', 'originId', 'parentId', 'observedAt', 'receivedAt', 'finding'])) fail('INVALID_REPORT');
    if (!label(report.id) || !label(report.originId) || byId.has(report.id)) fail('INVALID_OR_DUPLICATE_ID');
    if (report.parentId !== null && !label(report.parentId)) fail('INVALID_PARENT_ID');
    if (report.observedAt !== null && !timestamp(report.observedAt)) fail('INVALID_OBSERVATION_TIME');
    if (!timestamp(report.receivedAt)) fail('INVALID_RECEIPT_TIME');
    if (!findings.has(report.finding)) fail('INVALID_FINDING');
    const received = Date.parse(report.receivedAt);
    if (received > now || (report.observedAt !== null && Date.parse(report.observedAt) > received)) fail('INCONSISTENT_TIME');
    byId.set(report.id, report);
  }
  // Check graph shape first, so a cycle cannot masquerade as a time error.
  for (const report of packet.reports) {
    const seen = new Set();
    let cursor = report;
    while (cursor) {
      if (seen.has(cursor.id)) fail('COPY_CYCLE');
      seen.add(cursor.id);
      if (cursor.parentId === null) break;
      cursor = byId.get(cursor.parentId);
      if (!cursor) fail('MISSING_PARENT');
    }
  }
  const roots = new Map();
  function rootOf(report) {
    if (roots.has(report.id)) return roots.get(report.id);
    const seen = new Set();
    let cursor = report;
    while (cursor.parentId !== null) {
      if (seen.has(cursor.id)) fail('COPY_CYCLE');
      seen.add(cursor.id);
      const parent = byId.get(cursor.parentId);
      if (!parent) fail('MISSING_PARENT');
      if (cursor.originId !== parent.originId) fail('ORIGIN_CHANGED_IN_COPY');
      if (cursor.finding !== parent.finding || cursor.observedAt !== parent.observedAt) fail('COPY_CHANGED_OBSERVATION');
      if (Date.parse(cursor.receivedAt) < Date.parse(parent.receivedAt)) fail('COPY_BEFORE_PARENT');
      cursor = parent;
    }
    roots.set(report.id, cursor);
    return cursor;
  }
  const rows = packet.reports.map(report => {
    const root = rootOf(report);
    const ageMinutes = root.observedAt === null ? null : (now - Date.parse(root.observedAt)) / 60000;
    return {id: report.id, rootId: root.id, declaredOriginId: root.originId,
      kind: report.id === root.id ? 'ORIGINAL_DECLARED' : 'COPY_DECLARED',
      finding: root.finding, ageMinutes,
      timeState: ageMinutes === null ? 'OBSERVATION_TIME_UNKNOWN' :
        ageMinutes > packet.freshnessMinutes ? 'STALE_OBSERVATION' : 'FRESH_DECLARED'};
  });
  const originalRows = rows.filter(row => row.kind === 'ORIGINAL_DECLARED');
  const fresh = originalRows.filter(row => row.timeState === 'FRESH_DECLARED');
  const freshOrigins = new Set(fresh.map(row => row.declaredOriginId));
  const freshFindings = new Set(fresh.map(row => row.finding).filter(value => value !== 'unresolved'));
  const conflict = freshFindings.size > 1;
  const gap = originalRows.some(row => row.timeState !== 'FRESH_DECLARED') || fresh.length === 0;
  const unresolved = fresh.some(row => row.finding === 'unresolved');
  return {
    contract: 'halveth.lagefaden.synthetic.v1', caseId: packet.caseId,
    reportCount: rows.length, originalReportCount: originalRows.length,
    freshDeclaredOrigins: freshOrigins.size, conflict,
    status: conflict ? 'REVIEW_CONFLICT' : gap ? 'REVIEW_GAP' : unresolved ? 'REVIEW_UNRESOLVED'
      : freshOrigins.size < 2 ? 'REVIEW_SINGLE_SOURCE' : 'PROVISIONAL_CONSISTENT',
    rows, worldState: 'UNKNOWN',
    sourceAuthentication: 'NOT_PERFORMED',
    action: 'HUMAN_REVIEW_ONLY'
  };
}
