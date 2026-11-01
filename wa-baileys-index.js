import express from 'express';
import { canonicalJid, sameConversation, validRecipient, tokenMatches, messageCacheKey, webhookAccepted, retryKind, serviceDiagnostics } from './wa-safety.mjs';
import pino from 'pino';
import fs from 'fs';
import path from 'path';
import QRCode from 'qrcode';
import NodeCache from 'node-cache';
import { Mutex } from 'async-mutex';
import {
  makeWASocket,
  useMultiFileAuthState,
  makeCacheableSignalKeyStore,
  DisconnectReason,
  fetchLatestBaileysVersion,
  proto,
  BufferJSON
} from '@whiskeysockets/baileys';

const app = express();
const logger = pino({ level: 'warn', redact: ['session', 'creds', 'keys'] }, {
  write(line) {
    try {
      const event = JSON.parse(line);
      const kind = retryKind([event.msg || '', event.err?.message || '']);
      if (/decrypt|bad mac|no.*session|matching sessions/i.test(`${event.msg || ''} ${event.err?.message || ''}`)) {
        metrics.decryptionErrors++;
        if (event.key?.fromMe) metrics.selfDecryptionErrors++;
      }
      addLog(event.level >= 50 ? 'error' : 'warn', event.msg || 'Baileys transport event', event.err?.message || '',
        event.key ? { message_id: event.key.id, remote_jid: event.key.remoteJid, from_me: event.key.fromMe } : '');
    } catch (_) { addLog('warn', 'Unparseable Baileys log event'); }
  }
});

const PORT = process.env.PORT || 3000;
const API_TOKEN = process.env.WA_API_TOKEN || '';
if (!API_TOKEN) throw new Error('WA_API_TOKEN must be provided through the environment');
const SESSION_DIR = process.env.SESSION_DIR || '/app/session';
const FRAPPE_WEBHOOK_URL = process.env.FRAPPE_WEBHOOK_URL || 'http://backend:8000/api/method/hagag_erp.whatsapp_bridge.receive_baileys_event';
const FRAPPE_HOST = process.env.FRAPPE_HOST || 'erp.local';

app.use(express.json({ limit: '50mb' }));

// ─── Engine State Enum ────────────────────────────────────────────────────────
const EngineState = {
  STOPPED: 'STOPPED',
  INITIALIZING: 'INITIALIZING',
  CONNECTING: 'CONNECTING',
  CONNECTED: 'CONNECTED',
  DISCONNECTED: 'DISCONNECTED',
  RESETTING: 'RESETTING',
  ERROR: 'ERROR'
};

let currentState = EngineState.STOPPED;
let engineStartTime = Date.now();

// ─── Telemetry & Metrics ──────────────────────────────────────────────────────
const metrics = {
  errors: 0,
  decryptionErrors: 0,
  selfDecryptionErrors: 0,
  absentMessages: 0,
  lastInbound: null,
  lastOutbound: null,
  messagesReceived: 0,
  messagesSent: 0,
  webhookSuccess: 0,
  webhookFailed: 0,
  healOperations: 0,
  reconnections: 0,
  startTime: Date.now()
};

// ─── In-Memory Log Ring Buffer (Last 200 entries) ─────────────────────────────
const logBuffer = [];
const MAX_LOG_ENTRIES = 200;

function addLog(level, ...args) {
  const safeObject = value => {
    if (value instanceof Error) return { name: value.name, message: value.message };
    return Object.fromEntries(['message_id', 'remote_jid', 'from_me', 'status', 'code']
      .filter(key => value && value[key] !== undefined).map(key => [key, value[key]]));
  };
  // libsignal sometimes logs entire SessionEntry objects through console.warn.
  // Keep only diagnostic metadata, never key material or authentication state.
  let msg = args.map(a => (typeof a === 'object' ? JSON.stringify(safeObject(a)) : String(a))).join(' ');
  if (API_TOKEN) msg = msg.split(API_TOKEN).join('[redacted]');
  if (level === 'error') metrics.errors++;
  const entry = { ts: new Date().toISOString(), level: level.toLowerCase(), msg };
  logBuffer.push(entry);
  if (logBuffer.length > MAX_LOG_ENTRIES) logBuffer.shift();

  if (level === 'error') {
    process.stderr.write(`[${entry.ts}] [ERROR] ${msg}\n`);
  } else {
    process.stdout.write(`[${entry.ts}] [${level.toUpperCase()}] ${msg}\n`);
  }
}

console.log = (...a) => addLog('info', ...a);
console.warn = (...a) => addLog('warn', ...a);
console.error = (...a) => addLog('error', ...a);

// ─── Mutexes & Socket Singleton Manager ───────────────────────────────────────
const initMutex = new Mutex();
let reconnectTimer = null;

let sock = null;
let qrCodeData = null;
let qrCodeDataUrl = null;
let connectedPhone = null;
let botName = null;
let lastDisconnectReason = null;
let pendingPairingCode = null;

// Caches & Durable Stores
const msgRetryCounterCache = new NodeCache({ stdTTL: 600, checkperiod: 120 });
const messageStore = new NodeCache({ stdTTL: 3600, checkperiod: 600 });
const dedupCache = new NodeCache({ stdTTL: 3600, checkperiod: 300 });
let credentialWrites = Promise.resolve();
let authRegistered = false;
let ownLid = '';
const keyWrites = new Set();
let shuttingDown = false;
const pendingRetries = new Map(); // msgId -> { remoteJid, timestamp }

const MESSAGE_CACHE_DIR = path.join(SESSION_DIR, 'message_cache');
const MAPPINGS_FILE = path.join(SESSION_DIR, 'contact_mappings.json');

