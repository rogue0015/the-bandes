const path = require("node:path");
const fs = require("node:fs/promises");
const crypto = require("node:crypto");
const express = require("express");
const axios = require("axios");
const dotenv = require("dotenv");
const { isStaleProfileError, removeStaleProfileLocks } = require("./profile-locks");

dotenv.config({ path: path.resolve(__dirname, "../.env") });

const QRCode = require("qrcode");
const { Client, LocalAuth } = require("whatsapp-web.js");

const port = Number(process.env.PORT || process.env.WHATSAPP_PORT || 3100);
const apiBaseUrl = process.env.BACKEND_API_URL || "http://127.0.0.1:8000";
const internalToken = process.env.INTERNAL_API_TOKEN || "";
const targetGroupName = (process.env.WHATSAPP_GROUP_NAME || "Bandes").trim();
const urlPattern = /https?:\/\/[^\s<>"']+/gi;
const pendingFile = process.env.WHATSAPP_QUEUE_FILE || path.join(__dirname, "pending-messages.json");
const authDataPath = path.resolve(
  process.env.WHATSAPP_AUTH_PATH || path.join(__dirname, ".wwebjs_auth")
);
const app = express();
app.use(express.json({ limit: "10mb" }));

let ready = false;
let targetGroupFound = null;
let targetChannelFound = null;
let state = "stopped";
let qrDataUrl = null;
let lastError = null;
let startedByUser = false;
let queueReady = false;
let forwarding = false;
let persistence = Promise.resolve();
let reconnectAttempt = 0;
let reconnectTimer = null;
let pendingMessages = [];
let channelProcessing = Promise.resolve();

function isAuthorized(value) {
  const provided = Buffer.from(value || "");
  const expected = Buffer.from(internalToken);
  return expected.length > 0
    && provided.length === expected.length
    && crypto.timingSafeEqual(provided, expected);
}
function isTargetGroup(chat) {
  return chat.isGroup
    && String(chat.name || "").trim().normalize("NFKC").toLocaleLowerCase()
      === targetGroupName.normalize("NFKC").toLocaleLowerCase();
}
function isTargetChannel(chat) {
  return chat.isChannel
    && String(chat.name || "").trim().normalize("NFKC").toLocaleLowerCase()
      === (process.env.WHATSAPP_CHANNEL_NAME || "IT Opportunities Zim")
        .trim().normalize("NFKC").toLocaleLowerCase();
}

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: authDataPath }),
  puppeteer: { headless: true, args: ["--no-sandbox", "--disable-setuid-sandbox"] },
});

async function initializeWhatsAppClient() {
  try {
    await client.initialize();
  } catch (error) {
    if (!isStaleProfileError(error) || client.pupBrowser) throw error;
    const profilePath = path.join(authDataPath, "session");
    if (!await removeStaleProfileLocks(profilePath)) throw error;
    console.warn("Removed stale Chromium profile lock files; retrying WhatsApp startup once.");
    await client.initialize();
  }
}

client.on("qr", (qr) => {
  ready = false;
  targetGroupFound = null;
  targetChannelFound = null;
  state = "qr";
  qrDataUrl = null;
  lastError = null;
  QRCode.toDataURL(qr, { errorCorrectionLevel: "M", width: 320, margin: 2 })
    .then((dataUrl) => {
      qrDataUrl = dataUrl;
      console.log("A new WhatsApp pairing QR is available in the Brandon dashboard.");
    })
    .catch((error) => {
      state = "error";
      lastError = "Could not generate WhatsApp pairing QR";
      console.error(lastError, error.message);
    });
});

client.on("authenticated", () => {
  state = "connecting";
  qrDataUrl = null;
  lastError = null;
  console.log("WhatsApp session authenticated.");
});

client.on("auth_failure", (message) => {
  ready = false;
  state = "error";
  qrDataUrl = null;
  lastError = "WhatsApp authentication failed";
  console.error(lastError, message);
  scheduleReconnect();
});

client.on("ready", async () => {
  ready = true;
  state = "connected";
  qrDataUrl = null;
  lastError = null;
  reconnectAttempt = 0;
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = null;
  console.log("WhatsApp service is ready.");
  try {
    const chats = await client.getChats();
    targetGroupFound = chats.some(isTargetGroup);
    const channels = await client.getChannels();
    targetChannelFound = channels.some(isTargetChannel);
    if (!targetGroupFound) {
      lastError = `Configured WhatsApp group "${targetGroupName}" was not found`;
      console.error(lastError);
    } else if (!targetChannelFound) {
      const channelName = process.env.WHATSAPP_CHANNEL_NAME || "IT Opportunities Zim";
      lastError = `Configured WhatsApp channel "${channelName}" was not found`;
      console.error(lastError);
    }
  } catch (error) {
    targetGroupFound = false;
    targetChannelFound = false;
    lastError = "Could not verify configured WhatsApp sources";
    console.error(lastError, error.message);
  }
});

