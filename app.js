import {BLUEPRINT_VERSION, blueprints} from './blueprints.js';
import {encodeRoom, decodeRoom, latestByBlueprint} from './room-state.js';
import {compileWish, MAX_WISH_CHARS} from './wish-engine.js?v=3';

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
const wishOpen = $('#wish-open');
const wishwell = $('#wishwell');
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
let lastWish = null;
let wishDraft = '';
let wishThrown = false;
const wishBlueprint = {id:'wish',label:'DEIN WUNSCH',kind:'wish',tone:'#ff315b',icon:'✦'};

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
  if (progress === blueprints.length && wishDraft) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'capsule is-next wish-capsule';
    button.dataset.id = wishBlueprint.id;
    button.style.setProperty('--tone',wishBlueprint.tone);
    button.setAttribute('aria-label','Deine rote Wunschkugel. Greifen und in den Raum ziehen oder antippen und Zielpunkt wählen.');
    button.setAttribute('aria-pressed','false');
    button.innerHTML = '<span class="orb"><span>✦</span></span><span class="capsule-name">DEIN WUNSCH</span>';
    button.addEventListener('pointerdown', event => startDrag(event,wishBlueprint,button));
    button.addEventListener('click', () => { if (Date.now() >= suppressClickUntil) selectCapsule(wishBlueprint); });
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
    wishThrown ? 'Dein Wunsch lebt im Raum.' : wishDraft ? 'Wirf deine rote Kugel.' : 'Jetzt ist deine Kugel dran.'
  ];
  storyPrompt.textContent = prompts[progress];
  storyCounter.textContent = progress === blueprints.length ? '∞ / 05' : String(progress + 1).padStart(2, '0') + ' / 05';
  room.dataset.stage = String(progress);
  openingHint.hidden = progress > 0;
  $('.story-rail').hidden = progress === 0 || (progress === blueprints.length && !wishDraft);
  wishOpen.hidden = progress !== blueprints.length || !!wishDraft;
  room.dataset.wish = wishThrown ? 'thrown' : wishDraft ? 'ready' : 'empty';
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
  if (target?.closest('.chrome, .dock, .help-panel, .layers-panel, .wish-open, .wishwell')) return false;
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
    case 'wish':
      return `<article class="scene-card wish-scene"><span class="scene-index">DEIN WURF / DEIN TEXT</span><div class="wish-scene-star" aria-hidden="true">✦</div><h2>${safe(lastWish?.analysis.title || 'Dein Wunsch')}</h2><p class="wish-scene-kind">${safe(lastWish?.analysis.modeLabel || 'Wunschprozess')} · Prozess läuft</p><label for="wish-scene-search">In deinem Text suchen</label><input id="wish-scene-search" type="search" placeholder="Wort oder Gedanke"><div class="wish-scene-content" aria-live="polite"></div><details class="wish-original"><summary>Deinen vollständigen Text ansehen</summary><pre></pre></details><button class="wish-process-open" type="button">Wunschprozess und Code öffnen</button></article>`;
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
    localStorage.setItem(STORAGE_KEY, encodeRoom(instances.filter(item => item.blueprint.id !== 'wish'),rect.width,rect.height));
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
  const preferredWidths = {origin:[310,.78],signal:[330,.82],scarlet:[330,.82],wonder:[320,.82],universe:[450,.88],wish:[460,.9]};
  const [pixels, ratio] = preferredWidths[node.dataset.blueprintId] || [330,.82];
  const width = Math.min(pixels, rect.width <= 580 ? rect.width - 28 : rect.width * ratio);
  const left = Math.max(12, Math.min(rect.width - width - 12, x - width/2));
  node.style.setProperty('--object-width', `${width}px`);
  node.style.setProperty('--body-offset', `${left - x}px`);
  node.style.setProperty('--growth-origin', `${Math.max(0,Math.min(100,(x-left)/width*100))}%`);
  const mobile = rect.width <= 580;
  const sceneHeight = {origin:290,signal:335,scarlet:290,wonder:270,universe:395,wish:430}[node.dataset.blueprintId] || 335;
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

