import {mkdtemp, readFile, writeFile, rm, stat} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
const exec = promisify(execFile);
export const MAX_BYTES = 20 * 1024 * 1024;
export function mediaKind(file) {
  const uri=file.uri || '';
  const name=file.name || uri.split('?')[0];
  if (/^data:video\//i.test(uri) || /\.(mp4|mov|webm|mkv|m4v|avi|ogv)$/i.test(name)) return 'video';
  if (/^data:image\//i.test(uri) || /\.(png|jpe?g|gif|webp|bmp|avif|heic)$/i.test(name)) return 'image';
}
export async function boundedDownload(response) {
  if (!response.ok) throw Error('Media download failed.');
  if (Number(response.headers.get('content-length')) > MAX_BYTES) throw Error('Media limit: 20 MB.');
  const chunks=[];let size=0;
  for await (const chunk of response.body) {
    size+=chunk.length;
    if (size>MAX_BYTES) throw Error('Media limit: 20 MB.');
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks);
}
async function bytes(file) {
  if (file.uri.startsWith('data:')) {
    const match=/^data:[^;,]+;base64,([A-Za-z0-9+/=\s]*)$/.exec(file.uri);
    if (!match || match[1].length>Math.ceil(MAX_BYTES/3)*4+4) throw Error('Invalid or oversized media attachment (20 MB limit).');
    return Buffer.from(match[1],'base64');
  }
  if (file.uri.startsWith('file:')) {
    const path=fileURLToPath(file.uri);
    if ((await stat(path)).size>MAX_BYTES) throw Error('Media limit: 20 MB.');
    return readFile(path);
  }
  if (/^media:[0-9a-f]{64}$/.test(file.uri)) {
    const password=process.env.OPENCODE_SERVER_PASSWORD;
    if (!password) throw Error('Stored media authentication unavailable.');
    return boundedDownload(await fetch(`http://127.0.0.1:49375/api/experimental/media/${file.uri.slice(6)}`, {
      headers:{authorization:`Basic ${Buffer.from('opencode:'+password).toString('base64')}`},signal:AbortSignal.timeout(15000),
    }));
  }
  throw Error('Attach media using a data URI, uploaded media reference or local file URI.');
}
export async function preparePrompt(event, directory=process.cwd()) {
  const files=[...(event.prompt.files || [])];
  // Web/desktop stage non-image uploads on the server and send their paths in metadata.
  for (const ref of event.metadata?.attachments || []) {
    if (!ref || typeof ref.path!=='string') continue;
    const file={uri:pathToFileURL(resolve(directory,ref.path)).href,name:ref.name || ref.path};
    if (mediaKind(file) && !files.some(f=>f.uri===file.uri)) files.push(file);
  }
  const media=files.filter(f=>mediaKind(f));
  if (!media.length) return;
  if (media.filter(f=>mediaKind(f)==='video').length>1 || media.filter(f=>mediaKind(f)==='image').length>8)
    throw Error('Attach at most eight images or one video per message.');
  const rewritten=[];const descriptions=[];
  for (const file of files) {
    if (mediaKind(file)!=='video') {rewritten.push(file);continue;}
    const dir=await mkdtemp(join(tmpdir(),'royva-video-'));
    try {
      const source=join(dir,'clip');await writeFile(source,await bytes(file),{mode:0o600});
      const {stdout}=await exec('/usr/bin/ffprobe',['-v','error','-show_entries','format=duration','-of','json',source],{timeout:15000});
      const duration=Number(JSON.parse(stdout).format?.duration);
      if (!Number.isFinite(duration) || duration<=0 || duration>600) throw Error('Video must be between 0 and 600 seconds.');
      const count=Math.min(8,Math.max(2,Math.ceil(duration))),times=[];
      for (let i=0;i<count;i++) {
        const time=duration*(i+.5)/count;times.push(time.toFixed(2));
        const output=join(dir,`frame-${i}.jpg`);
        await exec('/usr/bin/ffmpeg',['-nostdin','-v','error','-ss',String(time),'-i',source,'-frames:v','1','-vf','scale=960:960:force_original_aspect_ratio=decrease','-y',output],{timeout:30000});
        rewritten.push({uri:'data:image/jpeg;base64,'+(await readFile(output)).toString('base64'),name:`video-frame-${i+1}-at-${time.toFixed(2)}s.jpg`});
      }
      descriptions.push(`Video ${duration.toFixed(2)}s: ${count} frames in chronological order at ${times.join(', ')}s. Sparse visual sampling only; audio is not included and events between frames may be missed.`);
    } finally {await rm(dir,{recursive:true,force:true});}
  }
  if (rewritten.filter(f=>mediaKind(f)==='image').length>8) throw Error('Image/video frame limit: eight per message.');
  event.prompt.files=rewritten;
  if (descriptions.length) event.prompt.text+='\n\n[Video input: '+descriptions.join('\n')+']';
  if (!event.prompt.text.trim()) event.prompt.text='Describe the attached images.';
}
export default {id:'royva.media-input',async setup(ctx) {await ctx.session.hook('prompt',event=>preparePrompt(event,ctx.location.directory));}};
