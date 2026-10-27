import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto, randomUUID} from 'node:crypto';

// Exercise the real event handlers while controlling the asynchronous hash boundary.
// This fixture uses no browser, remote request, filesystem write or private workspace.
test('download name and bytes retain the clicked state across awaited hashes', async () => {
  const original = new Map(['Option', 'document', 'requestAnimationFrame', 'fetch', 'crypto']
    .map(name => [name, Object.getOwnPropertyDescriptor(globalThis, name)]));
  const createURL = URL.createObjectURL, revokeURL = URL.revokeObjectURL;
  const downloads = [], blobs = new Map();
  class Element {
    constructor(tag = 'element') {
      this.tag = tag; this.children = []; this.dataset = {}; this.listeners = {};
      this.classList = {toggle() {}, add() {}}; this.value = '';
    }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    replaceChildren(...children) { this.children = children; }
    append(child) { this.children.push(child); }
    setAttribute(name, value) { this[name] = value; }
    click() {
      if (this.tag === 'a') downloads.push({filename: this.download, blob: blobs.get(this.href)});
    }
  }
  const html = readFileSync(new URL('./index.html', import.meta.url), 'utf8');
  const nodes = new Map([...html.matchAll(/id="([^"]+)"/g)].map(m => [m[1], new Element()]));
  nodes.get('scenario').value = 'journey'; nodes.get('gate').value = 'open'; nodes.get('speed').value = '8';
  const sources = JSON.parse(readFileSync(new URL('./data/sources.json', import.meta.url), 'utf8'));
  let hold = false, release;
  try {
    globalThis.Option = class extends Element {
      constructor(label, value) { super('option'); this.textContent = label; this.value = value; }
    };
    globalThis.document = {
      getElementById: id => nodes.get(id), createElement: tag => new Element(tag),
      createElementNS: (_, tag) => new Element(tag), addEventListener() {},
    };
    globalThis.requestAnimationFrame = () => {};
    const history = Array.from({length: 21}, (_, i) => ({sequence: 21-i, step: i,
      packetDigest: String(i).padStart(64, '0'), sourceId: 'fixture-source-' + i}));
    globalThis.fetch = async url => ({ok: true, json: async () => url === 'data/sources.json'
      ? sources : {ok: true, version: '2.1.2', ledgerCount: 21, sourceCount: 0, checkpoints: history}});
    URL.createObjectURL = blob => { const id = 'blob:fixture-' + blobs.size; blobs.set(id, blob); return id; };
    URL.revokeObjectURL = () => {};
    Object.defineProperty(globalThis, 'crypto', {configurable: true, value: {
      randomUUID, subtle: {digest: async (...args) => {
        if (hold) { hold = false; await new Promise(resolve => { release = resolve; }); }
        return webcrypto.subtle.digest(...args);
      }},
    }});
    await import('./app.mjs');
    assert.equal(nodes.get('saved-records').children.length, 20);
    assert.equal(nodes.get('more-records').hidden, false);
    nodes.get('more-records').listeners.click();
    assert.equal(nodes.get('saved-records').children.length, 21, 'oldest retained record becomes reachable');
    assert.equal(nodes.get('more-records').hidden, true);
    for (const interleave of ['scenario', 'step']) {
      nodes.get('timeline').value = '17'; nodes.get('timeline').listeners.input();
      const selected = nodes.get('molecule').value;
      hold = true;
      const pending = nodes.get('download').listeners.click();
      assert.equal(typeof release, 'function', 'checkpoint reached its asynchronous digest');
      if (interleave === 'scenario') {
        nodes.get('scenario').value = 'catalase'; nodes.get('scenario').listeners.change();
        assert.notEqual(nodes.get('molecule').value, selected);
      } else nodes.get('step').listeners.click();
      release(); await pending;
      const downloaded = downloads.at(-1), text = await downloaded.blob.text(), packet = JSON.parse(text);
      assert.equal(packet.step, 17);
      assert.equal(packet.view.selectedEntityId, selected);
      assert.equal(downloaded.filename, 'nova-molecule-' + packet.run.runId.slice(-12) + '-step-17.json');
      assert.equal(text.endsWith('\n'), true);
    }
    assert.equal(downloads.length, 2);
  } finally {
    for (const [name, descriptor] of original) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else delete globalThis[name];
    }
    URL.createObjectURL = createURL; URL.revokeObjectURL = revokeURL;
  }
});
