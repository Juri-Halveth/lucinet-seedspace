export const WISH_SCHEMA = 'seedspace.wish.v1';
export const MAX_WISH_CHARS = 500_000;

const SIGNALS = [
  ['book', /\b(?:buch|roman|kapitel|chapter|novel|manuskript|manuscript)\b/iu],
  ['tasks', /\b(?:aufgabenliste|aufgaben|checkliste|to-?do|tasks?|kanban)\b/iu],
  ['timeline', /\b(?:zeitstrahl|zeitachse|chronik|timeline|chronology)\b/iu],
  ['search', /\b(?:suche|suchbar|finden|search|filter)\b/iu],
  ['quiz', /\b(?:quiz|fragenkatalog|fragebogen)\b/iu],
  ['external-api', /\b(?:api|schnittstelle|live-?daten|internetdaten)\b/iu],
  ['account', /\b(?:login|anmeldung|konto|account)\b/iu],
  ['database', /\b(?:datenbank|database|server)\b/iu],
  ['payment', /(?<![\p{L}\p{N}_])(?:zahlung(?:en)?|bezahlen|überweis[\p{L}]*|wallet|ethereum|bitcoin|btc|payment|checkout)(?![\p{L}\p{N}_])/iu],
  ['ai-model', /\b(?:ki|ai|llm|sprachmodell|intelligenz)\b/iu]
];

const MODE_LABELS = Object.freeze({
  reader: 'Leseraum',
  tasks: 'Aufgabenraum',
  timeline: 'Zeitspur',
  explorer: 'Ideenatlas'
});

