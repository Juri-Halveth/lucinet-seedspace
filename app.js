import {BLUEPRINT_VERSION, blueprints} from './blueprints.js';

const $ = (selector) => document.querySelector(selector);
const room = $('#room');
const projection = $('#projection');
const throwLayer = $('#throw-layer');
const welcome = $('#welcome');
const capsuleContainer = $('#capsules');
const status = $('#live-status');
const manifest = $('#manifest-preview');
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
let selected = null;
let lastPlacement = null;
let busy = false;
let generation = 0;

const sampleManifest = {
  schema: BLUEPRINT_VERSION,
  capsule: {id: 'garden', parameters: {variant: 'luminous-flower'}},
  placement: {surface: 'browser-stage', x: 'pointer', y: 'pointer'},
  sequence: ['trigger', 'impact', 'unfold', 'interactive-scene'],
  renderer: 'registered-local-component'
};
manifest.textContent = JSON.stringify(sampleManifest, null, 2);

const escapeHTML = (value) => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const wait = (milliseconds) => new Promise(resolve => setTimeout(resolve, milliseconds));

function setStatus(message) { status.textContent = message; }

function renderCapsules() {
  capsuleContainer.replaceChildren();
  for (const capsule of blueprints) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'capsule';
    button.draggable = true;
    button.dataset.id = capsule.id;
    button.style.setProperty('--tone', capsule.tone);
    button.setAttribute('aria-pressed', String(selected?.id === capsule.id));
    button.setAttribute('aria-label', `${capsule.label}: ${capsule.description} Auswählen, dann im Raum platzieren.`);
    button.innerHTML = `<span class="capsule-orb"><span>${escapeHTML(capsule.icon)}</span></span><span class="capsule-copy"><strong>${escapeHTML(capsule.label)}</strong><small>${escapeHTML(capsule.description)}</small></span><span class="capsule-arrow" aria-hidden="true">↗</span>`;
    button.addEventListener('click', () => selectCapsule(capsule.id));
    button.addEventListener('dragstart', event => { selectCapsule(capsule.id); event.dataTransfer.setData('text/plain', capsule.id); event.dataTransfer.effectAllowed = 'copy'; });
    capsuleContainer.append(button);
  }
}

function selectCapsule(id) {
  selected = blueprints.find(item => item.id === id) ?? null;
  capsuleContainer.querySelectorAll('.capsule').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.id === id)));
  if (selected) { setStatus(`${selected.label} gewählt. Klicke in den Raum oder ziehe die Kapsel hinein.`); room.focus({preventScroll:true}); }
}

function localPoint(clientX, clientY) {
  const box = room.getBoundingClientRect();
  return {x: Math.max(46, Math.min(box.width - 46, clientX - box.left)), y: Math.max(70, Math.min(box.height - 88, clientY - box.top))};
}

function buildScene(capsule) {
  switch (capsule.kind) {
    case 'profile': return `<article class="reveal-card profile-card"><span class="scene-label">SEED 01 / MENSCH</span><div class="profile-glyph">J<span>·</span></div><div><p class="card-kicker">AUS EINEM PUNKT WIRD EINE GESCHICHTE</p><h3>Hallo, ich bin <em>Juri.</em></h3><p>Ich baue HALVETH und LUCINET: Räume zum Beobachten, Vergleichen, Erforschen und Gestalten. Diese Kapsel ist eine neue Form, Projekte zu zeigen — zuerst als Erfahrung, dann als Inhalt.</p><div class="card-tags"><span>FORSCHUNG</span><span>CODE</span><span>VISUELLE WELTEN</span></div></div></article>`;
    case 'garden': return `<article class="reveal-card garden-card"><span class="scene-label">SEED 02 / WACHSTUM</span><div class="plant-art" aria-hidden="true"><div class="plant-aura"></div><div class="plant-stem"></div><div class="plant-leaf left"></div><div class="plant-leaf right"></div><div class="plant-flower"><i></i><i></i><i></i><i></i><i></i><b></b></div><div class="plant-ground"></div></div><div class="garden-copy"><p class="card-kicker">GLEICHER AUSLÖSER · ANDERER BAUPLAN</p><h3>Ein Garten <em>aus Licht.</em></h3><p>Die Kapsel setzt Wurzel, Stiel, Blätter und Blüte zu einer Szene zusammen. Der sichtbare Wuchs ist eine Animation; die Pflanze bleibt als Objekt im Raum.</p></div></article>`;
    case 'projects': return `<article class="reveal-card atlas-card"><span class="scene-label">SEED 03 / ATLAS</span><p class="card-kicker">DREI PFADE · EIN URSPRUNG</p><h3>HALVETH <em>Universum.</em></h3><div class="project-list"><div><span>01</span><strong>RED ROOM</strong><small>Quellenräume und kritische Recherche</small></div><div><span>02</span><strong>LUCINET</strong><small>Beobachtung, Vergleich und Projektion</small></div><div><span>03</span><strong>MORROWIND</strong><small>Spielwelt, Atmosphäre und Gestaltung</small></div></div><p class="atlas-foot">Ein Portfolio kann als Folge eigenständiger Kapseln entstehen.</p></article>`;
    case 'tool': return `<article class="reveal-card tool-card"><span class="scene-label">SEED 04 / WERKZEUG</span><p class="card-kicker">EIN FUNKTIONIERENDES MINI-WERKZEUG</p><h3>Microvalue <em>Studio.</em></h3><p>Verteile einen Cent auf vier Anteile. Das Restfeld wird sofort berechnet.</p><div class="tool-grid"><label>Anteil A <input type="number" min="0" max="100" value="24" inputmode="decimal"></label><label>Anteil B <input type="number" min="0" max="100" value="24" inputmode="decimal"></label><label>Anteil C <input type="number" min="0" max="100" value="24" inputmode="decimal"></label><label>Anteil D <input type="number" min="0" max="100" value="24" inputmode="decimal"></label></div><div class="tool-result" aria-live="polite">Rest: <strong data-rest>4 %</strong><small data-euro>0,0004 €</small></div><p class="tool-error" data-error role="alert"></p></article>`;
    default: throw new Error('Unknown scene type');
  }
}

