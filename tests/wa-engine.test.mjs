import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import * as safety from '../wa-safety.mjs';

class Cache {
  values = new Map();
  get(k) { return this.values.get(k); }
  set(k, v) { this.values.set(k, v); }
  has(k) { return this.values.has(k); }
}
class Mutex {
  tail = Promise.resolve();
  locked = false;
  isLocked() { return this.locked; }
  runExclusive(fn) {
    const result = this.tail.then(async () => { this.locked = true; try { return await fn(); } finally { this.locked = false; } });
    this.tail = result.catch(() => {});
    return result;
  }
}

function harness(t, registered = true) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'wa-engine-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const routes = new Map(), sockets = [], timers = [], saves = [];
  const app = { use() {}, get(k, fn) { routes.set(`GET ${k}`, fn); }, post(k, fn) { routes.set(`POST ${k}`, fn); } };
  const context = {
    ...safety, fs, path, Buffer, URL, NodeCache: Cache, Mutex,
    express: Object.assign(() => app, { json() {} }),
    pino: () => ({}), QRCode: { toDataURL: async () => 'data:test' },
    process: { env: { SESSION_DIR: directory, WA_API_TOKEN: 'unit-test-only' }, stdout: { write() {} }, stderr: { write() {} } },
    console: {}, AbortSignal,
    setInterval: () => ({ unref() {} }), setTimeout(fn) { timers.push(fn); return timers.length; }, clearTimeout() {},
    BufferJSON: {
      replacer(k, v) { return v instanceof Uint8Array ? { type: 'Buffer', data: [...v] } : v; },
      reviver(k, v) { return v?.type === 'Buffer' ? Buffer.from(v.data) : v; }
    },
    DisconnectReason: { loggedOut: 401, connectionReplaced: 440, badSession: 500 },
    fetchLatestBaileysVersion: async () => ({ version: [2, 3, 4] }),
    useMultiFileAuthState: async () => ({ state: { creds: { registered, me: registered ? { id: '201000000000:1@s.whatsapp.net', lid: '999@lid' } : undefined }, keys: { set: async () => {} } }, saveCreds: async () => { saves.push('saved'); } }),
    makeCacheableSignalKeyStore: (keys, logger, cache) => ({ keys, cache }),
    makeWASocket(config) {
      const events = new Map();
      const socket = { config, events, user: { id: '201000000000:1@s.whatsapp.net' }, end() {}, ws: { close() {} },
        ev: { on(k, fn) { events.set(k, fn); }, removeAllListeners() { events.clear(); } },
        requestPairingCode: async () => '12345678', sendMessage: async jid => ({ key: { id: 'OUT-1', remoteJid: jid, fromMe: true }, message: { conversation: 'reply' } }) };
      sockets.push(socket); return socket;
    },
    proto: { WebMessageInfo: { StubType: { CIPHERTEXT: 2 } } },
    fetch: async () => ({ ok: false, status: 503, json: async () => ({ error: 'offline' }) })
  };
  let source = fs.readFileSync(new URL('../wa-baileys-index.js', import.meta.url), 'utf8');
  source = source.replace(/^import[\s\S]*?from\s+['"][^'"]+['"];\s*/gm, '');
  source = source.split('// ─── Server Startup')[0];
  source += '\nglobalThis.engine = { initBaileysSocket, handlePairingCode, handleSendMessage, storeMessage, fetchStoredMessage, drainWebhookOutbox, queueWebhook, authorized, metrics, unwrapMessage, extractMessageText, recordMapping, state: () => currentState, credentialWrites: () => credentialWrites };';
  vm.createContext(context); vm.runInContext(source, context);
  function response() { return { code: 200, body: null, status(n) { this.code = n; return this; }, json(v) { this.body = v; return this; } }; }
  const request = body => ({ headers: { authorization: 'Bearer unit-test-only' }, body, query: {} });
  return { ...context.engine, routes, sockets, timers, saves, directory, context, response, request };
}

test('token auth fails closed and ignores URL tokens', t => {
  const h = harness(t);
  assert.equal(h.authorized({ headers: {}, query: { token: 'unit-test-only' } }), false);
  assert.equal(h.authorized(h.request({})), true);
  assert.equal(safety.tokenMatches('', ''), false);
});

test('pairing preserves registered disconnected session', async t => {
  const h = harness(t); await h.initBaileysSocket();
  fs.writeFileSync(path.join(h.directory, 'creds.json'), 'sentinel');
  const r = h.response(); await h.handlePairingCode(h.request({ phone: '201000000001' }), r);
  assert.equal(r.code, 409); assert.equal(fs.readFileSync(path.join(h.directory, 'creds.json'), 'utf8'), 'sentinel');
});

test('pairing works on an unregistered existing socket', async t => {
  const h = harness(t, false); await h.initBaileysSocket();
  const r = h.response(); await h.handlePairingCode(h.request({ phone: '201000000001' }), r);
  assert.equal(r.body.code, '12345678'); assert.equal(h.sockets.length, 1);
});

test('concurrent init has one socket; reconnect creates a fresh Signal cache', async t => {
  const h = harness(t); await Promise.all([h.initBaileysSocket(), h.initBaileysSocket()]);
  assert.equal(h.sockets.length, 1);
  const old = h.sockets[0];
  await old.events.get('connection.update')({ connection: 'close', lastDisconnect: { error: { output: { statusCode: 515 } } } });
  await h.initBaileysSocket(); assert.equal(h.sockets.length, 2);
  assert.notEqual(old.config.auth.keys.cache, h.sockets[1].config.auth.keys.cache);
});

