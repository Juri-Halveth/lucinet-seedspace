import test from 'node:test';
import assert from 'node:assert/strict';
import {Script} from 'node:vm';
import {compileWish, MAX_WISH_CHARS, WISH_SCHEMA} from './wish-engine.js';

test('a German task request becomes a usable offline task app inside JSON', () => {
  const source = 'Baue eine Aufgabenliste für meine Reise.\n- Tickets prüfen\n- Tasche packen';
  const result = compileWish(source);
  assert.equal(result.schema,WISH_SCHEMA);
  assert.equal(result.source.originalText,source);
  assert.equal(result.analysis.mode,'tasks');
  assert.equal(result.analysis.taskCount,2);
  assert.equal(result.analysis.statementCandidates[0].text,'Baue eine Aufgabenliste für meine Reise.');
  assert.equal(result.source.normalizedText.slice(result.analysis.statementCandidates[0].start,result.analysis.statementCandidates[0].end),result.analysis.statementCandidates[0].text);
  assert.match(result.artifact.files[0].content,/addEventListener\('submit'/);
  assert.match(result.artifact.files[0].content,/localStorage\.setItem/);
  const inlineCode = result.artifact.files[0].content.match(/<script>\n([\s\S]*?)\n<\/script>/)?.[1];
  assert.ok(inlineCode);
  assert.doesNotThrow(() => new Script(inlineCode));
  assert.equal(JSON.parse(JSON.stringify(result)).artifact.entry,'index.html');
});

test('long unheaded prose still receives the reader template', () => {
  const result = compileWish('Dies ist ein langer Abschnitt. '.repeat(360));
  assert.equal(result.analysis.mode,'reader');
  assert.equal(result.source.originalText.length,result.source.normalizedText.length);
});

test('chapters from a book become a searchable reader without losing the source', () => {
  const source = 'Kapitel 1: Anfang\r\nEin Stern erscheint.\r\n\r\nKapitel 2: Reise\r\nEr fliegt weiter.';
  const result = compileWish(source);
  assert.equal(result.analysis.mode,'reader');
  assert.equal(result.source.originalText,source);
  assert.equal(result.analysis.chapterCount,2);
  assert.equal(result.analysis.sections.length,2);
  assert.equal(result.source.normalizedText.slice(result.analysis.sections[1].start,result.analysis.sections[1].end).trim(),'Kapitel 2: Reise\nEr fliegt weiter.');
  assert.match(result.artifact.files[0].content,/type="search"/);
});

test('dated text creates a timeline and names external connections separately', () => {
  const source = 'Baue eine Zeitachse mit API.\n\n2025 begann das Projekt.\n\n2026 erschien die Demo.';
  const result = compileWish(source);
  assert.equal(result.analysis.mode,'timeline');
  assert.equal(result.analysis.dateCount,2);
  assert.deepEqual(result.analysis.openConnections,['external-api']);
  assert.equal(result.generator.networkRequests,0);
});

test('untrusted input remains data and cannot close the embedded JSON script', () => {
  const source = '</script><script>alert(1)</script>\nEine Idee.';
  const result = compileWish(source);
  const html = result.artifact.files[0].content;
  assert.equal(result.source.originalText,source);
  assert.ok(!html.includes(source));
  assert.match(html,/\\u003c\/script\\u003e/);
  assert.match(html,/<script id="wish-data" type="application\/json">/);
});

test('empty and oversized wishes are rejected rather than silently truncated', () => {
  assert.throws(() => compileWish('   '),/Schreibe zuerst/);
  assert.throws(() => compileWish('x'.repeat(MAX_WISH_CHARS+1)),/überschreitet/);
});