// Bidirectional Dynamic LID <-> Phone Number mapping
const lidPnMap = new Map(); // LID -> Phone
const pnLidMap = new Map(); // Phone -> LID

function ensureDirectories() {
  try {
    if (!fs.existsSync(SESSION_DIR)) fs.mkdirSync(SESSION_DIR, { recursive: true });
    if (!fs.existsSync(MESSAGE_CACHE_DIR)) {
      fs.mkdirSync(MESSAGE_CACHE_DIR, { recursive: true });
    } else {
      for (const file of fs.readdirSync(MESSAGE_CACHE_DIR)) {
        if (file.startsWith('id_') && file.endsWith('.json')) {
          try { fs.unlinkSync(path.join(MESSAGE_CACHE_DIR, file)); } catch (_) {}
        }
      }
    }
  } catch (err) {
    addLog('warn', `[Init] Error ensuring directories: ${err.message}`);
  }
}

function loadMappings() {
  try {
    if (fs.existsSync(MAPPINGS_FILE)) {
      const data = JSON.parse(fs.readFileSync(MAPPINGS_FILE, 'utf8'));
      if (data && typeof data === 'object') {
        for (const [k, v] of Object.entries(data.lidToPn || {})) {
          lidPnMap.set(k, v);
        }
        for (const [k, v] of Object.entries(data.pnToLid || {})) {
          pnLidMap.set(k, v);
        }
        addLog('info', `[MappingStore] Loaded ${lidPnMap.size} LID->PN mappings and ${pnLidMap.size} PN->LID mappings from disk`);
      }
    }
  } catch (err) {
    addLog('warn', `[MappingStore] Error loading contact mappings: ${err.message}`);
  }
}

let saveMappingsTimer = null;
function saveMappings() {
  if (saveMappingsTimer) return;
  saveMappingsTimer = setTimeout(() => {
    saveMappingsTimer = null;
    try {
      const lidToPnObj = Object.fromEntries(lidPnMap);
      const pnToLidObj = Object.fromEntries(pnLidMap);
      fs.writeFileSync(MAPPINGS_FILE, JSON.stringify({ lidToPn: lidToPnObj, pnToLid: pnToLidObj }, null, 2), 'utf8');
    } catch (err) {
      addLog('warn', `[MappingStore] Error saving contact mappings: ${err.message}`);
    }
  }, 1000);
}

function recordMapping(lidOrJid, phoneNumber) {
  if (!lidOrJid || !phoneNumber) return;
  const cleanPn = normalizeNumber(phoneNumber);
  if (!cleanPn) return;

  const raw = canonicalJid(lidOrJid);
  if (!/^\d+@lid$/.test(raw) || !/^\d{9,15}$/.test(cleanPn)) return;
  const cleanLid = raw.replace('@lid', '').split(':')[0];
  const lidJid = `${cleanLid}@lid`;

  lidPnMap.set(cleanLid, cleanPn);
  lidPnMap.set(lidJid, cleanPn);

  pnLidMap.set(cleanPn, lidJid);
  pnLidMap.set(`${cleanPn}@s.whatsapp.net`, lidJid);

  saveMappings();
}

function atomicJson(file, value) {
  const temp = `${file}.tmp`;
  fs.writeFileSync(temp, JSON.stringify(value, BufferJSON.replacer), { mode: 0o600 });
  fs.renameSync(temp, file);
}

function storeMessage(msgId, msgObj) {
  const cacheKey = messageCacheKey(msgObj?.key);
  if (!msgId || !cacheKey || !msgObj.message) return;
  messageStore.set(cacheKey, msgObj);
  ensureDirectories();
  atomicJson(path.join(MESSAGE_CACHE_DIR, `${cacheKey}.json`), msgObj);
}

function fetchStoredMessage(key) {
  const cacheKey = messageCacheKey(key);
  if (!cacheKey) return null;
  const cached = messageStore.get(cacheKey);
  if (cached) return cached;
  try {
    const value = JSON.parse(fs.readFileSync(path.join(MESSAGE_CACHE_DIR, `${cacheKey}.json`), 'utf8'), BufferJSON.reviver);
    messageStore.set(cacheKey, value);
    return value;
  } catch (_) { return null; }
}

async function fetchRetryMessage(key, socket) {
  if (!key?.id || !key?.remoteJid) return null;
  const reqJid = canonicalJid(key.remoteJid);
  if (!reqJid) return null;

  // Build list of verified candidate remoteJids belonging to the exact same conversation
  const conversationJids = [reqJid];
  let alternate = reqJid.endsWith('@lid') ? (lidPnMap.get(reqJid) || lidPnMap.get(reqJid.split('@')[0])) : (pnLidMap.get(reqJid) || pnLidMap.get(reqJid.split('@')[0]));
  if (alternate && !alternate.includes('@')) {
    alternate = reqJid.endsWith('@lid') ? `${alternate}@s.whatsapp.net` : `${alternate}@lid`;
  }
  if (!alternate && socket?.signalRepository?.lidMapping) {
    try {
      const mapping = socket.signalRepository.lidMapping;
      const res = reqJid.endsWith('@lid') ? await mapping.getPNForLID(reqJid) : await mapping.getLIDForPN(reqJid);
      if (res) {
        if (reqJid.endsWith('@lid')) {
          recordMapping(reqJid, res);
          alternate = res.includes('@') ? res : `${res}@s.whatsapp.net`;
        } else {
          recordMapping(res, reqJid);
          alternate = res.includes('@') ? res : `${res}@lid`;
        }
      }
    } catch (_) {}
  }
  if (alternate) {
    conversationJids.push(canonicalJid(alternate));
  }

  // Check valid conversation variants across fromMe and participant dimensions
  for (const cJid of conversationJids) {
    const variants = [
      { id: key.id, remoteJid: cJid, fromMe: key.fromMe, participant: key.participant },
      { id: key.id, remoteJid: cJid, fromMe: !key.fromMe, participant: undefined },
      { id: key.id, remoteJid: cJid, fromMe: key.fromMe, participant: undefined },
      { id: key.id, remoteJid: cJid, fromMe: !key.fromMe, participant: key.participant }
    ];
    for (const v of variants) {
      const match = fetchStoredMessage(v);
      if (match?.message) {
        // Enforce strict conversation matching: candidate message must belong to the requested conversation
        if (match.key?.id === key.id && sameConversation(reqJid, match.key.remoteJid, lidPnMap)) {
          return match;
        }
      }
    }
  }

  return null;
}

