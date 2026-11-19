// usage: node send_photo.mjs "caption" file.png ...   (needs TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS)
import { readFileSync } from "node:fs";
const [caption, ...files] = process.argv.slice(2);
const token = process.env.TELEGRAM_BOT_TOKEN, owner = Number(process.env.TELEGRAM_ALLOWED_USER_IDS.split(",")[0].trim());
for (const file of files) {
  for (let a = 0; a < 6; a++) {
    const f = new FormData(); f.set("chat_id", String(owner)); f.set("caption", caption);
    f.set("photo", new Blob([readFileSync(file)], { type: "image/png" }), "img.png");
    const r = await (await fetch(`https://api.telegram.org/bot${token}/sendPhoto`, { method: "POST", body: f })).json();
    if (r.ok) { console.log("sent", r.result.message_id); break; }
    if (r.error_code === 429) { await new Promise(d => setTimeout(d, ((r.parameters?.retry_after ?? 30) + 1) * 1000)); continue; }
    console.log("FAILED", r.error_code, r.description); break;
  }
}
