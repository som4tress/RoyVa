import test, {before,after} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
let directory,videoURI;
before(async()=>{directory=await mkdtemp(join(tmpdir(),'royva-media-test-'));const path=join(directory,'colors.mp4');execFileSync('/usr/bin/ffmpeg',['-nostdin','-v','error','-f','lavfi','-i','color=c=red:s=320x240:d=4:r=5','-pix_fmt','yuv420p','-y',path]);videoURI=pathToFileURL(path).href;});
after(async()=>rm(directory,{recursive:true,force:true}));
import {mediaKind,preparePrompt,boundedDownload,MAX_BYTES} from './index.js';
import {attachment,telegramMedia} from '../telegram/media.mjs';
import {runText,steerText} from '../telegram/opencode.mjs';
test('Telegram photos, video notes, documents and captions keep actual media',async()=>{
 assert.equal(attachment({photo:[{file_id:'small'},{file_id:'large'}]}).file_id,'large');
 assert.equal(attachment({video_note:{file_id:'note'}}).mime,'video/mp4');
 assert.equal(attachment({document:{mime_type:'image/png',file_name:'a.png'}}).name,'a.png');
 const original=globalThis.fetch;
 try {
  globalThis.fetch=async()=>new Response(new Uint8Array([1,2,3]));
  const files=await telegramMedia({photo:[{file_id:'photo',file_size:3}]},async()=>({file_path:'photo.jpg'}),'fixture');
  assert.equal(files[0].uri,'data:image/jpeg;base64,AQID');
 }finally{globalThis.fetch=original;}
});
test('video is decoded into ordered timestamped JPEGs; captions retained',async()=>{
 const e={prompt:{text:'Describe changes',files:[{uri:videoURI,name:'clip.mp4'}]}};
 await preparePrompt(e);
 assert.equal(e.prompt.files.length,4);
 assert(e.prompt.files.every(f=>f.uri.startsWith('data:image/jpeg;base64,')));
 assert.match(e.prompt.files[0].name,/0.50s/);assert.match(e.prompt.files[3].name,/3.50s/);
 assert.match(e.prompt.text,/Describe changes/);assert.match(e.prompt.text,/audio is not included/);
});
test('native images preserved, attachment-only defaults and bad media rejected',async()=>{
 const image={uri:'data:image/png;base64,AQID',name:'image.png'};const e={prompt:{text:'',files:[image]}};
 await preparePrompt(e);assert.deepEqual(e.prompt.files,[image]);assert(e.prompt.text);
 await assert.rejects(preparePrompt({prompt:{text:'x',files:[{uri:'data:video/mp4;base64,AQID',name:'bad.mp4'}]}}));
 await assert.rejects(preparePrompt({prompt:{text:'x',files:Array(9).fill(image)}}),/eight/);
 await assert.rejects(boundedDownload(new Response('x',{headers:{'content-length':String(MAX_BYTES+1)}})),/20 MB/);
});
test('native queued prompts and active steering retain image and video attachments',async()=>{
 const files=[{uri:'data:image/png;base64,AQID',name:'photo.png'}];const posts=[];let admitted=false;
 const api=async(path,method,body)=>{
  if(method==='POST'){posts.push(body);admitted=true;return;}
  if(path.endsWith('/permission'))return [];
  if(path.endsWith('/message'))return admitted?[{id:'u',type:'user',time:{created:1}},{id:'a',type:'assistant',time:{created:2},content:[{type:'text',text:'image answer'}]}]:[];
  return {time:{busy:1,idle:3}};
 };
 assert.equal(await runText('s','caption',{api,files}),'image answer');
 await steerText('s','followup',{api,files});
 assert.deepEqual(posts,[{text:'caption',delivery:'queue',files},{text:'followup',delivery:'steer',files}]);
});

test('web/desktop staged video uploads use the same shared preparation',async()=>{
 const e={prompt:{text:'Inspect uploaded clip',files:[]},metadata:{attachments:[{path:new URL(videoURI).pathname,name:'colors.mp4',mime:'video/mp4'}]}};
 await preparePrompt(e);assert.equal(e.prompt.files.length,4);assert.match(e.prompt.text,/chronological/);
});
