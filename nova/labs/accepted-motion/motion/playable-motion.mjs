// SPDX-License-Identifier: LicenseRef-HALVETH-PIRL-2.0
// Small, deterministic capsule-on-floor controller. Units are metres/seconds.
export const BODY = Object.freeze({radius:0.28,height:1.75,walk:2.15,run:3.7,
  acceleration:13,braking:17,gravity:14.7,jump:5.25,worldHalf:7.7});

export function makeBody(x=0,z=2.7){return {x,z,y:0,vx:0,vz:0,vy:0,grounded:true,
  contacts:0,distance:0,time:0};}

// Explicit kinematic navigation constraint, not a claim about biological gait.
// A sole anchor may correct a step, but cannot reverse the requested direction.
export function boundSupportDisplacement(command,proposed){
  if(![command.x,command.z,proposed.x,proposed.z].every(Number.isFinite))throw new RangeError('finite support step required');
  const length=Math.hypot(command.x,command.z);if(length<1e-10)return {x:0,z:0};
  const ux=command.x/length,uz=command.z/length;
  const forward=Math.max(0,Math.min(length*1.25,proposed.x*ux+proposed.z*uz));
  const sideLimit=forward*Math.tan(Math.PI/12);
  const side=Math.max(-sideLimit,Math.min(sideLimit,proposed.x*uz-proposed.z*ux));
  return{x:ux*forward+uz*side,z:uz*forward-ux*side};
}

// A unilateral floor constraint for the articulated video figure. Clearance
// comes from the active sampled surface: dressed sole or rendered hand skin.
export function advanceGroundSupport(state,clearance,dt,gravity=9.81){
  if(!Number.isFinite(clearance)||!Number.isFinite(dt)||dt<=0||dt>.1||
     !Number.isFinite(gravity)||gravity<=0)throw new RangeError('finite ground step required');
  const velocity=state.velocity-gravity*dt;
  const height=state.height+velocity*dt;
  if(height+clearance<=0)return {height:-clearance,velocity:0,grounded:true,
    normalAcceleration:gravity,clearance:0};
  return {height,velocity,grounded:false,normalAcceleration:0,
    clearance:height+clearance};
}

// Image-space displacement moves the whole figure laterally in a bounded
// way. Monocular landmarks do not recover true depth or external forces.
export function lateralVideoTarget(pose,anchor,metresPerImageWidth=2){
  const left=pose?.image?.[23],right=pose?.image?.[24];
  if(!left||!right||left[3]<.55||right[3]<.55)return {anchor,target:null};
  const center=(left[0]+right[0])/2;
  if(!Number.isFinite(center))return {anchor,target:null};
  const origin=anchor??center;
  return {anchor:origin,target:Math.max(-1.8,Math.min(1.8,(center-origin)*metresPerImageWidth))};
}
// Keep a stance joint at its previous world position while its articulated
// leg moves. This is bounded kinematic root motion, not force reconstruction.
export function anchorStanceFoot(body,foot,anchor,dt,boxes=[],maxSpeed=3.7){
  if(![body.x,body.z,body.y,foot.x,foot.z,anchor.x,anchor.z,dt,maxSpeed].every(finite)||
     dt<=0||dt>.1||maxSpeed<=0)throw new RangeError('finite stance step required');
  const dx=anchor.x-foot.x,dz=anchor.z-foot.z;
  const length=Math.hypot(dx,dz),ratio=length?Math.min(1,maxSpeed*dt/length):0;
  const x=Math.max(-BODY.worldHalf+BODY.radius,Math.min(BODY.worldHalf-BODY.radius,body.x+dx*ratio));
  const z=Math.max(-BODY.worldHalf+BODY.radius,Math.min(BODY.worldHalf-BODY.radius,body.z+dz*ratio));
  if(boxes.some(box=>body.y<box.height&&overlap(x,z,box,BODY.radius)))
    return {moved:0,remaining:length,blocked:true};
  const appliedX=x-body.x,appliedZ=z-body.z,moved=Math.hypot(appliedX,appliedZ);
  body.x=x;body.z=z;body.distance+=moved;
  return {moved,remaining:Math.hypot(dx-appliedX,dz-appliedZ),blocked:false};
}
export function angleDelta(target,current){return Math.atan2(Math.sin(target-current),Math.cos(target-current));}
export function turnToward(current,target,maxStep){
  if(!finite(current)||!finite(target)||!finite(maxStep)||maxStep<0)throw new RangeError('invalid turn');
  return current+Math.max(-maxStep,Math.min(maxStep,angleDelta(target,current)));
}
const toward=(current,target,limit)=>current+Math.max(-limit,Math.min(limit,target-current));
const finite=n=>typeof n==='number'&&Number.isFinite(n);
function overlap(x,z,box,r){return x+r>box.minX&&x-r<box.maxX&&z+r>box.minZ&&z-r<box.maxZ;}

