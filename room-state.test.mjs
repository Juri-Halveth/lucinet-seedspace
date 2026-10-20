import test from 'node:test';
import assert from 'node:assert/strict';
import {encodeRoom, decodeRoom, latestByBlueprint} from './room-state.js';

test('room instances survive reload and scale to a changed viewport', () => {
  const saved = encodeRoom([
    {id:1,blueprint:{id:'garden'},x:200,y:300,visible:true},
    {id:2,blueprint:{id:'atlas'},x:600,y:500,visible:false}
  ], 800, 1000);
  assert.deepEqual(decodeRoom(saved,new Set(['garden','atlas']),400,500),[
    {id:1,blueprintId:'garden',x:100,y:150,visible:true},
    {id:2,blueprintId:'atlas',x:300,y:250,visible:false}
  ]);
});

test('forged or malformed local state is refused', () => {
  const allowed = new Set(['garden']);
  assert.throws(() => decodeRoom('{"schema":"wrong","items":[]}',allowed,800,600));
  assert.throws(() => decodeRoom('{"schema":"seedspace.room.v1","items":[{"id":1,"blueprintId":"script","x":0.5,"y":0.5,"visible":true}]}',allowed,800,600));
  assert.throws(() => decodeRoom('{"schema":"seedspace.room.v1","items":[{"id":1,"blueprintId":"garden","x":2,"y":0.5,"visible":true}]}',allowed,800,600));
});

test('a repeated capsule relocates to its latest saved position without removing other types', () => {
  const legacy = JSON.stringify({schema:'seedspace.room.v1',items:[
    {id:1,blueprintId:'garden',x:.2,y:.3,visible:true},
    {id:2,blueprintId:'atlas',x:.6,y:.5,visible:true},
    {id:3,blueprintId:'garden',x:.8,y:.7,visible:false}
  ]});
  const records = latestByBlueprint(decodeRoom(legacy,new Set(['garden','atlas']),1000,1000));
  assert.deepEqual(records,[
    {id:2,blueprintId:'atlas',x:600,y:500,visible:true},
    {id:3,blueprintId:'garden',x:800,y:700,visible:false}
  ]);
  assert.throws(() => encodeRoom([
    {id:1,blueprint:{id:'garden'},x:100,y:100,visible:true},
    {id:2,blueprint:{id:'garden'},x:200,y:200,visible:true}
  ],1000,1000), /Duplicate blueprint/);
});
