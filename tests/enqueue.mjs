// Queue test prompts for the running RoyVa bridge. Each is mirrored into the owner's Telegram chat and run through
// the bridge's normal handle() path, so every test is watchable on Telegram.
// Usage: node tests/enqueue.mjs "P1" "What is the status of lights upstairs?" ["P2" "..."]   (label/text pairs)
//        node tests/enqueue.mjs --suite            (the six standard example prompts)
import { writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

const dir = process.env.ROYVA_INJECT_DIR || '/home/somdutta/RoyVa/runtime/inject';
mkdirSync(dir, { recursive: true, mode: 0o700 });

const SUITE = [
  ['P1 lights', 'What is the status of lights upstairs?'],
  ['P2 mustang', 'How much distance has my mustang travelled this week?'],
  ['P3 forecast', 'What is the weather forecast for the next 10 days?'],
  ['P4 in/out', 'What is the weather inside and outside of my house?'],
  ['P5 unread', 'List the top 20 oldest unread emails from my gmail.'],
  ['P6 xyz', 'Find any email that has mention of "XYZ".'],
];

const args = process.argv.slice(2);
const jobs = args[0] === '--suite' ? SUITE : args.reduce((acc, a, i) => (i % 2 ? (acc[acc.length - 1].push(a), acc) : (acc.push([a]), acc)), []);
const base = Date.now();
jobs.forEach(([label, text], i) => {
  writeFileSync(join(dir, `${base}-${String(i).padStart(2, '0')}.json`), JSON.stringify({ label, text, as: 'royva' }), { mode: 0o600 });
});
console.log(`queued ${jobs.length} test prompt(s) in ${dir}`);
