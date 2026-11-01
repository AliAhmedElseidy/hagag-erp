import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { drainOfflineBatches } from '../wa-safety.mjs';

function fixture(overrides = {}) {
  const pending = new Map(), requests = [], logs = [];
  let clockId = 0;
  const socket = { ws: new EventEmitter(), sendNode: async node => { requests.push(node); } };
  const options = {
    setTimer: fn => { const id = ++clockId; pending.set(id, fn); return id; },
    clearTimer: id => pending.delete(id), log: (...args) => logs.push(args), ...overrides
  };
  const dispose = drainOfflineBatches(socket, options);
  const tick = async () => { const [id, fn] = pending.entries().next().value || []; if (fn) { pending.delete(id); await fn(); } };
  return { socket, pending, requests, logs, dispose, tick };
}

test('missing offline terminator requests another existing-message batch after idle', async () => {
  const h = fixture();
  h.socket.ws.emit('CB:ib,,offline_preview', {});
  for (let i = 0; i < 104; i++) h.socket.ws.emit('CB:message', { attrs: { offline: '1' } });
  assert.equal(h.requests.length, 0);
  assert.equal(h.pending.size, 1);
  await h.tick();
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].content[0].tag, 'offline_batch');
  h.socket.ws.emit('CB:ib,,offline', {});
  assert.equal(h.pending.size, 0);
  await h.tick();
  assert.equal(h.requests.length, 1);
  h.dispose();
});

test('live traffic including offline zero does not starve a stalled offline batch', async () => {
  const h = fixture();
  h.socket.ws.emit('CB:ib,,offline_preview', {});
  const timer = [...h.pending.keys()][0];
  h.socket.ws.emit('CB:message', { attrs: { offline: '0' } });
  h.socket.ws.emit('CB:message', { attrs: {} });
  assert.equal([...h.pending.keys()][0], timer);
  await h.tick(); assert.equal(h.requests.length, 1); h.dispose();
});

test('reconnect/disposal never requests a batch on an obsolete socket', async () => {
  let current = true;
  const h = fixture({ isCurrent: () => current });
  h.socket.ws.emit('CB:ib,,offline_preview', {});
  current = false; await h.tick(); assert.equal(h.requests.length, 0);
  h.dispose(); assert.equal(h.socket.ws.listenerCount('CB:message'), 0);
});

test('batch requests are bounded and stop after a transport error', async () => {
  const h = fixture({ maxRequests: 2 }); h.socket.ws.emit('CB:ib,,offline_preview', {});
  await h.tick(); await h.tick(); await h.tick();
  assert.equal(h.requests.length, 2); assert.equal(h.pending.size, 0);
  assert.equal(h.logs.at(-1)[0], 'error'); h.dispose();
  const failed = fixture(); failed.socket.sendNode = async () => { throw new Error('offline'); };
  failed.socket.ws.emit('CB:ib,,offline_preview', {}); await failed.tick();
  assert.equal(failed.pending.size, 0); failed.dispose();
});
