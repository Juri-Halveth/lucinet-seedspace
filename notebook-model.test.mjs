import test from 'node:test';
import assert from 'node:assert/strict';
import {BOARD,createNotebook,addSlot,moveSlot,renewSlot,releaseSlot,advanceNotebook,slotStatus,termEnd,validNotebook,demoNotebook} from './notebook-model.js';

const note=(title,x,y,radius=40)=>({title,text:`Text für ${title}`,x,y,radius});

test('calendar renewal retains the original month-day anchor',()=>{
  assert.equal(termEnd('2027-01-31',1),'2027-02-28');
  assert.equal(termEnd('2027-01-31',2),'2027-03-31');
});

test('placement respects boundary, gap and finite capacity without displacing earlier slots',()=>{
  let state=createNotebook('2026-10-20');
  state=addSlot(state,note('Erste',100,100));
  assert.throws(()=>addSlot(state,note('Zu nah',190,100)),/Zu nah/);
  assert.throws(()=>addSlot(state,note('Rand',20,100)),/Raumgrenze/);
  assert.equal(state.slots.length,1);
  for (const [i,x,y] of [[2,300,100],[3,500,100],[4,700,100],[5,900,100],[6,200,350],[7,450,350],[8,700,350]]) state=addSlot(state,note(`Kugel ${i}`,x,y));
  assert.equal(state.slots.length,BOARD.maxSlots);
  assert.throws(()=>addSlot(state,note('Neunte',500,550)),/acht Plätze/);
  assert.ok(validNotebook(state));
});

test('moving preserves term and refuses collisions',()=>{
  let state=createNotebook('2026-10-20');
  state=addSlot(state,note('A',100,100));
  state=addSlot(state,note('B',350,100));
  const before=state.slots[0].termEndsAt;
  assert.throws(()=>moveSlot(state,'K01',300,100),/Zu nah/);
  state=moveSlot(state,'K01',120,270);
  assert.equal(state.slots[0].termEndsAt,before);
  assert.deepEqual([state.slots[0].x,state.slots[0].y],[120,270]);
});

test('on-time renewal raises honor, grace renewal does not, expiry archives text',()=>{
  let state=createNotebook('2026-10-20');
  state=addSlot(state,note('A',100,100));
  state=renewSlot(state,'K01');
  assert.equal(state.slots[0].honor,1);
  state=advanceNotebook(state,62); // after the second term, inside grace
  assert.equal(slotStatus(state.slots[0],state.day),'grace');
  state=renewSlot(state,'K01');
  assert.equal(state.slots[0].honor,1);
  state=advanceNotebook(state,40);
  assert.equal(state.slots.length,0);
  assert.equal(state.archive[0].text,'Text für A');
  assert.equal(state.archive[0].reason,'Nachfrist abgelaufen');
});

test('manual release archives the content and leaves no penalty entry',()=>{
  let state=addSlot(createNotebook('2026-10-20'),note('A',100,100));
  state=releaseSlot(state,'K01');
  assert.equal(state.slots.length,0);
  assert.equal(state.archive[0].reason,'freiwillig');
  assert.ok(validNotebook(state));
});

test('demo state is reloadable and malformed local state is refused',()=>{
  const state=demoNotebook();
  assert.equal(state.slots.length,3);
  assert.ok(validNotebook(JSON.parse(JSON.stringify(state))));
  assert.equal(validNotebook({...state,slots:[...state.slots,{...state.slots[0]}]}),false);
});
