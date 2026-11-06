// SPDX-License-Identifier: LicenseRef-HALVETH-PIRL-2.0
import * as THREE from './vendor/three.module.min.js';

// Source clips animate a different-proportioned mannequin. Copying every
// translation would replace the target's limb lengths. Bind in world-rest
// orientation instead; retain local segment offsets except root/pelvis motion.
export function createRetargeter(source, target) {
  source.updateMatrixWorld(true);target.updateMatrixWorld(true);
  const sourceBones=new Map(),targetBones=new Map();
  source.traverse(o=>{if(o.isBone)sourceBones.set(o.name,o);});
  target.traverse(o=>{if(o.isBone)targetBones.set(o.name,o);});
  const pairs=[];
  target.traverse(o=>{if(!o.isBone)return;const s=sourceBones.get(o.name);if(!s)throw Error('Missing motion joint: '+o.name);
    pairs.push({source:s,target:o,sourceRestQ:s.getWorldQuaternion(new THREE.Quaternion()),targetRestQ:o.getWorldQuaternion(new THREE.Quaternion()),sourceRestP:s.position.clone(),targetRestP:o.position.clone(),targetRestLocalQ:o.quaternion.clone()});});
  if(pairs.length!==65||sourceBones.size!==65)throw Error('Unreviewed rig revision');
  const sh=sourceBones.get('pelvis').getWorldPosition(new THREE.Vector3()).y,th=targetBones.get('pelvis').getWorldPosition(new THREE.Vector3()).y;
  const scale=th/sh,mixer=new THREE.AnimationMixer(source),cache=new Map();
  const q=new THREE.Quaternion(),parentQ=new THREE.Quaternion();
  function restore(){for(const p of pairs){p.target.quaternion.copy(p.targetRestLocalQ);p.target.position.copy(p.targetRestP);}target.updateMatrixWorld(true);}
  function bake(clip){
    if(cache.has(clip.name))return cache.get(clip.name);
    restore();mixer.stopAllAction();const action=mixer.clipAction(clip);action.setLoop(THREE.LoopOnce,1);action.clampWhenFinished=true;action.play();
    const count=Math.max(2,Math.ceil(clip.duration*30)+1),times=[],values=pairs.map(()=>({q:[],p:[]}));
    for(let i=0;i<count;i++){
      const time=clip.duration*i/(count-1);times.push(time);mixer.setTime(time);source.updateMatrixWorld(true);
      for(let j=0;j<pairs.length;j++){
        const p=pairs[j];p.source.getWorldQuaternion(q);q.multiply(p.sourceRestQ.clone().invert()).multiply(p.targetRestQ);
        if(p.target.parent)p.target.parent.getWorldQuaternion(parentQ);else parentQ.identity();
        p.target.quaternion.copy(parentQ.invert().multiply(q));
        p.target.position.copy(p.targetRestP);
        if(p.target.name==='root'||p.target.name==='pelvis')p.target.position.addScaledVector(p.source.position.clone().sub(p.sourceRestP),scale);
        p.target.updateWorldMatrix(false,false);values[j].q.push(...p.target.quaternion.toArray());values[j].p.push(...p.target.position.toArray());
      }
    }
    const tracks=[];
    for(let j=0;j<pairs.length;j++){const name=pairs[j].target.name;tracks.push(new THREE.QuaternionKeyframeTrack(name+'.quaternion',times,values[j].q));if(name==='root'||name==='pelvis')tracks.push(new THREE.VectorKeyframeTrack(name+'.position',times,values[j].p));}
    mixer.stopAllAction();restore();const result=new THREE.AnimationClip(clip.name,clip.duration,tracks);cache.set(clip.name,result);return result;
  }
  return {bake,bones:pairs.length,scale,contract:'WORLD_REST_ORIENTATION_WITH_TARGET_SEGMENT_LENGTHS',cache};
}
