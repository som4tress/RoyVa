#!/usr/bin/env node
import {processingDetails} from '../lib/processing-trace.mjs';
import {renderTimeline} from './timeline.mjs';
import {runNativeText,openCodeAPI} from './native-runner.mjs';
import {completionProblem} from '../lib/completion-check.mjs';
import {discardSession,isDiscarded} from '../lib/discard-session.mjs';
import {markDiscarded} from '/home/somdutta/Projects/agent-learning/src/discard.mjs';
import {readLiveTokens,formatLiveTokens} from './live-tokens.mjs';
import {parseFeedback,emojiVote,completedTarget,mapTelegram,telegramTarget,recordFeedback,status as feedbackStatus,receipt,HELP as FEEDBACK_HELP} from '/home/somdutta/Projects/agent-learning/src/feedback.mjs';
import {controlKind,correctionText} from './steering.mjs';
import {pollBackoffMs} from '../lib/telegram-poll-backoff.mjs';
import {formatExecutionError} from '../lib/execution-errors.mjs';
import {resolvedTargets} from '../lib/ha-focus.mjs';
import {completeTask} from '../lib/task-learning.mjs';
import {inferHAIntent} from '../lib/ha-intent.mjs';
import {phraseKindForTool} from '../plugins/ha-mcp-routing/phrases.js';
import {quotaInfo,recordFreeQuota,isFreeCoolingDown,freeQuotaState,cloudModelID} from '../lib/free-quota.mjs';
/**
 * Telegram <-> OpenCode bridge
 *
 * Long-polls Telegram, forwards each message from an allowlisted user into an
 * OpenCode session (model pinned to OPENCODE_TG_MODEL), and sends the reply
 * back. Tools/MCP servers configured in OpenCode (including Home Assistant)
 * are available to the agent, so the phone becomes a remote control for HA.
 */
import {planHA,rememberHA,prepareHA} from "./ha-context.mjs";
import {attachment,MAX_BYTES} from "./media.mjs";
import { spawn } from "node:child_process";
import {
  readFileSync,
  writeFileSync,
  appendFileSync,
  mkdirSync,
  existsSync,
  createWriteStream,
  rmSync,
} from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import { pathToFileURL } from "node:url";
// whisper.cpp lives in ~/.config/opencode/lib/whisper.mjs so the WhatsApp bridge shares it.
import {
  createTranscriber,
  WHISPER_BIN,
  WHISPER_MODEL,
  WHISPER_LANG,
  WHISPER_TMP,
  WHISPER_REMOTE,
} from "../lib/whisper.mjs";

const CONFIG_DIR = join(homedir(), ".config/opencode/telegram");
const ENV_FILE = join(CONFIG_DIR, "bot.env");
const STATE_FILE = process.env.OPENCODE_TG_STATE_FILE || join(CONFIG_DIR, "state.json");
const LOG_FILE = join(homedir(), ".local/state/opencode/telegram-bridge.log");

function getModel() {
  if(process.env.OPENCODE_TG_MODEL)return process.env.OPENCODE_TG_MODEL;
  try{return JSON.parse(readFileSync(join(homedir(),'.config/opencode/opencode.json'),'utf8')).model||'opencode/glm-5.3-flash-free'}catch{return 'opencode/glm-5.3-flash-free'}
}
// Terse agent (2 sentences, no tables) — see ~/.config/opencode/agents/telegram.md
const AGENT = process.env.OPENCODE_TG_AGENT ?? "telegram";
const WORKDIR = process.env.OPENCODE_TG_DIR || homedir();
const OPENCODE_BIN = process.env.OPENCODE_TG_BIN || "opencode";
const RUN_TIMEOUT_MS = Number(process.env.OPENCODE_TG_TIMEOUT || 15 * 60 * 1000);
const CHUNK = 3900;

// --- Voice notes -> text (whisper.cpp, shared with the WhatsApp bridge) -----
const TMP_DIR = WHISPER_TMP;

mkdirSync(CONFIG_DIR, { recursive: true });
mkdirSync(dirname(LOG_FILE), { recursive: true });
mkdirSync(TMP_DIR, { recursive: true });