export function stepBody(body,input,dt,boxes=[]){
  if(!finite(dt)||dt<=0||dt>.1)throw new RangeError('dt must be in (0, 0.1]');
  for(const value of [body.x,body.z,body.y,body.vx,body.vz,body.vy,input.x,input.z])
    if(!finite(value))throw new RangeError('non-finite body/input');
  const len=Math.hypot(input.x,input.z),scale=len>1?1/len:1;
  const speed=input.run?BODY.run:BODY.walk;
  const ax=input.x*scale*speed,az=input.z*scale*speed;
  const rate=len>1e-5?BODY.acceleration:BODY.braking;
  body.vx=toward(body.vx,ax,rate*dt);body.vz=toward(body.vz,az,rate*dt);
  if(input.jump&&body.grounded)body.vy=BODY.jump;
  body.grounded=false;
  body.vy-=BODY.gravity*dt;
  const previousX=body.x,previousZ=body.z,previousY=body.y;
  for(const axis of ['x','z']){
    const velocity=axis==='x'?'vx':'vz';
    const candidate=Math.max(-BODY.worldHalf+BODY.radius,Math.min(BODY.worldHalf-BODY.radius,
      body[axis]+body[velocity]*dt));
    const x=axis==='x'?candidate:body.x,z=axis==='z'?candidate:body.z;
    const blocked=boxes.some(box=>body.y<box.height&&overlap(x,z,box,BODY.radius));
    if(blocked){body[velocity]=0;body.contacts++;}else {
      // A bounded world must also bound its velocity, otherwise the walk clip
      // continues while the root is pressed against the outer wall.
      if(candidate!==body[axis]+body[velocity]*dt)body[velocity]=(candidate-body[axis])/dt;
      body[axis]=candidate;
    }
  }
  body.y+=body.vy*dt;
  for(const box of boxes){
    if(body.vy<=0&&previousY>=box.height-1e-6&&body.y<=box.height&&
       overlap(body.x,body.z,box,BODY.radius)){
      body.y=box.height;body.vy=0;body.grounded=true;
    }
  }
  if(body.y<=0){body.y=0;body.vy=0;body.grounded=true;}
  body.distance+=Math.hypot(body.x-previousX,body.z-previousZ);body.time+=dt;
  return body;
}

// The video reference has its own articulated support constraint. This moves
// only the scene root laterally; a hidden foot/capsule floor cannot carry it.
export function stepVideoRoot(body,input,dt,boxes=[]){
  if(!finite(dt)||dt<=0||dt>.1||![body.x,body.z,body.vx,body.vz,input.x,input.z].every(finite))
    throw new RangeError('finite planar video step required');
  const len=Math.hypot(input.x,input.z),scale=len>1?1/len:1;
  const ax=input.x*scale*BODY.walk,az=input.z*scale*BODY.walk;
  const rate=len>1e-5?BODY.acceleration:BODY.braking;
  body.vx=toward(body.vx,ax,rate*dt);body.vz=toward(body.vz,az,rate*dt);
  const previousX=body.x,previousZ=body.z;
  for(const axis of ['x','z']){
    const velocity=axis==='x'?'vx':'vz';
    const candidate=Math.max(-BODY.worldHalf+BODY.radius,Math.min(BODY.worldHalf-BODY.radius,
      body[axis]+body[velocity]*dt));
    const x=axis==='x'?candidate:body.x,z=axis==='z'?candidate:body.z;
    if(boxes.some(box=>overlap(x,z,box,BODY.radius))){body[velocity]=0;body.contacts++;}
    else body[axis]=candidate;
  }
  body.y=0;body.vy=0;body.grounded=false;
  body.distance+=Math.hypot(body.x-previousX,body.z-previousZ);body.time+=dt;
  return body;
}

export function lineOfSight(from,to,boxes){
  // Segment versus horizontal AABB at eye/target height; same source boxes as collision.
  for(const b of boxes){
    if(Math.min(from.y,to.y)>b.height)continue;
    let low=0,high=1;
    for(const [axis,min,max] of [['x',b.minX,b.maxX],['z',b.minZ,b.maxZ]]){
      const d=to[axis]-from[axis];
      if(Math.abs(d)<1e-9){if(from[axis]<min||from[axis]>max){low=2;break;}continue;}
      let a=(min-from[axis])/d,c=(max-from[axis])/d;if(a>c)[a,c]=[c,a];
      low=Math.max(low,a);high=Math.min(high,c);
    }
    if(low<=high&&high>=0&&low<=1)return false;
  }
  return true;
}

export function perceive(body,facing,objects,boxes){
  const eye={x:body.x,y:body.y+1.55,z:body.z};
  return objects.filter(o=>{
    const dx=o.x-eye.x,dz=o.z-eye.z,d=Math.hypot(dx,dz);
    const angle=Math.atan2(dx,dz)-facing;
    return d<7&&Math.cos(angle)>Math.cos(Math.PI*55/180)&&
      lineOfSight(eye,{x:o.x,y:o.y,z:o.z},boxes);
  }).map(o=>o.id);
}
