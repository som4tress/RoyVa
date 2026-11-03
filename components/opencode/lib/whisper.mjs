/**
 * Shared local speech-to-text for the chat bridges (Telegram, WhatsApp).
 *
 * whisper.cpp + ffmpeg, running on this box only — nothing leaves the machine.
 * Voice notes arrive as OGG/Opus, so ffmpeg converts to the 16 kHz mono PCM
 * WAV that whisper expects before transcription.
 */
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const WHISPER_ROOT =
  process.env.WHISPER_ROOT || join(homedir(), ".local/share/opencode/whisper");
export const WHISPER_BIN = process.env.WHISPER_BIN || join(WHISPER_ROOT, "bin/whisper-cli");
export const WHISPER_MODEL =
  process.env.WHISPER_MODEL || join(WHISPER_ROOT, "models/ggml-large-v3-turbo-q5_0.bin");
export const WHISPER_LANG = process.env.WHISPER_LANG || "auto";
// Vocabulary bias: whisper mishears the unusual proper nouns ("Shobha" -> "Shabka",
// "Shivi" -> "shivvy"), and those are exactly the names the agent must match to a
// Home Assistant entity. Fed as the initial prompt; never echoed into the transcript.
// Set WHISPER_PROMPT="" to disable.
export const WHISPER_PROMPT =
  process.env.WHISPER_PROMPT ??
  "Kitchen Dimmer, Island Dimmer, Den Switch, Shivi Room Fan, Shivi Room Study Tubelight, Shivi Bedroom Light, Shivi Linux Box, Pecky, Shobha, Shivangsh, somdutta.";
// Remote transcription: whisper.cpp lives on the OTHER machine (somdutta-linux),
// not on this box. Set WHISPER_REMOTE="" to force local-only.
export const WHISPER_REMOTE =
  process.env.WHISPER_REMOTE === undefined
    ? "somdutta@somdutta-linux.local"
    : process.env.WHISPER_REMOTE.trim();
export const WHISPER_REMOTE_ROOT =
  process.env.WHISPER_REMOTE_ROOT || ".local/share/opencode/whisper";
export const FFMPEG_BIN = process.env.FFMPEG_BIN || "ffmpeg";
export const WHISPER_TMP = join(homedir(), ".local/state/opencode/tmp");
const WHISPER_TIMEOUT_MS = Number(process.env.WHISPER_TIMEOUT || 180_000);

mkdirSync(WHISPER_TMP, { recursive: true });

/** Run a command, capturing output, with a hard timeout. */
function runOnce(cmd, args, { timeoutMs = WHISPER_TIMEOUT_MS } = {}) {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
    }, timeoutMs);
    child.stdout.on("data", (d) => (stdout += d.toString()));
    child.stderr.on("data", (d) => (stderr += d.toString()));
    child.on("error", (e) => {
      clearTimeout(timer);
      resolve({ code: -1, stdout, stderr: `${stderr}\n${e.message}` });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ code, stdout, stderr });
    });
  });
}

export const whisperReady = () => existsSync(WHISPER_BIN) && existsSync(WHISPER_MODEL);

/**
 * Build a transcriber bound to a logger.
 * Returns async (srcPath, tag) => { ok, text, elapsed } | { ok: false, error }
 */
