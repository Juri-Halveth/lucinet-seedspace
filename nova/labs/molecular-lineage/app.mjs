import {createRun,stateAt,auditRun,checkpoint,validateCheckpoint,canonical,STEPS} from './engine.mjs';
const $ = id => document.getElementById(id);
const sources = await fetch('data/sources.json').then(r => {if (!r.ok) throw Error('Quellen fehlen'); return r.json();});
let run, step = 0, selected, selectedAtom, playing = false, last = 0, accumulated = 0, records = [], visibleRecords = 20;
const labels = {CREATE:'Ursprung',TRANSPORT:'Transport',CONTACT:'Kontakt',BIND:'Gebunden',RELEASE:'Wieder frei',TRANSFORM:'Umwandlung',BLOCKED:'Transport hält'};
const palette = ['#c7f29e','#d1b8f3','#f2b889'];
const namespace = 'http://www.w3.org/2000/svg';
function svg(tag, attrs, parent, text) {const e=document.createElementNS(namespace,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;parent.append(e);return e;}
function newRun() {
  const parentRunId = run?.runId ?? null;
  installRun(createRun({scenario:$('scenario').value, seed:127, gate:$('gate').value},sources,{parentRunId}),0);
}
function installRun(next,viewStep,view=null) {
  auditRun(next,sources);run=next;step=viewStep;playing=false;accumulated=0;selected=view?.selectedEntityId??stateAt(run,step).active[0].id;selectedAtom=view?.selectedAtomId??null;
  $('scenario').value=run.config.scenario;$('gate').value=run.config.gate;
  $('molecule').replaceChildren(...run.entities.map(e => new Option(e.label + ' · ' + sources.species[e.speciesId].formula,e.id)));
  $('molecule').value=selected;
  $('run-id').textContent='MODEL '+run.runId.slice(-12);
  $('comparison').hidden=true;
  $('model-note').textContent=run.config.scenario==='journey' ? 'Schematischer Transport und Bindungsplatz · PubChem-Struktur · Zeit in Modellschritten.' : 'Rhea:20309 · 2 H₂O₂ → 2 H₂O + O₂ · konkrete Atomzuordnung als gewählte Modellregel.';
  $('middle-label').textContent=run.config.scenario==='journey'?'30 · Kontakt':'32 · Umwandlung';
  const chapters = run.config.gate==='closed'?[[0,'Ursprung'],[24,'Membran'],[60,'Endstand']]:run.config.scenario==='journey'?[[0,'Ursprung'],[23,'Transport'],[37,'Bindung'],[50,'Freigabe'],[60,'Endstand']]:[[0,'Ursprung'],[23,'Transport'],[32,'Umwandlung'],[60,'Neue Instanzen']];
  $('chapters').replaceChildren(...chapters.map(([t,label])=>{const b=document.createElement('button');b.textContent=t+' · '+label;b.dataset.step=t;b.addEventListener('click',()=>jump(t));return b;}));
  render();
}
function choose(id) {selected=id;selectedAtom=null;$('molecule').value=id;render();}
function jump(t){step=t;playing=false;accumulated=0;render();}
function render() {
  const state=stateAt(run,step), entity=run.entities.find(e=>e.id===selected), species=sources.species[entity.speciesId];
  $('timeline').value=step;$('step-label').textContent=`Schritt ${step} / ${STEPS}`;
  $('play').textContent=playing?'❚❚ Anhalten':step===STEPS?'↻ Erneut abspielen':'▶ Ablauf starten';
  $('step').disabled=step===STEPS;
  $('formula').textContent=species.formula;
  const live=state.active.find(e=>e.id===selected), past=entity.retired!==null&&step>=entity.retired;
  $('entity-state').textContent=live?(labels[live.state]??live.state):past?'Umgewandelt':'Ab Schritt '+entity.born;
  $('atom-count').textContent=entity.atomIds.length;
  const events=run.events.filter(e=>e.inputs.includes(selected)||e.outputs.includes(selected));
  $('event-count').textContent=events.filter(e=>e.time.step<=step).length;
  $('event-summary').textContent=events.filter(e=>e.time.step<=step).length+' / '+events.length+' im Modellplan';
  $('pubchem-link').href='https://pubchem.ncbi.nlm.nih.gov/compound/'+species.cid;
  const originalAtom=selectedAtom;
  if(!entity.atomIds.includes(selectedAtom))selectedAtom=entity.atomIds[0];
  if(originalAtom!==selectedAtom||$('atom').dataset.entity!==entity.id){$('atom').replaceChildren(...entity.atomIds.map(id=>{const a=run.atoms.find(x=>x.id===id);return new Option(a.element+' · '+id.split('_').slice(-2).join(' / '),id);}));$('atom').dataset.entity=entity.id;}
  $('atom').value=selectedAtom;
  const atom=run.atoms.find(a=>a.id===selectedAtom),owner=state.active.find(e=>e.atomIds.includes(selectedAtom));
  $('atom-history').textContent=atom.element+' · Ursprung '+run.entities.find(e=>e.id===atom.originEntityId).label+' · aktuell '+(owner?run.entities.find(e=>e.id===owner.id).label:'noch ohne aktuelle Instanz');
  $('lineage-note').textContent=entity.parents.length?'Eltern: '+entity.parents.map(id=>run.entities.find(e=>e.id===id).label).join(' + ')+'. Die Atom-IDs verbinden Herkunft und Produkt.':'Die Instanz bleibt in der Historie erhalten, auch wenn ihre Atom-IDs später auf Produkte verteilt werden.';
  $('events').replaceChildren(...events.map(e=>{const li=document.createElement('li');li.className=e.time.step<=step?'past':'';if(e.time.step===step)li.classList.add('now');const time=document.createElement('span');time.className='when';time.textContent=String(e.time.step).padStart(2,'0');const body=document.createElement('div'),button=document.createElement('button'),p=document.createElement('p');button.textContent=labels[e.type];button.addEventListener('click',()=>jump(e.time.step));p.textContent=e.detail;body.append(button,p);li.append(time,body);return li;}));
  const recent=run.events.filter(e=>e.time.step<=step).at(-1);$('story').textContent=recent?.detail??'Ursprung';
  for(const b of $('chapters').children)b.classList.toggle('active',Number(b.dataset.step)===step);
  drawScene(state);drawStructure(entity,species);
}
function drawScene(state){
  const root=$('scene');root.replaceChildren();
  const defs=svg('defs',{},root),pattern=svg('pattern',{id:'grid',width:40,height:40,patternUnits:'userSpaceOnUse'},defs);svg('circle',{cx:1,cy:1,r:1,fill:'#31433a'},pattern);svg('rect',{x:0,y:0,width:920,height:460,fill:'url(#grid)'},root);
  svg('text',{x:32,y:37,fill:'#78977f','font-size':12,'letter-spacing':2},root,'RAUM A');svg('text',{x:495,y:37,fill:'#78977f','font-size':12,'letter-spacing':2},root,'RAUM B');
  const gateColor=run.config.gate==='open'?'#9ac48a':'#b38a8a';
  svg('rect',{x:407,y:60,width:16,height:350,rx:8,fill:gateColor,opacity:.25},root);
  for(let y=75;y<410;y+=25)svg('circle',{cx:415,cy:y,r:5,fill:gateColor,opacity:.65},root);
  svg('text',{x:415,y:440,fill:gateColor,'font-size':12,'text-anchor':'middle'},root,run.config.gate==='open'?'MEMBRAN OFFEN':'MEMBRAN GESCHLOSSEN');
  if(run.config.scenario==='journey')for(let i=0;i<3;i++)svg('path',{d:`M 670 ${126+i*100} L 653 ${126+i*100} Q 631 ${145+i*100} 653 ${164+i*100} L 670 ${164+i*100}`,fill:'none',stroke:'#546d57','stroke-width':7,'stroke-linecap':'round'},root);
  else {svg('circle',{cx:590,cy:245,r:52,fill:'#ba99df',opacity:.1,stroke:'#ba99df','stroke-width':2,'stroke-dasharray':'4 6'},root);svg('text',{x:590,y:100,fill:'#bba2d3','font-size':12,'text-anchor':'middle'},root,'REAKTIONSFELD');}
  for(const entity of run.entities.filter(e=>!e.parents.length)){
    const p=entity.waypoints.map(v=>v[1]+','+v[2]).join(' ');svg('polyline',{points:p,fill:'none',stroke:palette[run.entities.indexOf(entity)%3],opacity:.16,'stroke-width':2,'stroke-dasharray':'3 6'},root);
  }
  let separated=false;
  for(const live of state.active){
    const coincident=state.active.filter(e=>Math.hypot(e.position.x-live.position.x,e.position.y-live.position.y)<1),rank=coincident.indexOf(live),offset=coincident.length>1?[[-65,-38],[65,-38],[0,45]][rank]:[0,0];
    const x=live.position.x+offset[0],y=live.position.y+offset[1];
    if(coincident.length>1){separated=true;svg('line',{x1:live.position.x,y1:live.position.y,x2:x,y2:y,stroke:'#a995bc','stroke-width':1,'stroke-dasharray':'3 5'},root);}
    const ent=run.entities.find(e=>e.id===live.id),idx=run.entities.indexOf(ent),color=palette[idx%3],g=svg('g',{'class':'molecule-node',role:'button',tabindex:0,'aria-label':ent.label,transform:`translate(${x} ${y})`},root);g.addEventListener('click',()=>choose(ent.id));g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose(ent.id);}});if(ent.id===selected)svg('circle',{cx:0,cy:0,r:38,fill:'none',stroke:color,'stroke-width':1,'stroke-dasharray':'3 5',opacity:.7},g);svg('circle',{cx:0,cy:0,r:25,fill:color,stroke:ent.id===selected?'#f8ffe7':'#314f3b','stroke-width':ent.id===selected?2:1},g);svg('text',{x:0,y:5,'text-anchor':'middle',fill:'#1b3022','font-size':11,'font-weight':750},g,ent.speciesId==='dmt'?'DMT':sources.species[ent.speciesId].formula);svg('text',{x:0,y:53,'text-anchor':'middle',fill:color,'font-size':12},g,ent.label);
  }
  if(separated)svg('text',{x:590,y:393,fill:'#c1aacf','font-size':12,'text-anchor':'middle'},root,'GLEICHE MODELLPOSITION · ANSICHT ENTZERRT');
}
function drawStructure(entity,species){
  const root=$('structure');root.replaceChildren();const xs=species.atoms.map(a=>a.x),ys=species.atoms.map(a=>a.y),xmin=Math.min(...xs),ymin=Math.min(...ys),w=Math.max(...xs)-xmin,h=Math.max(...ys)-ymin,scale=Math.min(290/Math.max(1,w),145/Math.max(1,h));
  const coords=Object.fromEntries(species.atoms.map(a=>[a.aid,{x:25+(290-w*scale)/2+(a.x-xmin)*scale,y:24+(145-h*scale)/2+(a.y-ymin)*scale}]));
  for(const b of species.bonds){const a=coords[b.a],c=coords[b.b];svg('line',{x1:a.x,y1:a.y,x2:c.x,y2:c.y,stroke:'#8c9b85','stroke-width':b.order===2?3:1.5},root);}
  const remaining=entity.atomIds.map(id=>run.atoms.find(a=>a.id===id));
  for(const a of species.atoms){const i=remaining.findIndex(x=>x.element===a.element),bound=remaining.splice(i,1)[0],p=coords[a.aid],chosen=bound?.id===selectedAtom;svg('circle',{cx:p.x,cy:p.y,r:chosen?9:a.element==='H'?4.5:7,fill:chosen?'#7752aa':a.element==='N'?'#688cbf':a.element==='O'?'#bc6e68':a.element==='H'?'#e1e5d8':'#61765b',stroke:chosen?'#d9c8ec':'#fffefa','stroke-width':2},root);if(a.element!=='H')svg('text',{x:p.x,y:p.y+3,'text-anchor':'middle','font-size':8,fill:'white'},root,a.element);}
}
function frame(now){if(playing){if(last)accumulated+=(now-last)/1000*Number($('speed').value);if(accumulated>=1){const ticks=Math.floor(accumulated);accumulated-=ticks;step=Math.min(STEPS,step+ticks);if(step===STEPS)playing=false;render();}}last=now;requestAnimationFrame(frame);}
$('scenario').addEventListener('change',newRun);$('gate').addEventListener('change',newRun);
$('molecule').addEventListener('change',()=>choose($('molecule').value));$('atom').addEventListener('change',()=>{selectedAtom=$('atom').value;render();});
$('timeline').addEventListener('input',()=>jump(Number($('timeline').value)));
$('play').addEventListener('click',()=>{if(step===STEPS)step=0;playing=!playing;accumulated=0;last=performance.now();render();});
$('step').addEventListener('click',()=>jump(Math.min(STEPS,step+1)));$('reset').addEventListener('click',()=>jump(0));
$('compare').addEventListener('click',()=>{const other=createRun({...run.config,gate:run.config.gate==='open'?'closed':'open'},sources);const a=stateAt(run,60),b=stateAt(other,60),right=s=>s.active.filter(e=>e.position.x>423).length;$('comparison').hidden=false;$('comparison').textContent=`Gleicher Start und gleiche Regeln; nur die Membran wechselt. Dieser Lauf: ${right(a)} Moleküle in Raum B, ${a.active.length} aktive Instanzen. Gegenlauf: ${right(b)} in Raum B, ${b.active.length} aktive Instanzen. ${run.atoms.length} Atom-IDs bleiben in beiden Läufen erhalten.`;});
function download(data){const blob=new Blob([canonical(data)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='nova-molecule-'+data.run.runId.slice(-12)+'-step-'+data.step+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('download').addEventListener('click',async()=>download(await checkpoint(run,step,sources,{selectedEntityId:selected,selectedAtomId:selectedAtom})));
function renderRecords(){
  $('saved-records').replaceChildren(...records.slice(0,visibleRecords).map(r=>{const li=document.createElement('li'),button=document.createElement('button'),small=document.createElement('span');button.className='quiet';button.textContent=`Stand ${r.sequence} · Schritt ${r.step} öffnen`;button.addEventListener('click',async()=>{try{const response=await fetch('/api/checkpoints/'+r.packetDigest);if(!response.ok)throw Error('Quellrecord fehlt');const packet=await response.json();await validateCheckpoint(packet,sources);installRun(packet.run,packet.step,packet.view??null);$('receipt').textContent=`Aus NOVA wieder geöffnet · ${r.sourceId} · Schritt ${r.step} · Modellrecord geprüft.`;}catch(error){$('receipt').textContent='Wiederöffnen offen: '+error.message;}});small.textContent=r.sourceId;li.append(button,small);return li;}));
  $('more-records').hidden=visibleRecords>=records.length;
  $('more-records').textContent='Weitere Stände anzeigen · '+Math.max(0,records.length-visibleRecords)+' übrig';
}
$('more-records').addEventListener('click',()=>{visibleRecords+=20;renderRecords();});
async function status(){try{const response=await fetch('/api/status');if(!response.ok)throw Error('Verbindung nicht verfügbar');const data=await response.json();if(!data.ok)throw Error('NOVA-Prüfung offen');$('connection').textContent=`NOVA ${data.version} · verbunden · ${data.ledgerCount} Forschungsrecords`;$('connection-dot').className='dot ok';$('save').disabled=false;records=data.checkpoints;renderRecords();$('nova-meta').replaceChildren(...Object.entries({'Runtime':data.version,'Ledgerrecords':data.ledgerCount,'Quellrecords':data.sourceCount,'Aktueller Hash':data.latestHash??'leer','Vorgänger':data.predecessorHash??'neuer Workspace'}).flatMap(([key,value])=>{const k=document.createElement('dt'),v=document.createElement('dd');k.textContent=key;v.textContent=value;return[k,v];}));}catch(error){$('connection').textContent='NOVA-Verbindung offen';$('receipt').textContent='Über den lokalen Python-Starter öffnen, um NOVA anzubinden. Der Modellrecord lässt sich weiterhin herunterladen.';}}
$('save').addEventListener('click',async()=>{playing=false;render();const button=$('save');button.disabled=true;try{const packet=await checkpoint(run,step,sources,{selectedEntityId:selected,selectedAtomId:selectedAtom});const response=await fetch('/api/checkpoints',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(packet)}),receipt=await response.json();if(!response.ok||!receipt.ok)throw Error(receipt.error??'Speichern fehlgeschlagen');$('receipt').textContent=`${receipt.alreadySaved?'Bereits festgehalten':'Gespeichert'} · Schritt ${receipt.step} · Quelle ${receipt.sourceId} · Ledger ${receipt.sequence} · Quell-SHA-256 ${receipt.sourceDigest} · NOVA-Rückprüfung erfolgreich.`;await status();}catch(error){$('receipt').textContent='Stand nicht abgeschlossen: '+error.message;}finally{button.disabled=false;}});
document.addEventListener('visibilitychange',()=>{last=0;accumulated=0;if(document.hidden){playing=false;render();}});
newRun();requestAnimationFrame(frame);await status();