client.on("disconnected", (reason) => {
  ready = false;
  targetGroupFound = null;
  targetChannelFound = null;
  qrDataUrl = null;
  lastError = "WhatsApp disconnected";
  console.error(lastError, reason);
  if (reason === "LOGOUT") {
    state = "reconnecting";
    lastError = "WhatsApp logged out; waiting for a new pairing QR";
    return;
  }
  state = "disconnected";
  scheduleReconnect();
});

function scheduleReconnect() {
  if (!startedByUser || reconnectTimer) return;
  state = "reconnecting";
  const delay = Math.min(30000 * (2 ** reconnectAttempt), 5 * 60 * 1000);
  reconnectAttempt += 1;
  reconnectTimer = setTimeout(async () => {
    reconnectTimer = null;
    try {
      await client.destroy();
      await initializeWhatsAppClient();
    } catch (error) {
      lastError = "WhatsApp reconnection failed";
      console.error(lastError, error.message);
      scheduleReconnect();
    }
  }, delay);
  reconnectTimer.unref();
}

client.on("message", async (message) => {
  try {
    if (message.fromMe || message.isStatus) return;
    const chat = await message.getChat();
    if (isTargetChannel(chat)) {
      targetChannelFound = true;
      if (lastError?.startsWith("Configured WhatsApp channel")) lastError = null;
      await queueChannelPost(message, chat, true);
      return;
    }
    if (!isTargetGroup(chat)) return;
    targetGroupFound = true;
    if (lastError?.startsWith("Configured WhatsApp group")) lastError = null;
    const body = String(message.body || "");
    const urls = [...new Set((body.match(urlPattern) || [])
      .map((url) => url.replace(/[.,;:!?)}\]]+$/, "")))].slice(0, 10);
    const completionCommand = /^(applied|done)[.!]?$/i.test(body.trim());
    let quotedMessage = null;
    if (completionCommand && message.hasQuotedMsg) {
      const quoted = await message.getQuotedMessage();
      quotedMessage = String(quoted.body || "").slice(0, 10000);
    }
    if (!urls.length && (!completionCommand || !quotedMessage)) return;
    const messageId = message.id._serialized;
    if (pendingMessages.some((item) => item.message_id === messageId)) return;
    if (pendingMessages.length >= 10000) {
      throw new Error("The local WhatsApp intake queue is full");
    }
    pendingMessages.push({
      chat_id: chat.id._serialized,
      message_id: messageId,
      chat_name: chat.name,
      sender: message.author || message.from,
      message: body.slice(0, 10000),
      urls,
      quoted_message: quotedMessage,
    });
    await persistPendingMessages();
    const linkCount = urls.length;
    try {
      await message.reply(
        `Got ${linkCount === 1 ? "the link" : `${linkCount} links`}. ` +
        "I'm checking the page and extracting the opportunity details now."
      );
    } catch (error) {
      console.error("Could not send the WhatsApp link acknowledgement:", error.message);
    }
    await forwardPendingMessages();
  } catch (error) {
    lastError = "Could not forward a WhatsApp message to the backend";
    console.error(lastError, error.message);
  }
});

async function persistPendingMessages() {
  persistence = persistence.catch((error) => {
    console.error("Could not save the previous WhatsApp intake queue state:", error.message);
  }).then(async () => {
    const temporary = `${pendingFile}.tmp`;
    await fs.writeFile(temporary, JSON.stringify(pendingMessages), { mode: 0o600 });
    await fs.rename(temporary, pendingFile);
  });
  return persistence;
}

async function loadPendingMessages() {
  try {
    pendingMessages = JSON.parse(await fs.readFile(pendingFile, "utf8"));
    if (!Array.isArray(pendingMessages)) throw new TypeError("Queue data must be an array");
  } catch (error) {
    if (error.code === "ENOENT") return;
    if (error instanceof SyntaxError || error instanceof TypeError) {
      const corruptFile = `${pendingFile}.${Date.now()}.corrupt`;
      await fs.rename(pendingFile, corruptFile);
      console.error("WhatsApp intake queue was invalid; preserved it at", corruptFile);
      pendingMessages = [];
      return;
    }
    throw error;
  }
}

