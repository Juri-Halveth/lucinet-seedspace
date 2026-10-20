import {BLUEPRINT_VERSION, blueprints} from './blueprints.js';
import {encodeRoom, decodeRoom, latestByBlueprint} from './room-state.js';

const $ = selector => document.querySelector(selector);
const room = $('#room');
const world = $('#world');
const capsules = $('#capsules');
const layers = $('#layers');
const layersPanel = $('#layers-panel');
const openingHint = $('#opening-hint');
const targetPreview = $('#target-preview');
const throwLayer = $('#throw-layer');
const dragGhost = $('#drag-ghost');
const status = $('#live-status');
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
const STORAGE_KEY = 'lucinet.seedspace.room.v1';
const instances = [];
const pendingThrows = new Map();
const throwEpochs = new Map();
let selected = null;
let pointerDrag = null;
let suppressClickUntil = 0;
let nextId = 1;
let generation = 0;

$('#manifest-preview').textContent = JSON.stringify({
  schema: BLUEPRINT_VERSION,
  capsule: {id: 'garden', renderer: 'registered-local-component'},
  placement: {x: 'drop-coordinate', y: 'drop-coordinate', anchor: 'root-point'},
  lifecycle: ['throw', 'impact', 'grow-at-anchor', 'persist', 'hide-or-show']
}, null, 2);

const safe = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function say(message) { status.textContent = message; }
function findCapsule(id) { return blueprints.find(item => item.id === id); }

function renderCapsules() {
  capsules.replaceChildren();
  for (const blueprint of blueprints) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'capsule';
    button.dataset.id = blueprint.id;
    button.style.setProperty('--tone', blueprint.tone);
    button.setAttribute('aria-label', `${blueprint.label}: ${blueprint.description} Greifen und in den Raum ziehen oder antippen.`);
    button.setAttribute('aria-pressed', 'false');
    button.innerHTML = `<span class="orb"><span>${safe(blueprint.icon)}</span></span><span class="capsule-name">${safe(blueprint.label)}</span>`;
    button.addEventListener('pointerdown', event => startDrag(event, blueprint, button));
    button.addEventListener('click', () => {
      if (Date.now() < suppressClickUntil) return;
      selectCapsule(blueprint);
    });
    capsules.append(button);
  }
}

function selectCapsule(blueprint) {
  selected = blueprint;
  capsules.querySelectorAll('.capsule').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.id === blueprint.id)));
  room.classList.add('has-selection');
  targetPreview.style.setProperty('--tone', blueprint.tone);
  say(`${blueprint.label} gewählt. Jetzt in den Raum klicken oder die Kugel direkt hineinziehen.`);
}

function isPlaceable(clientX, clientY, blueprint = selected) {
  const box = room.getBoundingClientRect();
  if (clientX < box.left || clientX > box.right || clientY < box.top || clientY > box.bottom) return false;
  const target = document.elementFromPoint(clientX, clientY);
  if (target?.closest('.chrome, .dock, .help-panel, .layers-panel')) return false;
  const object = target?.closest('.world-object');
  return !object || object.dataset.blueprintId === blueprint?.id;
}

function setPreview(clientX, clientY, visible) {
  targetPreview.style.left = `${clientX}px`;
  targetPreview.style.top = `${clientY}px`;
  targetPreview.classList.toggle('visible', visible);
}

function startDrag(event, blueprint, button) {
  if (event.button !== 0 && event.pointerType === 'mouse') return;
  const box = button.getBoundingClientRect();
  pointerDrag = {id:event.pointerId, blueprint, startX:event.clientX, startY:event.clientY, originX:box.left+box.width/2, originY:box.top+box.height/2, moved:false, button};
  button.setPointerCapture(event.pointerId);
  selectCapsule(blueprint);
}

window.addEventListener('pointermove', event => {
  if (pointerDrag && event.pointerId === pointerDrag.id) {
    const distance = Math.hypot(event.clientX-pointerDrag.startX, event.clientY-pointerDrag.startY);
    if (distance > 8) pointerDrag.moved = true;
    if (pointerDrag.moved) {
      event.preventDefault();
      dragGhost.style.setProperty('--tone', pointerDrag.blueprint.tone);
      dragGhost.style.left = `${event.clientX}px`;
      dragGhost.style.top = `${event.clientY}px`;
      dragGhost.classList.add('visible');
      setPreview(event.clientX,event.clientY,isPlaceable(event.clientX,event.clientY,pointerDrag.blueprint));
      room.classList.add('dragging');
    }
  } else if (selected && isPlaceable(event.clientX,event.clientY)) {
    setPreview(event.clientX,event.clientY,true);
  } else if (!pointerDrag) targetPreview.classList.remove('visible');
}, {passive:false});