const OUTBOX_DIR = path.join(SESSION_DIR, 'webhook_outbox');
let drainingOutbox = false;
async function drainWebhookOutbox() {
  if (drainingOutbox || !API_TOKEN || !fs.existsSync(OUTBOX_DIR)) return;
  drainingOutbox = true;
  try {
    for (const file of fs.readdirSync(OUTBOX_DIR).filter(f => f.endsWith('.json')).slice(0, 100)) {
      const filePath = path.join(OUTBOX_DIR, file);
      try {
        const payload = JSON.parse(fs.readFileSync(filePath, 'utf8'));
        const resp = await fetch(FRAPPE_WEBHOOK_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Host': FRAPPE_HOST,
            'X-Frappe-Site-Name': FRAPPE_HOST, 'X-Api-Token': API_TOKEN },
          body: JSON.stringify(payload), signal: AbortSignal.timeout(15000)
        });
        const body = await resp.json();
        if (!webhookAccepted(resp.ok, body)) throw new Error(`Webhook not accepted (HTTP ${resp.status})`);
        fs.unlinkSync(filePath);
        metrics.webhookSuccess++;
      } catch (err) {
        metrics.webhookFailed++;
        addLog('error', '[Webhook] Retained event for retry:', err.message);
        break;
      }
    }
  } finally { drainingOutbox = false; }
}

function queueWebhook(payload) {
  fs.mkdirSync(OUTBOX_DIR, { recursive: true, mode: 0o700 });
  const key = messageCacheKey({ id: `${payload.event_type}:${payload.message_id}:${payload.status_code ?? ''}`,
    remoteJid: payload.remote_jid, fromMe: payload.event_type === 'status_update' });
  if (!key) throw new Error('Webhook identity missing');
  atomicJson(path.join(OUTBOX_DIR, `${key}.json`), payload);
  void drainWebhookOutbox();
}
setInterval(() => { void drainWebhookOutbox(); }, 5000).unref();

function cleanOldMessageCache() {
  try {
    if (!fs.existsSync(MESSAGE_CACHE_DIR)) return;
    const now = Date.now();
    const maxAgeMs = 72 * 60 * 60 * 1000; // 3 days
    const files = fs.readdirSync(MESSAGE_CACHE_DIR);
    for (const f of files) {
      if (f.endsWith('.json')) {
        const fp = path.join(MESSAGE_CACHE_DIR, f);
        const stat = fs.statSync(fp);
        if (now - stat.mtimeMs > maxAgeMs) {
          fs.unlinkSync(fp);
        }
      }
    }
  } catch (err) {}
}
setInterval(cleanOldMessageCache, 6 * 60 * 60 * 1000);

// ─── Utility Functions ────────────────────────────────────────────────────────
function normalizeNumber(number) {
  if (!number) return '';
  let n = String(number).replace(/[٠-٩]/g, d => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d))).replace(/\D/g, '');

  if (n.startsWith('00')) {
    n = n.substring(2);
  }

  // Egypt local format: 010..., 011..., 012..., 015... -> 201...
  if (/^0(1[0125]\d{8})$/.test(n)) {
    n = '20' + n.substring(1);
  } else if (/^(1[0125]\d{8})$/.test(n)) {
    n = '20' + n;
  }
  // Saudi local format: 05... -> 9665...
  else if (/^0(5\d{8})$/.test(n)) {
    n = '966' + n.substring(1);
  } else if (/^(5\d{8})$/.test(n)) {
    n = '966' + n;
  }

  return n;
}

function authorized(req) {
  const auth = req.headers.authorization || '';
  const headerToken = req.headers['x-api-token'] || '';
  return tokenMatches(API_TOKEN, auth.startsWith('Bearer ') ? auth.slice(7) : headerToken);
}

function cancelReconnectTimer() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

async function closeExistingSocket(reason = 'Close request') {
  cancelReconnectTimer();
  if (sock) {
    try {
      addLog('info', `[SocketManager] Closing existing socket: ${reason}`);
      sock.end(new Error(reason));
      sock.ev.removeAllListeners();
      if (sock.ws) {
        sock.ws.close();
      }
    } catch (e) {
      addLog('warn', `[SocketManager] Non-critical error closing socket: ${e.message}`);
    } finally {
      sock = null;
    }
  }
}

function unwrapMessage(msg) {
  let m = msg?.message;
  while (m && (m.ephemeralMessage || m.viewOnceMessage || m.viewOnceMessageV2 || m.documentWithCaptionMessage)) {
    m = (m.ephemeralMessage || m.viewOnceMessage || m.viewOnceMessageV2 || m.documentWithCaptionMessage).message;
  }
  return m;
}