async function forwardPendingMessages() {
  if (!ready || forwarding || !internalToken || !pendingMessages.length) return;
  forwarding = true;
  try {
    while (ready && pendingMessages.length) {
      const pending = pendingMessages[0];
      const result = await axios.post(
        `${apiBaseUrl}/api/internal/whatsapp/messages`,
        pending,
        {
          headers: { "X-Internal-Token": internalToken },
          timeout: 10 * 60 * 1000,
        }
      );
      const replies = [
        ...(typeof result.data.completion?.reply === "string"
          ? [result.data.completion.reply]
          : []),
        ...(Array.isArray(result.data.results)
        ? result.data.results
          .map((item) => item.reply)
          .filter((reply) => typeof reply === "string" && reply.trim())
          : []),
      ];
      if (pending.chat_id && replies.length) {
        const chat = await client.getChatById(pending.chat_id);
        if (!isTargetGroup(chat)) {
          throw new Error("Queued reply does not belong to the configured group");
        }
        const text = replies.join("\n\n").slice(0, 10000);
        await chat.sendMessage(
          text,
          pending.message_id ? { quotedMessageId: pending.message_id } : {}
        );
      }
      pendingMessages.shift();
      await persistPendingMessages();
    }
    lastError = null;
  } catch (error) {
    lastError = "Could not forward a WhatsApp message to the backend";
    console.error(lastError, error.message);
  } finally {
    forwarding = false;
  }
}

app.get("/health", (_request, response) => {
  const healthy = Boolean(internalToken);
  response.status(healthy ? 200 : 503).json({
    status: healthy ? "ok" : "not_ready",
    whatsapp: state,
    error: lastError || (internalToken ? null : "Backend authentication is not configured"),
    pending_messages: pendingMessages.length,
  });
});

app.get("/status", (request, response) => {
  if (!isAuthorized(request.get("X-Internal-Token"))) {
    return response.status(401).json({ error: "Unauthorized" });
  }
  return response.json({
    state,
    connected: ready,
    error: lastError,
    target_group: targetGroupName,
    target_group_found: targetGroupFound,
    target_channel: process.env.WHATSAPP_CHANNEL_NAME || "IT Opportunities Zim",
    target_channel_found: targetChannelFound,
  });
});

app.get("/qr", (request, response) => {
  if (!isAuthorized(request.get("X-Internal-Token"))) {
    return response.status(401).json({ error: "Unauthorized" });
  }
  if (!qrDataUrl) return response.status(404).json({ error: "Pairing QR is not available" });
  return response.json({ qr: qrDataUrl });
});

app.post("/start", (request, response) => {
  if (!isAuthorized(request.get("X-Internal-Token"))) {
    return response.status(401).json({ error: "Unauthorized" });
  }
  if (ready || state === "qr" || state === "connecting" || state === "starting") {
    return response.json({ state, connected: ready });
  }
  if (!queueReady) return response.status(503).json({ error: "WhatsApp service is still starting" });
  startedByUser = true;
  state = "starting";
  lastError = null;
  initializeWhatsAppClient()
    .then(() => {
      if (state === "starting") state = "connecting";
    })
    .catch((error) => {
      ready = false;
      state = "error";
      lastError = "WhatsApp client initialization failed";
      console.error(lastError, error.message);
      scheduleReconnect();
    });
  return response.json({ state });
});

function channelPostUrl(channel, message) {
  const channelCode = String(channel.id.user || channel.id._serialized).replace(/@.*$/, "");
  return `https://whatsapp.com/channel/${encodeURIComponent(channelCode)}?post=${encodeURIComponent(message.id._serialized)}`;
}

function queueChannelPost(message, channel, notifyGroup) {
  const task = channelProcessing.then(
    () => forwardChannelPost(message, channel, notifyGroup),
    () => forwardChannelPost(message, channel, notifyGroup)
  );
  channelProcessing = task.catch(() => {});
  return task;
}

async function channelMedia(message) {
  if (!message.hasMedia) return [];
  const media = await message.downloadMedia();
  if (!media || !media.data) throw new Error("The channel attachment could not be downloaded");
  const allowedTypes = new Set([
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
  ]);
  if (!allowedTypes.has(media.mimetype)) {
    throw new Error("The channel attachment is not a supported image or PDF");
  }
  if (Buffer.byteLength(media.data, "base64") > 2 * 1024 * 1024) {
    throw new Error("The channel attachment is larger than 2 MiB");
  }
  return [{
    mime_type: media.mimetype,
    data: media.data,
    filename: media.filename || null,
  }];
}