window.addEventListener('pointerup', event => {
  if (!pointerDrag || event.pointerId !== pointerDrag.id) return;
  const drag = pointerDrag; pointerDrag = null;
  dragGhost.classList.remove('visible'); room.classList.remove('dragging'); targetPreview.classList.remove('visible');
  if (drag.moved) {
    suppressClickUntil = Date.now()+500;
    if (isPlaceable(event.clientX,event.clientY,drag.blueprint)) place(drag.blueprint,event.clientX,event.clientY,drag.originX,drag.originY);
    else say('Kugel im dunklen Raum loslassen.');
  }
});

window.addEventListener('pointercancel', () => {
  pointerDrag=null; dragGhost.classList.remove('visible'); room.classList.remove('dragging'); targetPreview.classList.remove('visible');
});

function sceneMarkup(blueprint) {
  switch (blueprint.kind) {
    case 'profile': return `<article class="scene-card profile-card"><span class="scene-index">01 / JURI</span><div class="portrait">J<span>·</span></div><h2>Hallo, ich bin <em>Juri.</em></h2><p>Ich baue HALVETH und LUCINET: Forschung, Code und Räume, in denen Ideen sichtbar werden.</p><div class="mini-tags"><span>FORSCHUNG</span><span>CODE</span><span>WELTEN</span></div></article>`;
    case 'garden': return `<article class="garden-scene" aria-label="Lichtpflanze"><div class="plant-aura"></div><div class="plant-stem"></div><div class="plant-leaf leaf-left"></div><div class="plant-leaf leaf-right"></div><div class="flower"><i></i><i></i><i></i><i></i><i></i><b></b></div><span class="plant-label">GARDEN / 01</span></article>`;
    case 'projects': return `<article class="scene-card atlas-card"><span class="scene-index">03 / PROJEKTE</span><h2>HALVETH <em>Atlas.</em></h2><div class="project-row"><b>01</b><span>RED ROOM<small>Recherche und Quellenräume</small></span></div><div class="project-row"><b>02</b><span>LUCINET<small>Beobachtung und Projektion</small></span></div><div class="project-row"><b>03</b><span>MORROWIND<small>Spielwelt und Gestaltung</small></span></div></article>`;
    case 'tool': return `<article class="scene-card tool-card"><span class="scene-index">04 / WERKZEUG</span><h2>Microvalue <em>Studio.</em></h2><p>Ein Cent. Vier Anteile. Ein berechneter Rest.</p><div class="tool-inputs"><label>A <input type="number" min="0" max="100" value="24" inputmode="decimal"></label><label>B <input type="number" min="0" max="100" value="24" inputmode="decimal"></label><label>C <input type="number" min="0" max="100" value="24" inputmode="decimal"></label><label>D <input type="number" min="0" max="100" value="24" inputmode="decimal"></label></div><div class="tool-result">REST <strong data-rest>4 %</strong><small data-euro>0,0004 €</small></div><p class="tool-error" data-error role="alert"></p></article>`;
    default: throw new Error('Unregistered renderer');
  }
}

function connectTool(root) {
  const card = root.querySelector('.tool-card');
  if (!card) return;
  const inputs = [...card.querySelectorAll('input')];
  const update = () => {
    const values = inputs.map(input => input.value.trim() === '' ? NaN : Number(input.value));
    const sum = values.reduce((a,b) => a+b,0);
    const valid = values.every(n => Number.isFinite(n) && n >= 0 && n <= 100) && sum <= 100;
    card.querySelector('[data-rest]').textContent = valid ? `${Math.round((100-sum)*100)/100} %` : '—';
    card.querySelector('[data-euro]').textContent = valid ? `${((100-sum)/10000).toFixed(4).replace('.',',')} €` : '—';
    card.querySelector('[data-error]').textContent = valid ? '' : 'Summe muss zwischen 0 und 100 % liegen.';
  };
  inputs.forEach(input => input.addEventListener('input',update));
  update();
}

