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
const storyPrompt = $('#story-prompt');
const storyCounter = $('#story-counter');
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
const STORAGE_KEY = 'lucinet.seedspace.room.v2';
const instances = [];
const pendingThrows = new Map();
const throwEpochs = new Map();
const topics = [
  {number:'02 / LUCINET', title:'Aus Beobachtung wird Raum.', body:'Ein Bild ist der Anfang. LUCINET fragt, welche Szene, Bewegung und Verbindung daraus werden kann.', nodes:['QUELLE','MODELL','SZENE']},
  {number:'02 / RED ROOM', title:'Eine Frage öffnet Quellen.', body:'Spuren werden gesammelt, verglichen und als offene oder gestützte Verbindung sichtbar gemacht.', nodes:['FRAGE','QUELLE','VERBINDUNG']},
  {number:'02 / SPIELWELT', title:'Ein Punkt wird zur Welt.', body:'Kleine Bausteine entfalten Orte, Grafik und Bewegung – erst im Browser, später vielleicht im Spiel.', nodes:['PUNKT','RAUM','WELT']}
];
const wonders = [
  {name:'PORTAL', line:'Eine Grenze wird zu einem Übergang.'},
  {name:'SCHMETTERLING', line:'Eine kleine Bewegung verändert die ganze Szene.'},
  {name:'STERNKARTE', line:'Getrennte Punkte finden eine Form.'}
];
const mantras = [
  'WO DU EINEN PUNKT SETZT, ENTSTEHT EIN ORT. WO ZWEI ORTE SIND, WARTET EINE VERBINDUNG.',
  'DAS LICHT GEHT NACH LINKS. DER GEDANKE GEHT WEITER. DEIN NÄCHSTER WURF ENTSCHEIDET.',
  'EIN ALTES BILD VERGEHT. DIE NEUE SPUR BLEIBT NUR DORT, WO DU SIE SETZT.',
  'DIE KUGEL FÄLLT. DER RAUM ANTWORTET. NICHTS MUSS VORHER WISSEN, WAS DARAUS WIRD.'
];
let selected = null;
let pointerDrag = null;
let suppressClickUntil = 0;
let nextId = 1;
let generation = 0;
let progress = 0;
let panelOpen = false;
let focusedId = null;

$('#manifest-preview').textContent = JSON.stringify({
  schema: BLUEPRINT_VERSION,
  capsule: {id: 'origin', renderer: 'registered-local-component'},
  placement: {x: 'drop-coordinate', y: 'drop-coordinate', anchor: 'root-point'},
  lifecycle: ['unlock', 'throw', 'impact', 'grow-at-anchor', 'persist', 'hide-or-show'],
  observer: 'local page interaction only'
}, null, 2);

const safe = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function say(message) { status.textContent = message; }
function findCapsule(id) { return blueprints.find(item => item.id === id); }

function renderCapsules() {
  capsules.replaceChildren();
  for (const [index, blueprint] of blueprints.entries()) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'capsule';
    button.dataset.id = blueprint.id;
    button.hidden = index > progress;
    button.classList.toggle('is-next', index === progress || progress === blueprints.length);
    button.classList.toggle('is-past', index < progress);
    button.style.setProperty('--tone', blueprint.tone);
    button.setAttribute('aria-label', `Kugel ${index + 1}: ${index < progress ? blueprint.label : 'unbekannter Inhalt'}. Greifen und in den Raum ziehen oder antippen.`);
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

function updateStory() {
  const prompts = [
    'Nimm die Kugel.',
    'Hier ist noch eine.',
    'Die rote will etwas sagen.',
    'Was steckt in der nächsten?',
    'Zum Schluss: alles verbinden.',
    'Der Raum ist offen. Wirf weiter.'
  ];
  storyPrompt.textContent = prompts[progress];
  storyCounter.textContent = progress === blueprints.length ? '∞ / 05' : String(progress + 1).padStart(2, '0') + ' / 05';
  room.dataset.stage = String(progress);
  openingHint.hidden = progress > 0;
  $('.story-rail').hidden = progress === 0;
  selected = null;
  room.classList.remove('has-selection');
  targetPreview.classList.remove('visible');
  renderCapsules();
}

function selectCapsule(blueprint) {
  selected = blueprint;
  capsules.querySelectorAll('.capsule').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.id === blueprint.id)));
  room.classList.add('has-selection');
  targetPreview.style.setProperty('--tone', blueprint.tone);
  say(`${blueprint.label} gewählt. Jetzt in den Raum klicken oder die Kugel direkt hineinziehen.`);
}