async function forwardChannelPost(message, channel, notifyGroup) {
  if (!ready || !internalToken) throw new Error("WhatsApp channel intake is not ready");
  const media = await channelMedia(message);
  const body = String(message.body || "");
  const urls = [...new Set((body.match(urlPattern) || [])
    .map((url) => url.replace(/[.,;:!?)}\]]+$/, "")))].slice(0, 10);
  const result = await axios.post(
    `${apiBaseUrl}/api/internal/whatsapp/channel-posts`,
    {
      channel_name: channel.name,
      channel_id: channel.id._serialized,
      message_id: message.id._serialized,
      post_url: channelPostUrl(channel, message),
      message: body.slice(0, 10000),
      urls,
      media,
      notify_group: notifyGroup,
    },
    {
      headers: { "X-Internal-Token": internalToken },
      timeout: 120000,
    }
  );
  return {
    message_id: message.id._serialized,
    ...result.data,
  };
}

app.post("/channels/test-last-10", async (request, response) => {
  if (!isAuthorized(request.get("X-Internal-Token"))) {
    return response.status(401).json({ error: "Unauthorized" });
  }
  if (!ready) return response.status(503).json({ error: "WhatsApp is not connected" });
  try {
    const channels = await client.getChannels();
    const channel = channels.find(isTargetChannel);
    if (!channel) {
      targetChannelFound = false;
      return response.status(404).json({
        error: `Configured WhatsApp channel "${process.env.WHATSAPP_CHANNEL_NAME || "IT Opportunities Zim"}" was not found`,
      });
    }
    targetChannelFound = true;
    if (lastError?.startsWith("Configured WhatsApp channel")) lastError = null;
    const messages = await channel.fetchMessages({ limit: 10 });
    const results = [];
    for (const message of messages) {
      try {
        results.push(await queueChannelPost(message, channel, false));
      } catch (error) {
        console.error("Could not process a recent IT Opportunities Zim post:", error.message);
        results.push({
          message_id: message.id._serialized,
          created: false,
          error: "The post could not be processed",
        });
      }
    }
    return response.json({
      channel: channel.name,
      scanned: messages.length,
      processed: results.filter((item) => !item.error).length,
      items: results,
    });
  } catch (error) {
    console.error("Could not scan recent IT Opportunities Zim posts:", error.message);
    return response.status(502).json({ error: "Could not scan recent channel posts" });
  }
});

app.post("/send", async (request, response) => {
  if (!isAuthorized(request.get("X-Internal-Token"))) {
    return response.status(401).json({ error: "Unauthorized" });
  }
  if (!ready) return response.status(503).json({ error: "WhatsApp is not connected" });
  const text = typeof request.body.text === "string" ? request.body.text.trim() : "";
  if (!text || text.length > 10000) {
    return response.status(400).json({ error: "Message text is required (max 10,000 characters)" });
  }
  const broadcast = request.body.broadcast === true;
  const recipients = Array.isArray(request.body.recipients) ? request.body.recipients : [];
  if ((!broadcast && recipients.length === 0) || (broadcast && recipients.length > 0)) {
    return response.status(400).json({ error: "Choose explicit recipients or an explicit group broadcast" });
  }

  try {
    const chats = await client.getChats();
    const chat = chats.find(isTargetGroup);
    if (!chat) return response.status(503).json({ error: "Configured WhatsApp group was not found" });

    const mentions = [];
    const mentionText = [];
    for (const rawPhone of recipients) {
      const phone = String(rawPhone).replace(/\D/g, "");
      if (!phone) continue;
      const participant = chat.participants.find((item) => item.id.user === phone);
      if (!participant) {
        console.warn("Configured mention recipient is not a member of the target group.");
        continue;
      }
      mentions.push(await client.getContactById(participant.id._serialized));
      mentionText.push(`@${phone}`);
    }

    if (!broadcast && mentions.length === 0) {
      return response.status(422).json({ error: "No configured recipients are members of the target group" });
    }
    const outgoing = mentionText.length ? `${mentionText.join(" ")}\n${text}` : text;
    await chat.sendMessage(outgoing, mentions.length ? { mentions } : {});
    return response.json({ sent: true });
  } catch (error) {
    lastError = "WhatsApp message delivery failed";
    console.error(lastError, error.message);
    return response.status(502).json({ error: lastError });
  }
});

const server = app.listen(port, process.env.WHATSAPP_HOST || "0.0.0.0", () => {
  console.log(`WhatsApp service listening on port ${port}`);
});
setInterval(() => {
  forwardPendingMessages().catch((error) => {
    lastError = "Could not forward queued WhatsApp messages";
    console.error(lastError, error.message);
  });
}, 5000).unref();

async function shutdown() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  server.close();
  if (startedByUser) {
    try {
      await client.destroy();
    } catch (error) {
      console.error("WhatsApp shutdown encountered an error:", error.message);
      process.exitCode = 1;
    }
  }
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

loadPendingMessages().catch((error) => {
  state = "error";
  lastError = "WhatsApp local intake queue could not be loaded";
  console.error(lastError, error.message);
}).then(() => {
  queueReady = true;
});