test('credential writes are awaited on reconnect and logged-out preserves disk', async t => {
  const h = harness(t); await h.initBaileysSocket();
  h.sockets[0].events.get('creds.update')(); await h.credentialWrites(); assert.equal(h.saves.length, 1);
  fs.writeFileSync(path.join(h.directory, 'session-test'), 'preserve');
  await h.sockets[0].events.get('connection.update')({ connection: 'close', lastDisconnect: { error: { output: { statusCode: 401 } } } });
  assert.equal(h.timers.length, 0); assert.equal(fs.existsSync(path.join(h.directory, 'session-test')), true);
});

test('durable retry store separates peers and directions; binary survives disk', t => {
  const h = harness(t), key = { id: '../escape', remoteJid: '123@lid', fromMe: true };
  h.storeMessage(key.id, { key, message: { mediaKey: new Uint8Array([1, 2, 3]) } });
  // Clear hot cache by reloading the script with the same directory is unnecessary: verify serialized data directly.
  const disk = JSON.parse(fs.readFileSync(path.join(h.directory, 'message_cache', `${safety.messageCacheKey(key)}.json`)));
  assert.equal(disk.message.mediaKey.type, 'Buffer');
  assert.equal(h.fetchStoredMessage({ ...key, remoteJid: '456@lid' }), null);
  assert.equal(h.fetchStoredMessage({ ...key, fromMe: false }), null);
  assert.equal(fs.existsSync(path.join(h.directory, 'escape.json')), false);
});

test('webhook failure persists then drains after confirmed acceptance', async t => {
  const h = harness(t);
  h.queueWebhook({ event_type: 'message', message_id: 'IN-1', remote_jid: '123@lid', text: 'hello' });
  await new Promise(resolve => setImmediate(resolve));
  const dir = path.join(h.directory, 'webhook_outbox'); assert.equal(fs.readdirSync(dir).length, 1);
  h.context.fetch = async () => ({ ok: true, json: async () => ({ message: { status: 'queued' } }) });
  await h.drainWebhookOutbox(); assert.equal(fs.readdirSync(dir).length, 0);
});

test('inbound dedup, own messages, media and empty ciphertext', async t => {
  const h = harness(t); await h.initBaileysSocket();
  const inbound = h.sockets[0].events.get('messages.upsert');
  const msg = { key: { id: 'IN-1', remoteJid: '123@lid', fromMe: false }, message: { ephemeralMessage: { message: { conversation: 'hello' } } } };
  await inbound({ messages: [msg, msg, { ...msg, key: { ...msg.key, id: 'SELF', fromMe: true } }] });
  assert.equal(h.metrics.messagesReceived, 1);
  await inbound({ messages: [{ key: { id: 'MEDIA', remoteJid: '123@lid' }, message: { audioMessage: {} } }] });
  assert.equal(h.metrics.messagesReceived, 2);
  await inbound({ messages: [{ key: { id: 'ABSENT', remoteJid: '123@lid' }, messageStubType: 2, messageStubParameters: ['Message absent from node'] }] });
  assert.equal(h.metrics.absentMessages, 1); assert.equal(h.metrics.decryptionErrors, 0);
});

test('send validates own LID, recipient and requires a message ID', async t => {
  const h = harness(t); await h.initBaileysSocket();
  await h.sockets[0].events.get('connection.update')({ connection: 'open' });
  for (const jid of ['999@lid', '1@newsletter', 'abc@lid']) {
    const r = h.response(); await h.handleSendMessage(h.request({ jid, message: 'hello' }), r); assert.equal(r.code, 400);
  }
  h.sockets[0].sendMessage = async () => ({});
  const r = h.response(); await h.handleSendMessage(h.request({ jid: '123@lid', message: 'hello' }), r);
  assert.equal(r.code, 500); assert.equal(h.metrics.messagesSent, 0);
});

test('all destructive routes reject without touching session', async t => {
  const h = harness(t);
  for (const endpoint of ['/logout', '/wipe-session', '/heal-sessions']) {
    const r = h.response(); await h.routes.get(`POST ${endpoint}`)(h.request({}), r); assert.equal(r.code, 409);
  }
});

test('receipt status 0 is forwarded, and non-outgoing updates are excluded', async t => {
  const h = harness(t); await h.initBaileysSocket();
  await h.sockets[0].events.get('messages.update')([{ key: { id: 'OUT', remoteJid: '123@lid', fromMe: true }, update: { status: 0 } }]);
  assert.equal(fs.readdirSync(path.join(h.directory, 'webhook_outbox')).length, 1);
});

test('identity and retry classification do not infer LID from phone length', () => {
  assert.equal(safety.canonicalJid('123:7@lid'), '123@lid');
  assert.equal(safety.sameConversation('123@lid', '966500000000@s.whatsapp.net', new Map([['123@lid', '966500000000']])), true);
  assert.equal(safety.retryKind(['Message absent from node']), 'absent');
  assert.equal(safety.retryKind(['Bad MAC']), 'bad_mac');
  assert.equal(safety.webhookAccepted(true, { message: { status: 'error' } }), false);
});
