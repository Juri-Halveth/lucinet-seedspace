// SPDX-License-Identifier: HALVETH-PIRL-2.0
// Fixed offline bridge to the explicitly vendored MIT modules.
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const manifest=JSON.parse(await readFile(new URL('./SOURCE_BINDINGS.json',import.meta.url),'utf8'));
for(const row of manifest.files){
  const bytes=await readFile(new URL('./'+row.path,import.meta.url));
  if(createHash('sha256').update(bytes).digest('hex')!==row.sha256)throw Error('BOUND_INTEGRATION_CHANGED');
}
const {evaluateReplay}=await import('./witness-replay.mjs');
const {witnessCases}=await import('./witness-cases.mjs');
const {syntheticWRows,wQuestions}=await import('./w-space.mjs');
const cases=witnessCases.map(item=>{
  const result=evaluateReplay(item.packet,item.packet.events.length+1);
  // A deliberately simple executable checklist, not a human participant.
  const baseline={routeObservations:item.packet.events.filter(e=>['OBSERVATION','FORWARD','PEER_ACTION_OBSERVATION'].includes(e.kind)).length,
    sourceCount:new Set(item.packet.events.map(e=>e.nodeId)).size};
  const expectedPass=Object.entries(item.expected).every(([key,value])=>result[key]===value);
  const coverage=result.core?syntheticWRows({packet:{referenceTime:result.asOf,freshnessMinutes:item.packet.freshnessMinutes}},result.core)
    :wQuestions.map(question=>({question,state:'UNKNOWN',value:'No route-report packet'}));
  return {id:item.id,input:item.packet,result,coverage,fixtureOracle:item.expected,fixturePass:expectedPass,baseline,
    countingDifference:baseline.routeObservations-result.ownRouteObservations,
    fixtureAuthority:'SYNTHETIC_DECLARED_MODEL',physicalObservationCount:'UNKNOWN'};
});
if(cases.some(c=>!c.fixturePass))throw Error('REPLAY_REGRESSION');
console.log(JSON.stringify({contract:'nova.lagefaden-integration.v1',source:manifest,cases,
  baselineKind:'DETERMINISTIC_CHECKLIST_NOT_HUMAN_TRIAL',
  results:{cases:cases.length,fixturePasses:cases.filter(c=>c.fixturePass).length,
    checklistOvercountsRouteEvidence:cases.filter(c=>c.countingDifference>0).length},
  humanPerformance:'NOT_MEASURED',hardwareConnected:false,externalAction:false}));
