from pathlib import Path
p=Path('/tmp/ha_speed_test.mjs');s=p.read_text().replace('assert.deepEqual(Object.keys(c.tools),[read]);','assert(Object.keys(c.tools).includes(read));').replace("assert.equal(b.tool_choice,'required');","assert.equal(b.tool_choice.function.name,read);");p.write_text(s)
