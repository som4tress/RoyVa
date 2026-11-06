import {telegramMedia} from './media.mjs';
import { readFileSync, writeFileSync } from 'node:fs';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL } from 'node:url';
import { setTimeout } from 'node:timers/promises';
import { createTranscriber } from './whisper.mjs';
import { openCodeAPI, runText, replySession, steerText } from './opencode.mjs';
import { tokenUsage, formatUsage, streamingTokens } from './usage.mjs';
import {formatPermission} from './permissions.mjs';

export async function main({transcriber = createTranscriber()} = {}) {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const modelLabel = process.env.OPENCODE_TG_MODEL_LABEL || 'Qwen3.8 27B Q8_0 · reasoning off · MTP 6';
  const allowed = new Set((process.env.TELEGRAM_ALLOWED_USER_IDS || '').split(',').map(value => value.trim()).filter(Boolean));
  if (!token || !allowed.size) throw new Error('Telegram token and explicit allowed user IDs are required.');
  const stateFile = process.env.OPENCODE_TG_STATE_FILE;
  let state;
  try { state = JSON.parse(readFileSync(stateFile, 'utf8')); }
  catch (error) { if (error.code !== 'ENOENT') throw error; state = { offset: 0, messages: {} }; }
  state.permissions ||= {};
  const save = () => writeFileSync(stateFile, JSON.stringify(state), { mode: 0o600 });
  const active = new Map();
  const queues = new Map();
  const transcribe = transcriber;
  async function tg(method, payload) {
    const response = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(65000),
    });
    const result = await response.json();
    if (!result.ok) throw new Error(`Telegram ${method}: ${result.error_code}`);
    return result.result;
  }
  async function send(message, text, sessionID, permissionID) {
    const points = Array.from(text);
    let first;
    for (let offset = 0; offset < points.length; offset += 3900) {
      const result = await tg('sendMessage', {
        chat_id: message.chat.id, text: points.slice(offset, offset + 3900).join(''),
        reply_parameters: { message_id: message.message_id, allow_sending_without_reply: true },
      });
      first ??= result;
      if (permissionID) state.permissions[`${message.chat.id}:${result.message_id}`] = {sessionID, requestID: permissionID};
      if (sessionID) { state.messages[`${message.chat.id}:${result.message_id}`] = sessionID; save(); }
    }
    return first;
  }
  async function preparePrompt(message, text, sessionID) {
    let prompt = text;
    let replyTo = message;
    const audio = message.voice || message.audio;
    if (audio) {
      if (audio.file_size > 20 * 1024 * 1024 || audio.duration > 600) throw new Error('Voice limit: 20 MB and 10 minutes.');
      const directory = await mkdtemp(join(tmpdir(), 'opencode-voice-'));
      try {
        const file = await tg('getFile', { file_id: audio.file_id });
        const response = await fetch(`https://api.telegram.org/file/bot${token}/${file.file_path}`, { signal: AbortSignal.timeout(60000) });
        if (!response.ok) throw new Error('Audio download failed.');
        const bytes = Buffer.from(await response.arrayBuffer());
        if (bytes.length > 20 * 1024 * 1024) throw new Error('Audio exceeds 20 MB.');
        const source = join(directory, 'audio'); await writeFile(source, bytes, { mode: 0o600 });
        const result = await transcribe(source, directory.split('/').at(-1));
        if (!result.ok) throw new Error('Speech transcription failed.');
        prompt = result.text;
        const transcript = await send(message, prompt, sessionID);
        if (transcript) replyTo = {...message, message_id: transcript.message_id};
      } finally { await rm(directory, { recursive: true, force: true }); }
    }
    const files = await telegramMedia(message, tg, token);
    if (files.length && !prompt.trim()) prompt = message.video || message.video_note || /^video\//.test(message.document?.mime_type || '') ? 'Describe this video.' : 'Describe this image.';
    return {prompt, replyTo, files};
  }
  async function handle(message) {
    if (!allowed.has(String(message.from?.id)) || message.from?.is_bot) return;
    const linked = replySession(state, message);
    const text = message.text || message.caption || '';
    if (text === '/start' || text === '/help') return send(message, 'Send text, a voice note, a photo or a video to OpenCode. Each standalone message starts a new session; reply to continue or steer it while it is running. /stop stops a running request. Reply with /approve or /deny to answer a permission request. /status shows the connection.');
    if (text === '/status') return send(message, `Vanilla OpenCode v2.2.5. ${modelLabel}. Text, voice, images and sampled-video analysis enabled. Home Assistant MCP connected. No model routing.`);
    if (text === '/stop') {
      const runs = linked ? [active.get(linked)] : [...active.values()].filter(run => run.chat === message.chat.id && run.user === message.from.id);
      runs.filter(Boolean).forEach(run => run.controller.abort());
      return send(message, runs.filter(Boolean).length ? 'Stop requested.' : 'No matching request is running.', linked);
    }
    if (text === '/approve' || text === '/deny') {
      if (!linked) return send(message, 'Reply to a permission request with /approve or /deny.');
      const pending = await openCodeAPI(`/api/session/${linked}/permission`);
      if (!pending.length) return send(message, 'No pending permission request.', linked);
      const target = state.permissions[`${message.chat.id}:${message.reply_to_message.message_id}`];
      if (!target || target.sessionID !== linked) {
        for (const permission of pending) await send(message, formatPermission(permission), linked, false, permission.id);
        return;
      }
      const request = pending.find(permission => permission.id === target.requestID);
      if (!request) return send(message, 'That permission request is no longer waiting. Reply to the current approval prompt.', linked);
      try {
        await openCodeAPI(`/api/session/${linked}/permission/${request.id}/reply`, 'POST', { decision: text === '/approve' ? 'once' : 'reject' });
      } catch (error) {
        return send(message, `Could not confirm the permission decision: ${error.message}. Retry only if the request is still waiting.`, linked);
      }
      return send(message, text === '/approve' ? 'Approved once.' : 'Denied.', linked);
    }
    const sessionID = linked || (await openCodeAPI('/api/session', 'POST', { location: { directory: process.env.OPENCODE_TG_DIR } })).id;
    state.messages[`${message.chat.id}:${message.message_id}`] = sessionID; save();
    const running = linked && active.get(sessionID);
    if (running?.accepting) {
      running.revision++;
      running.steering = running.steering.then(async () => {
        const {prompt, replyTo, files} = await preparePrompt(message, text, sessionID);
        if (!prompt.trim()) return send(message, 'Send text, a voice note, a photo or a video.', sessionID);
        if (await running.ready && !running.controller.signal.aborted) {
          await steerText(sessionID, prompt, {files});
          running.replyTo = replyTo;
        }
      }).catch(async error => {
        console.error('Steering failed:', error.name);
        await send(message, 'Could not deliver that follow-up. Please try again.', sessionID);
      });
      return running.steering;
    }
    const prior = queues.get(sessionID) || Promise.resolve();
    const job = prior.catch(() => {}).then(async () => {
      const controller = new AbortController();
      const admission = Promise.withResolvers();
      const run = {replyTo: message, ready: admission.promise, controller, chat: message.chat.id, user: message.from.id, accepting: true, revision: 0, steering: Promise.resolve()};
      active.set(sessionID, run);
      let observedRevision = 0;
      const typing = () => tg('sendChatAction', { chat_id: message.chat.id, action: 'typing' }).catch(() => {});
      const timer = setInterval(typing, 4000); void typing();
      const started = Date.now();
      let status;
      let lastUpdate = 0;
      let rows = [];
      async function updateStatus(finished = false) {
        if (!status) return;
        if (!finished && Date.now() - lastUpdate < 3000) return;
        lastUpdate = Date.now();
        const usage = tokenUsage(rows);
        const pending = rows.filter(row => row.type === 'assistant' && !row.time.completed);
        const partial = pending.flatMap(row => (row.content || []).filter(part => part.type === 'text' || part.type === 'reasoning').map(part => part.text || '')).join('');
        const live = finished ? null : await streamingTokens(partial).catch(() => null);
        const tool = rows.flatMap(row => row.content || []).filter(part => part.type === 'tool').at(-1);
        const elapsed = Math.round((Date.now() - started) / 1000);
        const blocks = Math.max(1, Math.ceil(elapsed / 3));
        const localBar = '▰'.repeat(blocks);
        const hourglass = Math.floor(elapsed / 3) % 2 ? '⌛' : '⏳';
        const lines = [
          `${finished ? '✓ Finished' : `${hourglass} Processing`} · ${Math.round((Date.now() - started) / 1000)}s elapsed`,
          modelLabel,
          `Local ${localBar} · ${elapsed}s`,
          'Remote ▱ · idle',
          'Each block ≈ 3s',
          usage.passes ? formatUsage(usage) : 'Tokens: awaiting provider usage',
          ...(!finished && pending.length ? [`Current pass: ${live === null ? 'output usage pending' : `~${live} streamed output tokens`} · input usage pending`] : []),
          ...(!finished && tool ? [`Tool: ${tool.name} · ${tool.state?.status || 'running'}`] : []),
          ...(!finished ? ['Reply to steer · /stop'] : []),
        ];
        await tg('editMessageText', { chat_id: message.chat.id, message_id: status.message_id, text: lines.join('\n') }).catch(() => {});
      }
      const statusTimer = setInterval(() => { void updateStatus().catch(() => {}); }, 3000);
      try {
        const prepared = await preparePrompt(message, text, sessionID);
        const prompt = prepared.prompt;
        run.replyTo = prepared.replyTo;
        if (!prompt.trim()) return await send(message, 'Send text, a voice note, a photo or a video.', sessionID);
        if (controller.signal.aborted) return;
        status = await tg('sendMessage', { chat_id: message.chat.id, text: `⏳ Processing · 0s elapsed\n${modelLabel}\nTokens: awaiting provider usage`, reply_parameters: { message_id: run.replyTo.message_id, allow_sending_without_reply: true } });
        state.messages[`${message.chat.id}:${status.message_id}`] = sessionID; save();
        const answer = await runText(sessionID, prompt, {
          signal: controller.signal, files: prepared.files,
          onAdmitted: () => admission.resolve(true),
          onBeforeFinish: async () => {
            const revision = run.revision;
            await run.steering;
            if (revision !== observedRevision || revision !== run.revision) {
              observedRevision = revision;
              return true;
            }
            run.accepting = false;
            return false;
          },
          onProgress: async progress => { rows = progress; },
          onPermission: (permission, history) => send(run.replyTo, formatPermission(permission, history), sessionID, permission.id),
        });
        await updateStatus(true);
        await send(run.replyTo, answer, sessionID);
      } catch (error) {
        console.error('Request failed:', error.name);
        await send(run.replyTo, `Request failed: ${error.message.includes('http') ? error.name : error.message}`, sessionID);
      } finally { run.accepting = false; controller.abort(); admission.resolve(false); clearInterval(timer); clearInterval(statusTimer); active.delete(sessionID); }
    });
    queues.set(sessionID, job);
    void job.finally(() => { if (queues.get(sessionID) === job) queues.delete(sessionID); }).catch(() => {});
  }
  await tg('deleteWebhook' , { drop_pending_updates: false });
  const me = await tg('getMe', {});
  console.log(`Telegram connected as @${me.username}; standalone messages create native sessions.`);
  while (true) {
    try {
      const updates = await tg('getUpdates', { offset: state.offset + 1, timeout: 30, allowed_updates: ['message'] });
      for (const update of updates) {
        // Record admission before execution; never automatically replay household actions after restart.
        state.offset = update.update_id; save();
        if (update.message) void handle(update.message).catch(error => console.error('Update failed:', error.name));
      }
    } catch (error) { console.error('Polling failed:', error.name); await setTimeout(5000); }
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
