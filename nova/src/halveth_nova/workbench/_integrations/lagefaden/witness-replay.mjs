// SPDX-License-Identifier: MIT
import {evaluatePacket} from './model.mjs';

export const replayContract = 'halveth.lagefaden.witness-replay.v1';
const kinds = ['OBSERVATION','FORWARD','REACTION','PEER_ACTION_OBSERVATION','VIEW_LOST','VIEW_RESTORED'];
const claims = ['possibly_blocked','free','unresolved'];
const exact = (o, keys) => o && typeof o === 'object' && !Array.isArray(o)
  && Object.keys(o).length === keys.length && keys.every(k => Object.hasOwn(o,k));
const id = s => typeof s === 'string' && /^[A-Za-z0-9_-]{1,48}$/.test(s);
const time = s => typeof s === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:Z|[+-]\d\d:\d\d)$/.test(s)
  && Number.isFinite(Date.parse(s)) && new Date(s.slice(0,19)+'Z').toISOString().slice(0,19) === s.slice(0,19);
const fail = code => {throw Error(code);};

// A read-only synthetic message adapter, not a sensor/flight-control interface.
// References are backward-only. Peer actions never become route observations.
export function evaluateReplay(packet, step) {
  if (!exact(packet,['caseId','routeId','startsAt','endsAt','freshnessMinutes','reviewAvailable','nodes','events'])
    || !id(packet.caseId) || !id(packet.routeId) || !time(packet.startsAt) || !time(packet.endsAt)
    || Date.parse(packet.startsAt) > Date.parse(packet.endsAt) || typeof packet.reviewAvailable !== 'boolean'
    || !Number.isInteger(packet.freshnessMinutes) || packet.freshnessMinutes < 1 || packet.freshnessMinutes > 1440
    || !Array.isArray(packet.nodes) || packet.nodes.length < 1 || packet.nodes.length > 16
    || !Array.from(packet.nodes).every(id) || new Set(packet.nodes).size !== packet.nodes.length
    || !Array.isArray(packet.events) || packet.events.length > 64) fail('INVALID_REPLAY');
  if (!Number.isInteger(step) || step < 0 || step > packet.events.length+1) fail('INVALID_STEP');
  const all = new Map();
  let previousTime = Date.parse(packet.startsAt);
  // Validate the complete declared stream even when displaying a prefix.
  for (const e of packet.events) {
    if (!exact(e,['id','nodeId','kind','at','observedAt','refId','claim'])
      || !id(e.id) || all.has(e.id) || !packet.nodes.includes(e.nodeId) || !kinds.includes(e.kind)
      || !time(e.at) || Date.parse(e.at) < previousTime || Date.parse(e.at) > Date.parse(packet.endsAt)) fail('INVALID_EVENT');
    previousTime = Date.parse(e.at);
    const observation = e.kind === 'OBSERVATION';
    const peer = e.kind === 'PEER_ACTION_OBSERVATION';
    if (observation || peer) {
      if (e.observedAt !== null && (!time(e.observedAt) || Date.parse(e.observedAt) > Date.parse(e.at))) fail('INVALID_OBSERVED_TIME');
    } else if (e.observedAt !== null) fail('UNEXPECTED_OBSERVED_TIME');
    if (observation ? !claims.includes(e.claim) : e.claim !== null) fail('INVALID_ROUTE_CLAIM');
    if (['FORWARD','REACTION','PEER_ACTION_OBSERVATION'].includes(e.kind)) {
      if (e.refId !== null && (!id(e.refId) || !all.has(e.refId))) fail('MISSING_OR_FUTURE_REFERENCE');
      const parent = all.get(e.refId);
      if (parent && e.kind === 'FORWARD' && !['OBSERVATION','FORWARD'].includes(parent.kind)) fail('FORWARD_NOT_ROUTE_REPORT');
      if (parent && peer && (parent.kind !== 'REACTION' || parent.nodeId === e.nodeId)) fail('INVALID_PEER_REFERENCE');
    } else if (e.refId !== null) fail('UNEXPECTED_REFERENCE');
    all.set(e.id,e);
  }
  const visible = packet.events.slice(0,Math.min(step,packet.events.length));
  const asOf = step === 0 ? packet.startsAt : step > packet.events.length ? packet.endsAt : visible.at(-1).at;
  const roots = new Map();
  const reports = [];
  const rows = [];
  const nodeView = new Map(packet.nodes.map(n => [n,{nodeId:n,state:'NO_ROUTE_OBSERVATION',lastObservationId:null}]));
  for (const e of visible) {
    let rootId = null;
    const n = nodeView.get(e.nodeId);
    if (e.kind === 'OBSERVATION') {
      rootId = e.id;
      reports.push({id:e.id,originId:e.nodeId,parentId:null,observedAt:e.observedAt,receivedAt:e.at,
        finding:({possibly_blocked:'possible_object',free:'alternative_explanation',unresolved:'unresolved'})[e.claim]});
      n.lastObservationId=e.id;
      // An observation received after loss does not silently restore the view.
      if (n.state !== 'VIEW_LOST') n.state='OBSERVATION_RECEIVED';
    } else if (e.kind === 'FORWARD') {
      rootId = roots.get(e.refId) ?? null;
      if (rootId) {
        const parent = reports.find(r => r.id === e.refId);
        reports.push({...parent,id:e.id,parentId:e.refId,receivedAt:e.at});
      }
    } else if (e.kind === 'VIEW_LOST') n.state='VIEW_LOST';
    else if (e.kind === 'VIEW_RESTORED') n.state='RESTORED_AWAITING_OBSERVATION';
    roots.set(e.id,rootId);
    const root = all.get(rootId);
    const ageMinutes = root?.observedAt ? (Date.parse(asOf)-Date.parse(root.observedAt))/60000 : null;
    rows.push({...e,rootId,routeEvidence:e.kind === 'OBSERVATION' ? 'OWN_DECLARED'
      : e.kind === 'FORWARD' ? (rootId ? 'COPY_DECLARED' : 'PROVENANCE_MISSING') : 'NO_ROUTE_OBSERVATION',
      ageMinutes,timeState:rootId ? (ageMinutes === null ? 'TIME_UNKNOWN' : ageMinutes > packet.freshnessMinutes ? 'STALE' : 'IN_WINDOW') : 'NOT_APPLICABLE'});
  }
  const core = reports.length ? evaluatePacket({caseId:packet.caseId,referenceTime:asOf,
    freshnessMinutes:packet.freshnessMinutes,reports}) : null;
  const missingProvenance = rows.filter(r => ['FORWARD','REACTION','PEER_ACTION_OBSERVATION'].includes(r.kind)
    && (r.refId === null || r.routeEvidence === 'PROVENANCE_MISSING')).map(r=>r.id);
  const views = [...nodeView.values()];
  const gaps = views.filter(n => n.state !== 'OBSERVATION_RECEIVED').map(n=>({nodeId:n.nodeId,reason:n.state}));
  return {contract:replayContract,caseId:packet.caseId,routeId:packet.routeId,step,
    totalSteps:packet.events.length+1,asOf,receivedEvents:visible.length,rows,
    ownRouteObservations:reports.filter(r=>r.parentId===null).length,
    forwardedReports:rows.filter(r=>r.kind==='FORWARD').length,
    peerSignals:rows.filter(r=>['REACTION','PEER_ACTION_OBSERVATION'].includes(r.kind)).length,
    freshDeclaredOrigins:core?.freshDeclaredOrigins ?? 0,conflict:core?.conflict ?? false,
    missingProvenance,viewGaps:gaps,core,
    reviewState:!packet.reviewAvailable ? 'REVIEWER_UNAVAILABLE' : missingProvenance.length ? 'PROVENANCE_REVIEW'
      : core?.conflict ? 'CONFLICT_REVIEW' : gaps.length || !core || core.status==='REVIEW_GAP' ? 'GAP_REVIEW' : 'HUMAN_REVIEW',
    routeState:'UNKNOWN',sourceAuthentication:'NOT_PERFORMED',
    sensorIndependence:'UNKNOWN',action:'HUMAN_REVIEW_ONLY',hardwareConnected:false};
}
