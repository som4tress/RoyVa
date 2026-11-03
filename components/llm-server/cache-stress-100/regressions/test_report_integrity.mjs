import assert from 'node:assert/strict';import {isStatusReport,reportFromRequest} from '/home/somdutta/.config/opencode/lib/ha-reports.mjs';
assert.equal(isStatusReport('Check NT50W in Home Assistant and give its live state only.'),false);
assert.equal(isStatusReport('Show the current status of all lights in my home. Do not change anything.'),true);
const mk=(name,domain,state)=>({kind:'ha_status_report',version:1,read_only:true,columns:['Device','Type','State'],domains:[domain],rows:[[name,domain,state]],total:1,filters:{},truncated:false});
const body={messages:[{role:'user',content:'Show devices'},{role:'assistant',tool_calls:[{id:'a',function:{name:'ha-history_get_device_status_report'}},{id:'b',function:{name:'ha-history_get_device_status_report'}}]},{role:'tool',tool_call_id:'a',content:JSON.stringify(mk('Lamp','light','off'))},{role:'tool',tool_call_id:'b',content:JSON.stringify(mk('Fan','fan','on'))}]};
const text=reportFromRequest(body);assert.ok(text.includes('Lamp')&&text.includes('Fan'));assert.ok(text.includes('2 of 2'));
console.log('PASS: HA product name is not whole-home intent; read-only qualifiers preserve reports; parallel reports merge without a second LLM pass.');