const shQuote = (s) => `'${String(s).replace(/'/g, `'\\''`)}'`;
const b64 = (s) => Buffer.from(String(s), "utf8").toString("base64");

/**
 * Transcribe on the remote whisper host over SSH: gzip the 16 kHz WAV into a
 * mktemp dir there, run whisper-cli, print the .txt back. One round trip.
 * Returns { ok, text, elapsed } | { ok: false, error }.
 */
async function transcribeRemote(wav, { log }) {
  const model = WHISPER_MODEL.split("/").pop();
  const remote = [
    'd=$(mktemp -d) || exit 3',
    'gunzip -c > "$d/a.wav" || exit 4',
    `W="$HOME/${WHISPER_REMOTE_ROOT}"`,
    `P=$(printf %s ${b64(WHISPER_PROMPT)} | base64 -d)`, // base64 is quote-safe
    `"$W/bin/whisper-cli" -m "$W/models/${model}" -f "$d/a.wav" -l "${WHISPER_LANG}" -otxt -of "$d/o" -nt -np -bs 1 -t 8 --prompt "$P" >"$d/log" 2>&1`,
    "rc=$?",
    'cat "$d/o.txt" 2>/dev/null',
    'rm -rf "$d"',
    "exit $rc",
  ].join("; ");
  const started = Date.now();
  const r = await runOnce("bash", [
    "-c",
    `gzip -c ${shQuote(wav)} | ssh -o BatchMode=yes -o ConnectTimeout=10 ${WHISPER_REMOTE} ${shQuote(remote)}`,
  ]);
  const elapsed = ((Date.now() - started) / 1000).toFixed(1);
  if (r.code !== 0 && !r.stdout.trim()) {
    return { ok: false, error: `remote whisper exited ${r.code}: ${r.stderr.trim().slice(-300)}` };
  }
  const text = cleanText(r.stdout);
  if (!text) return { ok: false, error: "remote whisper returned no speech" };
  log(`transcribed remotely (${WHISPER_REMOTE}) in ${elapsed}s`);
  return { ok: true, text, elapsed };
}

/** Shared transcript cleanup: strip timestamps and non-speech markers. */
function cleanText(raw) {
  return raw
    .split("\n")
    .map((l) => l.replace(/\[[\d:.\s>-]+\]\s*/g, "").trim())
    .filter((l) => l && !/^\(?(music|applause|silence|no speech)\)?$/i.test(l))
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
}

export function createTranscriber({ log = () => {} } = {}) {
  return async function transcribeAudio(srcPath, tag) {
    const localReady = existsSync(WHISPER_BIN) && existsSync(WHISPER_MODEL);
    if (!localReady && !WHISPER_REMOTE) {
      return { ok: false, error: `whisper binary missing at ${WHISPER_BIN} and no WHISPER_REMOTE configured` };
    }

    const wav = join(WHISPER_TMP, `${tag}.wav`);
    const prefix = join(WHISPER_TMP, `${tag}.out`);
    const txtPath = `${prefix}.txt`;

    const ff = await runOnce(
      FFMPEG_BIN,
      ["-hide_banner", "-loglevel", "error", "-y", "-i", srcPath, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav],
      { timeoutMs: 60_000 },
    );
    if (ff.code !== 0) return { ok: false, error: `ffmpeg failed: ${ff.stderr.slice(-300)}` };

    // Preferred path: whisper.cpp on the dedicated host (GPU there, none here).
    if (WHISPER_REMOTE) {
      const remote = await transcribeRemote(wav, { log });
      try {
        rmSync(wav, { force: true });
      } catch {}
      if (remote.ok) return remote;
      log(`remote whisper failed (${remote.error}); ${localReady ? "falling back to local" : "no local whisper here"}`);
      if (!localReady) return { ok: false, error: remote.error };
    }

    const readTxt = () => {
      try {
        return readFileSync(txtPath, "utf8");
      } catch {
        return "";
      }
    };

    const baseArgs = [
      "-m", WHISPER_MODEL,
      "-f", wav,
      "-l", WHISPER_LANG,
      "-otxt",
      "-of", prefix,
      "-nt", // no timestamps
      "-np", // no progress prints
      "-bs", "1",
      ...(WHISPER_PROMPT.trim() ? ["--prompt", WHISPER_PROMPT] : []),
    ];

    const started = Date.now();
    let wh = await runOnce(WHISPER_BIN, baseArgs);
    let text = readTxt();
    // At boot the CUDA driver may not be up yet; retry once on the CPU backend.
    if (wh.code !== 0 && !text.trim()) {
      log(`whisper failed on GPU (rc=${wh.code}); retrying on CPU: ${wh.stderr.trim().split("\n").pop()}`);
      try {
        rmSync(txtPath, { force: true });
      } catch {}
      wh = await runOnce(WHISPER_BIN, [...baseArgs, "-ng"]);
      text = readTxt();
    }
    const elapsed = ((Date.now() - started) / 1000).toFixed(1);

    for (const p of [wav, txtPath]) {
      try {
        rmSync(p, { force: true });
      } catch {}
    }
    if (wh.code !== 0 && !text.trim()) {
      return { ok: false, error: `whisper exited ${wh.code}: ${wh.stderr.slice(-300)}` };
    }

    text = cleanText(text);

    log(`transcribed ${tag} in ${elapsed}s: "${text.slice(0, 120)}"`);
    return { ok: true, text, elapsed };
  };
}
