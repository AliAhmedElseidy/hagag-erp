import express from 'express';
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
  jidDecode,
  isJidGroup,
  S_WHATSAPP_NET,
  proto
} from '@whiskeysockets/baileys';

const app = express();
const logger = pino({ level: 'warn' });

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
  const msg = args.map(a => (typeof a === 'object' ? JSON.stringify(a) : String(a))).join(' ');
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
const resetMutex = new Mutex();
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
const signalCache = new NodeCache({ stdTTL: 300, useClones: false, deleteOnExpire: true });
const pendingRetries = new Map(); // msgId -> { remoteJid, timestamp }

const MESSAGE_CACHE_DIR = path.join(SESSION_DIR, 'message_cache');
const MAPPINGS_FILE = path.join(SESSION_DIR, 'contact_mappings.json');

// Session healing cooldown tracker: JID -> { count, lastAttempt }
const healCooldownMap = new Map();
const MAX_HEAL_ATTEMPTS = 3;
const HEAL_COOLDOWN_MS = 5 * 60 * 1000; // 5 minutes

// Bidirectional Dynamic LID <-> Phone Number mapping
const lidPnMap = new Map(); // LID -> Phone
const pnLidMap = new Map(); // Phone -> LID

function ensureDirectories() {
  try {
    if (!fs.existsSync(SESSION_DIR)) fs.mkdirSync(SESSION_DIR, { recursive: true });
    if (!fs.existsSync(MESSAGE_CACHE_DIR)) fs.mkdirSync(MESSAGE_CACHE_DIR, { recursive: true });
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

  const raw = String(lidOrJid).trim();
  const cleanLid = raw.replace('@lid', '').split(':')[0];
  const lidJid = `${cleanLid}@lid`;

  lidPnMap.set(cleanLid, cleanPn);
  lidPnMap.set(lidJid, cleanPn);

  pnLidMap.set(cleanPn, lidJid);
  pnLidMap.set(`${cleanPn}@s.whatsapp.net`, lidJid);

  saveMappings();
}

function storeMessage(msgId, msgObj) {
  if (!msgId || !msgObj) return;
  messageStore.set(msgId, msgObj);
  try {
    ensureDirectories();
    const filePath = path.join(MESSAGE_CACHE_DIR, `${msgId}.json`);
    fs.writeFileSync(filePath, JSON.stringify(msgObj), 'utf8');
  } catch (err) {
    // Non-fatal cache failure
  }
}

function fetchStoredMessage(msgId) {
  if (!msgId) return null;
  const inMem = messageStore.get(msgId);
  if (inMem) return inMem;
  try {
    const filePath = path.join(MESSAGE_CACHE_DIR, `${msgId}.json`);
    if (fs.existsSync(filePath)) {
      const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
      messageStore.set(msgId, data);
      return data;
    }
  } catch (err) {
    // Non-fatal cache read failure
  }
  return null;
}

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
  let n = String(number).replace(/\D/g, '');

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
  return auth === `Bearer ${API_TOKEN}` || headerToken === API_TOKEN;
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
      sock.ev.removeAllListeners();
      sock.end(new Error(reason));
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

function clearSessionDirectory() {
  try {
    if (fs.existsSync(SESSION_DIR)) {
      const files = fs.readdirSync(SESSION_DIR);
      for (const file of files) {
        try {
          fs.rmSync(path.join(SESSION_DIR, file), { recursive: true, force: true });
        } catch (e) {
          addLog('error', `Failed to delete session file ${file}:`, e.message);
        }
      }
      addLog('info', '[Baileys] Entire session directory purged.');
    }
  } catch (err) {
    addLog('error', 'Error purging session directory:', err.message);
  }
}

// ─── Targeted Session Healing (Bad MAC / Decrypt Error Recovery) ───────────────
async function healTargetSession(targetId) {
  // Automatic or manual deletion of live Signal keys is unsafe.
  // Retain this endpoint as an explicit non-destructive diagnostic response.
  addLog('warn', '[SessionHeal] Deprecated destructive healing blocked');
  return {
    status: 'disabled',
    message: 'Destructive Signal key healing is disabled. Use read-only diagnostics and controlled re-pairing only if explicitly approved.'
  };
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

  let rawSenderPn = msg.key.senderPn || msg.key.participantPn || '';
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
      timestamp: msg.messageTimestamp,
      has_media: !!(
        m?.imageMessage ||
        m?.videoMessage ||
        m?.audioMessage ||
        m?.documentMessage
      ),
      message_type: Object.keys(m || {})[0] || 'text',
      push_name: msg.pushName || ''
    };

    const resp = await fetch(FRAPPE_WEBHOOK_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Host': FRAPPE_HOST,
        'X-Frappe-Site-Name': FRAPPE_HOST,
        'X-Api-Token': API_TOKEN
      },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(15000)
    });

    if (resp.ok) {
      metrics.webhookSuccess++;
    } else {
      metrics.webhookFailed++;
      addLog('warn', `[Webhook] Frappe returned HTTP ${resp.status} for msg ${msgId}`);
    }
  } catch (fetchErr) {
    metrics.webhookFailed++;
    addLog('error', '[Webhook] Failed to forward message to Frappe:', fetchErr.message);
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

      const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);

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
        generateHighQualityLinkPreview: false,
        logger,
        printQRInTerminal: false,
        getMessage: async (key) => {
          if (!key?.id) return undefined;
          const cached = fetchStoredMessage(key.id);
          if (cached?.message) {
            addLog('info', `[GetMessage] Serving stored message ${key.id} for retry to ${key.remoteJid}`);
            return cached.message;
          }
          addLog('warn', `[GetMessage] Message ${key.id} requested for retry but not found in cache`);
          return undefined;
        }
      });

      sock.ev.on('creds.update', saveCreds);

      // ── Connection Update ───────────────────────────────────────────────────
      sock.ev.on('connection.update', async (update) => {
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
        for (const msg of (messages || [])) {
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
                pendingRetries.set(msgId, { remoteJid, timestamp: Date.now() });
              }
              addLog('info', `[RetryPending] Message ${msgId} from ${remoteJid} absent from node — Baileys retry request initiated.`);
            } else {
              addLog('warn', `[MsgUndecrypted] Message ${msgId} from ${remoteJid} undecrypted | StubType: ${stubType} | Params: ${JSON.stringify(stubParams)}`);
            }
            continue;
          }

          if (msgId && dedupCache.has(msgId)) {
            continue;
          }
          if (msgId) dedupCache.set(msgId, true);
          metrics.messagesReceived++;

          storeMessage(msgId, msg);

          const m = unwrapMessage(msg);
          const text = extractMessageText(m);

          if (!text) {
            addLog('debug', `[MsgNoText] Message ${msgId} has no text (type: ${Object.keys(m || {})[0]})`);
            continue;
          }

          await dispatchMessageToFrappe(msg, m, text);
        }
      });

      // ── Message Updates ─────────────────────────────────────────────────────
      sock.ev.on('messages.update', async (updates) => {
        for (const update of updates) {
          if (update.update?.status) {
            const statusNames = { 1: 'PENDING', 2: 'SERVER_ACK', 3: 'DELIVERY_ACK', 4: 'READ', 5: 'PLAYED' };
            const statusName = statusNames[update.update.status] || update.update.status;
            addLog('info', `[MsgStatus] MsgID: ${update.key?.id} | To: ${update.key?.remoteJid} | Status: ${statusName} (${update.update.status})`);

            // Forward delivery receipt status to Frappe webhook
            try {
              fetch(FRAPPE_WEBHOOK_URL, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  'Host': FRAPPE_HOST,
                  'X-Frappe-Site-Name': FRAPPE_HOST,
                  'X-Api-Token': API_TOKEN
                },
                body: JSON.stringify({
                  event_type: 'status_update',
                  message_id: update.key?.id,
                  remote_jid: update.key?.remoteJid,
                  status_code: update.update.status,
                  status_name: statusName
                }),
                signal: AbortSignal.timeout(5000)
              }).catch(() => {});
            } catch (_) {}
          }

          if (update.key?.id && update.update?.message) {
            const msgId = update.key.id;
            const fullMsg = { key: update.key, message: update.update.message };
            storeMessage(msgId, fullMsg);

            // If this message was pending retry resolution from a previously absent node
            if (pendingRetries.has(msgId) || !dedupCache.has(msgId)) {
              pendingRetries.delete(msgId);
              const m = unwrapMessage(fullMsg);
              const text = extractMessageText(m);
              if (text && !dedupCache.has(msgId)) {
                dedupCache.set(msgId, true);
                metrics.messagesReceived++;
                addLog('info', `[RetryResolved] Successfully decrypted pending message ${msgId} after retry! Forwarding to Frappe...`);
                await dispatchMessageToFrappe(fullMsg, m, text);
              }
            }
          }
        }
      });

      sock.ev.on('message-receipt.update', (receipts) => {
        for (const r of (receipts || [])) {
          const isRead = !!r.receipt?.readTimestamp;
          addLog('info', `[Receipt] MsgID: ${r.key?.id} | From: ${r.receipt?.userJid || r.key?.remoteJid} | ${isRead ? 'READ' : 'DELIVERED'}`);
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
      jid = clean.length > 13 ? `${clean}@lid` : `${clean}@s.whatsapp.net`;
    }

    // Dynamic Outbound Identity Resolution (Auto-route PN -> verified Cloud LID to avoid ratchet mismatch)
    if (jid.endsWith('@s.whatsapp.net')) {
      const cleanPn = normalizeNumber(jid.split('@')[0]);
      if (pnLidMap.has(cleanPn)) {
        const mappedLid = pnLidMap.get(cleanPn);
        addLog('info', `[SendRouting] Auto-routed recipient PN ${cleanPn} -> verified Cloud LID ${mappedLid}`);
        jid = mappedLid;
      }
    }

    // Guard 1: Never send to newsletter or broadcast
    if (jid.includes('@newsletter') || jid.includes('@broadcast') || jid === 'status@broadcast') {
      addLog('warn', `[SendBlocked] Blocked sending to newsletter/broadcast: ${jid}`);
      return res.status(400).json({ error: 'غير مسموح بالإرسال إلى قنوات البث أو النشرات الإخبارية' });
    }

    // Guard 2: Never send to bot's own number
    if (connectedPhone && (jid.startsWith(connectedPhone) || jid === `${connectedPhone}@s.whatsapp.net`)) {
      addLog('warn', `[SendBlocked] Blocked sending to bot own number: ${jid}`);
      return res.status(400).json({ error: 'غير مسموح بإرسال الرسالة إلى رقم البوت نفسه' });
    }

    let options = {};
    if (quoted_message_id) {
      const cached = fetchStoredMessage(quoted_message_id);
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

    metrics.messagesSent++;
    const sentMsgId = sentMsg?.key?.id;
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

// POST /heal-sessions (Self-Healing Bad MAC without full wipe)
app.post('/heal-sessions', async (req, res) => {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });

  const { target } = req.body;
  if (!target) {
    return res.status(400).json({ error: 'معرف الهدف (target / JID / Phone) مطلوب لإجراء الإصلاح الموجه' });
  }

  const result = await healTargetSession(target);
  res.status(409).json(result);
});

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

  const limit = Math.min(parseInt(req.query.limit || '100', 10), MAX_LOG_ENTRIES);
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

  addLog('info', '[Restart] Manual graceful restart initiated...');
  currentState = EngineState.RESETTING;

  setTimeout(() => {
    initBaileysSocket('Manual restart').catch(err => addLog('error', 'Restart failed:', err.message));
  }, 500);

  res.json({ status: 'ok', message: 'جاري إعادة تشغيل المقبس بأمان دون مسح الجلسة...' });
});

