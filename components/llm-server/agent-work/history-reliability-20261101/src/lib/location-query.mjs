/** A fast current-location lookup must never capture history or explanation. */
export function isCurrentLocationQuery(query,people){
 const q=String(query||'').normalize('NFKC').replace(/’/g,"'").toLowerCase().trim().replace(/[?.!]+$/g,'').replace(/\s+/g,' ');
 if(/\b(history|historical|visited|visits|been|went|past|last|previous|ago|earlier|during|between|hours?|minutes?|days?|yesterday|timeline|why|explain|asking|asked|instead|getting|wrong|rather|route|model|deepseek|glm|qwen)\b/.test(q))return false;
 const escape=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
 const names=Object.keys(people).sort((a,b)=>b.length-a.length).map(escape).join('|');
 if(!names)return false;
 return new RegExp('^(?:please )?(?:(?:where (?:is|are)|where\'s|locate|find) (?:'+names+')(?: (?:now|currently|right now))?|(?:show|give|tell)(?: me)? (?:the )?(?:current )?location (?:of|for) (?:'+names+')|(?:'+names+')(?:\'s)? (?:current )?location)$','i').test(q);
}
export function isLocationExplanation(query){return /\b(why|explain|asking|asked|instead|wrong|getting|rather than)\b/i.test(query)&&/\b(location|locations|history|answer|response)\b/i.test(query);}
