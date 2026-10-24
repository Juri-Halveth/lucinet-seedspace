export const NOTEBOOK_SCHEMA = 'seedspace.notebook-lab.v1';
export const BOARD = Object.freeze({width:1000,height:620,maxSlots:8,minRadius:40,maxRadius:82,gap:18,graceDays:7});

function dateOnly(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('Ungültiges Simulationsdatum.');
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime()) || date.toISOString().slice(0,10) !== value) throw new Error('Ungültiges Simulationsdatum.');
  return date;
}

function iso(date) { return date.toISOString().slice(0,10); }

export function addDays(day, count) {
  if (!Number.isInteger(count) || count < 0 || count > 3660) throw new Error('Ungültiger Zeitsprung.');
  const date = dateOnly(day);
  date.setUTCDate(date.getUTCDate() + count);
  return iso(date);
}

// All renewals use the original start day as their anchor: Jan 31 -> Feb 28 -> Mar 31.
export function termEnd(startAt, terms) {
  if (!Number.isInteger(terms) || terms < 1 || terms > 120) throw new Error('Ungültige Laufzeit.');
  const start = dateOnly(startAt);
  const year = start.getUTCFullYear();
  const month = start.getUTCMonth() + terms;
  const lastDay = new Date(Date.UTC(year,month + 1,0)).getUTCDate();
  return iso(new Date(Date.UTC(year,month,Math.min(start.getUTCDate(),lastDay))));
}

export function createNotebook(day = new Date().toISOString().slice(0,10)) {
  dateOnly(day);
  return {schema:NOTEBOOK_SCHEMA,day,nextId:1,slots:[],archive:[],events:[]};
}

function copy(state) {
  return {...state,slots:state.slots.map(slot=>({...slot})),archive:state.archive.map(slot=>({...slot})),events:[...state.events]};
}

function note(state, message) {
  state.events.unshift({day:state.day,message});
  state.events = state.events.slice(0,100);
}

function fit(state, x, y, radius, exceptId = null) {
  if (![x,y,radius].every(Number.isFinite)) throw new Error('Ort und Größe müssen Zahlen sein.');
  if (radius < BOARD.minRadius || radius > BOARD.maxRadius) throw new Error(`Radius: ${BOARD.minRadius}–${BOARD.maxRadius}.`);
  if (x-radius < 0 || y-radius < 0 || x+radius > BOARD.width || y+radius > BOARD.height) throw new Error('Diese Kugel ragt über die Raumgrenze.');
  const occupied = state.slots.find(slot => slot.id !== exceptId && Math.hypot(x-slot.x,y-slot.y) < radius+slot.radius+BOARD.gap);
  if (occupied) throw new Error(`Zu nah an ${occupied.id}: ${BOARD.gap} Einheiten Abstand sind nötig.`);
}

function nextEvent(state, message) { note(state,message); return state; }

export function addSlot(state, {title,text,x,y,radius}) {
  if (!validNotebook(state)) throw new Error('Der gespeicherte Notizraum ist ungültig.');
  if (state.nextId >= Number.MAX_SAFE_INTEGER) throw new Error('Die sichere Zahl der Platzadressen ist ausgeschöpft.');
  if (state.slots.length >= BOARD.maxSlots) throw new Error('Alle acht Plätze sind belegt.');
  title = String(title ?? '').trim(); text = String(text ?? '').trim();
  if (!title || title.length > 48) throw new Error('Titel: 1–48 Zeichen.');
  if (!text || text.length > 280) throw new Error('Text: 1–280 Zeichen.');
  fit(state,x,y,radius);
  const next = copy(state);
  const id = `K${String(next.nextId++).padStart(2,'0')}`;
  next.slots.push({id,title,text,x,y,radius,startAt:next.day,terms:1,termEndsAt:termEnd(next.day,1),honor:0});
  return nextEvent(next,`${id} platziert · erster Simulationsmonat`);
}

export function moveSlot(state,id,x,y) {
  const slot = state.slots.find(item=>item.id===id);
  if (!slot) throw new Error('Platz nicht gefunden.');
  fit(state,x,y,slot.radius,id);
  const next = copy(state);
  const moved = next.slots.find(item=>item.id===id);
  moved.x=x; moved.y=y;
  return nextEvent(next,`${id} versetzt · Laufzeit unverändert`);
}