function updateLayers() {
  layersPanel.hidden = instances.length === 0;
  $('#object-count').textContent = String(instances.length);
  layers.replaceChildren();
  for (const instance of instances) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'layer-button';
    button.style.setProperty('--tone', instance.blueprint.tone);
    button.setAttribute('aria-pressed', String(instance.visible));
    button.setAttribute('aria-label', `${instance.blueprint.label} ${instance.id}: ${instance.visible ? 'sichtbar, ausblenden' : 'ausgeblendet, einblenden'}`);
    button.innerHTML = `<span aria-hidden="true">${instance.visible ? '◉' : '○'}</span><span>${safe(instance.blueprint.label)}</span><small>#${instance.id}</small>`;
    button.addEventListener('click', event => { event.stopPropagation(); toggleInstance(instance.id); });
    layers.append(button);
  }
}

function saveRoom() {
  try {
    const rect = room.getBoundingClientRect();
    localStorage.setItem(STORAGE_KEY, encodeRoom(instances,rect.width,rect.height));
  } catch { say('Raum funktioniert weiter; lokales Speichern ist hier nicht verfügbar.'); }
}

function toggleInstance(id) {
  const instance = instances.find(item => item.id === id);
  if (!instance) return;
  instance.visible = !instance.visible;
  instance.element.hidden = !instance.visible;
  updateLayers();
  saveRoom();
  say(`${instance.blueprint.label} ${instance.visible ? 'eingeblendet' : 'ausgeblendet'}. Andere Objekte bleiben stehen.`);
}

function positionNode(node,x,y,rect) {
  node.classList.toggle('grow-right',x < 190);
  node.classList.toggle('grow-left',x >= 190 && x > rect.width-190);
  node.classList.toggle('grow-down',y < 240);
  node.style.setProperty('--x',`${x}px`);
  node.style.setProperty('--y',`${y}px`);
}

function removePrevious(blueprintId) {
  for (let index = instances.length - 1; index >= 0; index--) {
    const instance = instances[index];
    if (instance.blueprint.id !== blueprintId) continue;
    instance.element.remove();
    instance.pulse?.remove();
    instances.splice(index, 1);
  }
}

function materialize(blueprint,x,y,{id=nextId++,visible=true,animate=true,persist=true}={}) {
  const rect = room.getBoundingClientRect();
  removePrevious(blueprint.id);
  const node = document.createElement('div');
  node.className = `world-object ${blueprint.kind}`;
  node.dataset.blueprintId = blueprint.id;
  if (!animate) node.classList.add('restored');
  positionNode(node,x,y,rect);
  node.style.setProperty('--tone',blueprint.tone);
  node.innerHTML = `<span class="anchor" aria-hidden="true"></span><div class="object-body">${sceneMarkup(blueprint)}</div><button class="object-hide" type="button" aria-label="${safe(blueprint.label)} ausblenden" title="Dieses Objekt ausblenden">×</button>`;
  const instance = {id,blueprint,element:node,visible,x,y,rx:x/rect.width,ry:y/rect.height};
  instances.push(instance);
  world.append(node);
  node.hidden=!visible;
  node.querySelector('.object-hide').addEventListener('click', event => { event.stopPropagation(); toggleInstance(id); });
  connectTool(node);
  updateLayers();
  if (animate) {
    const pulse = document.createElement('span'); pulse.className='ground-pulse'; pulse.style.left=`${x}px`; pulse.style.top=`${y}px`; pulse.style.setProperty('--tone',blueprint.tone); world.append(pulse); instance.pulse=pulse;
    pulse.addEventListener('animationend',()=>pulse.remove(),{once:true});
  }
  if (persist) saveRoom();
  return instance;
}

