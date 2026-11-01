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
  S_WHATSAPP_NET
} from '@whiskeysockets/baileys';

const app = express();
const logger = pino({ level: 'warn' });

const PORT = process.env.PORT || 3000;
const API_TOKEN = process.env.WA_API_TOKEN || 'HAGAG_WA_7f3c9a2d6e4b8a1c';
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

// Caches
const msgRetryCounterCache = new NodeCache({ stdTTL: 600, checkperiod: 120 });
const messageStore = new NodeCache({ stdTTL: 3600, checkperiod: 600 });
const dedupCache = new NodeCache({ stdTTL: 3600, checkperiod: 300 });
const signalCache = new NodeCache({ stdTTL: 300, useClones: false, deleteOnExpire: true });

// Session healing cooldown tracker: JID -> { count, lastAttempt }
const healCooldownMap = new Map();
const MAX_HEAL_ATTEMPTS = 3;
const HEAL_COOLDOWN_MS = 5 * 60 * 1000; // 5 minutes

// Dynamic LID <-> Phone Number mapping (learned at runtime from WhatsApp stanzas & Frappe contacts)
const lidPnMap = new Map();

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
  const queryToken = req.query.token || '';
  return auth === `Bearer ${API_TOKEN}` || headerToken === API_TOKEN || queryToken === API_TOKEN;
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
  if (!targetId) return { status: 'error', message: 'Target ID / JID is required' };

  // Check cooldown
  const now = Date.now();
  const history = healCooldownMap.get(targetId) || { count: 0, lastAttempt: 0 };
  if (history.count >= MAX_HEAL_ATTEMPTS && (now - history.lastAttempt) < HEAL_COOLDOWN_MS) {
    const waitSec = Math.ceil((HEAL_COOLDOWN_MS - (now - history.lastAttempt)) / 1000);
    addLog('warn', `[SessionHeal] Cooldown active for ${targetId}. Try again in ${waitSec}s.`);
    return { status: 'cooldown', message: `العملية في فترة التهدئة لهذا المعرف. انتظر ${waitSec} ثانية.` };
  }

  addLog('info', `[SessionHeal] Diagnosing and healing session for target: ${targetId}...`);
  metrics.healOperations++;

  // Normalize target identifier
  const cleanId = String(targetId).trim();
  const isLid = cleanId.includes('@lid');
  const isGroup = cleanId.includes('@g.us');
  let signalUser = cleanId.split('@')[0].split(':')[0];

  // If provided as 251036744843464.0, strip device
  const addrMatch = signalUser.match(/^(\d+)\.\d+$/);
  if (addrMatch) {
    signalUser = addrMatch[1];
  }

  let deletedCount = 0;
  const deletedFiles = [];

  try {
    if (fs.existsSync(SESSION_DIR)) {
      const files = fs.readdirSync(SESSION_DIR);
      for (const file of files) {
        // STRICT SAFETY: Never touch creds.json or core auth keys
        if (file === 'creds.json' || file.startsWith('app-state-sync-key')) {
          continue;
        }

        let isMatch = false;
        if (isGroup) {
          // If group, clear sender keys for this group
          if (file.startsWith(`sender-key-${signalUser}`) || file.startsWith(`sender-key-memory-${signalUser}`)) {
            isMatch = true;
          }
        } else {
          // Direct chat / LID / PN session file
          if (file.startsWith(`session-${signalUser}`)) {
            isMatch = true;
          }
        }

        if (isMatch) {
          try {
            fs.unlinkSync(path.join(SESSION_DIR, file));
            deletedCount++;
            deletedFiles.push(file);
            addLog('info', `[SessionHeal] Safely removed corrupted key file: ${file}`);
          } catch (delErr) {
            addLog('warn', `[SessionHeal] Could not delete ${file}: ${delErr.message}`);
          }
        }
      }
    }

    // Flush in-memory signalCache for this user
    try {
      let flushedKeys = 0;
      for (const k of signalCache.keys()) {
        if (k.includes(signalUser)) {
          signalCache.del(k);
          flushedKeys++;
        }
      }
      if (flushedKeys > 0) {
        addLog('info', `[SessionHeal] Flushed ${flushedKeys} in-memory signal keys for ${signalUser}`);
      }
    } catch (cErr) {
      addLog('warn', `[SessionHeal] Could not clear signalCache: ${cErr.message}`);
    }

    // Update cooldown
    healCooldownMap.set(targetId, {
      count: history.count + 1,
      lastAttempt: now
    });

    return {
      status: 'ok',
      target: targetId,
      deleted_files_count: deletedCount,
      deleted_files: deletedFiles,
      session_reasserted: false,
      message: `تم تطهير ملفات وكاش الجلسة بأمان للمعرف (${targetId}). الملفات المعالجة: ${deletedCount}.`
    };

  } catch (err) {
    addLog('error', `[SessionHeal] Error healing session for ${targetId}:`, err.message);
    return { status: 'error', error: err.message };
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
          const msg = messageStore.get(key?.id);
          return msg?.message || undefined;
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
            addLog('warn', '[Baileys] 401 Logged Out — purging session directory and restarting in 3s...');
            clearSessionDirectory();
            connectedPhone = null;
            botName = null;
            qrCodeDataUrl = null;
            qrCodeData = null;
            scheduleReconnect(3000, '401 LoggedOut');
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
            addLog('warn', `[MsgUndecrypted] Message ${msgId} from ${remoteJid} could not be decrypted | StubType: ${stubType} | Params: ${JSON.stringify(stubParams)}`);
            continue;
          }

          if (msgId && dedupCache.has(msgId)) {
            continue;
          }
          if (msgId) dedupCache.set(msgId, true);
          metrics.messagesReceived++;

          const isGroup = remoteJid.endsWith('@g.us');
          const senderJid = isGroup
            ? (msg.key.participant || msg.participant || '')
            : remoteJid;

          // Learn / resolve LID <-> Phone Number
          let rawSenderPn = msg.key.senderPn || msg.key.participantPn || '';
          const signalUser = senderJid.split('@')[0].split(':')[0];
          if (rawSenderPn) {
            lidPnMap.set(signalUser, normalizeNumber(rawSenderPn));
            lidPnMap.set(senderJid, normalizeNumber(rawSenderPn));
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
          // replyJid: MUST ALWAYS be remoteJid (the conversation chat where the message was sent!)
          const replyJid = remoteJid;

          messageStore.set(msgId, msg);

          // Unwrap all message wrappers (ephemeral, viewOnce, etc.)
          let m = msg.message;
          while (m && (m.ephemeralMessage || m.viewOnceMessage || m.viewOnceMessageV2 || m.documentWithCaptionMessage)) {
            m = (m.ephemeralMessage || m.viewOnceMessage || m.viewOnceMessageV2 || m.documentWithCaptionMessage).message;
          }

          const text =
            m?.conversation ||
            m?.extendedTextMessage?.text ||
            m?.imageMessage?.caption ||
            m?.videoMessage?.caption ||
            m?.documentMessage?.caption ||
            m?.buttonsResponseMessage?.selectedButtonId ||
            m?.listResponseMessage?.singleSelectReply?.selectedRowId ||
            '';

          if (!text) {
            addLog('debug', `[MsgNoText] Message ${msgId} has no text (type: ${Object.keys(m || {})[0]})`);
            continue;
          }

          addLog('info', `[Msg] From: ${senderPhone || senderJid} | RemoteJid: ${remoteJid} | Text: ${text.substring(0, 60)} | MsgID: ${msgId}`);

          // Forward to Frappe webhook
          try {
            const payload = {
              event_type: 'message',
              message_id: msgId,
              remote_jid: remoteJid,
              sender_jid: senderJid,
              sender_phone: senderPhone,
              sender_lid: senderJid.includes('@lid') ? senderJid : (remoteJid.includes('@lid') ? remoteJid : ''),
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
          if (update.key.id && update.update.message) {
            messageStore.set(update.key.id, { key: update.key, message: update.update.message });
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
    clearSessionDirectory();
    await initBaileysSocket('Pre-pairing session wipe');

    await new Promise(resolve => setTimeout(resolve, 2500));

    if (!sock) {
      return res.status(500).json({ error: 'تعذر تهيئة مقبس الواتساب' });
    }

    const code = await sock.requestPairingCode(cleanPhone);
    pendingPairingCode = code;

    addLog('info', `[PairPhone] ✅ Pairing Code generated: ${code} for ${cleanPhone}`);

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
      const cached = messageStore.get(quoted_message_id);
      if (cached) {
        options.quoted = cached;
      } else {
        options.quoted = {
          key: { remoteJid: jid, id: quoted_message_id, fromMe: false },
          message: { conversation: '' }
        };
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
      messageStore.set(sentMsgId, sentMsg);
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
  const httpCode = result.status === 'ok' ? 200 : (result.status === 'cooldown' ? 429 : 500);
  res.status(httpCode).json(result);
});

// POST /sync-contact-mapping (Dynamic LID <-> Phone mapping from Frappe)
app.post('/sync-contact-mapping', (req, res) => {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });

  const { mappings } = req.body;
  let count = 0;
  if (Array.isArray(mappings)) {
    for (const m of mappings) {
      if (m.lid && m.phone) {
        const cleanLid = String(m.lid).trim().replace('@lid', '');
        const cleanPn = normalizeNumber(m.phone);
        lidPnMap.set(cleanLid, cleanPn);
        lidPnMap.set(`${cleanLid}@lid`, cleanPn);
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
