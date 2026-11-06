// SPDX-License-Identifier: LicenseRef-HALVETH-PIRL-2.0
import * as THREE from './vendor/three.module.min.js';
import {GLTFLoader} from './vendor/GLTFLoader.js';
import {createMotionModel,auditInput} from './motion-model.mjs';
const $=id=>document.getElementById(id),host=$('world');
const scene=new THREE.Scene();scene.background=new THREE.Color('#152936');scene.fog=new THREE.Fog('#152936',18,35);
const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.25;host.append(renderer.domElement);
const camera=new THREE.PerspectiveCamera(42,1,.05,50);let yaw=.35,pitch=.12,radius=3.5,drag=null;
scene.add(new THREE.HemisphereLight(0xd5ecff,0x5c584c,2));
const key=new THREE.DirectionalLight(0xffead4,3.5);key.position.set(3,7,4);key.castShadow=true;key.shadow.mapSize.set(2048,2048);Object.assign(key.shadow.camera,{left:-12,right:12,top:12,bottom:-12});scene.add(key);
const fill=new THREE.DirectionalLight(0x8bbfff,1.4);fill.position.set(-4,3,-2);scene.add(fill);
const floor=new THREE.Mesh(new THREE.PlaneGeometry(24,24),new THREE.MeshStandardMaterial({color:0x5d6c70,roughness:.95}));floor.rotation.x=-Math.PI/2;floor.receiveShadow=true;scene.add(floor);
const grid=new THREE.GridHelper(24,24,0x8b9ba3,0x6c7a81);grid.position.y=.001;grid.material.opacity=.25;grid.material.transparent=true;scene.add(grid);
const loader=new GLTFLoader();const character=await loader.loadAsync('/motion/character-assets/fictional-adult.glb');
const motions=await loader.loadAsync('/motion/character-assets/motions.glb');let model;
let keys=new Set(),touch={x:0,z:0},autoprobe=false,probeTime=0,probeFrame=0,accumulator=0,last=performance.now(),tick=0;
function reset(){if(model)scene.remove(model.avatar);for(const root of [character.scene,motions.scene])root.traverse(o=>{if(o.isBone&&o.userData.rest){o.position.copy(o.userData.rest.p);o.quaternion.copy(o.userData.rest.q);}});character.scene.position.set(0,0,0);character.scene.rotation.set(0,0,0);
 model=createMotionModel(character,motions,{supportLock:$('support').checked});model.avatar.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;o.frustumCulled=false;}});scene.add(model.avatar);probeTime=0;probeFrame=0;keys.clear();touch={x:0,z:0};}