function extractMessageText(m) {
  return (
    m?.conversation ||
    m?.extendedTextMessage?.text ||
    m?.imageMessage?.caption ||
    m?.videoMessage?.caption ||
    m?.documentMessage?.caption ||
    m?.buttonsResponseMessage?.selectedButtonId ||
    m?.listResponseMessage?.singleSelectReply?.selectedRowId ||
    ''
  );
}

async function dispatchMessageToFrappe(msg, m, text) {
  const msgId = msg.key?.id;
  const remoteJid = msg.key?.remoteJid || '';
  const isGroup = remoteJid.endsWith('@g.us');
  const senderJid = isGroup
    ? (msg.key.participant || msg.participant || '')
    : remoteJid;

  let rawSenderPn = isGroup ? (msg.key.participantAlt || msg.key.participantPn || '') : (msg.key.remoteJidAlt || msg.key.senderPn || '');
  if (String(rawSenderPn).includes('@') && !String(rawSenderPn).endsWith('@s.whatsapp.net')) rawSenderPn = '';
  if (!rawSenderPn && senderJid.endsWith('@lid') && sock?.signalRepository?.lidMapping?.getPNForLID) {
    rawSenderPn = await sock.signalRepository.lidMapping.getPNForLID(canonicalJid(senderJid)) || '';
  }
  const signalUser = senderJid.split('@')[0].split(':')[0];

  if (rawSenderPn) {
    recordMapping(senderJid, rawSenderPn);
    recordMapping(signalUser, rawSenderPn);
  }

  if (!rawSenderPn) {
    if (senderJid.endsWith('@s.whatsapp.net')) {
      rawSenderPn = signalUser;
    } else if (remoteJid.endsWith('@s.whatsapp.net')) {
      rawSenderPn = remoteJid.split('@')[0].split(':')[0];
    } else if (lidPnMap.has(signalUser)) {
      rawSenderPn = lidPnMap.get(signalUser);
    } else if (lidPnMap.has(senderJid)) {
      rawSenderPn = lidPnMap.get(senderJid);
    }
  }

  const senderPhone = normalizeNumber(rawSenderPn);
  const senderLid = senderJid.includes('@lid') ? senderJid : (remoteJid.includes('@lid') ? remoteJid : '');
  if (senderLid && senderPhone) {
    recordMapping(senderLid, senderPhone);
  }

  const replyJid = remoteJid;

  addLog('info', `[Msg] From: ${senderPhone || senderJid} | RemoteJid: ${remoteJid} | ReplyJid: ${replyJid} | Text: ${text.substring(0, 60)} | MsgID: ${msgId}`);

  try {
    const payload = {
      event_type: 'message',
      message_id: msgId,
      remote_jid: remoteJid,
      sender_jid: senderJid,
      sender_phone: senderPhone,
      sender_lid: senderLid,
      reply_jid: replyJid,
      is_group: isGroup,
      text: text,
      timestamp: Number(msg.messageTimestamp) || Math.floor(Date.now() / 1000),
      mentioned_jids: m?.extendedTextMessage?.contextInfo?.mentionedJid || [],
      has_media: !!(
        m?.imageMessage ||
        m?.videoMessage ||
        m?.audioMessage ||
        m?.documentMessage
      ),
      message_type: Object.keys(m || {})[0] || 'text',
      push_name: msg.pushName || ''
    };

    queueWebhook(payload);
    metrics.lastInbound = new Date().toISOString();

  } catch (fetchErr) {
    metrics.webhookFailed++;
    addLog('error', '[Webhook] Failed to persist message:', fetchErr.message);
    throw fetchErr;
  }
}

