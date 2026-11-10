// Crude no-undef: identifiers referenced in a file that are declared nowhere in it and are not globals. Catches missing imports and typos.
const acorn = require('internal/deps/acorn/acorn/dist/acorn');
const walk = require('internal/deps/acorn/acorn-walk/dist/walk');
const fs = require('fs');
const GLOBALS = new Set(['undefined','NaN','Infinity','globalThis','console','process','Buffer','URL','URLSearchParams','AbortSignal','AbortController','fetch','setTimeout','clearTimeout','setInterval','clearInterval','setImmediate','queueMicrotask','structuredClone','TextEncoder','TextDecoder','Object','Array','String','Number','Boolean','Symbol','Map','Set','WeakMap','WeakSet','Promise','JSON','Math','Date','RegExp','Error','TypeError','RangeError','SyntaxError','Proxy','Reflect','Intl','BigInt','parseInt','parseFloat','isNaN','isFinite','encodeURIComponent','decodeURIComponent','encodeURI','decodeURI','Uint8Array','ArrayBuffer','DataView','Blob','FormData','Headers','Request','Response','arguments','require','module','exports','__dirname','__filename','escape','unescape','Atomics','SharedArrayBuffer','Float64Array','Int32Array','Uint32Array','Uint16Array','Int8Array','Int16Array','Float32Array','BigInt64Array','performance','crypto','navigator','WebSocket','EventTarget','Event','AggregateError','FinalizationRegistry','WeakRef','eval','Function','test']);
let bad = 0;
for (const file of process.argv.slice(1)) {
  const src = fs.readFileSync(file, 'utf8');
  let ast; try { ast = acorn.parse(src, {ecmaVersion: 'latest', sourceType: 'module', locations: true}); } catch (e) { console.log(`${file}: parse error ${e.message}`); bad++; continue; }
  const declared = new Set();
  const decl = p => { if (!p) return; switch (p.type) {
    case 'Identifier': declared.add(p.name); break;
    case 'ObjectPattern': p.properties.forEach(x => decl(x.type === 'RestElement' ? x.argument : x.value)); break;
    case 'ArrayPattern': p.elements.forEach(decl); break;
    case 'RestElement': decl(p.argument); break;
    case 'AssignmentPattern': decl(p.left); break; } };
  walk.full(ast, n => {
    if (n.type === 'VariableDeclarator') decl(n.id);
    if (n.type === 'FunctionDeclaration' || n.type === 'ClassDeclaration') { if (n.id) declared.add(n.id.name); }
    if (n.type === 'FunctionDeclaration' || n.type === 'FunctionExpression' || n.type === 'ArrowFunctionExpression') { n.params.forEach(decl); if (n.id) declared.add(n.id.name); }
    if (n.type === 'ClassExpression' && n.id) declared.add(n.id.name);
    if (n.type === 'CatchClause' && n.param) decl(n.param);
    if (n.type === 'ImportSpecifier' || n.type === 'ImportDefaultSpecifier' || n.type === 'ImportNamespaceSpecifier') declared.add(n.local.name);
  });
  // references: identifiers that are not property names / keys / labels
  const seen = new Set();
  walk.fullAncestor(ast, (n, _s, anc) => {
    if (n.type !== 'Identifier') return;
    const parent = anc[anc.length - 2];
    if (parent) {
      if (parent.type === 'MemberExpression' && parent.property === n && !parent.computed) return;
      if ((parent.type === 'Property' || parent.type === 'MethodDefinition' || parent.type === 'PropertyDefinition') && parent.key === n && !parent.computed) { if (!(parent.type === 'Property' && parent.shorthand)) return; }
      if (parent.type === 'LabeledStatement' || parent.type === 'BreakStatement' || parent.type === 'ContinueStatement') return;
      if (parent.type === 'MetaProperty') return;
    }
    if (declared.has(n.name) || GLOBALS.has(n.name)) return;
    const k = n.name + ':' + n.loc.start.line; if (seen.has(k)) return; seen.add(k);
    console.log(`${file}:${n.loc.start.line}: undefined name ${n.name}`); bad++;
  });
}
console.log(bad ? `${bad} problem(s)` : 'js: done, no undefined names');
process.exit(bad ? 1 : 0);
