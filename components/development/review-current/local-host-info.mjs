import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {hostname} from 'node:os';
const exec=promisify(execFile);
const COMMANDS={
 'uname -r':{id:'kernel',bin:'/usr/bin/uname',argv:['-r']},
 'uname --kernel-release':{id:'kernel',bin:'/usr/bin/uname',argv:['-r']},
 'cat /etc/os-release':{id:'os',bin:'/usr/bin/cat',argv:['/etc/os-release']},
 'df -h /':{id:'disk',bin:'/usr/bin/df',argv:['-h','/']},
 'free -h':{id:'memory',bin:'/usr/bin/free',argv:['-h']},
 'hostname':{id:'hostname',bin:'/usr/bin/hostname',argv:[]},
 'uptime':{id:'uptime',bin:'/usr/bin/uptime',argv:[]},
};
function classify(query){
 const q=query.toLowerCase();
 if(query.length>600||/\b(delete|remove|write|create|edit|install|restart|reboot|shutdown|turn|switch|enable|disable|execute|run|ssh|remote|vm|virtual|docker|container|kubernetes|windows|macos|mac|android|ios|gpu|vram|also|then|and|not|never|if|unless|password|token|secret)\b|[;\n`{}]/.test(q))return null;
 if(/\bkernel\b/.test(q)&&/\b(version|release)\b/.test(q))return 'kernel';
 if(/\b(ubuntu|linux|os|operating system)\b/.test(q)&&/\b(version|release|distribution)\b/.test(q))return 'os';
 if(/\b(disk|storage|filesystem)\b/.test(q)&&/\b(free|space|usage|used|available|capacity)\b/.test(q)&&!/\b(directory|directories|folder|folders|largest)\b/.test(q))return 'disk';
 if(/\b(ram|memory)\b/.test(q)&&/\b(free|usage|used|available|capacity|status)\b/.test(q))return 'memory';
 if(/\b(hostname|host name)\b/.test(q))return 'hostname';
 if(/\buptime\b|how long.*running/.test(q))return 'uptime';
 return null;
}
function flatten(value,depth=0){
 if(depth>5)return '';
 if(typeof value==='string'){try{return flatten(JSON.parse(value),depth+1)}catch{return value}}
 if(Array.isArray(value))return value.map(v=>flatten(v?.text??v,depth+1)).join('\n');
 if(!value||value.isError||value.error)return '';
 return flatten(value.content??value.output??value.stdout??value.value??'',depth+1);
}
async function read(command){const {stdout}=await exec(command.bin,command.argv,{timeout:4000,maxBuffer:65536,encoding:'utf8',shell:false});return {stdout:stdout.trim(),category:command.id,host:hostname()};}
export default {
 id:'local-host-info',tools:['shell'],writeTools:[],lookupTools:[],fingerprintFiles:['/etc/machine-id'],
 decode(value){const stdout=flatten(value);return stdout&& !/command not found|permission denied|\bError:/.test(stdout)?{stdout}:null},
 async run(request){
  try{
   if(request.operation==='certify'){
    const args=request.args||{};const text=Array.isArray(args.command)?args.command.join(' '):String(args.command||'');const command=COMMANDS[text.trim()];
    if(!command||classify(request.query)!==command.id)return {ok:false,message:'Not a standalone supported host-info request.'};
    if(!request.data?.stdout)return {ok:false,message:'No successful command output.'};
    const data=await read(command);
    return {ok:true,recipe:{tool:'shell',kind:'read',args:{command:text.trim()},query:request.query,expectedHost:hostname(),adapter:'local-host-info'},data};
   }
   const recipe=request.recipe,command=COMMANDS[recipe?.args?.command];
   if(!command||recipe.expectedHost!==hostname()||classify(request.query)!==command.id)return {ok:false,message:'Host or request changed.'};
   return {ok:true,data:await read(command),tool:'shell'};
  }catch{return {ok:false,message:'Host-info command unavailable.'}}
 },
 format(_tool,data){
  if(!data?.stdout||data.host!==hostname())return null;
  if(data.category==='kernel')return 'Kernel: '+data.stdout;
  if(data.category==='hostname')return 'Hostname: '+data.stdout;
  if(data.category==='os'){const pretty=data.stdout.match(/^PRETTY_NAME="?(.*?)"?$/m)?.[1];return pretty||null}
  if(data.category==='uptime')return 'Uptime: '+data.stdout;
  return '```text\n'+data.stdout+'\n```';
 }
};