// ─── Socket Singleton Manager & Lifecycle ─────────────────────────────────────
async function initBaileysSocket(reason = 'Startup') {
  return initMutex.runExclusive(async () => {
    cancelReconnectTimer();

    if (currentState === EngineState.INITIALIZING || currentState === EngineState.CONNECTING) {
      addLog('warn', `[SocketManager] Init requested while in ${currentState} state. Skipping redundant init.`);
      return;
    }

    currentState = EngineState.INITIALIZING;
    addLog('info', `[SocketManager] 🔄 Initializing Baileys Socket (${reason})...`);

    try {
      await closeExistingSocket(reason);

      if (!fs.existsSync(SESSION_DIR)) {
        fs.mkdirSync(SESSION_DIR, { recursive: true });
      }

      ensureDirectories();
      loadMappings();

      await credentialWrites;
      await Promise.all([...keyWrites]);
      const credentialsPath = path.join(SESSION_DIR, 'creds.json');
      if (fs.existsSync(credentialsPath)) {
        let existingCredentials;
        try { existingCredentials = JSON.parse(fs.readFileSync(credentialsPath, 'utf8'), BufferJSON.reviver); }
        catch { throw new Error('Existing authentication file is unreadable; replacement and pairing are blocked'); }
        if (!existingCredentials?.noiseKey?.private || !existingCredentials?.signedIdentityKey?.private) {
          throw new Error('Existing authentication file is incomplete; replacement and pairing are blocked');
        }
      }
      const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);
      const persistKeys = state.keys.set.bind(state.keys);
      state.keys.set = data => {
        const pending = persistKeys(data);
        keyWrites.add(pending);
        pending.then(() => keyWrites.delete(pending), err => {
          keyWrites.delete(pending);
          currentState = EngineState.ERROR;
          addLog('error', '[Auth] Signal key persistence failed:', err.message);
        });
        return pending;
      };
      authRegistered = Boolean(state.creds.registered || state.creds.me?.id);
      ownLid = canonicalJid(state.creds.me?.lid || '');
      const signalCache = new NodeCache({ stdTTL: 300, useClones: false });

      let version = [2, 3000, 1015901307];
      try {
        const v = await fetchLatestBaileysVersion();
        if (v?.version) version = v.version;
      } catch (verErr) {
        addLog('warn', '[SocketManager] fetchLatestBaileysVersion fallback:', verErr.message);
      }

      currentState = EngineState.CONNECTING;
      addLog('info', `[SocketManager] Establishing connection (WA Version: ${version.join('.')})...`);

      sock = makeWASocket({
        version,
        browser: ['Ubuntu', 'Chrome', '20.0.04'],
        auth: {
          creds: state.creds,
          keys: makeCacheableSignalKeyStore(state.keys, logger, signalCache)
        },
        msgRetryCounterCache,
        syncFullHistory: false,
        shouldSyncHistoryMessage: () => false,
        markOnlineOnConnect: false,
        // The installed 6.7.24 API applies this before attempting to decrypt ignored channels.
        shouldIgnoreJid: jid => typeof jid === 'string' && (jid === 'status@broadcast' || jid.endsWith('@broadcast') || jid.endsWith('@newsletter')),
        generateHighQualityLinkPreview: false,
        logger,
        printQRInTerminal: false,
        getMessage: async (key) => {
          if (!key?.id) return undefined;
          const cached = await fetchRetryMessage(key, sock);
          const msg = cached?.message || cached;
          if (msg && (msg.conversation || msg.extendedTextMessage || msg.imageMessage || msg.documentMessage || msg.videoMessage || msg.audioMessage)) {
            addLog('info', `[GetMessage] Serving stored message ${key.id} for retry to ${key.remoteJid}`);
            return msg;
          }
          if (cached?.message) {
            addLog('info', `[GetMessage] Serving stored message ${key.id} for retry to ${key.remoteJid}`);
            return cached.message;
          }
          addLog('warn', `[GetMessage] Message ${key.id} requested for retry but not found in cache`);
          return undefined;
        }
      });

      const activeSocket = sock;
      sock.ev.on('chats.phoneNumberShare', ({ lid, jid }) => recordMapping(lid, jid));
      sock.ev.on('contacts.upsert', contacts => {
        for (const contact of contacts || []) {
          if (contact.lid && contact.id?.endsWith('@s.whatsapp.net')) recordMapping(contact.lid, contact.id);
        }
      });
      sock.ev.on('creds.update', () => {
        credentialWrites = credentialWrites.then(saveCreds).catch(err => {
          currentState = EngineState.ERROR;
          addLog('error', '[Auth] Credential persistence failed:', err.message);
          throw err;
        });
        // Observe rejection; the chain remains rejected to block unsafe recreation.
        void credentialWrites.catch(() => {});
        authRegistered = Boolean(state.creds.registered || state.creds.me?.id);
      });

      // ── Connection Update ───────────────────────────────────────────────────
      sock.ev.on('connection.update', async (update) => {
        if (sock !== activeSocket) return;
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
          qrCodeData = qr;
          try {
            qrCodeDataUrl = await QRCode.toDataURL(qr);
            addLog('info', '[Baileys] New QR Code generated — ready for scan.');
          } catch (e) {
            addLog('error', '[Baileys] Failed to generate QR data URL:', e.message);
          }
        }

        if (connection === 'open') {
          currentState = EngineState.CONNECTED;
          authRegistered = true;
          qrCodeData = null;
          qrCodeDataUrl = null;
          pendingPairingCode = null;

          const userJid = sock.user?.id || '';
          connectedPhone = normalizeNumber(userJid.split('@')[0].split(':')[0]);
          botName = sock.user?.name || 'Elsaidy Bot';

          addLog('info', `[Baileys] ✅ WhatsApp Connected! Phone: ${connectedPhone}, Name: ${botName}`);
        }

        if (connection === 'close') {
          currentState = EngineState.DISCONNECTED;
          const statusCode = lastDisconnect?.error?.output?.statusCode;
          lastDisconnectReason = statusCode;

          addLog('warn', `[Baileys] Connection closed. StatusCode: ${statusCode}`);

          if (statusCode === DisconnectReason.loggedOut) {
            addLog('warn', '[Baileys] 401 Logged Out — preserving session files and requiring explicit re-pairing approval.');
            connectedPhone = null;
            botName = null;
            qrCodeDataUrl = null;
            qrCodeData = null;
            cancelReconnectTimer();
          } else if ([DisconnectReason.connectionReplaced, DisconnectReason.badSession].includes(statusCode)) {
            addLog('error', '[Baileys] Terminal disconnect; preserved session for investigation');
            cancelReconnectTimer();
          } else if (statusCode === 515) {
            addLog('warn', '[Baileys] 515 Restart Required — reconnecting without purge in 2.5s...');
            scheduleReconnect(2500, '515 Restart Required');
          } else {
            scheduleReconnect(5000, `Disconnect code ${statusCode}`);
          }
        }
      });

      // ── Messages Upsert ─────────────────────────────────────────────────────
      sock.ev.on('messages.upsert', async ({ messages, type }) => {
        if (sock !== activeSocket) return;
        for (const msg of (messages || [])) {
          try {
          const msgId = msg.key?.id;
          const remoteJid = msg.key?.remoteJid || '';
          const fromMe = !!msg.key?.fromMe;

          // 1. Immediately drop status broadcasts and newsletter channels
          if (!remoteJid || remoteJid === 'status@broadcast' || remoteJid.endsWith('@broadcast') || remoteJid.includes('@newsletter')) {
            continue;
          }

          if (fromMe) {
            continue;
          }

          // Dynamically drop companion sync messages from the bot's own primary device
          const remoteUser = (remoteJid || '').split('@')[0].split(':')[0];
          const myPhone = (connectedPhone || state?.creds?.me?.id || '').split('@')[0].split(':')[0];
          const myLid = (state?.creds?.me?.lid || '').split('@')[0].split(':')[0];
          if ((myPhone && remoteUser === myPhone) || (myLid && remoteUser === myLid)) {
            continue; // Drop internal multi-device peer sync messages
          }

          if (!msg.message) {
            const stubType = msg.messageStubType;
            const stubParams = msg.messageStubParameters;
            if (stubType === 2 || stubType === proto?.WebMessageInfo?.StubType?.CIPHERTEXT) {
              if (msgId) {
                pendingRetries.set(messageCacheKey(msg.key), { remoteJid, timestamp: Date.now(), original: msg });
                for (const [id, pending] of pendingRetries) {
                  if (Date.now() - pending.timestamp > 600000 || pendingRetries.size > 1000) pendingRetries.delete(id);
                }
              }
              const kind = retryKind(stubParams);
              if (kind === 'absent') metrics.absentMessages++; else metrics.decryptionErrors++;
              addLog('warn', `[RetryPending] Message ${msgId} from ${remoteJid}: ${kind}; recovery not confirmed.`);
            } else {
              addLog('warn', `[MsgUndecrypted] Message ${msgId} from ${remoteJid} undecrypted | StubType: ${stubType} | Params: ${JSON.stringify(stubParams)}`);
            }
            continue;
          }

          const dedupKey = messageCacheKey(msg.key);
          if (dedupKey && dedupCache.has(dedupKey)) {
            continue;
          }

          metrics.messagesReceived++;

          storeMessage(msgId, msg);

          const m = unwrapMessage(msg);
          const text = extractMessageText(m);

          if (!text && !(m?.imageMessage || m?.videoMessage || m?.audioMessage || m?.documentMessage)) {
            addLog('debug', `[MsgNoText] Message ${msgId} has no text (type: ${Object.keys(m || {})[0]})`);
            continue;
          }

          await dispatchMessageToFrappe(msg, m, text);
          if (dedupKey) dedupCache.set(dedupKey, true);
          } catch (err) { addLog('error', '[Inbound] Processing failed:', err.message); }
        }
      });

      // ── Message Updates ─────────────────────────────────────────────────────
      sock.ev.on('messages.update', async (updates) => {
        if (sock !== activeSocket) return;
        for (const update of updates || []) {
          try {
            if (update.key?.fromMe && update.update?.status != null) {
              queueWebhook({ event_type: 'status_update', message_id: update.key.id,
                remote_jid: update.key.remoteJid, status_code: update.update.status });
            }
            if (update.key?.id && update.update?.message && !update.key.fromMe) {
              // Only retry previously observed inbound messages; unknown updates may be history/self sync.
              const dedupKey = messageCacheKey(update.key);
              if (!pendingRetries.has(dedupKey)) continue;
              const fullMsg = { ...pendingRetries.get(dedupKey).original, key: update.key, message: update.update.message };
              if (dedupCache.has(dedupKey)) continue;
              storeMessage(update.key.id, fullMsg);
              const m = unwrapMessage(fullMsg);
              await dispatchMessageToFrappe(fullMsg, m, extractMessageText(m));
              dedupCache.set(dedupKey, true);
              pendingRetries.delete(dedupKey);
            }
          } catch (err) { addLog('error', '[MessageUpdate]', err.message); }
        }
      });

      sock.ev.on('message-receipt.update', receipts => {
        if (sock !== activeSocket) return;
        for (const r of receipts || []) {
          if (!r.key?.fromMe) continue;
          const status = r.receipt?.readTimestamp ? 4 : r.receipt?.receiptTimestamp ? 3 : null;
          if (status != null) {
            try { queueWebhook({ event_type: 'status_update', message_id: r.key.id,
              remote_jid: r.key.remoteJid, status_code: status }); }
            catch (err) { addLog('error', '[Receipt]', err.message); }
          }
        }
      });

      addLog('info', '[SocketManager] Socket setup complete, waiting for event updates...');

    } catch (err) {
      currentState = EngineState.ERROR;
      addLog('error', '[SocketManager] Fatal socket initialization error:', err.message);
      scheduleReconnect(8000, 'Fatal init error');
    }
  });
}