function installWishScene(node) {
  const content = node.querySelector('.wish-scene-content');
  const search = node.querySelector('#wish-scene-search');
  const result = lastWish;
  const program = result.program;
  node.querySelector('.wish-original pre').textContent = result.source.originalText;
  const sections = program.sections;
  let tasks = program.tasks.map(text => ({text,done:false}));
  function render() {
    content.replaceChildren();
    const query = search.value.toLocaleLowerCase();
    if (program.mode === 'tasks' && tasks.length) {
      for (const item of tasks) {
        if (!item.text.toLocaleLowerCase().includes(query)) continue;
        const label=document.createElement('label'); label.className='wish-scene-task';
        const checkbox=document.createElement('input'); checkbox.type='checkbox'; checkbox.checked=item.done;
        checkbox.addEventListener('change', () => { item.done=checkbox.checked; label.classList.toggle('done',item.done); });
        const span=document.createElement('span'); span.textContent=item.text; label.append(checkbox,span); content.append(label);
      }
    } else {
      for (const section of sections) {
        if (!(section.title+' '+section.text).toLocaleLowerCase().includes(query)) continue;
        const article=document.createElement('article'); article.className='wish-scene-section';
        const heading=document.createElement('strong'); heading.textContent=section.title;
        const body=document.createElement('p'); body.textContent=section.text;
        article.append(heading,body); content.append(article);
      }
    }
    if (!content.children.length) { const empty=document.createElement('p'); empty.textContent='Keine Treffer.'; content.append(empty); }
  }
  search.addEventListener('input',render);
  node.querySelector('.wish-process-open').addEventListener('click', event => {
    event.stopPropagation();
    if (!lastWish || !wishThrown) return;
    showWishResult(lastWish);
    setWishwell(true,'process');
  });
  render();
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
  if (blueprint.id === 'wish') installWishScene(node);
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
  if (blueprint.id === 'wish') {
    try { lastWish = compileWish(wishDraft); }
    catch (error) { say(error.message); return; }
    wishThrown = true;
    materialize(blueprint,x,y);
    updateStory();
    say('Dein Wunsch ist im Raum erschienen. Öffne danach den getrennten Wunschprozess für Code und JSON.');
    return;
  }
  const variant = blueprint.id === 'scarlet' ? (x >= rect.width/2 ? 2 : 0) + (y >= rect.height/2 ? 1 : 0) : Math.floor(Math.random() * 3);
  materialize(blueprint,x,y,{variant});
  if (blueprints[progress]?.id === blueprint.id) {
    progress++;
    updateStory();
  }
  say(`${blueprint.label} ist erschienen. ${storyPrompt.textContent}`);
}

