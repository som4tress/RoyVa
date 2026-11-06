// Telegram transport mocked; use fixture files and a mocked native API for offline routing.
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const root=mkdtempSync(join(tmpdir(),'royva-telegram-media-'));
Object.assign(process.env,{TELEGRAM_BOT_TOKEN:'fixture',TELEGRAM_ALLOWED_USER_IDS:'1',OPENCODE_TG_STATE_FILE:join(root,'state.json'),OPENCODE_TG_URL:'http://fixture',OPENCODE_SERVER_PASSWORD:'fixture',OPENCODE_TG_DIR:root});
const kind=process.argv[2]||'image';let polled=false,admitted=false,files;let id=100;
const json=value=>new Response(JSON.stringify(value),{headers:{'content-type':'application/json'}});
globalThis.fetch=async(url,options={})=>{
 const body=options.body?JSON.parse(options.body):{};
 if(url.includes('/file/bot'))return new Response(new Uint8Array([1,2,3]));
 if(url.startsWith('https://api.telegram.org/')){
  const method=url.split('/').at(-1);let result=true;
  if(method==='getMe')result={username:'fixture'};
  if(method==='getFile')result={file_path:kind==='image'?'image.jpg':'video.mp4'};
  if(method==='getUpdates'){
   if(polled)return new Promise(()=>{});polled=true;
   result=[{update_id:1,message:{message_id:7,chat:{id:1},from:{id:1},caption:'Inspect this attachment',...(kind==='image'?{photo:[{file_id:'photo',file_size:3}]}:{video:{file_id:'video',file_size:3,duration:1,mime_type:'video/mp4'}})}}];
  }
  if(method==='sendMessage'){
   result={message_id:id++};
   if(body.reply_markup)setImmediate(()=>{
    try{assert.equal(body.text,'Visual answer');assert(files[0].uri.startsWith(kind==='image'?'data:image/jpeg;base64,':'data:video/mp4;base64,'));console.log('Telegram '+kind+' caption, attachment admission and reply verified.');rmSync(root,{recursive:true,force:true});process.exit(0);}
    catch(e){console.error(e);process.exit(1);}
   });
  }
  return json({ok:true,result});
 }
 const path=new URL(url).pathname;
 if(path==='/api/session')return json({data:{id:'session'}});
 if(path.endsWith('/prompt')){assert.equal(body.text,'Inspect this attachment');assert.equal(body.files.length,1);files=body.files;admitted=true;return json({data:{}});}
 if(path.endsWith('/permission'))return json({data:[]});
 if(path.endsWith('/message'))return json({data:admitted?[{id:'u',type:'user',time:{created:1}},{id:'a',type:'assistant',time:{created:2,completed:2},content:[{type:'text',text:'Visual answer'}]}]:[]});
 if(path==='/api/session/session')return json({data:{time:{idle:3,busy:1}}});
 throw Error('Unexpected fixture request '+path);
};
const {main}=await import('./bridge.mjs');await main();