function localId(text) {
  let hash = 2166136261;
  for (let index = 0; index < text.length; index++) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function lineRecords(text) {
  const lines = [];
  const pattern = /[^\n]*(?:\n|$)/g;
  for (const match of text.matchAll(pattern)) {
    if (!match[0]) continue;
    lines.push({text:match[0].replace(/\n$/, ''), start:match.index, end:match.index + match[0].length});
  }
  return lines;
}

function isHeading(line) {
  return /^\s*(?:#{1,6}\s+|(?:kapitel|chapter|teil|part)\s+\d+[\s.:–-])/iu.test(line);
}

function sectionsFrom(text) {
  const blocks = [];
  const lines = lineRecords(text);
  let start = null;
  let end = null;
  let heading = null;
  const flush = () => {
    if (start === null) return;
    const content = text.slice(start, end).trim();
    if (content) blocks.push({title:heading || `Abschnitt ${blocks.length + 1}`, start, end, text:content});
    start = null; end = null; heading = null;
  };
  for (const line of lines) {
    if (!line.text.trim()) { flush(); continue; }
    if (isHeading(line.text)) { flush(); heading = line.text.trim().replace(/^#{1,6}\s*/, ''); }
    if (start === null) start = line.start;
    end = line.end;
  }
  flush();
  if (blocks.length <= 120) return blocks;
  const first = blocks.slice(0, 119);
  const startOfRest = blocks[119].start;
  first.push({title:'Weitere Abschnitte',start:startOfRest,end:text.length,text:text.slice(startOfRest).trim()});
  return first;
}

function explicitStatements(text) {
  const found = [];
  const pattern = /[^.!?\n]+[.!?]?/g;
  for (const match of text.matchAll(pattern)) {
    const phrase = match[0].trim();
    if (!/\b(?:soll|muss|möchte|will|brauche|erstelle|baue|erzeuge|should|must|want|build|create|need|bitte)\b/iu.test(phrase)) continue;
    const leading = match[0].indexOf(phrase);
    const start = match.index + leading;
    found.push({start,end:start + phrase.length,text:phrase});
  }
  return {shown:found.slice(0,24),total:found.length};
}

function taskItems(text) {
  const tasks = [];
  for (const line of lineRecords(text)) {
    const match = /^\s*(?:[-*•]|\d+[.)])\s+(.{2,200})\s*$/u.exec(line.text);
    if (match) tasks.push(match[1].trim());
  }
  return tasks.slice(0,200);
}

function datedItems(sections) {
  const events = [];
  const date = /\b(?:\d{1,2}[.\/-]\d{1,2}[.\/-]\d{4}|(?:19|20)\d{2})\b/gu;
  for (const section of sections) {
    for (const match of section.text.matchAll(date)) {
      events.push({date:match[0],text:section.text.slice(Math.max(0,match.index-80),Math.min(section.text.length,match.index+180)).replace(/\s+/g,' ').trim(),section:section.title});
      if (events.length >= 100) return events;
    }
  }
  return events;
}

function titleFrom(text, sections) {
  const first = sections[0]?.title;
  if (first && !first.startsWith('Abschnitt ')) return first.slice(0,90);
  const firstLine = text.split('\n').find(line => line.trim())?.trim() || 'Meine Idee';
  return firstLine.replace(/^[-*#\s]+/u,'').slice(0,90);
}

function htmlEscape(text) {
  return text.replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}

function standaloneHtml(data) {
  const embedded = JSON.stringify(data).replace(/</g,'\\u003c').replace(/>/g,'\\u003e').replace(/&/g,'\\u0026');
  return `<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src data:">
<title>${htmlEscape(data.title)}</title>
<style>
:root{font-family:system-ui,sans-serif;color:#f8eef5;background:#0b0911}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at 70% 0,#39233f,#0b0911 48%)}
main{max-width:980px;margin:auto;padding:clamp(20px,5vw,60px)}header{border-bottom:1px solid #c493b75a;padding-bottom:26px;margin-bottom:26px}small{color:#d8a7c5;letter-spacing:.18em;text-transform:uppercase}h1{font:clamp(34px,6vw,68px)/1.02 Georgia,serif;margin:14px 0}p{line-height:1.65;color:#d7cbd6}
.bar{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}.bar input,.bar button,.task-form input{font:inherit;padding:12px 14px;border:1px solid #af7eac;background:#1a1420;color:#fff;border-radius:8px}.bar input{flex:1;min-width:210px}.bar button,.task-form button{cursor:pointer;background:#b06a9e;color:#140d19;border:0;font-weight:700}.bar button:hover,.task-form button:hover{background:#d894c3}
.grid{display:grid;gap:14px}.card{border:1px solid #b586aa6a;background:#18121edc;padding:20px;border-radius:12px}.card h2{font:28px Georgia,serif;margin:0 0 10px}.card p{white-space:pre-wrap;overflow-wrap:anywhere;margin:0}.task{display:flex;gap:12px;align-items:flex-start}.task input{accent-color:#d894c3;width:20px;height:20px}.task.done span{text-decoration:line-through;opacity:.55}.task-form{display:flex;gap:8px;margin:16px 0}.task-form input{flex:1;min-width:0}.task-form button{padding:12px 16px;border-radius:8px}.empty{color:#c4afc0}.source{margin-top:30px}.source summary{cursor:pointer;color:#e6b7d4}.source pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:400px;overflow:auto;background:#120d16;padding:20px;border:1px solid #b586aa6a}
</style></head><body><main><header><small id="kind"></small><h1 id="title"></h1><p id="intro"></p></header><div class="bar"><input id="search" type="search" placeholder="Im Text suchen" aria-label="Im Text suchen"><button id="clear" type="button">Suche löschen</button></div><div id="task-controls"></div><div id="content" class="grid"></div><details class="source"><summary>Originaltext ansehen</summary><pre id="source"></pre></details></main>
<script id="wish-data" type="application/json">${embedded}</script>
<script>
(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('wish-data').textContent);
  const byId = id => document.getElementById(id);
  byId('kind').textContent = data.modeLabel;
  byId('title').textContent = data.title;
  byId('intro').textContent = data.intro;
  byId('source').textContent = data.source;
  const key = 'seedspace.wish.tasks.' + data.id;
  let tasks = data.tasks.map(text => ({text,done:false}));
  if (data.mode === 'tasks') {
    try { const saved = JSON.parse(localStorage.getItem(key)); if (Array.isArray(saved) && saved.length < 1000) tasks = saved.filter(item => item && typeof item.text === 'string' && typeof item.done === 'boolean'); } catch {}
    const form = document.createElement('form'); form.className = 'task-form';
    const input = document.createElement('input'); input.placeholder = 'Neue Aufgabe'; input.maxLength = 200; input.required = true; input.setAttribute('aria-label','Neue Aufgabe');
    const add = document.createElement('button'); add.type = 'submit'; add.textContent = 'Hinzufügen'; form.append(input,add); byId('task-controls').append(form);
    form.addEventListener('submit', event => { event.preventDefault(); const text = input.value.trim(); if (!text) return; tasks.push({text,done:false}); input.value = ''; save(); render(); });
  }
  function save() { try { localStorage.setItem(key,JSON.stringify(tasks)); } catch {} }
  function card(title,body) { const article = document.createElement('article'); article.className = 'card'; const h = document.createElement('h2'); h.textContent = title; const p = document.createElement('p'); p.textContent = body; article.append(h,p); return article; }
  function render() {
    const query = byId('search').value.toLocaleLowerCase(); const out = byId('content'); out.replaceChildren();
    if (data.mode === 'tasks') {
      tasks.forEach((item,index) => { if (!item.text.toLocaleLowerCase().includes(query)) return; const row = document.createElement('label'); row.className = 'card task' + (item.done ? ' done' : ''); const box = document.createElement('input'); box.type = 'checkbox'; box.checked = item.done; const span = document.createElement('span'); span.textContent = item.text; box.addEventListener('change',() => { tasks[index].done = box.checked; save(); render(); }); row.append(box,span); out.append(row); });
    } else if (data.mode === 'timeline') {
      data.events.filter(item => (item.date + ' ' + item.text).toLocaleLowerCase().includes(query)).forEach(item => out.append(card(item.date,item.text)));
    } else {
      data.sections.filter(item => (item.title + ' ' + item.text).toLocaleLowerCase().includes(query)).forEach(item => out.append(card(item.title,item.text)));
    }
    if (!out.children.length) { const p = document.createElement('p'); p.className = 'empty'; p.textContent = query ? 'Keine Treffer.' : 'Hier ist noch kein Eintrag. Der Originaltext bleibt unten erhalten.'; out.append(p); }
  }
  byId('search').addEventListener('input',render);
  byId('clear').addEventListener('click',() => { byId('search').value = ''; render(); byId('search').focus(); });
  render();
})();
</script></body></html>`;
}

export function compileWish(input) {
  if (typeof input !== 'string' || !input.trim()) throw new Error('Schreibe zuerst deinen Wunsch oder füge Text ein.');
  if (input.length > MAX_WISH_CHARS) throw new Error(`Der Text überschreitet ${MAX_WISH_CHARS.toLocaleString('de-DE')} Zeichen.`);
  const normalized = input.replace(/\r\n?/g,'\n');
  const sections = sectionsFrom(normalized);
  const signals = SIGNALS.flatMap(([name,pattern]) => {
    const match = pattern.exec(normalized);
    return match ? [{name,start:match.index,end:match.index+match[0].length,text:match[0]}] : [];
  });
  const tasks = taskItems(normalized);
  const events = datedItems(sections);
  const words = normalized.match(/[\p{L}\p{N}]+(?:[’'-][\p{L}\p{N}]+)*/gu) || [];
  const chapterCount = lineRecords(normalized).filter(line => isHeading(line.text)).length;
  const bookLike = chapterCount >= 2 || words.length >= 350;
  const mode = bookLike ? 'reader' : signals.some(item => item.name === 'tasks') ? 'tasks' :
    (signals.some(item => item.name === 'timeline') || events.length >= 2) ? 'timeline' : 'explorer';
  const title = titleFrom(normalized,sections);
  const statements = explicitStatements(normalized);
  const external = signals.filter(item => ['external-api','account','database','payment','ai-model'].includes(item.name)).map(item => item.name);
  const id = localId(normalized);
  const runData = {
    schema:'seedspace.wish-program.v1',
    id,title,mode,modeLabel:MODE_LABELS[mode],source:normalized,
    intro: mode === 'reader' ? 'Ein durchsuchbarer Leseraum aus deinem Text.' : mode === 'tasks' ? 'Eine benutzbare Aufgabenliste aus deiner Beschreibung.' : mode === 'timeline' ? 'Eine durchsuchbare Zeitspur aus den erkannten Datumsstellen.' : 'Ein durchsuchbarer Ideenatlas aus deinem Text.',
    sections:sections.map(({title,text}) => ({title,text})),tasks,events
  };
  const html = standaloneHtml(runData);
  return {
    schema:WISH_SCHEMA,
    generator:{name:'LUCINET Wunschbrunnen',version:'1.0.1',method:'local-rules-and-templates',networkRequests:0},
    source:{originalText:input,normalizedText:normalized,normalization:'CRLF/CR to LF',characters:input.length,words:words.length},
    analysis:{mode,modeLabel:MODE_LABELS[mode],title,signals,statementCandidates:statements.shown,statementCandidateCount:statements.total,sections:sections.map(({title,start,end}) => ({title,start,end})),chapterCount,taskCount:tasks.length,dateCount:events.length,openConnections:external,coverage:{maxSections:120,maxStatementCandidatesShown:24,sourcePreserved:true}},
    program:runData,
    artifact:{entry:'index.html',format:'standalone-html',runnableOffline:true,files:[{path:'index.html',mediaType:'text/html',content:html}]},
    claim:'Generated code implements the selected local template. Other requested behavior remains in the original source and openConnections.'
  };
}
