import assert from 'node:assert/strict';
import {classify} from '/home/somdutta/.config/opencode/plugins/ha-mcp-routing/index.js';
for(const q of ['Where is Shivangsh','Where is Shobha','Is Shivi home','Where is Shivangsh today'])assert.equal(classify(q),'devices');
for(const q of ['Where did Shivangsh go yesterday','Which locations did Shobha visit today'])assert.equal(classify(q),'history');
assert.equal(classify('Turn Shivi room light on'),'devices');
console.log('PASS: current presence differs from historical visits; device commands retain their route.');
