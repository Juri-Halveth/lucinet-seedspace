import {BOARD,addSlot,moveSlot,renewSlot,releaseSlot,advanceNotebook,demoNotebook,slotStatus,validNotebook} from './notebook-model.js?v=1';

const $ = selector => document.querySelector(selector);
const STORE='lucinet.seedspace.notebook-lab.v1';
const board=$('#board');
let state=load();
let selectedId=state.slots[0]?.id ?? null;
let mode='inspect';
let noticeTimer;

function load() {
  try {
    const raw=localStorage.getItem(STORE);
    if (raw && raw.length<250_000) {
      const parsed=JSON.parse(raw);
      if (validNotebook(parsed)) return parsed;
    }
  } catch { /* Start with the demo when local storage is unavailable. */ }
  return demoNotebook();
}

function persist() { try { localStorage.setItem(STORE,JSON.stringify(state)); } catch { message('Lokales Speichern ist hier nicht verfügbar. Exportiere den Zustand als JSON.'); } }
function message(text) {
  const box=$('#notice'); box.textContent=text;
  clearTimeout(noticeTimer);
  noticeTimer=setTimeout(()=>{ box.textContent=''; },6500);
}
function apply(operation,success) {
  try { state=operation(); persist(); render(); if (success) message(success); }
  catch(error) { message(error.message); }
}
function pxToModel(event) {
  const rect=board.getBoundingClientRect();
  return {x:Math.round((event.clientX-rect.left)/rect.width*BOARD.width),y:Math.round((event.clientY-rect.top)/rect.height*BOARD.height)};
}
function position(element,x,y,radius) {
  element.style.left=`${x/BOARD.width*100}%`;
  element.style.top=`${y/BOARD.height*100}%`;
  element.style.width=`${radius*2/BOARD.width*100}%`;
  element.style.aspectRatio='1';
  element.style.transform='translate(-50%,-50%)';
}
function setMode(next) {
  mode=next;
  const armed=mode==='place' || mode==='move';
  board.classList.toggle('armed',armed);
  $('#ghost').hidden=!armed;
  $('#arm').textContent=mode==='place' ? 'Platzwahl beenden ×' : 'Im Raum wählen ↗';
  $('#board-help').textContent=mode==='place' ? 'Jetzt im Raum auf einen freien Ort klicken. Esc bricht ab.' : mode==='move' ? 'Neuen Ort für die ausgewählte Kugel anklicken. Esc bricht ab.' : 'Platz vorbereiten, dann in den Raum klicken. Für Tastaturbedienung X und Y eintragen und „An Position setzen“ wählen.';
}
function renderBalls() {
  const layer=$('#ball-layer'); layer.replaceChildren();
  const list=$('#slot-list'); list.replaceChildren();
  for (const slot of state.slots) {
    const button=document.createElement('button');
    button.type='button'; button.className='ball';
    if (slot.id===selectedId) button.classList.add('selected');
    if (slotStatus(slot,state.day)==='grace') button.classList.add('grace');
    button.setAttribute('aria-label',`${slot.id}: ${slot.title}, Laufzeit bis ${slot.termEndsAt}`);
    button.title=`${slot.id} · ${slot.title}`;
    const label=document.createElement('span'); label.textContent=slot.title; button.append(label);
    position(button,slot.x,slot.y,slot.radius);
    button.addEventListener('click',event=>{event.stopPropagation();selectedId=slot.id;setMode('inspect');render();});
    layer.append(button);
    const row=makeButton(`${slot.id} · ${slot.title}`,()=>{selectedId=slot.id;setMode('inspect');render();});
    if(slot.id===selectedId) row.setAttribute('aria-current','true');
    list.append(row);
  }
}
function makeButton(text,action) {
  const button=document.createElement('button');button.type='button';button.className='secondary';button.textContent=text;button.addEventListener('click',action);return button;
}
function renderSelection() {
  const box=$('#selection-content');box.replaceChildren();
  const slot=state.slots.find(item=>item.id===selectedId);
  if (!slot) {const p=document.createElement('p');p.className='muted';p.textContent='Wähle eine Kugel im Raum.';box.append(p);return;}
  const id=document.createElement('span');id.className='slot-id';id.textContent=slot.id;
  const title=document.createElement('h3');title.textContent=slot.title;
  const text=document.createElement('p');text.textContent=slot.text;
  const status=document.createElement('span');status.className='status';status.textContent=slotStatus(slot,state.day)==='grace' ? `Nachfrist bis ${new Date(Date.parse(slot.termEndsAt+'T00:00:00Z')+BOARD.graceDays*86_400_000).toISOString().slice(0,10)}` : `Laufzeit bis ${slot.termEndsAt}`;
  const detail=document.createElement('p');detail.className='fine';detail.textContent=`Ort ${slot.x} / ${slot.y} · Radius ${slot.radius} · ${slot.terms} Monat(e) · Ehrenscore ${slot.honor}`;
  const actions=document.createElement('div');actions.className='form-actions';
  actions.append(
    makeButton('Monat simulieren +',()=>apply(()=>renewSlot(state,slot.id),'Laufzeit simuliert verlängert. Keine Zahlung ausgelöst.')),
    makeButton('Versetzen ↗',()=>{setMode('move');message('Wähle im Raum einen freien Zielpunkt.');}),
    makeButton('Freigeben',()=>apply(()=>{selectedId=null;return releaseSlot(state,slot.id);},'Platz freigegeben; die Notiz bleibt im lokalen Exportarchiv.'))
  );
  box.append(id,title,text,status,detail,actions);
}
function renderLog() {
  const list=$('#event-log');list.replaceChildren();
  for (const item of state.events.slice(0,5)) {
    const li=document.createElement('li');const time=document.createElement('time');time.textContent=item.day;const span=document.createElement('span');span.textContent=item.message;li.append(time,span);list.append(li);
  }
}
function render() {
  $('#count').textContent=`${state.slots.length} / ${BOARD.maxSlots} Plätze`;
  const area=state.slots.reduce((sum,slot)=>sum+Math.PI*slot.radius*slot.radius,0)/(BOARD.width*BOARD.height)*100;
  $('#area').textContent=`${area.toFixed(1).replace('.',',')} % Kugelfläche`;
  $('#day').textContent=new Intl.DateTimeFormat('de-DE',{dateStyle:'long',timeZone:'UTC'}).format(new Date(`${state.day}T00:00:00Z`));
  $('#archive-count').textContent=`${state.archive.length} freigegebene Einträge bleiben im lokalen Exportarchiv. Eine öffentliche Kopie lässt sich damit nicht löschen.`;
  renderBalls();renderSelection();renderLog();
}