function isPlaceable(clientX, clientY) {
  const box = room.getBoundingClientRect();
  if (clientX < box.left || clientX > box.right || clientY < box.top || clientY > box.bottom) return false;
  const target = document.elementFromPoint(clientX, clientY);
  if (target?.closest('.chrome, .dock, .help-panel, .layers-panel')) return false;
  return !target?.closest('.object-hide, a, input');
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
      setPreview(event.clientX,event.clientY,isPlaceable(event.clientX,event.clientY));
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
    if (isPlaceable(event.clientX,event.clientY)) place(drag.blueprint,event.clientX,event.clientY,drag.originX,drag.originY);
    else say('Kugel im dunklen Raum loslassen.');
  }
});

window.addEventListener('pointercancel', () => {
  pointerDrag=null; dragGhost.classList.remove('visible'); room.classList.remove('dragging'); targetPreview.classList.remove('visible');
});

function sceneMarkup(blueprint, variant) {
  switch (blueprint.kind) {
    case 'profile':
      return `<article class="scene-card profile-card"><span class="scene-index">01 / DER ANFANG</span><div class="portrait">J<span>·</span></div><h2>Juri<br><em>Janovski.</em></h2><p>Ich verbinde Forschung, Code, Grafik und Spielwelten zu Räumen, die man selbst entdecken kann.</p><div class="mini-tags"><span>HALVETH</span><span>LUCINET</span></div></article>`;
    case 'signal': {
      const topic = topics[variant % topics.length];
      return `<article class="scene-card signal-card"><span class="scene-index">${safe(topic.number)}</span><div class="signal-graphic" aria-hidden="true"><i></i><i></i><i></i><b></b></div><h2>${safe(topic.title)}</h2><p>${safe(topic.body)}</p><div class="signal-nodes">${topic.nodes.map(node => `<span>${safe(node)}</span>`).join('<i aria-hidden="true"></i>')}</div></article>`;
    }
    case 'scarlet':
      return `<article class="scarlet-scene"><div class="scarlet-halo" aria-hidden="true"><i></i><i></i><i></i><b>✧</b></div><div class="scarlet-words"><span>03 / DIE STIMME</span><p>${safe(mantras[variant % mantras.length])}</p></div></article>`;
    case 'wonder': {
      const wonder = wonders[variant % wonders.length];
      return `<article class="wonder-scene wonder-${variant % wonders.length}"><div class="wonder-art" aria-hidden="true"><i></i><i></i><i></i><i></i><b>✦</b></div><div class="wonder-copy"><span>04 / UNBEKANNT</span><h2>${safe(wonder.name)}</h2><p>${safe(wonder.line)}</p></div></article>`;
    }
    case 'projects':
      return `<article class="scene-card universe-card"><span class="scene-index">05 / JURIS PROJEKTUNIVERSUM</span><h2>Wer Verbindungen baut,<br><em>baut Welten.</em></h2><div class="universe-map" aria-label="Juri verbindet HALVETH, LUCINET, RED ROOM, Spielwelten und Connectoren"><div class="universe-core">J</div><span class="map-node n1">HALVETH</span><span class="map-node n2">LUCINET</span><span class="map-node n3">RED ROOM</span><span class="map-node n4">SPIELWELTEN</span><span class="map-node n5">CONNECTORS</span></div><p>Forschung · Grafik · Spiele · Code · Verbindungen</p></article>`;
    default: throw new Error('Unregistered renderer');
  }
}

function updateLayers() {
  const latest = instances.find(item => item.id === focusedId && item.visible) || [...instances].reverse().find(item => item.visible);
  focusedId = latest?.id ?? null;
  for (const item of instances) item.element.classList.toggle('is-latest', item === latest);
  if (instances.length === 0) panelOpen = false;
  $('#layers-toggle').hidden = instances.length === 0;
  $('#layers-toggle').setAttribute('aria-expanded', String(panelOpen));
  layersPanel.hidden = !panelOpen || instances.length === 0;
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
  if (!instance.visible && focusedId === id) focusedId = null;
  if (instance.visible) focusedId = id;
  updateLayers();
  saveRoom();
  say(`${instance.blueprint.label} ${instance.visible ? 'eingeblendet' : 'ausgeblendet'}.`);
}

