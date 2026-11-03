from pathlib import Path
p=Path('/tmp/ha_speed_test.mjs');s=p.read_text();s+='''
const todayCall={sessionID:'history-speed-test',tool:'ha-history_get_visited_locations',input:{person:'somdutta',date:'2000-01-01'}};await hooks['execute.before'](todayCall);assert.equal(todayCall.input.date,undefined);
await hooks.prompt({sessionID:'dated-history-test',prompt:{text:'Which recorded locations did Somdutta visit on 2026-10-30? Show history.'}});
const explicitCall={sessionID:'dated-history-test',tool:'ha-history_get_visited_locations',input:{person:'somdutta',date:'2026-10-30'}};await hooks['execute.before'](explicitCall);assert.equal(explicitCall.input.date,'2026-10-30');
console.log('PASS: today uses the backend clock and an explicit requested date remains unchanged.');
''';p.write_text(s)