function loadEnvFile(path) {
  if (!existsSync(path)) return {};
  const out = {};
  for (const raw of readFileSync(path, "utf8").split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    out[line.slice(0, eq).trim()] = line.slice(eq + 1).trim().replace(/^["']|["']$/g, "");
  }
  return out;
}

const fileEnv = loadEnvFile(ENV_FILE);
const TOKEN = process.env.TELEGRAM_BOT_TOKEN || fileEnv.TELEGRAM_BOT_TOKEN;
const allowed = (process.env.TELEGRAM_ALLOWED_USER_IDS || fileEnv.TELEGRAM_ALLOWED_USER_IDS || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

/** Persist a newly claimed owner id back into bot.env so it survives restarts. */
function claimOwner(userId) {
  const ids = [...allowed, String(userId)];
  allowed.push(String(userId));
  try {
    const body = readFileSync(ENV_FILE, "utf8");
    const next = body.includes("TELEGRAM_ALLOWED_USER_IDS=")
      ? body.replace(/TELEGRAM_ALLOWED_USER_IDS=.*/, `TELEGRAM_ALLOWED_USER_IDS=${ids.join(",")}`)
      : `${body.replace(/\n*$/, "\n")}TELEGRAM_ALLOWED_USER_IDS=${ids.join(",")}\n`;
    writeFileSync(ENV_FILE, next, { mode: 0o600 });
    log(`claimed owner ${userId}; allowlist now [${ids.join(",")}]`);
  } catch (e) {
    log("could not persist allowlist:", e.message);
  }
}

if (!TOKEN) {
  console.error(`No bot token. Put TELEGRAM_BOT_TOKEN=... in ${ENV_FILE}`);
  process.exit(1);
}

function log(...args) {
  const line = `[${new Date().toISOString()}] ${args.map(String).join(" ")}\n`;
  appendFileSync(LOG_FILE, line);
  process.stdout.write(line);
}

function loadState() {
  try {
    return JSON.parse(readFileSync(STATE_FILE, "utf8"));
  } catch {
    return { offset: 0, sessions: {} };
  }
}
function saveState(s) {
  try {
    writeFileSync(STATE_FILE, JSON.stringify(s, null, 2));
  } catch (e) {
    log("state save failed:", e.message);
  }
}
const state = loadState();
state.sessions ||= {};

const API = `https://api.telegram.org/bot${TOKEN}`;

async function tg(method, payload, timeoutMs = 70_000) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const res = await fetch(`${API}/${method}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload ?? {}),
      signal: ac.signal,
    });
    const json = await res.json();
    if (!json.ok) log(`telegram ${method} error:`, JSON.stringify(json));
    return json;
  } catch (e) {
    log(`telegram ${method} fetch failed:`, e.message);
    return { ok: false };
  } finally {
    clearTimeout(timer);
  }
}

const send = (chatId, text) => tg("sendMessage", { chat_id: chatId, text, disable_web_page_preview: true });

function splitMessage(text) {
  const parts = [];
  let rest = text;
  while (rest.length > CHUNK) {
    let cut = rest.lastIndexOf("\n", CHUNK);
    if (cut < CHUNK * 0.5) cut = rest.lastIndexOf(" ", CHUNK);
    if (cut < CHUNK * 0.5) cut = CHUNK;
    parts.push(rest.slice(0, cut));
    rest = rest.slice(cut).replace(/^\n/, "");
  }
  if (rest.trim()) parts.push(rest);
  return parts;
}

async function sendLong(chatId, text) {
  const delivered=[];
  for (const part of splitMessage(text)) {
    const r=await send(chatId,part);
    if(!r.ok)throw new Error('Telegram delivery failed: '+String(r.error_code||'unknown'));
    delivered.push(r.result.message_id);
  }
  return delivered;
}

// --- transcription helpers -------------------------------------------------

/** Download a Telegram file (voice note, audio) into TMP_DIR. */
async function downloadTelegramFile(fileId, dest) {
  const info = await tg("getFile", { file_id: fileId }, 30_000);
  const remote = info?.result?.file_path;
  if (!remote) {
    log("getFile failed for", fileId, JSON.stringify(info));
    return null;
  }
  if ((info.result.file_size||0)>MAX_BYTES) throw new Error("Telegram file exceeds 20 MB download limit");
  const res = await fetch(`https://api.telegram.org/file/bot${TOKEN}/${remote}`, {signal:AbortSignal.timeout(60000)});
  if (!res.ok || !res.body) {
    log(`file download failed: HTTP ${res.status}`);
    return null;
  }
  let downloaded=0;
  const limit=new Transform({transform(chunk,_encoding,callback){downloaded+=chunk.length;callback(downloaded>MAX_BYTES?new Error("File exceeds 20 MB download limit"):null,chunk);}});
  await pipeline(Readable.fromWeb(res.body),limit,createWriteStream(dest,{mode:0o600}));
  return dest;
}

const transcribeAudio = createTranscriber({ log });

function newSessionId(chatId) {
  const stamp = Date.now().toString(36);
  return `ses_tg_${String(chatId).replace("-", "g")}_${stamp}`;
}

function sessionFor(chatId) {
  const key = String(chatId);
  if (!state.sessions[key]) {
    state.sessions[key] = newSessionId(chatId);
    saveState(state);
  }
  return state.sessions[key];
}

async function tokenFooter(sessionId,messageIds){
 if(!messageIds?.length)return '';
 return new Promise(done=>{
  const usage=spawn('/usr/bin/python3',[homedir()+'/.config/opencode/scripts/openrouter-usage','--all-providers','--session',sessionId,'--message-ids',[...new Set(messageIds)].join(','),'--until-ms',String(Date.now())],{stdio:['ignore','pipe','ignore'],env:process.env});
  let out='';const limit=setTimeout(()=>{usage.kill('SIGKILL');done('')},5000);
  usage.stdout.on('data',data=>out+=data.toString());usage.on('error',()=>{clearTimeout(limit);done('')});usage.on('close',status=>{clearTimeout(limit);done(status===0?out.trim():'')});
 });
}
function stripUsageFooter(text){
 return String(text||'').replace(/\n(?:Usage(?: \(local\))?:|Tokens \((?:local|cloud)\):)[^\n]*(?:\n(?:Tokens \([^\n]+|Token usage unavailable[^\n]*|Cost:[^\n]*))*\s*$/,'').trim();
}

/** Run one prompt through OpenCode and return the assistant's text. */
function runOpenCode(sessionId, prompt, options = {}) {
 if(!options.files?.length)return runNativeText(sessionId,prompt,{...options,model:options.model||getModel(),agent:options.agent||AGENT,directory:WORKDIR,timeout:options.timeout||RUN_TIMEOUT_MS,collectReferences:tools=>tools.filter(p=>p.state?.status==='completed'&&phraseKindForTool(p.name||'',p.state)).slice(-6).map(p=>({tool:p.name,input:JSON.stringify(p.state.input||{}).slice(0,300),targets:resolvedTargets(p.name,p.state)}))}).then(reply=>{
  if(reply.ok&&completionProblem({messages:[{role:'user',content:prompt}]},reply.text))return {...reply,ok:false,text:'OpenCode returned an incomplete answer. Completion was not confirmed.'};
  if(reply.ok)completeTask(sessionId,true);else if(!reply.stopped)reply.text=formatExecutionError(reply.text,{toolActivity:reply.toolActivity});return reply;
 });
  return new Promise((resolve) => {
    const requestedModel=options.model||getModel();
    const selectedModel=requestedModel.startsWith('opencode/')&&isFreeCoolingDown()?cloudModelID():requestedModel;
    let freeLimitError=null,toolActivity=false;
    const args = ["run", "--server", "http://127.0.0.1:49374", "--format", "json", "-m", selectedModel, "-s", sessionId];
    if (options.agent || AGENT) args.push("--agent", options.agent || AGENT);
    for (const file of options.files || []) args.push("--file",file);
    // A leading dash would be parsed as a flag by the CLI.
    args.push(prompt.startsWith("-") ? ` ${prompt}` : prompt);

    const child = spawn(OPENCODE_BIN, args, {
      cwd: WORKDIR,
      env: { ...process.env, NO_COLOR: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    });

    let buf = "";
    let stderr = "";
    const texts = [];
    const usageIds=new Set();
    let errorText = "";
    let lastAssistant = null;
    const references=[];
    const lastByMessage = new Map();

    let aborted=false, steps=0;
    const abort = async reason => {
      if(aborted)return; aborted=true; log("interrupt",sessionId,reason);
      errorText=reason;
      try{await sessionControl(sessionId,'interrupt')}catch(e){log('interrupt failed',sessionId,e.message)}
      child.kill('SIGKILL');
    };
    options.onControl?.(abort);
    const killTimer=setTimeout(()=>void abort("Processing time budget exceeded"),options.timeout || RUN_TIMEOUT_MS);

    child.stdout.on("data", (d) => {
      options.onStarted?.();
      buf += d.toString();
      let nl;
      while ((nl = buf.indexOf("\n")) !== -1) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (!line.startsWith("{")) continue;
        let ev;
        try {
          ev = JSON.parse(line);
        } catch {
          continue;
        }
        if(ev.type === "step_start")options.onStarted?.();
        if(ev.type === "step_start" && options.maxSteps && ++steps>options.maxSteps) void abort("Model step budget exceeded");
        const part = ev.part;
        if(ev.type?.startsWith('tool')||part?.type==='tool'){toolActivity=true;if(part?.tool)options.onActivity?.({tool:part.tool,status:part.state?.status||'running',at:Date.now()});}
        if(part?.messageID)usageIds.add(part.messageID);
        if(ev.type==='tool_use'&&part?.state?.status==='completed'&&phraseKindForTool(part.tool||'',part.state)){
          references.push({tool:part.tool,input:JSON.stringify(part.state.input||{}).slice(0,300),targets:resolvedTargets(part.tool,part.state)});
          if(references.length>6)references.shift();
        }
        if (ev.type === "text" && part?.type === "text" && part.text) {
          const prev = lastByMessage.get(part.messageID) || "";
          lastByMessage.set(part.messageID, prev + part.text);
          lastAssistant = part.messageID;
        } else if (ev.type === "error") {
          if(selectedModel.startsWith('opencode/')&&quotaInfo(ev.error)){freeLimitError=ev.error;recordFreeQuota(ev.error);}
          errorText = ev.error?.data?.message || ev.error?.name || JSON.stringify(ev.error ?? ev);
        }
      }
    });
    child.stderr.on("data", (d) => (stderr += d.toString()));

    child.on("error", (e) => {
      clearTimeout(killTimer);
      resolve({ ok: false, text: `bridge could not start opencode: ${e.message}` });
    });

    child.on("close", async (code) => {
      clearTimeout(killTimer);
      const text = lastAssistant ? lastByMessage.get(lastAssistant).trim() : "";
      if (text && !aborted && !errorText) {
        if(!options.files?.length)completeTask(sessionId,true);
        return resolve({ok:true,text,references,assistantId:lastAssistant,usageIds:[...usageIds]});
      }
      if(freeLimitError&&!options._freeFallback&&!aborted){
        if(!toolActivity)return resolve(await runOpenCode(sessionId,prompt,{...options,model:cloudModelID(),_freeFallback:true}));
        return resolve({ok:false,text:'The free model reached its limit after starting this task. I have not replayed its tool calls. Ask me to continue with the configured cloud model.'});
      }
      if (aborted && options.isStopped?.()) return resolve({ok:false,stopped:true,text:"Stopped."});
      if (errorText) return resolve({ ok: false, text: formatExecutionError(errorText,{toolActivity}),usageIds:[...usageIds] });
      const tail = stderr.trim().split("\n").slice(-6).join("\n");
      resolve({
        ok: false,
        text: `OpenCode produced no reply (exit ${code}).\n${tail || "no output"}`,
      });
    });
  });
}

const activeRuns=new Map(), queueEpoch=new Map();
async function sessionControl(sessionId,operation,data,method="post"){
 return JSON.stringify({data:await openCodeAPI(`/api/session/${encodeURIComponent(sessionId)}/${operation}`,method,method.toUpperCase()==='GET'?undefined:data||{})});
}
let chain = Promise.resolve();
function enqueue(job) {
  chain = chain.then(job).catch((e) => log("job failed:", e?.stack || e));
  return chain;
}

function workingHourglass(chatId,messageId,active){
  let frame=0,pending=Promise.resolve(),busy=false,nextEditAt=0;
  const text=finished=>{const details=processingDetails(active.sessionId,active.startedAt);return renderTimeline({startedAt:active.startedAt,...details,activity:active.activity,frame:frame++,finished,tokenStats:finished&&active.finalTokenStats||formatLiveTokens(readLiveTokens(active.sessionId,active.startedAt),details)});};
  const edit=async finished=>{
    const rendered=text(finished);
    const result=await tg('editMessageText',{chat_id:chatId,message_id:messageId,text:rendered},10000);
    active.onProgress?.({text:rendered,finished:!!finished,delivered:result.ok===true});
    if(result.parameters?.retry_after)nextEditAt=Date.now()+result.parameters.retry_after*1000;
    return result;
  };
  const timer=setInterval(()=>{
    if(busy||Date.now()<nextEditAt)return;busy=true;
    pending=edit().finally(()=>{busy=false});
  },2000);timer.unref?.();
  return async label=>{
    clearInterval(timer);await pending;
    const finish=async()=>{const result=await edit(label);if(result.parameters?.retry_after){const retry=setTimeout(()=>void edit(label),result.parameters.retry_after*1000);retry.unref?.();}};
    if(Date.now()<nextEditAt){const delayed=setTimeout(()=>void finish(),nextEditAt-Date.now());delayed.unref?.();}
    else await finish();
  };
}

function typingLoop(chatId) {
  const tick = () => tg("sendChatAction", { chat_id: chatId, action: "typing" }, 10_000);
  tick();
  const id = setInterval(tick, 4500);
  return () => clearInterval(id);
}

const HELP = [
  "Connected to OpenCode.",
  "",
  `/new — start a fresh session (forget context)`,
  `/id — show your Telegram user and chat id`,
  `/status — model, working dir, session`,
  `/help — this list`,
  `/feedback accept | reject <reason> | status`,
  `👍 confirms the answer and authorizes a reusable tool candidate; validation is still required.`,
  `/steer correction — redirect the active task (or reply to its Working message)`,
  `/stop — interrupt the active task and clear queued requests`,
  "",
  "Photos and videos: local Qwen first, the configured cloud model fallback after 60 seconds or 3 model steps. Video uses up to 8 sampled frames, without audio. Limit 20 MB / 10 minutes.",
  "Anything else is sent to the agent. Home Assistant tools are available.",
  "",
  "🎤 Send a voice note instead of typing — it is transcribed locally with Whisper.",
].join("\n");

async function handleMessage(msg,diagnostic={}) {
  const chatId = msg.chat.id;
  const userId = msg.from?.id;
  let text = (msg.text ?? msg.caption ?? "").trim();
  const media = attachment(msg);

  // Voice note / audio file / round video note -> whisper.
  const clip =
    msg.voice ||
    msg.audio ||
    msg.video_note ||
    (msg.document && /^audio\//.test(msg.document.mime_type ?? "") ? msg.document : null);

  log(
    `msg chat=${chatId} (${msg.chat?.type}) user=${userId} ${
      clip ? `voice dur=${clip.duration ?? "?"}s size=${clip.file_size ?? "?"}B` : `text="${text.slice(0, 40)}"`
    }`,
  );
  if (!text && !clip && !media) {
    // Never stay silent: photos/stickers would otherwise vanish into nothing.
    if (msg.chat?.type === "private") {
      await send(
        chatId,
        "Send text, a voice note, a photo, or a video clip (up to 20 MB).",
      );
    }
    return;
  }

  // Onboarding: the very first private-chat sender becomes the owner.
  if (!allowed.length && msg.chat?.type === "private") {
    claimOwner(userId);
    await send(chatId, `Registered you as the owner (user id ${userId}). Anything you send now goes to OpenCode.`);
  }

  // Onboarding aid: reveal ids to the sender so the owner can build the allowlist.
  if (text === "/id" || text === "/start") {
    await sendLong(
      chatId,
      `user id: ${userId}\nchat id: ${chatId}` +
        (allowed.length ? `\nallowlisted: ${allowed.includes(String(userId)) ? "yes" : "no"}` : "\nallowlist: empty (owner not configured yet)"),
    );
    return;
  }

  // Family group is self-registering: any member who speaks gets allowlisted.
  const FAMILY_GROUP = process.env.OPENCODE_TG_GROUP || "-4680123561";
  if (String(chatId) === FAMILY_GROUP && !allowed.includes(String(userId))) {
    claimOwner(userId);
    await send(chatId, `✅ Allowlisted ${msg.from?.first_name || "family member"} (user id ${userId}). You can now control the house.`);
  }

  if (!allowed.includes(String(userId))) {
    log(`rejected message from user ${userId} (@${msg.from?.username ?? "?"}) chat ${chatId}`);
    await send(chatId, `Not authorized. Your user id is ${userId}. Ask the owner to allowlist it.`);
    return;
  }

  // Voice note -> transcript -> normal prompt path.
  if (clip && !text) {
    const tag = `tg${String(chatId).replace("-", "g")}-${Date.now().toString(36)}`;
    const src = join(TMP_DIR, `${tag}${msg.video_note ? ".mp4" : ".oga"}`);
    const stopTranscribeTyping = typingLoop(chatId);
    let clipResult;
    try {
      const got = await downloadTelegramFile(clip.file_id, src);
      if (!got) {
        await send(chatId, "Could not download that voice note from Telegram. Please try again.");
        return;
      }
      clipResult = await transcribeAudio(src, tag);
    } finally {
      stopTranscribeTyping();
      try {
        rmSync(src, { force: true });
      } catch {}
    }
    if (!clipResult.ok) {
      log("transcribe failed:", clipResult.error);
      await send(chatId, `Couldn't transcribe that: ${clipResult.error}`);
      return;
    }
    text = clipResult.text;
    if (!text) {
      await send(chatId, "I couldn't make out any words in that voice note. Try again a bit closer to the mic.");
      return;
    }
    await sendLong(chatId, `🎤 “${text}”`);
  }

  const feedback=parseFeedback(text);
  if(feedback)return handleFeedback(chatId,userId,feedback,msg.reply_to_message?.message_id,'telegram-command',String(msg.message_id));
  if (text === "/help") return sendLong(chatId, HELP);
  if (text === "/new") {
    const id = newSessionId(chatId);
    state.sessions[String(chatId)] = id;
    delete state.haContext?.[String(chatId)];
    saveState(state);
    return send(chatId, "New session started. Previous context is gone.");
  }
  if (text === "/status") {
    return sendLong(
      chatId,
      [
        `default model: ${getModel()}`,
        ...(isFreeCoolingDown()?[`free quota: unavailable until ${new Date(freeQuotaState().until).toLocaleString('en-US',{timeZone:'America/Los_Angeles'})} PT; general fallback: the configured cloud model`]:[]),
        `media: Qwen first; the configured cloud model after 60s / 3 steps; video up to 8 frames, no audio`,
        `HA: fresh request context; local budget 42s then the configured cloud model`,
        `dir: ${WORKDIR}`,
        `session: ${sessionFor(chatId)}`,
        `voice: whisper.cpp ${existsSync(WHISPER_BIN) ? "local" : WHISPER_REMOTE ? `remote (${WHISPER_REMOTE})` : "MISSING"} (${WHISPER_MODEL.split("/").pop()}, lang=${WHISPER_LANG})`,
        `service pid: ${process.pid}`,
      ].join("\n"),
    );
  }

  const key=String(chatId), current=activeRuns.get(key);
  const control=diagnostic.control || controlKind(msg,current);
  if(control==='stop'){
    queueEpoch.set(key,(queueEpoch.get(key)||0)+1);
    delete state.haContext?.[key];saveState(state);
    if(!current)return send(chatId,'No active task. Queued requests cleared.');
    current.stopped=true;
    try{if(current.sessionId)await sessionControl(current.sessionId,'interrupt');
      current.abort?.('Stopped by user');
      return send(chatId,'Stopped; queued requests cleared. An action already sent to a device may still finish.');
    }catch(e){current.abort?.('Stopped by user');return send(chatId,e.message);}
  }
  if(control==='steer'){
    if(msg.reply_to_message&&!/^\/steer(?:@\w+)?(?:\s|$)/i.test(text)&&controlKind(msg,current)!=='steer')return send(chatId,'That task has finished. Send your correction as a new request.');
    const correction=correctionText(text);
    if(!current||current.stopped)return send(chatId,'No active task to steer. Send your request normally.');
    if(!correction)return send(chatId,'Use /steer followed by your correction, or reply to the Working message.');
    if(media)return send(chatId,'Steering supports text and transcribed voice. Send attachments as a separate request.');
    try{if(!current.ready)current.pending.push(correction);
      else {current.lastCorrection=correction;await sessionControl(current.sessionId,'prompt',{text:correction,delivery:'steer'});}
      return send(chatId,'Correction sent to the active task.');
    }catch(e){return send(chatId,e.message);}
  }
  const active={startedAt:Date.now(),messageId:msg.message_id,sessionId:null,pending:[],stopped:false,onProgress:diagnostic.onProgress};
  activeRuns.set(key,active);
  const working=diagnostic.silent?null:await send(chatId,renderTimeline({startedAt:active.startedAt,tokenStats:'Tokens: awaiting provider usage'}));
  active.workingId=working?.result?.message_id;
  const finishIndicator=active.workingId?workingHourglass(chatId,active.workingId,active):null;
  try {
  state.haContext ||= {};
  const semanticKind=!media?await inferHAIntent(text):null;
  let haPlan=!media&&!['configuration','investigation'].includes(semanticKind)?planHA(text,state.haContext[String(chatId)]):null;
  if(!media&&!haPlan&&['devices','history'].includes(semanticKind))haPlan={kind:semanticKind,carry:null};
  const sessionId=haPlan?newSessionId(chatId)+'_ha':sessionFor(chatId);
  active.sessionId=sessionId;
  if(active.stopped)return {ok:false,stopped:true,text:'Stopped.',sessionId};
  if(diagnostic.onSession)await diagnostic.onSession(sessionId);
  log(`prompt chat=${chatId} user=${userId} session=${sessionId} chars=${text.length}`);
  const stopTyping = typingLoop(chatId);
  let reply;
  const controlOptions={onActivity:event=>{active.activity=event},onControl:abort=>{
    active.abort=abort;
    void (async()=>{for(let n=0;n<30&&!active.ready&&!active.stopped;n++){
      try{const messages=JSON.parse(await sessionControl(sessionId,'message',null,'get')).data||[];
        if(messages.some(m=>m.type==='user'&&m.time?.created>=active.startedAt)){controlOptions.onStarted();break;}
      }catch{}
      await new Promise(r=>setTimeout(r,200));
    }})();
    if(active.stopped){void abort('Stopped by user');return;}
  },onStarted:()=>{if(active.ready)return;active.ready=true;
    void (async()=>{for(const correction of active.pending.splice(0)){
      if(active.stopped)break;
      try{active.lastCorrection=correction;await sessionControl(sessionId,'prompt',{text:correction,delivery:'steer'})}catch(e){await send(chatId,e.message)}
    }})();
  },isStopped:()=>active.stopped};
  try {
    if(media){
      const dir=join(TMP_DIR,`media-${Date.now()}-${msg.message_id}`);
      mkdirSync(dir,{recursive:true,mode:0o700});
      try {
        if((media.file_size||0)>MAX_BYTES)throw new Error("Please send a photo/video smaller than 20 MB.");
        const source=join(dir,"input"+media.ext);
        if(!await downloadTelegramFile(media.file_id,source))throw new Error("Could not download this attachment.");
        const question=text || "Describe this media and anything relevant or unusual.";
        log("media shared router",sessionId,media.kind);
        reply=await runOpenCode(sessionId,question,{files:[source],timeout:270000,...controlOptions});
      }catch(error){reply={ok:false,text:error.message};}
      finally{rmSync(dir,{recursive:true,force:true});}
    }else {
      if(haPlan)await prepareHA(sessionId,haPlan);
      reply=await runOpenCode(sessionId,text,controlOptions);
      if(reply.ok&&(haPlan||reply.references?.length))state.haContext[String(chatId)]=rememberHA(text,{...reply,haKind:haPlan?.kind},Date.now(),state.haContext[String(chatId)]);
      else delete state.haContext[String(chatId)];
      saveState(state);
    }
  } catch(error) {
    reply={ok:false,text:error.message};
  } finally {
    stopTyping();
  }
  if(active.lastCorrection&&!active.stopped){
    delete state.haContext?.[key];saveState(state);
    // CLI run follows its own original turn. Native steering can finish in a later
    // turn; read that result rather than resubmitting/replaying the correction.
    const until=Date.now()+RUN_TIMEOUT_MS;let received=false;
    while(!active.stopped&&Date.now()<until){
      const snapshot=JSON.parse(await sessionControl(sessionId,'message',null,'get')).data||[];
      const user=snapshot.find(m=>m.type==='user'&&m.text===active.lastCorrection);
      const answer=user&&snapshot.find(m=>m.type==='assistant'&&m.time?.created>=user.time.created&&m.time?.completed);
      const idle=answer&&snapshot.find(m=>m.type==='idle'&&m.time?.created>=answer.time.completed);
      if(answer&&idle){reply={ok:true,assistantId:answer.id,text:(answer.content||[]).filter(p=>p.type==='text').map(p=>p.text).join(''),references:[],usageIds:snapshot.filter(m=>m.type==='assistant'&&m.time?.created>=active.startedAt&&m.time?.created<=idle.time.created).map(m=>m.id)};received=true;break;}
      await new Promise(r=>setTimeout(r,400));
    }
    if(!received&&!active.stopped)reply={ok:false,text:'The correction was submitted, but completion is unconfirmed. Use /status before retrying device actions.'};
  }
  if(active.stopped)return {...reply,stopped:true,delivered:[],sessionId};
  const footer=await tokenFooter(sessionId,reply.usageIds);
  active.finalTokenStats=footer;
  reply.text=stripUsageFooter(reply.text);
  log(`reply chat=${chatId} ok=${reply.ok} chars=${reply.text.length}`);
  const delivered=diagnostic.silent?[]:await sendLong(chatId, reply.text || "(empty reply)");
  if(reply.ok&&reply.assistantId&&delivered.length){
    try{
      const m=JSON.parse(await sessionControl(sessionId,'message/'+reply.assistantId,null,'get')).data;
      const target=completedTarget([m],sessionId,reply.assistantId);mapTelegram(chatId,delivered,target);
      await tg('editMessageReplyMarkup',{chat_id:chatId,message_id:delivered.at(-1),reply_markup:{inline_keyboard:[[{text:'👍 Accept & learn',callback_data:'feedback:accept'},{text:'👎 Incorrect',callback_data:'feedback:reject'}]]}});
    }catch(e){log('feedback mapping unavailable',e.name);}
  }
  active.completed=reply.ok;
  return {...reply,delivered,sessionId};
  } finally {if(activeRuns.get(key)===active)activeRuns.delete(key);await finishIndicator?.(active.stopped?'⏹ Stopped.':active.completed?'✓ Finished.':'Finished—see reply for status.');}
}

async function handleFeedback(chatId,userId,parsed,replyTo,source,eventID){
 if(!allowed.includes(String(userId)))return;
 if(parsed.action==='help')return sendLong(chatId,FEEDBACK_HELP);
 try{
  let target=telegramTarget(chatId,replyTo);
  if(parsed.messageID){
   // Explicit IDs must belong to this chat's mapped session; never search other users' sessions.
   if(!target)throw new Error('No answer mapped in this chat. Reply to an answer first.');
   const m=JSON.parse(await sessionControl(target.sessionID,'message/'+parsed.messageID,null,'get')).data;
   target=completedTarget([m],target.sessionID,parsed.messageID);
  }
  if(!target)throw new Error('No answer found. Reply to a completed Royva answer with /feedback accept or 👍.');
  if(parsed.action==='reject'){
    recordFeedback({target,action:'reject',actor:'telegram:'+userId,source,note:parsed.note,eventID});
    markDiscarded(target.sessionID);
    const key=String(chatId),active=activeRuns.get(key);queueEpoch.set(key,(queueEpoch.get(key)||0)+1);
    if(active?.sessionId===target.sessionID){active.stopped=true;await active.abort?.('Rejected session discarded');}
    delete state.sessions[key];delete state.haContext?.[key];saveState(state);
    await discardSession(target.sessionID);
    return send(chatId,receipt('reject',{discarded:true}));
  }
  const st=parsed.action==='status'?feedbackStatus(target):recordFeedback({target,action:parsed.action,actor:'telegram:'+userId,source,note:parsed.note,eventID});
  return send(chatId,receipt(parsed.action,st));
 }catch(e){return send(chatId,e.message);}
}
export async function handleTelegramFeedbackUpdate(update){
 const callback=update.callback_query;
 if(callback){
  if(!/^feedback:(accept|reject)$/.test(callback.data||''))return;
  const user=callback.from?.id,message=callback.message;
  if(!allowed.includes(String(user))||!message){await tg('answerCallbackQuery',{callback_query_id:callback.id,text:'Not authorized'});return;}
  await tg('answerCallbackQuery',{callback_query_id:callback.id});
  return handleFeedback(message.chat.id,user,{action:callback.data.split(':')[1],note:''},message.message_id,'telegram-button',callback.id);
 }
 const r=update.message_reaction;
 if(r?.user&&!r.user.is_bot&&allowed.includes(String(r.user.id))){
  const votes=r.new_reaction?.map(x=>emojiVote(x.emoji||'')).filter(Boolean)||[];
  const prior=r.old_reaction?.some(x=>emojiVote(x.emoji||''));
  const action=votes.includes('reject')?'reject':votes.includes('accept')?'accept':prior?'clear':null;
  if(action)return handleFeedback(r.chat.id,r.user.id,{action,note:''},r.message_id,'telegram-reaction',String(update.update_id));
 }
}

async function poll() {
  const res = await tg(
    "getUpdates",
    {
      offset: state.offset ? state.offset + 1 : undefined,
      timeout: 30,
      allowed_updates: ["message", "message_reaction", "callback_query"],
    },
    60_000,
  );
  if (!res.ok) throw Object.assign(new Error('Telegram polling failed'),{retryAfterMs:Number(res.parameters?.retry_after||0)*1000});
  if (res.result?.length) log(`received ${res.result.length} update(s) from Telegram`);
  for (const update of res.result ?? []) {
    state.offset = Math.max(state.offset, update.update_id);
    saveState(state);
    if(update.message_reaction||update.callback_query){void handleTelegramFeedbackUpdate(update).catch(e=>log('feedback update failed',e.name));continue;}
    const msg = update.message;
    if (!msg) continue;
    const key=String(msg.chat.id), kind=controlKind(msg,activeRuns.get(key));
    if(parseFeedback(msg.text||msg.caption||'')){void handleMessage(msg).catch(e=>log('feedback failed',e.name));continue;}
    if(kind){void handleMessage(msg,{control:kind}).catch(e=>log('control failed',e.message));continue;}
    const epoch=queueEpoch.get(key)||0;
    enqueue(() => epoch===(queueEpoch.get(key)||0)?handleMessage(msg):undefined);
  }
}

// Exported so the transcription path can be tested without starting the poller:
//   node -e 'import("./bridge.mjs").then(m => m.transcribeAudio("/tmp/x.oga","t").then(console.log))'
export { transcribeAudio, downloadTelegramFile, runOpenCode, handleMessage as runTelegramControlSelfTest };
// Local diagnostic entry point: same allowlisted message handler and Telegram delivery;
// no HTTP endpoint or change to Telegram authentication/polling.
export async function runTelegramSelfTest(chatId,prompt,label,{compact=false,onSession,onProgress}={}){
 if(!allowed.includes(String(chatId)))throw new Error('Diagnostic chat must already be allowlisted.');
 if(!process.env.OPENCODE_TG_STATE_FILE)throw new Error('Diagnostic requires an isolated state file.');
 state.sessions[String(chatId)]=newSessionId(chatId);delete state.haContext?.[String(chatId)];saveState(state);
 if(!compact)await sendLong(chatId,'[OpenCode cache test — '+label+']\n'+prompt);
 const started=Date.now();
 const reply=await handleMessage({message_id:Date.now(),date:Math.floor(Date.now()/1000),chat:{id:Number(chatId),type:'private'},from:{id:Number(chatId),is_bot:false},text:prompt},{silent:compact,onSession,onProgress});
 return {...reply,seconds:(Date.now()-started)/1000};
}
export {sendLong as sendTelegramTestReport};

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isMain) {
  log(`bridge starting; model=${getModel()} agent=${AGENT || "(default)"} dir=${WORKDIR} allowed=[${allowed.join(",")}]`);
  if (existsSync(WHISPER_BIN) && existsSync(WHISPER_MODEL)) {
    log(`voice ready (local): ${WHISPER_BIN} model=${WHISPER_MODEL} lang=${WHISPER_LANG}`);
  } else if (WHISPER_REMOTE) {
    log(`voice ready (remote): whisper.cpp on ${WHISPER_REMOTE} via ssh, model=${WHISPER_MODEL.split("/").pop()} lang=${WHISPER_LANG}`);
  } else {
    log(`WARNING: voice transcription unavailable — bin=${existsSync(WHISPER_BIN)} model=${existsSync(WHISPER_MODEL)} remote=""`);
  }
  if (!allowed.length) log("allowlist empty: first private-chat sender will be registered as owner");

  let pollFailures=0;
  for (;;) {
    try {
      await poll();
      pollFailures=0;
    } catch (e) {
      log("poll error:", e?.message || e);
      await new Promise((r) => setTimeout(r, pollBackoffMs(++pollFailures,e?.retryAfterMs)));
    }
  }
}