function positionNode(node,x,y,rect) {
  const preferredWidths = {origin:[310,.78],signal:[330,.82],scarlet:[330,.82],wonder:[320,.82],universe:[450,.88]};
  const [pixels, ratio] = preferredWidths[node.dataset.blueprintId] || [330,.82];
  const width = Math.min(pixels, rect.width <= 580 ? rect.width - 28 : rect.width * ratio);
  const left = Math.max(12, Math.min(rect.width - width - 12, x - width/2));
  node.style.setProperty('--object-width', `${width}px`);
  node.style.setProperty('--body-offset', `${left - x}px`);
  node.style.setProperty('--growth-origin', `${Math.max(0,Math.min(100,(x-left)/width*100))}%`);
  const mobile = rect.width <= 580;
  const sceneHeight = {origin:290,signal:335,scarlet:290,wonder:270,universe:395}[node.dataset.blueprintId] || 335;
  const above = y - (mobile ? 62 : 24);
  const below = rect.height - y - (mobile ? 112 : 24);
  const growDown = mobile ? (below >= sceneHeight || below > above) && above < sceneHeight : y < 240;
  node.classList.toggle('grow-down',growDown);
  node.style.setProperty('--space-height', `${Math.max(110, (growDown ? below : above) - 10)}px`);
  node.style.setProperty('--x',`${x}px`);
  node.style.setProperty('--y',`${y}px`);
}

function removePrevious(blueprintId) {
  for (let index = instances.length - 1; index >= 0; index--) {
    const instance = instances[index];
    if (instance.blueprint.id !== blueprintId) continue;
    if (focusedId === instance.id) focusedId = null;
    instance.element.remove();
    instance.pulse?.remove();
    instances.splice(index, 1);
  }
}

function materialize(blueprint,x,y,{id=nextId++,visible=true,variant=0,animate=true,persist=true}={}) {
  const rect = room.getBoundingClientRect();
  removePrevious(blueprint.id);
  const node = document.createElement('div');
  node.className = `world-object ${blueprint.kind}`;
  node.dataset.blueprintId = blueprint.id;
  if (!animate) node.classList.add('restored');
  positionNode(node,x,y,rect);
  node.style.setProperty('--tone',blueprint.tone);
  node.innerHTML = `<button class="anchor" type="button" aria-label="${safe(blueprint.label)} öffnen" title="Szene öffnen"></button><div class="object-body">${sceneMarkup(blueprint,variant)}</div><button class="object-hide" type="button" aria-label="${safe(blueprint.label)} ausblenden" title="Diese Szene ausblenden">×</button>`;
  const instance = {id,blueprint,element:node,visible,variant,x,y,rx:x/rect.width,ry:y/rect.height};
  instances.push(instance);
  focusedId = id;
  world.append(node);
  node.hidden=!visible;
  node.querySelector('.anchor').addEventListener('click', event => { event.stopPropagation(); focusedId=id; updateLayers(); say(`${blueprint.label} geöffnet.`); });
  node.querySelector('.object-hide').addEventListener('click', event => { event.stopPropagation(); toggleInstance(id); });
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
  const x = clientX - rect.left;
  const y = clientY - rect.top;
  const variant = blueprint.id === 'scarlet' ? (x >= rect.width/2 ? 2 : 0) + (y >= rect.height/2 ? 1 : 0) : Math.floor(Math.random() * 3);
  materialize(blueprint,x,y,{variant});
  if (blueprints[progress]?.id === blueprint.id) {
    progress++;
    updateStory();
  }
  say(`${blueprint.label} ist erschienen. ${storyPrompt.textContent}`);
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
  progress=0;
  panelOpen=false;
  focusedId=null;
  world.replaceChildren();
  throwLayer.replaceChildren();
  updateStory();
  updateLayers();
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* Session still clears. */ }
  say('Die Geschichte beginnt von vorn. Greif die erste Kugel.');
});

$('#layers-toggle').addEventListener('click', event => {
  event.stopPropagation();
  panelOpen = !panelOpen;
  updateLayers();
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
  try { raw=localStorage.getItem(STORAGE_KEY); } catch { updateStory(); return; }
  if (!raw) { updateStory(); return; }
  try {
    const rect=room.getBoundingClientRect();
    const decoded=decodeRoom(raw,new Set(blueprints.map(item=>item.id)),rect.width,rect.height);
    const records=latestByBlueprint(decoded);
    for (const record of records) {
      materialize(findCapsule(record.blueprintId),record.x,record.y,{id:record.id,visible:record.visible,variant:record.variant,animate:false,persist:false});
      nextId=Math.max(nextId,record.id+1);
    }
    while (progress < blueprints.length && instances.some(item => item.blueprint.id === blueprints[progress].id)) progress++;
    updateStory();
    if (records.length) say(`${records.length} Szenen im Raum. ${storyPrompt.textContent}`);
    if (records.length !== decoded.length) saveRoom();
  } catch { updateStory(); say('Gespeicherter Raum ist ungültig; diese Ansicht beginnt leer.'); }
}

window.addEventListener('resize', () => {
  const rect=room.getBoundingClientRect();
  for (const instance of instances) {
    instance.x=instance.rx*rect.width; instance.y=instance.ry*rect.height;
    positionNode(instance.element,instance.x,instance.y,rect);
  }
});

restoreRoom();