$('#radius-input').addEventListener('input',event=>{ $('#radius-value').textContent=event.target.value; });
$('#arm').addEventListener('click',()=>{setMode(mode==='place'?'inspect':'place'); if(mode==='place') message('Klicke jetzt auf einen freien Ort im Raum.');});
$('#new-form').addEventListener('submit',event=>{
  event.preventDefault();
  const input={title:$('#title-input').value,text:$('#text-input').value,radius:Number($('#radius-input').value),x:Number($('#x-input').value),y:Number($('#y-input').value)};
  apply(()=>{const next=addSlot(state,input);selectedId=next.slots.at(-1).id;setMode('inspect');return next;},'Testkugel platziert.');
});
board.addEventListener('click',event=>{
  if (mode==='inspect') return;
  const {x,y}=pxToModel(event);
  $('#x-input').value=x;$('#y-input').value=y;
  if (mode==='move') apply(()=>{const next=moveSlot(state,selectedId,x,y);setMode('inspect');return next;},'Kugel versetzt.');
  else apply(()=>{const next=addSlot(state,{title:$('#title-input').value,text:$('#text-input').value,radius:Number($('#radius-input').value),x,y});selectedId=next.slots.at(-1).id;setMode('inspect');return next;},'Testkugel platziert.');
});
board.addEventListener('pointermove',event=>{if(mode==='inspect')return;const {x,y}=pxToModel(event);position($('#ghost'),x,y,mode==='move' ? state.slots.find(slot=>slot.id===selectedId)?.radius ?? 56 : Number($('#radius-input').value));});
window.addEventListener('keydown',event=>{if(event.key==='Escape' && mode!=='inspect'){setMode('inspect');message('Platzwahl beendet.');}});
$('#advance-7').addEventListener('click',()=>apply(()=>advanceNotebook(state,7),'Simulationszeit: +7 Tage.'));
$('#advance-30').addEventListener('click',()=>apply(()=>advanceNotebook(state,30),'Simulationszeit: +30 Tage.'));
$('#reset-demo').addEventListener('click',()=>apply(()=>{const next=demoNotebook();selectedId=next.slots[0].id;setMode('inspect');return next;},'Demo neu geladen. Vorherigen Zustand bei Bedarf zuvor exportieren.'));
$('#export-all').addEventListener('click',()=>{
  const blob=new Blob([JSON.stringify(state,null,2)+'\n'],{type:'application/json'});
  const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='seedspace-notizheft-labor.json';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60_000);
  message('Lokaler Zustand samt Archiv exportiert.');
});
render();