room.addEventListener('click', event => {
  if (event.target.closest('.chrome, .dock, .help-panel, .layers-panel, .world-object, .wish-open, .wishwell')) return;
  if (!selected) { if (event.detail !== 0) say('Nimm unten eine der leuchtenden Kugeln.'); return; }
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

function resetRoom() {
  generation++;
  for (const pending of pendingThrows.values()) pending.flight.cancel();
  pendingThrows.clear();
  throwEpochs.clear();
  instances.length=0;
  nextId=1;
  progress=0;
  panelOpen=false;
  focusedId=null;
  wishDraft='';
  wishThrown=false;
  lastWish=null;
  wishText.value='';
  $('#wish-count').textContent=`0 / ${MAX_WISH_CHARS.toLocaleString('de-DE')} Zeichen`;
  $('#wish-result').hidden=true;
  world.replaceChildren();
  throwLayer.replaceChildren();
  updateStory();
  updateLayers();
  setWishwell(false);
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* Session still clears. */ }
  say('Die Geschichte beginnt von vorn. Greif die erste Kugel.');
  capsules.querySelector('.capsule')?.focus();
}
for (const selector of ['#clear-all','#reset-room']) {
  $(selector).addEventListener('click', event => { event.stopPropagation(); resetRoom(); });
}

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

function setWishwell(open, mode='compose') {
  wishwell.hidden = !open;
  if (open) {
    const process = mode === 'process' && wishThrown && lastWish;
    $('#wish-form').hidden = !!process;
    $('#wish-result').hidden = !process;
    $('#wish-title').textContent = process ? 'Dein Wunschprozess.' : 'Deine Sprache. Deine Kugel.';
    $('#wish-intro').textContent = process ? 'Diese Struktur und dieser Code entstanden nach dem Wurf deiner roten Kugel aus genau deinem Text.' : 'Schreib einen Wunsch oder füge eigenen Text ein. Daraus entsteht eine rote Kugel. Greif sie danach und wirf sie in den Raum: Erst dort entfaltet sich dein Text.';
    $('.wish-local-note').hidden = !process;
    (process ? $('#wish-close') : $('#wish-text')).focus();
  } else if (!wishOpen.hidden) wishOpen.focus();
}

wishOpen.addEventListener('click', event => { event.stopPropagation(); setWishwell(true); });
$('#wish-close').addEventListener('click', () => setWishwell(false));
wishwell.addEventListener('click', event => { if (event.target === wishwell) setWishwell(false); });
wishwell.addEventListener('keydown', event => {
  if (event.key === 'Escape') { event.preventDefault(); setWishwell(false); return; }
  if (event.key !== 'Tab') return;
  const focusable = [...wishwell.querySelectorAll('button,textarea,summary')].filter(item => !item.closest('[hidden]'));
  if (!focusable.length) return;
  if (event.shiftKey && document.activeElement === focusable[0]) { event.preventDefault(); focusable.at(-1).focus(); }
  else if (!event.shiftKey && document.activeElement === focusable.at(-1)) { event.preventDefault(); focusable[0].focus(); }
});

const wishText = $('#wish-text');
wishText.addEventListener('input', () => {
  $('#wish-count').textContent = `${wishText.value.length.toLocaleString('de-DE')} / ${MAX_WISH_CHARS.toLocaleString('de-DE')} Zeichen`;
  $('#wish-error').hidden = true;
});

const signalLabels = {'book':'Buchwort im Text','tasks':'Aufgaben','timeline':'Zeitspur','search':'Suche','quiz':'Quiz','external-api':'API','account':'Konto','database':'Datenbank','payment':'Zahlung','ai-model':'Sprachmodell'};
function showWishResult(result) {
  $('#wish-error').hidden = true;
  $('#wish-result').hidden = false;
  $('#wish-result-title').textContent = result.analysis.modeLabel;
  const sectionLabel = result.analysis.sections.length === 1 ? 'Abschnitt' : 'Abschnitte';
  $('#wish-result-summary').textContent = `${result.source.words.toLocaleString('de-DE')} Wörter · ${result.analysis.sections.length} ${sectionLabel} · eine eigenständige HTML-Datei im JSON`;
  const signalBox = $('#wish-signals'); signalBox.replaceChildren();
  for (const signal of result.analysis.signals) {
    const chip = document.createElement('span'); chip.textContent = signalLabels[signal.name] || signal.name; signalBox.append(chip);
  }
  if (!signalBox.children.length) { const chip=document.createElement('span'); chip.textContent='Freier Text'; signalBox.append(chip); }
  $('#wish-open-edges').textContent = result.analysis.openConnections.length ?
    result.analysis.openConnections.map(name => signalLabels[name] || name).join(' · ') + ' benötigen für echte Außenwirkung eine eigene Implementierung.' :
    'Die erzeugte Vorlage verwendet lokale Browserfunktionen.';
  const trace = $('#wish-requirements'); trace.replaceChildren();
  const candidates = result.analysis.statementCandidates;
  if (!candidates.length) {
    const item=document.createElement('li'); item.textContent='Struktur und Originaltext sind im JSON gebunden; eine ausdrückliche Muss/Soll-Anweisung wurde hier nicht erkannt.'; trace.append(item);
  } else {
    for (const candidate of candidates.slice(0,5)) { const item=document.createElement('li'); item.textContent=candidate.text; trace.append(item); }
    if (result.analysis.statementCandidateCount > 5) { const item=document.createElement('li'); item.textContent=`${result.analysis.statementCandidateCount - 5} weitere Textstellen im JSON.`; trace.append(item); }
  }
  $('#wish-json-preview').textContent = JSON.stringify({schema:result.schema,source:result.source,analysis:result.analysis,program:result.program,artifact:{entry:result.artifact.entry,format:result.artifact.format}},null,2);
  $('#wish-code-preview').textContent = result.artifact.files[0].content.slice(0,1600) + '\n…';
}

$('#wish-form').addEventListener('submit', event => {
  event.preventDefault();
  try {
    const text = wishText.value;
    if (!text.trim()) throw new Error('Schreib zuerst etwas in deine rote Kugel.');
    if (text.length > MAX_WISH_CHARS) throw new Error('Der Text ist zu lang.');
    const validUntilThrow = text;
    removePrevious(wishBlueprint.id);
    updateLayers();
    wishDraft = validUntilThrow;
    wishThrown = false;
    lastWish = null;
    $('#wish-result').hidden = true;
    setWishwell(false);
    updateStory();
    say('Die rote Kugel trägt deinen Text. Wirf sie jetzt in den Raum.');
  } catch (error) {
    $('#wish-error').textContent = error.message;
    $('#wish-error').hidden = false;
  }
});

$('#wish-new').addEventListener('click', () => { wishText.value=''; wishText.dispatchEvent(new Event('input')); setWishwell(true,'compose'); });
$('#wish-run').addEventListener('click', () => {
  if (!wishThrown || !lastWish) return;
  setWishwell(false);
  const active = instances.find(item => item.blueprint.id === 'wish' && item.visible);
  if (active) { focusedId=active.id; updateLayers(); active.element.querySelector('#wish-scene-search')?.focus(); }
});

function deliverFile(content, type, name) {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const anchor = document.createElement('a'); anchor.href=url; anchor.download=name; document.body.append(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
$('#wish-download-json').addEventListener('click', () => { if (lastWish) deliverFile(JSON.stringify(lastWish,null,2),'application/json;charset=utf-8','lucinet-wunschkugel.json'); });
$('#wish-download-html').addEventListener('click', () => { if (lastWish) deliverFile(lastWish.artifact.files[0].content,'text/html;charset=utf-8','lucinet-wunschkugel.html'); });

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