function scheduleReconnect(delayMs, reason) {
  if (shuttingDown) return;
  cancelReconnectTimer();
  metrics.reconnections++;
  addLog('warn', `[SocketManager] Scheduling reconnect in ${delayMs}ms (Reason: ${reason})...`);
  reconnectTimer = setTimeout(() => {
    initBaileysSocket(reason).catch(e => addLog('error', '[SocketManager] Reconnect failed:', e.message));
  }, delayMs);
}

// ─── HTTP API Endpoints ────────────────────────────────────────────────────────

// GET /health
app.get('/health', (req, res) => {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });
  const uptimeSec = Math.floor((Date.now() - engineStartTime) / 1000);
  const memUsage = process.memoryUsage();
  res.json({
    status: 'ok',
    engine_state: currentState,
    whatsapp: currentState.toLowerCase(),
    connected: currentState === EngineState.CONNECTED,
    phone: connectedPhone,
    bot_name: botName,
    has_qr: !!qrCodeDataUrl,
    version: '3.2.0-enterprise',
    uptime_seconds: uptimeSec,
    memory_mb: {
      rss: Math.round(memUsage.rss / 1024 / 1024),
      heapUsed: Math.round(memUsage.heapUsed / 1024 / 1024)
    },
    metrics: {
      errors: metrics.errors,
      decryption_errors: metrics.decryptionErrors,
      self_decryption_errors: metrics.selfDecryptionErrors,
      absent_messages: metrics.absentMessages,
      pending_retries: pendingRetries.size,
      webhook_success: metrics.webhookSuccess,
      webhook_failed: metrics.webhookFailed,
      webhook_pending: fs.existsSync(OUTBOX_DIR) ? fs.readdirSync(OUTBOX_DIR).filter(f => f.endsWith('.json')).length : 0,
      last_inbound: metrics.lastInbound,
      last_outbound: metrics.lastOutbound,
      messages_received: metrics.messagesReceived,
      messages_sent: metrics.messagesSent,
      heal_operations: metrics.healOperations,
      reconnections: metrics.reconnections
    }
  });
});

