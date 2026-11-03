// Text glyphs stay compact on Telegram; these are elapsed route samples, not completion percentages.
const icon={local:'▰',remote:'▱',both:'▧',other:'·'};
export function describeTool(name){
 if(/get_visited_locations$/.test(name))return 'Reading recorded location history';
 if(/get_device_status_report$/.test(name))return 'Reading device states';
 if(/get_device_status$|GetLiveContext$/.test(name))return 'Reading live device status';
 if(/get_on_entities_with_context$/.test(name))return 'Checking state-change evidence';
 if(/HassTurn|HassLightSet|HassFanSet|HassClimateSet|play_media$/.test(name))return 'Sending device command';
 if(/webfetch|websearch|search_web/.test(name))return 'Fetching sources';
 if(name==='shell'||name==='bash')return 'Running a command';
 if(name==='read')return 'Reading a file';
 if(/^(write|edit|apply_patch)$/.test(name))return 'Editing a file';
 return 'Using '+String(name||'a tool').replace(/[^a-zA-Z0-9_:-]/g,'').slice(0,60);
}
const modelName=name=>String(name).split('/').at(-1).replace(/[^a-zA-Z0-9_.:-]/g,'').slice(0,48);
export function renderTimeline({startedAt,now=Date.now(),events=[],models=[],activity=null,frame=0,finished=null,tokenStats=''}){
 const seconds=Math.max(0,Math.floor((now-startedAt)/1000)),width=Math.min(20,Math.max(1,Math.ceil(seconds/2))),span=Math.max(2000,(now-startedAt)/width);
 const sorted=events.filter(e=>e.at>=startedAt&&e.at<=now).sort((a,b)=>a.at-b.at),phaseAt=t=>sorted.filter(e=>e.at<=t).at(-1)?.phase||'other';
 const phase=phaseAt(now),label={local:'Local',remote:'Remote',both:'Local + remote',other:'OpenCode'}[phase]||'OpenCode';
 const graph=Array.from({length:width},(_,i)=>icon[phaseAt(Math.min(now,startedAt+(i+.5)*span))]||icon.other).join('');
 const current=models.length?models:sorted.at(-1)?.models||[];
 const lastModels=[...sorted].reverse().find(e=>e.models?.length)?.models||[];
 let detail;
 if(!finished&&activity?.status==='approval-required'&&activity.at>=startedAt)detail='Awaiting your approval for '+modelName(activity.action||'a tool')+'. Review this session in your OpenCode browser/client.';
 else if(finished)detail=lastModels.length?'Last model: '+lastModels.map(modelName).join(' + '):'OpenCode';
 else if(phase!=='other')detail=(current.length?current.map(modelName).join(' + '):label+' model')+' — generating next action / answer';
 else if(activity?.tool&&activity.at>=startedAt)detail='OpenCode — '+(activity.status==='running'?describeTool(activity.tool):describeTool(activity.tool)+' completed; preparing next step');
 else detail='OpenCode — preparing request / next step';
 const lastStep=!finished&&phase!=='other'&&activity?.tool&&activity.at>=startedAt&&activity.status==='completed'?'\nLast step: '+describeTool(activity.tool)+' ✓':'';
 return `${finished||`${frame%2?'⌛':'⏳'} ${label}`} · ${seconds}s elapsed\n${detail}${lastStep}\n${graph}\n▰ Local · ▱ Remote · · Other (~${Math.max(2,Math.round(span/1000))}s/block)${sorted.some(e=>e.phase==='both')?' · ▧ Both':''}${tokenStats?'\n'+tokenStats:''}${finished?'':'\nReply to steer · /stop'}`;
}
