import {BLUEPRINT_VERSION, blueprints} from './blueprints.js';

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
const instances = [];
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

function isPlaceable(clientX, clientY) {
  const box = room.getBoundingClientRect();
  if (clientX < box.left || clientX > box.right || clientY < box.top || clientY > box.bottom) return false;
  const target = document.elementFromPoint(clientX, clientY);
  return !target?.closest('.chrome, .dock, .help-panel, .layers-panel, .world-object');
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

function toggleInstance(id) {
  const instance = instances.find(item => item.id === id);
  if (!instance) return;
  instance.visible = !instance.visible;
  instance.element.hidden = !instance.visible;
  updateLayers();
  say(`${instance.blueprint.label} ${instance.visible ? 'eingeblendet' : 'ausgeblendet'}. Andere Objekte bleiben stehen.`);
}

async function place(blueprint, clientX, clientY, fromX, fromY) {
  if (!blueprint || instances.length >= 20) { say('Der Raum enthält schon 20 Objekte. Einzelne ausblenden oder den Raum leeren.'); return; }
  const ownGeneration = generation;
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
  say(`${blueprint.label} fliegt zum gewählten Punkt.`);
  await flight.finished.catch(()=>{});
  flying.remove();
  if (ownGeneration !== generation) return;
  const rect = room.getBoundingClientRect();
  const x = clientX-rect.left, y=clientY-rect.top;
  const node = document.createElement('div');
  node.className = `world-object ${blueprint.kind}`;
  if (x < 190) node.classList.add('grow-right');
  else if (x > rect.width-190) node.classList.add('grow-left');
  if (y < 240) node.classList.add('grow-down');
  node.style.setProperty('--x',`${x}px`);
  node.style.setProperty('--y',`${y}px`);
  node.style.setProperty('--tone',blueprint.tone);
  node.innerHTML = `<span class="anchor" aria-hidden="true"></span><div class="object-body">${sceneMarkup(blueprint)}</div><button class="object-hide" type="button" aria-label="${safe(blueprint.label)} ausblenden" title="Dieses Objekt ausblenden">×</button>`;
  const id = nextId++;
  const instance = {id,blueprint,element:node,visible:true,x,y};
  instances.push(instance);
  world.append(node);
  node.querySelector('.object-hide').addEventListener('click', event => { event.stopPropagation(); toggleInstance(id); });
  connectTool(node);
  updateLayers();
  const pulse = document.createElement('span'); pulse.className='ground-pulse'; pulse.style.left=`${x}px`; pulse.style.top=`${y}px`; pulse.style.setProperty('--tone',blueprint.tone); world.append(pulse);
  pulse.addEventListener('animationend',()=>pulse.remove(),{once:true});
  say(`${blueprint.label} ist am gewählten Ort gewachsen. ${instances.length} Objekt${instances.length===1?'':'e'} im Raum.`);
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
  instances.length=0;
  nextId=1;
  world.replaceChildren();
  throwLayer.replaceChildren();
  openingHint.hidden=false;
  updateLayers();
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

renderCapsules();
