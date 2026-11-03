#!/usr/bin/env node
/**
 * whisper-http — one shared speech-to-text endpoint for every frontend.
 *
 * POST /transcribe   body = raw audio (ogg/opus/wav/m4a/mp3…), ?tag= optional
 *                    -> { ok, text, elapsed }
 * GET  /health       -> { ok, remote, model, lang }
 *
 * It reuses lib/whisper.mjs, so it inherits the remote whisper.cpp host and the
 * vocabulary prompt. No audio leaves the LAN: EVO converts to 16 kHz mono WAV,
 * gzip-streams it over SSH to somdutta-linux, and returns the transcript.
 */
import { createServer } from "node:http";
import { writeFileSync, rmSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { createTranscriber, WHISPER_REMOTE, WHISPER_MODEL, WHISPER_LANG, WHISPER_TMP } from "../lib/whisper.mjs";

const PORT = Number(process.env.WHISPER_HTTP_PORT || 8777);
const MAX_BYTES = Number(process.env.WHISPER_HTTP_MAX || 25 * 1024 * 1024);
const log = (...a) => console.log(new Date().toISOString(), ...a);

mkdirSync(WHISPER_TMP, { recursive: true });
const transcribe = createTranscriber({ log });

let n = 0;

const server = createServer(async (req, res) => {
  const send = (code, obj) => {
    res.writeHead(code, { "Content-Type": "application/json" });
    res.end(JSON.stringify(obj));
  };

  if (req.method === "GET" && req.url.startsWith("/health")) {
    return send(200, { ok: true, remote: WHISPER_REMOTE || null, model: WHISPER_MODEL.split("/").pop(), lang: WHISPER_LANG });
  }
  if (req.method !== "POST" || !req.url.startsWith("/transcribe")) return send(404, { ok: false, error: "POST /transcribe" });

  const chunks = [];
  let size = 0;
  for await (const c of req) {
    size += c.length;
    if (size > MAX_BYTES) return send(413, { ok: false, error: `body over ${MAX_BYTES} bytes` });
    chunks.push(c);
  }
  if (!size) return send(400, { ok: false, error: "empty body" });

  const tag = `http-${Date.now()}-${++n}`;
  const src = join(WHISPER_TMP, `${tag}.bin`);
  writeFileSync(src, Buffer.concat(chunks));
  try {
    const r = await transcribe(src, tag);
    if (!r.ok) return send(502, { ok: false, error: r.error });
    return send(200, r);
  } finally {
    try {
      rmSync(src, { force: true });
    } catch {}
  }
});

server.listen(PORT, "0.0.0.0", () => log(`whisper-http listening on :${PORT} -> ${WHISPER_REMOTE || "local"}`));