function connectTool() {
  const card = projection.querySelector('.tool-card');
  if (!card) return;
  const inputs = [...card.querySelectorAll('input')];
  const update = () => {
    const nums = inputs.map(input => Number(input.value));
    const total = nums.reduce((a,b) => a+b, 0);
    const valid = nums.every(n => Number.isFinite(n) && n >= 0 && n <= 100) && total <= 100;
    card.querySelector('[data-error]').textContent = valid ? '' : 'Anteile müssen zwischen 0 und 100 liegen und zusammen höchstens 100 ergeben.';
    card.querySelector('[data-rest]').textContent = valid ? `${Math.round((100-total)*100)/100} %` : '—';
    card.querySelector('[data-euro]').textContent = valid ? `${((100-total)/10000).toFixed(4).replace('.',',')} €` : '—';
  };
  inputs.forEach(input => input.addEventListener('input', update));
  update();
}

async function place(capsule, point) {
  if (!capsule || busy) return;
  busy = true;
  const ownGeneration = ++generation;
  lastPlacement = {id:capsule.id, point};
  $('#clear').disabled = false;
  $('#replay').disabled = true;
  welcome.hidden = true;
  projection.replaceChildren();
  throwLayer.replaceChildren();
  room.style.setProperty('--impact-x', `${point.x}px`);
  room.style.setProperty('--impact-y', `${point.y}px`);
  const orb = document.createElement('div');
  orb.className = 'flying-orb';
  orb.style.setProperty('--tone', capsule.tone);
  throwLayer.append(orb);
  const box = room.getBoundingClientRect();
  const fromX = box.width * .5;
  const fromY = box.height + 18;
  const duration = reduceMotion.matches ? 1 : 680;
  const animation = orb.animate([
    {transform:`translate(${fromX}px,${fromY}px) scale(.62)`,opacity:.1},
    {transform:`translate(${(fromX+point.x)/2}px,${Math.min(fromY,point.y)-110}px) scale(1.15)`,opacity:1,offset:.55},
    {transform:`translate(${point.x}px,${point.y}px) scale(.65)`,opacity:1}
  ],{duration,easing:'cubic-bezier(.22,.7,.2,1)',fill:'forwards'});
  setStatus(`${capsule.label} fliegt in den Raum.`);
  await animation.finished.catch(()=>{});
  if (ownGeneration !== generation) return;
  orb.remove();
  const burst = document.createElement('div'); burst.className = 'impact-burst'; burst.style.setProperty('--tone', capsule.tone); throwLayer.append(burst);
  room.classList.remove('impact'); void room.offsetWidth; room.classList.add('impact');
  setStatus(`${capsule.label} ist gelandet. Bauplan entfaltet sich.`);
  if (!reduceMotion.matches) await wait(420);
  if (ownGeneration !== generation) return;
  projection.innerHTML = buildScene(capsule);
  projection.style.setProperty('--tone', capsule.tone);
  projection.classList.remove('visible'); void projection.offsetWidth; projection.classList.add('visible');
  connectTool();
  if (!reduceMotion.matches) await wait(580);
  if (ownGeneration !== generation) return;
  burst.remove(); room.classList.remove('impact'); busy = false;
  $('#replay').disabled = false;
  setStatus(`${capsule.label} entfaltet. Du kannst eine andere Kapsel wählen.`);
}

room.addEventListener('click', event => {
  if (event.target.closest('input, label, button, a, summary, details, .reveal-card')) return;
  if (!selected) { setStatus('Wähle zuerst unten eine Kapsel.'); return; }
  place(selected, localPoint(event.clientX,event.clientY));
});
room.addEventListener('keydown', event => {
  if (event.target !== room || !['Enter',' '].includes(event.key)) return;
  event.preventDefault();
  if (!selected) { setStatus('Wähle zuerst unten eine Kapsel.'); return; }
  const box=room.getBoundingClientRect(); place(selected,{x:box.width/2,y:box.height*.56});
});
room.addEventListener('dragover', event => { event.preventDefault(); room.classList.add('dragover'); event.dataTransfer.dropEffect='copy'; });
room.addEventListener('dragleave', event => { if (!room.contains(event.relatedTarget)) room.classList.remove('dragover'); });
room.addEventListener('drop', event => { event.preventDefault(); room.classList.remove('dragover'); const capsule=blueprints.find(item=>item.id===event.dataTransfer.getData('text/plain')) ?? selected; place(capsule,localPoint(event.clientX,event.clientY)); });
$('#clear').addEventListener('click', () => { generation++; busy=false; projection.replaceChildren(); throwLayer.replaceChildren(); welcome.hidden=false; room.classList.remove('impact'); $('#clear').disabled=true; $('#replay').disabled=true; lastPlacement=null; setStatus('Raum geleert. Wähle eine Kapsel.'); });
$('#replay').addEventListener('click', () => { if (lastPlacement) { const capsule=blueprints.find(item=>item.id===lastPlacement.id); place(capsule,lastPlacement.point); } });
renderCapsules();