async function place(blueprint, clientX, clientY, fromX, fromY) {
  if (!blueprint || (instances.length >= 20 && !instances.some(item => item.blueprint.id === blueprint.id))) { say('Der Raum enthält schon 20 verschiedene Objekte.'); return; }
  const ownGeneration = generation;
  const epoch = (throwEpochs.get(blueprint.id) || 0) + 1;
  throwEpochs.set(blueprint.id, epoch);
  const previousThrow = pendingThrows.get(blueprint.id);
  previousThrow?.flight.cancel();
  previousThrow?.orb.remove();
  const hadPrevious = instances.some(item => item.blueprint.id === blueprint.id);
  if (hadPrevious) {
    removePrevious(blueprint.id);
    updateLayers();
    saveRoom();
  }
  openingHint.hidden = true;
  const flying = document.createElement('div');
  flying.className = 'flying-orb';
  flying.style.setProperty('--tone',blueprint.tone);
  throwLayer.append(flying);
  const duration = reduceMotion.matches ? 1 : 540;
  const flight = flying.animate([
    {transform:`translate(${fromX}px,${fromY}px) scale(.7)`,opacity:.8},
    {transform:`translate(${(fromX+clientX)/2}px,${Math.min(fromY,clientY)-65}px) scale(1.5)`,opacity:1,offset:.58},
    {transform:`translate(${clientX}px,${clientY}px) scale(.18)`,opacity:1}
  ],{duration,easing:'cubic-bezier(.16,.7,.14,1)',fill:'forwards'});
  const pending = {flight, orb:flying};
  pendingThrows.set(blueprint.id,pending);
  say(hadPrevious ? `${blueprint.label} am alten Ort entfernt und unterwegs zum neuen Punkt.` : `${blueprint.label} fliegt zum gewählten Punkt.`);
  await flight.finished.catch(()=>{});
  flying.remove();
  if (pendingThrows.get(blueprint.id) === pending) pendingThrows.delete(blueprint.id);
  if (ownGeneration !== generation || throwEpochs.get(blueprint.id) !== epoch || flight.playState === 'idle') return;
  const rect = room.getBoundingClientRect();
  materialize(blueprint,clientX-rect.left,clientY-rect.top);
  say(`${blueprint.label} ist am neuen Ort gewachsen. Pro Kugeltyp bleibt genau ein Objekt im Raum.`);
}

room.addEventListener('click', event => {
  if (event.target.closest('.chrome, .dock, .help-panel, .layers-panel, .world-object')) return;
  if (!selected) { say('Nimm unten eine der leuchtenden Kugeln.'); return; }
  const source = capsules.querySelector(`[data-id="${selected.id}"]`).getBoundingClientRect();
  place(selected,event.clientX,event.clientY,source.left+source.width/2,source.top+source.height/2);
});
room.addEventListener('keydown', event => {
  if (event.target !== room || !['Enter',' '].includes(event.key)) return;
  event.preventDefault();
  if (!selected) { say('Nimm unten eine der leuchtenden Kugeln.'); return; }
  const box=room.getBoundingClientRect(); const source=capsules.querySelector(`[data-id="${selected.id}"]`).getBoundingClientRect();
  place(selected,box.left+box.width*.5,box.top+box.height*.48,source.left+source.width/2,source.top+source.height/2);
});

$('#clear-all').addEventListener('click', event => {
  event.stopPropagation();
  generation++;
  for (const pending of pendingThrows.values()) pending.flight.cancel();
  pendingThrows.clear();
  throwEpochs.clear();
  instances.length=0;
  nextId=1;
  world.replaceChildren();
  throwLayer.replaceChildren();
  openingHint.hidden=false;
  updateLayers();
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* Session still clears. */ }
  say('Raum geleert. Die Kugeln warten unten.');
});

function setHelp(open) {
  $('#help-panel').hidden=!open;
  $('#help-toggle').setAttribute('aria-expanded',String(open));
  if (open) $('#help-close').focus();
}
$('#help-toggle').addEventListener('click', () => setHelp($('#help-panel').hidden));
$('#help-close').addEventListener('click', () => { setHelp(false); $('#help-toggle').focus(); });
window.addEventListener('keydown', event => { if (event.key==='Escape' && !$('#help-panel').hidden) setHelp(false); });

function restoreRoom() {
  let raw;
  try { raw=localStorage.getItem(STORAGE_KEY); } catch { return; }
  if (!raw) return;
  try {
    const rect=room.getBoundingClientRect();
    const decoded=decodeRoom(raw,new Set(blueprints.map(item=>item.id)),rect.width,rect.height);
    const records=latestByBlueprint(decoded);
    for (const record of records) {
      materialize(findCapsule(record.blueprintId),record.x,record.y,{id:record.id,visible:record.visible,animate:false,persist:false});
      nextId=Math.max(nextId,record.id+1);
    }
    if (records.length) { openingHint.hidden=true; say(`${records.length} gespeicherte Objekte im Raum.`); }
    if (records.length !== decoded.length) saveRoom();
  } catch { say('Gespeicherter Raum ist ungültig; diese Ansicht beginnt leer.'); }
}

window.addEventListener('resize', () => {
  const rect=room.getBoundingClientRect();
  for (const instance of instances) {
    instance.x=instance.rx*rect.width; instance.y=instance.ry*rect.height;
    positionNode(instance.element,instance.x,instance.y,rect);
  }
});

renderCapsules();
restoreRoom();
