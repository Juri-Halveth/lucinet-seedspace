import {readFileSync} from 'node:fs';
import {validateCheckpoint,canonical,checkpoint,createRun} from './engine.mjs';
const sources=JSON.parse(readFileSync(new URL('./data/sources.json',import.meta.url),'utf8'));
try {
  const input=JSON.parse(readFileSync(0,'utf8'));
  if(process.argv.includes('--fixture')) {
    process.stdout.write(canonical(await checkpoint(createRun(input.config,sources,input.options??{}),input.step,sources)));
  } else {
    const audit=await validateCheckpoint(input,sources);
    process.stdout.write(JSON.stringify({ok:true,audit}));
  }
} catch(error) {process.stdout.write(JSON.stringify({ok:false,error:error.message}));process.exitCode=1;}
