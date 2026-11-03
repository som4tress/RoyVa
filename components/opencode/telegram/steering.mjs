export function controlKind(msg,active){
 const text=(msg.text||msg.caption||'').trim();
 if(/^\/stop(?:@\w+)?(?:\s|$)/i.test(text))return 'stop';
 if(/^\/steer(?:@\w+)?(?:\s|$)/i.test(text))return 'steer';
 const reply=msg.reply_to_message?.message_id;
 return active&&reply!=null&&[active.messageId,active.workingId].includes(reply)?'steer':null;
}
export function correctionText(text){return text.replace(/^\/steer(?:@\w+)?\s*/i,'').trim();}
