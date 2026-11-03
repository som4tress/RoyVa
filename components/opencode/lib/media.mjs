import {spawn} from 'node:child_process';
import {mkdirSync,readdirSync,statSync} from 'node:fs';
import {join} from 'node:path';
export const MAX_BYTES=20*1024*1024;
export function attachment(msg){
 if(msg.photo?.length)return {kind:'photo',...msg.photo.at(-1),ext:'.jpg'};
 if(msg.video)return {kind:'video',...msg.video,ext:'.mp4'};
 const d=msg.document;
 if(d&&/^image\/(jpeg|png|webp)$/.test(d.mime_type||''))return {kind:'photo',...d,ext:'.'+({ 'image/jpeg':'jpg','image/png':'png','image/webp':'webp'}[d.mime_type])};
 if(d&&/^video\//.test(d.mime_type||''))return {kind:'video',...d,ext:'.mp4'};
 return null;
}
function exec(bin,args,timeout=30000){return new Promise((resolve,reject)=>{
 const p=spawn(bin,args,{stdio:['ignore','pipe','pipe']});let out='',err='';
 const timer=setTimeout(()=>{p.kill('SIGKILL');reject(new Error('Media preparation timed out'));},timeout);
 p.stdout.on('data',d=>out+=d);p.stderr.on('data',d=>err+=d);
 p.on('error',e=>{clearTimeout(timer);reject(e)});
 p.on('close',code=>{clearTimeout(timer);code===0?resolve(out):reject(new Error('Media decoding failed: '+err.slice(-180)))});
});}
export async function prepareMedia(source,kind,dir){
 mkdirSync(dir,{recursive:true,mode:0o700});
 if(statSync(source).size>MAX_BYTES)throw new Error('Please send a photo/video smaller than 20 MB (Telegram bot download limit).');
 if(kind==='photo')return {files:[source],description:'Attached photo. Read the visible labels carefully. Distinguish screenshot evidence from live device state.'};
 const probe=JSON.parse(await exec('/usr/local/bin/ffprobe',['-v','error','-show_entries','format=duration','-of','json',source]));
 const duration=Number(probe.format?.duration);
 if(!Number.isFinite(duration)||duration<=0||duration>600)throw new Error('Please send a video clip no longer than 10 minutes.');
 const count=Math.min(8,Math.max(2,Math.ceil(duration))),times=[];
 for(let i=0;i<count;i++){
  const at=duration*(i+.5)/count;times.push(at.toFixed(2));
  await exec('/usr/local/bin/ffmpeg',['-nostdin','-v','error','-ss',String(at),'-i',source,'-frames:v','1','-vf','scale=960:960:force_original_aspect_ratio=decrease','-y',join(dir,`frame-${i}.jpg`)]);
 }
 const files=readdirSync(dir).filter(f=>/^frame-\d\.jpg$/.test(f)).sort().map(f=>join(dir,f));
 if(files.length!==count)throw new Error('Could not extract video frames');
 return {files,description:`Video ${duration.toFixed(2)} seconds. Attached ${count} frames in chronological order at ${times.join(', ')} seconds. This is sparse visual sampling, without audio; events between frames may be missed. State this limitation when relevant.`};
}
