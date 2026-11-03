export function resolvedTargets(tool,state){
 const out=[];
 function visit(x,depth=0){if(depth>6||!x)return;if(typeof x==='string'){try{visit(JSON.parse(x),depth+1)}catch{}return;}if(Array.isArray(x)){for(const i of x)visit(i,depth+1);return;}if(typeof x!=='object')return;
 if(Array.isArray(x.data?.success)&&x.data.success.length===1&&!x.data.failed?.length){const m=x.data.success[0];if(m.name&&m.id)out.push({name:m.name,domain:[m.id.split('.')[0]]});}
 if(x.kind==='ha_status_report'&&Array.isArray(x.rows)&&state.input?.name){const exact=x.rows.filter(r=>String(r[0]).toLowerCase()===String(state.input.name).toLowerCase());if(exact.length===1)out.push({name:exact[0][0],domain:[String(exact[0][1]).toLowerCase()]});}
 if(Array.isArray(x.matches)&&x.matches.length===1){const m=x.matches[0];if(m.name&&m.domain)out.push({name:m.name,domain:[m.domain]});}
 for(const k of ['output','content','text'])if(x[k])visit(x[k],depth+1);
 }
 visit(state);
 if(/HassTurn(?:On|Off)$|HassLightSet$|HassFanSetSpeed$|HassClimateSetTemperature$/.test(tool)&&state.input?.name)out.push({name:state.input.name,...(state.input.domain?{domain:state.input.domain}:{})});
 return [...new Map(out.map(t=>[JSON.stringify(t),t])).values()].slice(-10);
}
export function focusFromReferences(refs){
 for(const r of [...(refs||[])].reverse())if(r.targets?.length)return r.targets;
 return [];
}
export function assertFocusedWrite(tool,input,state){
 if(!state?.referenceFollowup||!/^home[-_]assistant_/.test(tool)||/GetLiveContext$|GetDateTime$|search_media$/.test(tool))return;
 const targets=state.focusTargets||[];
 if(!targets.length)throw new Error('This follow-up has no uniquely verified target. Ask which device; do not infer targets from older conversations.');
 const equal=(a,b)=>String(a||'').trim().toLowerCase()===String(b||'').trim().toLowerCase();
 const hit=targets.find(t=>equal(t.name,input?.name));
 if(!hit||input.area||input.floor)throw new Error('Follow-up action must name only its verified current target: '+targets.map(t=>t.name).join(', '));
 if(hit.domain?.every(d=>['light','switch'].includes(d))&&!/HassTurn(?:On|Off)$|HassLightSet$/.test(tool))throw new Error('A light/switch follow-up cannot operate media players or other domains.');
}
