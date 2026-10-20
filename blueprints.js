export const BLUEPRINT_VERSION = 'seedspace.blueprint.v1';

// Data chooses a registered renderer. It is never treated as executable code.
export const blueprints = Object.freeze([
  {id:'origin', label:'JURI / ORIGIN', kind:'profile', description:'Eine Person wird sichtbar.', tone:'#efc6b2', icon:'✦'},
  {id:'garden', label:'GARDEN / 01', kind:'garden', description:'Ein Punkt schlägt Wurzeln.', tone:'#aeedc2', icon:'✺'},
  {id:'atlas', label:'PROJECT / ATLAS', kind:'projects', description:'Ein Portfolio entfaltet sich.', tone:'#b5c7ff', icon:'◇'},
  {id:'matrix', label:'TOOL / MATRIX', kind:'tool', description:'Aus Licht wird ein Werkzeug.', tone:'#f8dc9d', icon:'▦'}
]);

export function validateBlueprints(items) {
  const kinds = new Set(['profile', 'garden', 'projects', 'tool']);
  if (!Array.isArray(items) || items.length === 0) throw new Error('Blueprint list is empty');
  const ids = new Set();
  for (const item of items) {
    if (!item || !/^[a-z][a-z0-9-]*$/.test(item.id) || ids.has(item.id)) throw new Error('Invalid or repeated blueprint id');
    if (!kinds.has(item.kind) || typeof item.label !== 'string' || !item.label.trim()) throw new Error('Invalid blueprint');
    ids.add(item.id);
  }
  return true;
}

validateBlueprints(blueprints);
