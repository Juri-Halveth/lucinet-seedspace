// SPDX-License-Identifier: LicenseRef-HALVETH-PIRL-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {BODY,makeBody,stepBody,boundSupportDisplacement} from './playable-motion.mjs';

test('all four world boundaries stop translation and walking velocity',()=>{
  for(const axis of ['x','z'])for(const sign of [-1,1]){
    const body=makeBody(0,0);body[axis]=sign*(BODY.worldHalf-BODY.radius);
    for(let i=0;i<120;i++)stepBody(body,{x:axis==='x'?sign:0,z:axis==='z'?sign:0},1/60,[]);
    assert.equal(body[axis],sign*(BODY.worldHalf-BODY.radius));
    assert.equal(body[axis==='x'?'vx':'vz'],0);
    assert.equal(body.distance,0);
  }
});
test('diagonal movement retains its free axis at a boundary and stops on release',()=>{
  const body=makeBody(BODY.worldHalf-BODY.radius,0);
  for(let i=0;i<60;i++)stepBody(body,{x:1,z:1},1/60,[]);
  assert.equal(body.vx,0);assert.ok(body.z>1);assert.ok(body.vz>0);
  for(let i=0;i<60;i++)stepBody(body,{x:0,z:0},1/60,[]);
  assert.equal(body.vx,0);assert.equal(body.vz,0);
});
test('support correction cannot reverse navigation or exceed its stated cone',()=>{
  let count=0;
  for(let angle=0;angle<2*Math.PI;angle+=Math.PI/8)for(let x=-.06;x<=.06;x+=.01)for(let z=-.06;z<=.06;z+=.01){
    const command={x:Math.sin(angle)*.03,z:Math.cos(angle)*.03};
    const step=boundSupportDisplacement(command,{x,z}),forward=(step.x*command.x+step.z*command.z)/.03;
    const lateral=Math.abs((step.x*command.z-step.z*command.x)/.03);
    assert.ok(forward>=-1e-12&&forward<=.03*1.25+1e-12);
    assert.ok(lateral<=forward*Math.tan(Math.PI/12)+1e-12);count++;
  }
  assert.ok(count>2000);assert.deepEqual(boundSupportDisplacement({x:0,z:0},{x:1,z:1}),{x:0,z:0});
  assert.throws(()=>boundSupportDisplacement({x:NaN,z:0},{x:0,z:0}),RangeError);
});
