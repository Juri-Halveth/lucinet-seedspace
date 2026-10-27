// HALVETH PIRL 2.0. Deterministic educational model; model time has no SI calibration.
export const VERSION = '1.0.0';
export const STEPS = 60;
const copy = value => structuredClone(value);
export function canonical(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
}
export async function digest(value) {
  const bytes = new TextEncoder().encode(canonical(value));
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(x => x.toString(16).padStart(2, '0')).join('');
}
function keys(value, allowed) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).sort().join('|') !== allowed.sort().join('|')) throw Error('CLOSED_OBJECT_REQUIRED');
}
export function validateConfig(config) {
  keys(config, ['scenario', 'seed', 'gate']);
  if (!['journey', 'catalase'].includes(config.scenario) || !Number.isInteger(config.seed) || config.seed < 0 || config.seed > 999999 || !['open', 'closed'].includes(config.gate)) throw Error('INVALID_CONFIG');
  return copy(config);
}
export function createRun(config, sources, options = {}) {
  validateConfig(config);
  const runId = options.runId ?? 'mol_' + crypto.randomUUID().replaceAll('-', '');
  const recordedAt = options.recordedAt ?? new Date().toISOString();
  if (!/^mol_[a-f0-9]{32}$/.test(runId) || !/^\d{4}-\d{2}-\d{2}T/.test(recordedAt) || !Number.isFinite(Date.parse(recordedAt))) throw Error('INVALID_RUN_ADDRESS');
  const parentRunId = options.parentRunId ?? null;
  if (parentRunId !== null && (!/^mol_[a-f0-9]{32}$/.test(parentRunId) || parentRunId === runId)) throw Error('INVALID_PARENT');
  const atoms = [], entities = [], events = [];
  function event(step, type, inputs, outputs, detail) {
    events.push({id: runId + '_evt_' + String(events.length + 1).padStart(3, '0'),
      time: {clockId: runId + '_model', step, unit: 'MODEL_STEP'}, recordedAt,
      type, inputs: [...inputs], outputs: [...outputs], detail, evidence: 'DECLARED_MODEL_EVENT'});
  }
  function entity(id, speciesId, born, retired, atomIds, parents, waypoints) {
    entities.push({id: runId + '_' + id, label: id, speciesId, born, retired,
      atomIds, parents, waypoints, sourceRef: 'pubchem-' + sources.species[speciesId].cid});
    return entities.at(-1);
  }
  function initial(label, speciesId, y) {
    const atomIds = sources.species[speciesId].atoms.map(a => {
      const id = runId + '_' + label + '_a' + a.aid;
      atoms.push({id, element: a.element, originEntityId: runId + '_' + label, sourceAtomAid: a.aid});
      return id;
    });
    return entity(label, speciesId, 0, null, atomIds, [], [[0, 110, y]]);
  }
  if (config.scenario === 'journey') {
    for (let i = 0; i < 3; i++) {
      const phase = (config.seed + i * 3) % 6;
      const ent = initial('DMT-' + String(i + 1).padStart(3, '0'), 'dmt', 145 + i * 100);
      event(0, 'CREATE', [], [ent.id], 'Eine eigene Modellinstanz mit 30 Atom-IDs.');
      ent.waypoints.push([12 + phase, 355, 145 + i * 100]);
      if (config.gate === 'closed') {
        ent.waypoints.push([28 + phase, 360, 145 + i * 100], [60, 290, 145 + i * 100]);
        event(18 + phase, 'BLOCKED', [ent.id], [ent.id], 'Die geschlossene Modellmembran verhindert den Transport.');
      } else {
        ent.waypoints.push([19 + phase, 407, 145 + i * 100], [20 + phase, 423, 145 + i * 100], [23 + phase, 510, 145 + i * 100], [31 + phase, 650, 145 + i * 100], [46 + phase, 650, 145 + i * 100], [60, 825, 145 + i * 100]);
        event(20 + phase, 'TRANSPORT', [ent.id], [ent.id], 'Dieselbe Instanz wechselt von Raum A nach Raum B.');
        event(31 + phase, 'CONTACT', [ent.id], [ent.id], 'Kontakt mit einem schematischen Bindungsplatz.');
        event(34 + phase, 'BIND', [ent.id], [ent.id], 'Vorübergehend gebunden; die Molekül-ID bleibt gleich.');
        event(46 + phase, 'RELEASE', [ent.id], [ent.id], 'Bindung gelöst; Molekül und Atome behalten ihre IDs.');
      }
    }
  } else {
    const one = initial('PER-001', 'peroxide', 185), two = initial('PER-002', 'peroxide', 305);
    for (const ent of [one, two]) {
      event(0, 'CREATE', [], [ent.id], 'Ein eigenes H₂O₂-Molekül mit vier Atom-IDs.');
      ent.waypoints.push([20, 355, ent.waypoints[0][2]]);
    }
    if (config.gate === 'closed') {
      for (const ent of [one, two]) {
        ent.waypoints.push([60, 310, ent.waypoints[0][2]]);
        event(24, 'BLOCKED', [ent.id], [ent.id], 'Modellmembran geschlossen; das Reaktionsfeld wird nicht erreicht.');
      }
    } else {
      for (const ent of [one, two]) {
        ent.waypoints.push([30, 560, ent.waypoints[0][2]], [32, 590, 245]); ent.retired = 32;
        event(23, 'TRANSPORT', [ent.id], [ent.id], 'Transport in das schematische Reaktionsfeld.');
        event(30, 'CONTACT', [ent.id], [ent.id], 'Reaktanten erreichen das Reaktionsfeld.');
      }
      const select = (e, symbol) => e.atomIds.filter(id => atoms.find(a => a.id === id).element === symbol);
      const [o1, o2] = select(one, 'O'), [o3, o4] = select(two, 'O');
      const [h1, h2] = select(one, 'H'), [h3, h4] = select(two, 'H');
      const ids = [one.id, two.id];
      const w1 = entity('WATER-001', 'water', 32, null, [o1, h1, h3], ids, [[32, 590, 245], [60, 815, 130]]);
      const w2 = entity('WATER-002', 'water', 32, null, [o3, h2, h4], ids, [[32, 590, 245], [60, 815, 350]]);
      const ox = entity('OXYGEN-001', 'oxygen', 32, null, [o2, o4], ids, [[32, 590, 245], [60, 815, 245]]);
      event(32, 'TRANSFORM', ids, [w1.id, w2.id, ox.id], 'Rhea:20309 · 2 H₂O₂ → 2 H₂O + O₂. Gewählte, atomkonservierende Modellzuordnung.');
    }
  }
  events.sort((a, b) => a.time.step - b.time.step || a.id.localeCompare(b.id, 'en'));
  return {schema: 'molecular-run.v1', modelVersion: VERSION, runId, parentRunId, recordedAt,
    config: copy(config), maxStep: STEPS, clock: {id: runId + '_model', unit: 'MODEL_STEP', calibratedToSeconds: false},
    atoms, entities, events,
    sourceRefs: [...new Set(entities.map(e => e.sourceRef))].sort(),
    modelLimits: ['SCHEMATIC_GEOMETRY', 'NO_CALIBRATED_KINETICS', 'MODEL_IDS_NOT_MEASURED_PARTICLE_TRACKS', 'SELECTED_ATOM_MAPPING_NOT_TRACER_EVIDENCE']};
}
export function positionAt(ent, step) {
  const points = ent.waypoints;
  for (let i = 1; i < points.length; i++) if (step <= points[i][0]) {
    const [t, x, y] = points[i - 1], [t2, x2, y2] = points[i];
    const f = Math.max(0, (step - t) / (t2 - t));
    return {x: x + f * (x2 - x), y: y + f * (y2 - y)};
  }
  return {x: points.at(-1)[1], y: points.at(-1)[2]};
}
export function stateAt(run, step) {
  if (!Number.isInteger(step) || step < 0 || step > STEPS) throw Error('INVALID_STEP');
  return {runId: run.runId, step, active: run.entities.filter(e => e.born <= step && (e.retired === null || step < e.retired)).map(e => {
    const relevant = run.events.filter(v => v.time.step <= step && v.outputs.includes(e.id));
    return {id: e.id, speciesId: e.speciesId, atomIds: copy(e.atomIds), state: relevant.at(-1)?.type ?? 'CREATE', position: positionAt(e, step)};
  })};
}
// Separate oracle: event replay owns atom inventory. It does not read waypoints or stateAt().
export function auditRun(run, sources) {
  const expected = createRun(run.config, sources, {runId: run.runId, recordedAt: run.recordedAt, parentRunId: run.parentRunId});
  if (canonical(run) !== canonical(expected)) throw Error('MODEL_REPLAY_MISMATCH');
  const atomIds = new Set(run.atoms.map(a => a.id)), ownership = new Map(), live = new Set();
  if (atomIds.size !== run.atoms.length) throw Error('DUPLICATE_ATOM');
  for (const e of run.events) {
    if (e.type === 'CREATE') live.add(e.outputs[0]);
    if (e.type === 'TRANSFORM') {
      const inputAtoms = e.inputs.flatMap(id => run.entities.find(m => m.id === id).atomIds).sort();
      const outputAtoms = e.outputs.flatMap(id => run.entities.find(m => m.id === id).atomIds).sort();
      if (canonical(inputAtoms) !== canonical(outputAtoms)) throw Error('ATOM_LOSS');
      for (const id of e.inputs) { if (!live.delete(id)) throw Error('MISSING_REACTANT'); }
      for (const id of e.outputs) live.add(id);
    }
  }
  for (const id of live) for (const aid of run.entities.find(e => e.id === id).atomIds) {
    if (!atomIds.has(aid) || ownership.has(aid)) throw Error('ATOM_OWNER_CONFLICT');
    ownership.set(aid, id);
  }
  if (ownership.size !== atomIds.size) throw Error('UNOWNED_ATOM');
  return {ok: true, oracleVersion: VERSION, atomCount: atomIds.size, currentEntityCount: live.size,
    eventCount: run.events.length, modelReplay: true, atomConservation: true, singleAtomOwner: true,
    meaning: 'Declared model consistency; not an empirical molecular trajectory'};
}
export async function checkpoint(run, step, sources, view = null) {
  const audit = auditRun(run, sources), runDigest = await digest(run), snapshot = stateAt(run, step);
  const definition = {id: 'atom-transfer.v1', version: VERSION, type: 'MODELED_ATOM_TRANSFER', direction: 'PARENT_TO_PRODUCT', transitive: false};
  const entities = Object.fromEntries(await Promise.all(run.entities.map(async e => [e.id, await digest(e)])));
  const relations = [];
  for (const product of run.entities.filter(e => e.parents.length)) for (const parentId of product.parents) {
    const parent = run.entities.find(e => e.id === parentId), shared = product.atomIds.filter(id => parent.atomIds.includes(id));
    if (!shared.length) continue;
    const address = e => ({kind: 'MODELED_MOLECULE_INSTANCE', id: e.id, digest: entities[e.id], semanticAddress: '/entities/' + run.entities.indexOf(e), scope: run.runId});
    const id = run.runId + '_rel_' + String(relations.length + 1).padStart(3, '0');
    relations.push({id, definition, definitionDigest: await digest(definition),
      left: address(parent), right: address(product), atomIds: shared,
      eventTime: {clockId: run.clock.id, step: product.born, unit: 'MODEL_STEP'}, recordedAt: run.recordedAt,
      sourceRefs: ['rhea-20309', ...run.sourceRefs], evidence: 'ANALYST_SELECTED_MODEL_MAP', authorityEffect: 'NONE', writeDomainId: id});
  }
  const packet = {schema: 'molecular-checkpoint.v1', run, runDigest, step, snapshot, snapshotDigest: await digest(snapshot), audit, relations};
  if (view !== null) {
    keys(view, ['selectedEntityId', 'selectedAtomId']);
    const selected = run.entities.find(e => e.id === view.selectedEntityId);
    if (!selected || !selected.atomIds.includes(view.selectedAtomId)) throw Error('INVALID_VIEW_ADDRESS');
    packet.view = copy(view);
  }
  return {...packet, packetDigest: await digest(packet)};
}
export async function validateCheckpoint(packet, sources) {
  const expected = await checkpoint(packet.run, packet.step, sources, packet.view ?? null);
  if (canonical(packet) !== canonical(expected)) throw Error('CHECKPOINT_BINDING_MISMATCH');
  return expected.audit;
}
