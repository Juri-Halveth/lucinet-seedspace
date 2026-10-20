import test from 'node:test';
import assert from 'node:assert/strict';
import {encodeRoom, decodeRoom} from './room-state.js';

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
