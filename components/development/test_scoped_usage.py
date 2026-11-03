import importlib.machinery,importlib.util,tempfile,sqlite3,json,pathlib
path=pathlib.Path.home()/'.config/opencode/scripts/openrouter-usage';loader=importlib.machinery.SourceFileLoader('usage_scoped',str(path));spec=importlib.util.spec_from_loader(loader.name,loader);m=importlib.util.module_from_spec(spec);loader.exec_module(m)
with tempfile.TemporaryDirectory() as tmp:
 db=pathlib.Path(tmp)/'usage.db';c=sqlite3.connect(db)
 c.executescript('create table session_message(id text,session_id text,type text,time_created integer,data text);create table session_v2(id text,parent_id text);create table session_part(message_id text,session_id text,type text,data text);')
 def add(mid,sid,cost,provider='openrouter',created=1000):
  data={'model':{'providerID':provider},'tokens':{'input':100,'output':20,'cache':{'read':50}},'cost':cost};c.execute('insert into session_message values(?,?,?,?,?)',(mid,sid,'assistant',created,json.dumps(data)))
 add('a','chat-A',.01);add('b','chat-B',99);add('old','chat-A',10,created=10);add('child-a','child-A',.003,created=1100);add('child-b','child-B',50,created=1100);add('free','chat-A',20,'opencode');add('local','chat-A',10,'evo-agent')
 c.executemany('insert into session_v2 values(?,?)',[('child-A','chat-A'),('child-B','chat-B')]);part={'tool':'subagent','state':{'metadata':{'sessionID':'child-A'}}};c.execute('insert into session_part values(?,?,?,?)',('a','chat-A','tool',json.dumps(part)));c.commit()
 t=m.collect(db,'chat-A',['a','free','local'],until_ms=2000);assert abs(t['cost']-.013)<1e-8 and t['requests']==2
 assert m.collect(db,'chat-A',['a','free','local'],until_ms=2000)==t
 assert m.collect(db,'chat-B',['b'])['cost']==99
 assert m.collect(db,'chat-A',['free','local'])['requests']==0
 assert m.format_usage(m.collect(db,'chat-A',['free','local']))==''
 assert m.collect(db,'chat-A',since_ms=1000,until_ms=2000)['cost']==.013
 print('PASS: independent concurrent sessions, exact invocation IDs, linked child usage, old-turn exclusion, repeatable stateless reads and free/local suppression.')