// GET /status
app.get('/status', (req, res) => {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });
  res.json({
    status: 'ok',
    engine_state: currentState,
    connection_status: currentState === EngineState.CONNECTED ? 'connected' : (currentState === EngineState.CONNECTING ? 'connecting' : 'disconnected'),
    connected: currentState === EngineState.CONNECTED,
    bot_phone: connectedPhone,
    bot_name: botName,
    has_qr: !!qrCodeDataUrl,
    last_disconnect_reason: lastDisconnectReason,
    uptime_seconds: Math.floor((Date.now() - engineStartTime) / 1000)
  });
});

app.get('/diagnostics', (req, res) => {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });
  res.json({ status: 'ok', ...serviceDiagnostics(SESSION_DIR),
    engine_state: currentState, pending_retries: pendingRetries.size,
    auth_registered: authRegistered, destructive_actions_enabled: false });
});

// GET /qr
app.get('/qr', (req, res) => {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });

  if (currentState === EngineState.CONNECTED) {
    return res.json({ status: 'already_connected', bot_phone: connectedPhone });
  }

  if (!qrCodeDataUrl) {
    return res.json({ status: 'no_qr', message: 'لا يوجد QR Code حالياً. جاري تهيئة الاتصال أو يمكنك استخدام Pairing Code.' });
  }

  res.json({
    status: 'ok',
    qr_data_url: qrCodeDataUrl,
    qr_data: qrCodeData
  });
});

// POST /pairing-code & /pair-phone
async function handlePairingCode(req, res) {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });

  if (currentState === EngineState.CONNECTED) {
    return res.json({ status: 'already_connected', bot_phone: connectedPhone });
  }

  const { phone } = req.body;
  if (!phone) {
    return res.status(400).json({ error: 'حقل phone مطلوب' });
  }

  const cleanPhone = normalizeNumber(phone);
  if (!cleanPhone || cleanPhone.length < 9) {
    return res.status(400).json({ error: 'رقم هاتف غير صالح' });
  }

  addLog('info', `[PairPhone] Requesting pairing code for: ${cleanPhone}...`);

  try {
    // Pair on the existing unregistered socket. Never erase an active auth store.
    if (authRegistered) return res.status(409).json({ error: 'Registered session preserved; pairing is blocked' });
    if (!sock) {
      return res.status(500).json({ error: 'تعذر تهيئة مقبس الواتساب' });
    }

    const code = await sock.requestPairingCode(cleanPhone);
    pendingPairingCode = code;

    addLog('info', `[PairPhone] Pairing Code generated for ${cleanPhone}`);

    res.json({
      status: 'ok',
      code: code,
      phone: cleanPhone,
      formatted_code: code ? `${code.slice(0, 4)}-${code.slice(4)}` : code
    });

  } catch (err) {
    addLog('error', '[PairPhone] Failed to generate pairing code:', err.message);
    res.status(500).json({ error: `فشل إنشاء كود الربط: ${err.message}` });
  }
}

app.post('/pairing-code', handlePairingCode);
app.post('/pair-phone', handlePairingCode);

// POST /send & /send-message
async function handleSendMessage(req, res) {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });

  if (!sock || currentState !== EngineState.CONNECTED) {
    return res.status(503).json({ error: 'واتساب غير متصل حالياً' });
  }

  try {
    let { jid, number, message, quoted_message_id, pdf_base64, filename } = req.body;

    if (!jid && number) {
      const clean = normalizeNumber(number);
      if (!clean) return res.status(400).json({ error: 'رقم هاتف غير صالح' });
      jid = `${clean}@s.whatsapp.net`;
    }

    if (!jid) return res.status(400).json({ error: 'المستلم غير محدد (jid أو number مطلوب)' });

    // Ensure valid domain if digits only
    if (!jid.includes('@')) {
      const clean = normalizeNumber(jid);
      jid = `${clean}@s.whatsapp.net`;
    }

    jid = canonicalJid(jid);
    if (!validRecipient(jid)) return res.status(400).json({ error: 'Invalid recipient JID' });
    if (sameConversation(jid, `${connectedPhone}@s.whatsapp.net`, lidPnMap) || (ownLid && jid === ownLid)) {
      return res.status(400).json({ error: 'Sending to the bot itself is blocked' });
    }
    // Baileys 6.x has no repository LID mapping API: use only dynamically learned exact mappings.
    if (jid.endsWith('@s.whatsapp.net') && pnLidMap.has(jid)) jid = pnLidMap.get(jid);
    if (ownLid && jid === ownLid) return res.status(400).json({ error: 'Sending to the bot itself is blocked' });

    let options = {};
    if (quoted_message_id) {
      const cached = fetchStoredMessage({ id: quoted_message_id, remoteJid: jid, fromMe: false });
      if (cached) {
        options.quoted = cached;
      } else {
        addLog('warn', `[Send] Missing original quoted message ${quoted_message_id}; sending without a fabricated quote.`);
      }
    }

    let sentMsg;
    if (pdf_base64) {
      const buffer = Buffer.from(pdf_base64, 'base64');
      sentMsg = await sock.sendMessage(jid, {
        document: buffer,
        fileName: filename || 'document.pdf',
        mimetype: 'application/pdf',
        caption: message || ''
      }, options);
    } else {
      if (!message) return res.status(400).json({ error: 'نص الرسالة مطلوب' });
      sentMsg = await sock.sendMessage(jid, { text: message }, options);
    }

    const sentMsgId = sentMsg?.key?.id;
    if (!sentMsgId) throw new Error('Baileys did not return a message ID');
    metrics.messagesSent++;
    metrics.lastOutbound = new Date().toISOString();
    if (sentMsgId) {
      storeMessage(sentMsgId, sentMsg);
    }

    addLog('info', `[Send] Sent to ${jid}: ${String(message || '').substring(0, 50)} | MsgID: ${sentMsgId}`);

    res.json({
      status: 'ok',
      msg_id: sentMsgId,
      jid: jid,
      number: jid.split('@')[0],
      delivery_ack: sentMsg?.status || 'PENDING'
    });

  } catch (err) {
    addLog('error', '[Send] Error sending message:', err.message);
    res.status(500).json({ error: `فشل إرسال الرسالة: ${err.message}` });
  }
}