export function slotStatus(slot,day) {
  dateOnly(day);
  return day <= slot.termEndsAt ? 'active' : day <= addDays(slot.termEndsAt,BOARD.graceDays) ? 'grace' : 'released';
}

export function renewSlot(state,id) {
  const slot = state.slots.find(item=>item.id===id);
  if (!slot) throw new Error('Platz nicht gefunden.');
  if (slotStatus(slot,state.day)==='released') throw new Error('Die Nachfrist ist abgelaufen; der Platz ist frei.');
  if (slot.terms >= 120) throw new Error('Maximale Simulationslaufzeit erreicht.');
  const next = copy(state);
  const renewed = next.slots.find(item=>item.id===id);
  const onTime = slotStatus(slot,state.day)==='active';
  renewed.terms++;
  renewed.termEndsAt=termEnd(renewed.startAt,renewed.terms);
  if (onTime) renewed.honor++;
  return nextEvent(next,`${id} simuliert verlängert bis ${renewed.termEndsAt}${onTime ? ' · Ehrenscore +1' : ''}`);
}

export function releaseSlot(state,id,reason='freiwillig') {
  const slot = state.slots.find(item=>item.id===id);
  if (!slot) throw new Error('Platz nicht gefunden.');
  const next = copy(state);
  next.slots=next.slots.filter(item=>item.id!==id);
  next.archive.push({...slot,releasedAt:next.day,reason});
  return nextEvent(next,`${id} freigegeben · Eintrag im lokalen Archiv`);
}

export function advanceNotebook(state,days) {
  const next = copy(state);
  next.day=addDays(state.day,days);
  const expired=next.slots.filter(slot=>slotStatus(slot,next.day)==='released');
  next.slots=next.slots.filter(slot=>slotStatus(slot,next.day)!=='released');
  for (const slot of expired) next.archive.push({...slot,releasedAt:next.day,reason:'Nachfrist abgelaufen'});
  return nextEvent(next,`${days} Tage weiter · ${expired.length} Platz/Plätze ins Archiv`);
}

export function demoNotebook(day='2026-10-20') {
  let state=createNotebook(day);
  state=addSlot(state,{title:'Ein Anfang',text:'Eine Idee bekommt ihren eigenen Platz.',x:220,y:240,radius:64});
  state=addSlot(state,{title:'Zweite Stimme',text:'Abstand schafft Raum für eine andere Stimme.',x:510,y:380,radius:56});
  state=addSlot(state,{title:'Offene Frage',text:'Was sollte hier als Nächstes wachsen?',x:790,y:200,radius:70});
  return state;
}

export function validNotebook(state) {
  try {
    if (!state || state.schema!==NOTEBOOK_SCHEMA || !Array.isArray(state.slots) || !Array.isArray(state.archive) || !Array.isArray(state.events) || !Number.isSafeInteger(state.nextId) || state.nextId<1 || state.slots.length>BOARD.maxSlots || state.archive.length>1000 || state.events.length>100) return false;
    dateOnly(state.day);
    const ids=new Set();
    for (const slot of [...state.slots,...state.archive]) {
      if (!slot || typeof slot.id!=='string' || !/^K\d{2,}$/.test(slot.id) || ids.has(slot.id)) return false;
      const sequence=Number(slot.id.slice(1));
      if (!Number.isSafeInteger(sequence) || sequence<1 || sequence>=state.nextId || slot.id!==`K${String(sequence).padStart(2,'0')}`) return false;
      ids.add(slot.id);
    }
    for (const slot of state.slots) {
      if (typeof slot.title!=='string' || slot.title.length>48 || typeof slot.text!=='string' || slot.text.length>280 || !Number.isInteger(slot.terms) || slot.termEndsAt!==termEnd(slot.startAt,slot.terms) || !Number.isInteger(slot.honor) || slot.honor<0 || slot.honor>slot.terms-1 || slotStatus(slot,state.day)==='released') return false;
      fit({...state,slots:state.slots.filter(item=>item.id!==slot.id)},slot.x,slot.y,slot.radius);
    }
    return state.events.every(item=>typeof item.message==='string' && item.message.length<=200 && typeof item.day==='string') && state.archive.every(item=>typeof item.id==='string' && typeof item.title==='string' && typeof item.text==='string');
  } catch { return false; }
}
