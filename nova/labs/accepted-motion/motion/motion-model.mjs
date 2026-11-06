// SPDX-License-Identifier: LicenseRef-HALVETH-PIRL-2.0
// Reuses the existing NOVA controller and named-rest-pose retargeter.
import * as THREE from './vendor/three.module.min.js';
import {createRetargeter} from './character-retarget.mjs';
import {BODY,makeBody,stepBody,turnToward,angleDelta,boundSupportDisplacement} from './playable-motion.mjs';

export function createMotionModel(character,motions,{supportLock=true}={}){
 const figure=character.scene,avatar=new THREE.Group();avatar.add(figure);
 const retarget=createRetargeter(motions.scene,figure),mixer=new THREE.AnimationMixer(figure);
 const source=motions.animations.find(c=>c.name==='Walk_Loop');if(!source)throw Error('Walk clip missing');
 const baked=retarget.bake(source),rootTrack=baked.tracks.find(t=>t.name==='root.position');
 const displacement=rootTrack?Math.hypot(rootTrack.values.at(-3)-rootTrack.values[0],rootTrack.values.at(-1)-rootTrack.values[2]):0;
 if(!(displacement>.1&&displacement<5))throw Error('Unbound root stride '+displacement);
 const clips=new Map();for(const name of ['Idle_Loop','Walk_Loop']){
  const c=name==='Walk_Loop'?baked:retarget.bake(motions.animations.find(c=>c.name===name));
  clips.set(name,new THREE.AnimationClip(name,c.duration,c.tracks.filter(t=>t.name!=='root.position')));
 }
 const actions=new Map([...clips].map(([n,c])=>[n,mixer.clipAction(c)]));
 const body=makeBody(0,0);let facing=0,active='Idle_Loop',anchor=null,previousContact=null,previousFeet=null;
 actions.get(active).play();mixer.update(0);avatar.updateMatrixWorld(true);
 const meshes=[];figure.traverse(o=>{if(o.isSkinnedMesh)meshes.push(o);});
 const footMesh=meshes.find(m=>m.name.includes('_Feet'));if(!footMesh)throw Error('Authored shoe mesh missing');
 const p=new THREE.Vector3();const lower={l:[],r:[]};let restMin=Infinity;
 footMesh.skeleton.update();for(let i=0;i<footMesh.geometry.attributes.position.count;i++)restMin=Math.min(restMin,footMesh.getVertexPosition(i,p).applyMatrix4(footMesh.matrixWorld).y);
 for(let i=0;i<footMesh.geometry.attributes.position.count;i++){
  footMesh.getVertexPosition(i,p).applyMatrix4(footMesh.matrixWorld);if(p.y<restMin+.045)lower[p.x>=0?'l':'r'].push(i);
 }
 if(!lower.l.length||!lower.r.length)throw Error('Sole samples missing');
 const traces=[];let maxPenetration=0,maxSlip=0,totalSlip=0,stanceSamples=0,fullVertexSamples=0;
 function poseUpdate(){avatar.updateMatrixWorld(true);for(const m of meshes)m.skeleton.update();}
 function foot(side){const indices=lower[side],center=new THREE.Vector3();let minY=Infinity;
  for(const i of indices){footMesh.getVertexPosition(i,p).applyMatrix4(footMesh.matrixWorld);center.add(p);minY=Math.min(minY,p.y);}
  center.divideScalar(indices.length);return {x:center.x,y:minY,z:center.z};}
 function setMotion(name){if(name===active)return;const next=actions.get(name);next.reset().play();actions.get(active).crossFadeTo(next,.18,false);active=name;anchor=null;}
 function step(input,dt=1/60){
  const previousAnimation=active;
  const previous={x:body.x,z:body.z};stepBody(body,{...input,run:false,jump:false},dt,[]);
  const commandedStep=Math.hypot(body.x-previous.x,body.z-previous.z);
  const speed=Math.hypot(body.vx,body.vz);if(speed>.025)facing=turnToward(facing,Math.atan2(body.vx,body.vz),6*dt);
  setMotion(speed>.025?'Walk_Loop':'Idle_Loop');
  actions.get('Walk_Loop').timeScale=speed*source.duration/displacement;
  mixer.update(dt);avatar.position.set(body.x,0,body.z);avatar.rotation.y=facing;poseUpdate();
  let feet={l:foot('l'),r:foot('r')};avatar.position.y=-Math.min(feet.l.y,feet.r.y);poseUpdate();feet={l:foot('l'),r:foot('r')};
  const side=feet.l.y<=feet.r.y?'l':'r';
  if(supportLock&&speed>.025){
   if(anchor&&feet[anchor.side].y<.035){
    const current=feet[anchor.side],dx=anchor.x-current.x,dz=anchor.z-current.z;
    const distance=Math.hypot(dx,dz),ratio=distance?Math.min(1,.06/distance):1;
    const edge=BODY.worldHalf-BODY.radius;
    const bounded=boundSupportDisplacement({x:body.x-previous.x,z:body.z-previous.z},
      {x:avatar.position.x+dx*ratio-previous.x,z:avatar.position.z+dz*ratio-previous.z});
    avatar.position.x=Math.max(-edge,Math.min(edge,previous.x+bounded.x));
    avatar.position.z=Math.max(-edge,Math.min(edge,previous.z+bounded.z));
    body.x=avatar.position.x;body.z=avatar.position.z;poseUpdate();feet={l:foot('l'),r:foot('r')};
   }else anchor={side,x:feet[side].x,z:feet[side].z};
  }
  if(speed<=.025)anchor=null;
  const contact=anchor?.side??side,current=feet[contact];let slip=null;
  if(previousContact?.side===contact&&current.y<.035&&previousContact.y<.035){
   slip=Math.hypot(current.x-previousContact.x,current.z-previousContact.z);maxSlip=Math.max(maxSlip,slip);totalSlip+=slip;stanceSamples++;
  }
  previousContact={...current,side:contact};
  // Track both soles independently across animation and support changes.
  // A change of support cannot erase a displacement from the audit trail.
  const soleDisplacement=previousFeet?Object.fromEntries(['l','r'].map(side=>[side,{
   horizontal:Math.hypot(feet[side].x-previousFeet[side].x,feet[side].z-previousFeet[side].z),
   previousHeight:previousFeet[side].y,currentHeight:feet[side].y,
   bothNearFloor:previousFeet[side].y<.035&&feet[side].y<.035
  }])):null;
  previousFeet={l:{...feet.l},r:{...feet.r}};
  let minimum=Infinity;for(const m of meshes)for(let i=0;i<m.geometry.attributes.position.count;i++){m.getVertexPosition(i,p).applyMatrix4(m.matrixWorld);minimum=Math.min(minimum,p.y);fullVertexSamples++;}
  const penetration=Math.max(0,-minimum);maxPenetration=Math.max(maxPenetration,penetration);
  const dx=body.x-previous.x,dz=body.z-previous.z,actual=Math.hypot(dx,dz);
  body.distance+=actual-commandedStep;
  const row={time:body.time,x:body.x,y:avatar.position.y,z:body.z,animation:active,desiredSpeed:speed,stepDistance:actual,
   facing,orientationError:speed>.025?Math.abs(angleDelta(Math.atan2(body.vx,body.vz),facing)):0,
   sole:feet,soleDisplacement,animationChanged:active!==previousAnimation,support:contact,stanceSlip:slip,penetration,clipTime:actions.get('Walk_Loop').time};
  traces.push(row);if(traces.length>3600)traces.shift();return row;
 }
 return {avatar,body,step,traces,contract:{target:'FICTIONAL_ADULT_3D',source:'Quaternius Female_Peasant + Superhero_Female head + Hair_Buns',
  rig:retarget.contract,bones:retarget.bones,strideMeters:displacement,clipSeconds:source.duration,supportLock,
  measurementVersion:2,measurement:'Both sole identities persist across animation changes; near-floor does not prove physical load',
  support:'KINEMATIC_SAMPLED_SOLE_ANCHOR_NOT_FORCE_SIMULATION',supportDirection:supportLock?{forwardOnly:true,coneDegrees:15,maxForwardScale:1.25}:null,floor:'Y=0 metres',selfIntersection:'NOT_MEASURED',
  rendering:'Skinned 3D mesh; freely movable camera; no video surface',sampledVertices:meshes.reduce((s,m)=>s+m.geometry.attributes.position.count,0)},
  receipt(){return {schema:'halveth.fictional-motion-probe.v1',contract:this.contract,frames:traces.length,
   maxFloorPenetrationMeters:maxPenetration,maxStanceSlipPerStepMeters:maxSlip,meanStanceSlipMeters:stanceSamples?totalSlip/stanceSamples:null,
   stanceSamples,fullVertexSamples,trace:traces,claimCeiling:'Sampled geometric contact and authored animation, not mass/force/balance or visual approval'};}};
}

export function auditInput(time){
 if(time<1)return{x:0,z:0};if(time<3)return{x:0,z:1};
 if(time<5)return{x:Math.sin((time-3)*Math.PI/4),z:Math.cos((time-3)*Math.PI/4)};
 if(time<6.5)return{x:1,z:0};return{x:0,z:0};
}
