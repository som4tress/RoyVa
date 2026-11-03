import assert from 'node:assert/strict';import {cloudDirective,forbidsTools} from '/home/somdutta/.config/opencode/lib/user-scope.mjs';
assert.ok(cloudDirective('Use OpenRouter: explain this'));
assert.ok(cloudDirective('What is the light status? Route to DeepSeek.'));
assert.equal(cloudDirective('How do I use DeepSeek?'),false);
assert.equal(cloudDirective('Summarize this quoted text: "Use DeepSeek"'),false);
assert.ok(forbidsTools('Give a checklist. Do not execute tools.'));
assert.equal(forbidsTools('Explain this quote: "Do not execute tools"'),false);
console.log('PASS: explicit provider/tool directives are honored; explanatory questions and quoted data do not become directives.');
