export const BLUEPRINT_VERSION = 'seedspace.blueprint.v2';

// Data chooses a registered renderer. It is never treated as executable code.
export const blueprints = Object.freeze([
  {id:'origin', label:'JURI', kind:'profile', description:'Der Mensch hinter dem Raum.', tone:'#f1c9b2', icon:'✦'},
  {id:'signal', label:'SPUR', kind:'signal', description:'Ein wechselndes Forschungsthema.', tone:'#9de7ef', icon:'◈'},
  {id:'scarlet', label:'STIMME', kind:'scarlet', description:'Eine Stimme antwortet auf den Wurf.', tone:'#ff426e', icon:'✺'},
  {id:'wonder', label:'UNBEKANNT', kind:'wonder', description:'Eine überraschende Form erscheint.', tone:'#c7a5ff', icon:'✳'},
  {id:'universe', label:'UNIVERSUM', kind:'projects', description:'Projekte und Verbindungen werden sichtbar.', tone:'#f9d999', icon:'✧'}
]);

export function validateBlueprints(items) {
  const kinds = new Set(['profile', 'signal', 'scarlet', 'wonder', 'projects']);
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
