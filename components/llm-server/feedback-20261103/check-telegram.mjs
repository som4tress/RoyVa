import {readFileSync,writeFileSync} from 'node:fs';import assert from 'node:assert/strict';
const root='/home/somdutta/llm-server/feedback-20261103';
for(const n of ['api.env','opencode.env','ha.env'])for(const l of readFileSync('/home/somdutta/llm-server/'+n,'utf8').split('\n')){const i=l.indexOf('=');if(i>0)process.env[l.slice(0,i)]=l.slice(i+1).replace(/^["']|["']$/g,'');}
process.env.OPENCODE_TG_STATE_FILE=root+'/telegram-state.json';process.env.OPENCODE_TG_BIN='/home/somdutta/.opencode/bin/opencode';delete process.env.OPENCODE_TG_MODEL;
const {runTelegramSelfTest,handleTelegramFeedbackUpdate}=await import('/home/somdutta/.config/opencode/telegram/bridge.mjs');
const {telegramTarget,status}=await import('/home/somdutta/Projects/agent-learning/src/feedback.mjs');
const chat=6064019420;const reply=await runTelegramSelfTest(chat,'Do not use tools. Reply only FEEDBACK_READY.','Feedback binding check');assert(reply.ok);assert(reply.assistantId);const target=telegramTarget(chat,reply.delivered.at(-1));assert(target);assert.equal(target.messageID,reply.assistantId);
const reaction={chat:{id:chat,type:'private'},message_id:reply.delivered.at(-1),user:{id:chat,is_bot:false},old_reaction:[],new_reaction:[{type:'emoji',emoji:'👍🏻'}]};
await handleTelegramFeedbackUpdate({update_id:Date.now(),message_reaction:{...reaction,user:{id:0,is_bot:false}}});assert.equal(status(target).buildAllowed,false);
await handleTelegramFeedbackUpdate({update_id:Date.now(),message_reaction:reaction});assert.equal(status(target).buildAllowed,true);assert.equal(status(target).activated,false);
await handleTelegramFeedbackUpdate({update_id:Date.now()+1,message_reaction:{...reaction,old_reaction:reaction.new_reaction,new_reaction:[]}});assert.equal(status(target).buildAllowed,false);
writeFileSync(root+'/telegram-result.json',JSON.stringify({reply,target,finalStatus:status(target),checks:['exact message binding','unauthorized ignored','thumb grants creation consent only','withdrawal revokes consent']},null,2));console.log('PASS Telegram delivered-answer mapping and reaction handler; final authorization withdrawn');