for(const root of [character.scene,motions.scene])root.traverse(o=>{if(o.isBone)o.userData.rest={p:o.position.clone(),q:o.quaternion.clone()};});
reset();$('status').textContent='Bereit. Freie Steuerung oder den 11-Sekunden-Prüfweg starten.';
function render(){const b=model.body,target=new THREE.Vector3(b.x,.95,b.z);camera.position.set(b.x+Math.sin(yaw)*radius,1.45+Math.sin(pitch)*radius,b.z+Math.cos(yaw)*radius);camera.lookAt(target);renderer.render(scene,camera);}
function resize(){const w=host.clientWidth,h=host.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();render();}new ResizeObserver(resize).observe(host);resize();
function input(){if(autoprobe)return auditInput(probeTime);return{x:(keys.has('KeyD')||keys.has('ArrowRight')?1:0)-(keys.has('KeyA')||keys.has('ArrowLeft')?1:0)+touch.x,z:(keys.has('KeyW')||keys.has('ArrowUp')?1:0)-(keys.has('KeyS')||keys.has('ArrowDown')?1:0)+touch.z};}
window.addEventListener('keydown',e=>{if(/^(Key[WASD]|Arrow)/.test(e.code)){e.preventDefault();keys.add(e.code);autoprobe=false;}});
window.addEventListener('keyup',e=>keys.delete(e.code));window.addEventListener('blur',()=>{keys.clear();touch={x:0,z:0};});
renderer.domElement.addEventListener('pointerdown',e=>{host.focus();drag={x:e.clientX,y:e.clientY};renderer.domElement.setPointerCapture(e.pointerId);});
renderer.domElement.addEventListener('pointermove',e=>{if(!drag)return;yaw-=(e.clientX-drag.x)*.006;pitch=Math.max(-.13,Math.min(.65,pitch+(e.clientY-drag.y)*.004));drag={x:e.clientX,y:e.clientY};});
for(const event of ['pointerup','pointercancel'])renderer.domElement.addEventListener(event,()=>drag=null);
renderer.domElement.addEventListener('wheel',e=>{e.preventDefault();radius=Math.max(2.5,Math.min(10,radius+e.deltaY*.005));},{passive:false});
for(const b of document.querySelectorAll('[data-x]')){b.onpointerdown=e=>{b.setPointerCapture(e.pointerId);autoprobe=false;touch={x:Number(b.dataset.x),z:Number(b.dataset.z)};};b.onpointerup=b.onpointercancel=()=>touch={x:0,z:0};}
let recorder=null,recordedChunks=[],recordStarted=0,recordTimer=null,recordBytes=0,recordEnd='UNKNOWN';
function finishRecording(reason){if(recorder?.state==='recording'){recordEnd=reason;clearTimeout(recordTimer);recorder.stop();}}
$('audit').onclick=()=>{autoprobe=true;reset();yaw=.35;pitch=.12;radius=3.5;$('status').textContent='Prüfweg läuft: Stehen, Gehen, Wenden, Stoppen.';};
$('record').onclick=()=>{
 if(recorder?.state==='recording')return;
 if(!window.MediaRecorder||!renderer.domElement.captureStream){$('status').textContent='Canvas-Aufnahme in diesem Browser nicht verfügbar.';return;}
 recordedChunks=[];recordBytes=0;recordEnd='UNKNOWN';const stream=renderer.domElement.captureStream(30);
 recorder=new MediaRecorder(stream,{mimeType:MediaRecorder.isTypeSupported('video/webm;codecs=vp9')?'video/webm;codecs=vp9':'video/webm'});
 recorder.ondataavailable=e=>{if(e.data.size){recordBytes+=e.data.size;if(recordBytes<=20_000_000)recordedChunks.push(e.data);else finishRecording('OUTPUT_LIMIT');}};
 recorder.onstop=()=>{stream.getTracks().forEach(t=>t.stop());const blob=new Blob(recordedChunks,{type:recorder.mimeType});const link=$('clip-download');if(link.href.startsWith('blob:'))URL.revokeObjectURL(link.href);link.href=URL.createObjectURL(blob);link.hidden=false;
  link.dataset.coverage=JSON.stringify({modelSeconds:probeTime,wallSeconds:(performance.now()-recordStarted)/1000,endReason:recordEnd,targetFramesPerSecond:30,bytes:blob.size,mime:blob.type,actualFrameCount:'MEASURE_FROM_CONTAINER'});$('record').disabled=false;};
 $('record').disabled=true;$('clip-download').hidden=true;$('audit').click();recordStarted=performance.now();recorder.start(1000);recordTimer=setTimeout(()=>finishRecording('WALL_TIMEOUT'),25000);
};
window.addEventListener('pagehide',()=>finishRecording('PAGE_CLOSED'));
$('reset').onclick=()=>{autoprobe=false;reset();$('status').textContent='Bereit für freie Steuerung.';};
$('support').onchange=()=>{autoprobe=false;reset();};$('camera').onclick=()=>{yaw+=Math.PI/2;render();};
$('receipt').onclick=()=>{const receipt=model.receipt();$('receipt-view').textContent=JSON.stringify({...receipt,trace:undefined},null,2);const url=URL.createObjectURL(new Blob([JSON.stringify(receipt)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='HALVETH_FIKTIVE_FIGUR_MESSSPUR.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
function frame(now){requestAnimationFrame(frame);const elapsed=(now-last)/1000;last=now;if(elapsed>.25){accumulator=0;render();return;}accumulator+=Math.max(0,elapsed);let steps=0;
 while(accumulator>=1/60&&steps<5){const row=model.step(input());accumulator-=1/60;steps++;tick++;
 if(autoprobe){probeFrame++;probeTime=probeFrame/60;if(probeFrame===660){autoprobe=false;finishRecording('COMPLETED_660_STEPS');$('status').textContent='Prüfweg beendet. Perspektive wechseln oder selbst weitergehen.';}}
 if(tick%15===0){const r=model.receipt();$('metrics').textContent=`Wegpunkt ${row.x.toFixed(2)} / ${row.z.toFixed(2)} m · ${row.animation==='Idle_Loop'?'steht':'geht'} · Standfußgleiten max. ${(r.maxStanceSlipPerStepMeters*1000).toFixed(1)} mm je 1/60 s`;
  $('world').dataset.measuredState=JSON.stringify({x:row.x,z:row.z,animation:row.animation,samples:r.frames,projectionYaw:yaw,modelTime:row.time,autoprobe,source:'SKINNED_3D',maxStanceSlipMeters:r.maxStanceSlipPerStepMeters});}
 }render();}
requestAnimationFrame(frame);