app.post('/send', handleSendMessage);
app.post('/send-message', handleSendMessage);

// POST /sync-contact-mapping (Dynamic LID <-> Phone mapping from Frappe)
app.post('/sync-contact-mapping', (req, res) => {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });

  const { mappings } = req.body;
  let count = 0;
  if (Array.isArray(mappings)) {
    for (const m of mappings) {
      if (m.lid && m.phone) {
        recordMapping(m.lid, m.phone);
        count++;
      }
    }
  }
  res.json({ status: 'ok', mapped_count: count });
});

// GET /groups
app.get('/groups', async (req, res) => {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });

  if (!sock || currentState !== EngineState.CONNECTED) {
    return res.status(503).json({ error: 'واتساب غير متصل حالياً' });
  }

  try {
    const groupsMap = await sock.groupFetchAllParticipating();
    const groupsList = Object.values(groupsMap).map(g => ({
      jid: g.id,
      name: g.subject || 'بدون اسم',
      participants_count: (g.participants || []).length,
      creation: g.creation || 0,
      desc: g.desc || ''
    }));

    groupsList.sort((a, b) => a.name.localeCompare(b.name));
    res.json({ status: 'ok', count: groupsList.length, groups: groupsList });
  } catch (err) {
    addLog('error', '[Baileys] Error fetching participating groups:', err.message);
    res.status(500).json({ error: `فشل جلب المجموعات: ${err.message}` });
  }
});

// GET /logs
app.get('/logs', (req, res) => {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });

  const limit = Math.max(1, Math.min(parseInt(req.query.limit || '100', 10) || 100, MAX_LOG_ENTRIES));
  const levelFilter = (req.query.level || '').toLowerCase().trim();
  const searchFilter = (req.query.search || '').toLowerCase().trim();

  let filtered = [...logBuffer];
  if (levelFilter && levelFilter !== 'all') {
    filtered = filtered.filter(l => l.level === levelFilter);
  }
  if (searchFilter) {
    filtered = filtered.filter(l => l.msg.toLowerCase().includes(searchFilter));
  }

  const resultLogs = filtered.reverse().slice(0, limit);
  res.json({
    status: 'ok',
    count: resultLogs.length,
    total_buffered: logBuffer.length,
    logs: resultLogs
  });
});

// POST /restart (Graceful single socket recreation)
app.post('/restart', async (req, res) => {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });

  if (initMutex.isLocked() || currentState === EngineState.RESETTING) return res.status(409).json({ error: 'Restart already in progress' });
  addLog('info', '[Restart] Manual graceful restart initiated...');
  currentState = EngineState.RESETTING;

  setTimeout(() => {
    initBaileysSocket('Manual restart').catch(err => addLog('error', 'Restart failed:', err.message));
  }, 500);

  res.json({ status: 'ok', message: 'جاري إعادة تشغيل المقبس بأمان دون مسح الجلسة...' });
});

// Destructive session operations are deliberately unavailable in the production API.
for (const endpoint of ['/logout', '/wipe-session', '/heal-sessions']) {
  app.post(endpoint, (req, res) => {
    if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });
    return res.status(409).json({ status: 'disabled', error: 'Session destruction is disabled. Use diagnostics.' });
  });
}

// ─── Server Startup ───────────────────────────────────────────────────────────
const httpServer = app.listen(PORT, '0.0.0.0', () => {
  addLog('info', `[Baileys] 🚀 Server listening on port ${PORT} — Elsaidy WhatsApp Hub v3.2.0-Enterprise`);
});

async function shutdown() {
  if (shuttingDown) return;
  shuttingDown = true;
  cancelReconnectTimer();
  try {
    await closeExistingSocket('Service shutdown');
    await credentialWrites;
    await Promise.all([...keyWrites]);
    httpServer.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 5000).unref();
  } catch (err) {
    addLog('error', '[Shutdown] Persistence error:', err.message);
    process.exit(1);
  }
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

if (API_TOKEN) initBaileysSocket('Initial startup').catch(err => {
  addLog('error', '[Baileys] Fatal initial startup error:', err.message);
});
