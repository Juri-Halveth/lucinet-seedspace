import {readFile,writeFile} from 'node:fs/promises';
import {GLTFLoader} from './vendor/GLTFLoader.js';
import {createMotionModel,auditInput} from './motion-model.mjs';
// Node evaluation keeps the exact mesh/skin/animation buffers. Only rendering
// materials are omitted in the in-memory loader copy; source GLBs stay intact.
async function load(path){
 const raw=await readFile(new URL(path,import.meta.url));let offset=12,json,bin;
 while(offset<raw.length){const size=raw.readUInt32LE(offset),kind=raw.readUInt32LE(offset+4);const bytes=raw.subarray(offset+8,offset+8+size);if(kind===0x4e4f534a)json=JSON.parse(bytes.toString());if(kind===0x004e4942)bin=bytes;offset+=size+8;}
 delete json.images;delete json.textures;delete json.materials;for(const m of json.meshes)for(const p of m.primitives)delete p.material;
 let j=Buffer.from(JSON.stringify(json));j=Buffer.concat([j,Buffer.alloc((4-j.length%4)%4,32)]);const header=Buffer.alloc(20);header.writeUInt32LE(0x46546c67);header.writeUInt32LE(2,4);header.writeUInt32LE(28+j.length+bin.length,8);header.writeUInt32LE(j.length,12);header.writeUInt32LE(0x4e4f534a,16);const bh=Buffer.alloc(8);bh.writeUInt32LE(bin.length);bh.writeUInt32LE(0x004e4942,4);const result=Buffer.concat([header,j,bh,bin]);
 return new GLTFLoader().parseAsync(result.buffer.slice(result.byteOffset,result.byteOffset+result.length),'');
}
const results=[];
for(const supportLock of [false,true]){
 const model=createMotionModel(await load('character-assets/fictional-adult.glb'),await load('character-assets/motions.glb'),{supportLock});
 for(let n=0;n<660;n++)model.step(auditInput(n/60));
 const r=model.receipt();results.push(r);
 await writeFile(new URL(`../../../results/motion-${supportLock?'candidate':'baseline'}.json`,import.meta.url),JSON.stringify(r));
 console.log(JSON.stringify({...r,trace:undefined}));
}