// POST /logout (Clean logout and session purge)
app.post('/logout', async (req, res) => {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });

  addLog('warn', '[Logout] Manual logout requested...');
  currentState = EngineState.RESETTING;

  try {
    if (sock) {
      await sock.logout().catch(() => {});
    }
  } catch (e) {}

  await closeExistingSocket('Manual logout');
  clearSessionDirectory();

  connectedPhone = null;
  botName = null;
  qrCodeDataUrl = null;
  qrCodeData = null;
  currentState = EngineState.STOPPED;

  setTimeout(() => {
    initBaileysSocket('Post-logout restart').catch(e => addLog('error', 'Init after logout error:', e.message));
  }, 1000);

  res.json({ status: 'ok', message: 'تم تسجيل الخروج بنجاح ومسح الجلسة.' });
});

// POST /wipe-session (Hard reset)
app.post('/wipe-session', async (req, res) => {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });

  addLog('warn', '[WipeSession] Hard reset initiated...');
  currentState = EngineState.RESETTING;

  await closeExistingSocket('Hard reset');
  clearSessionDirectory();

  connectedPhone = null;
  botName = null;
  qrCodeDataUrl = null;
  qrCodeData = null;
  pendingPairingCode = null;

  setTimeout(() => {
    initBaileysSocket('Post-wipe restart').catch(e => addLog('error', 'Init after wipe error:', e.message));
  }, 1000);

  res.json({
    status: 'ok',
    message: 'تم تطهير مجلد الجلسة بالكامل وإعادة تهيئة المقبس بنجاح.'
  });
});

// ─── Server Startup ───────────────────────────────────────────────────────────
app.listen(PORT, '0.0.0.0', () => {
  addLog('info', `[Baileys] 🚀 Server listening on port ${PORT} — Elsaidy WhatsApp Hub v3.2.0-Enterprise`);
});

initBaileysSocket('Initial startup').catch(err => {
  addLog('error', '[Baileys] Fatal initial startup error:', err.message);
});
