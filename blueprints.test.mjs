import test from 'node:test';
import assert from 'node:assert/strict';
import {blueprints, validateBlueprints} from './blueprints.js';

test('registered capsules have unique ids and supported renderers', () => {
  assert.equal(validateBlueprints(blueprints), true);
  assert.equal(new Set(blueprints.map(x => x.kind)).size, 4);
});

test('invalid renderer and repeated id are rejected', () => {
  assert.throws(() => validateBlueprints([{id:'x',kind:'script',label:'Bad'}]));
  assert.throws(() => validateBlueprints([{id:'x',kind:'garden',label:'One'},{id:'x',kind:'garden',label:'Two'}]));
});
