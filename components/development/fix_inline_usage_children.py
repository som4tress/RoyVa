from pathlib import Path
p=Path.home()/'.config/opencode/scripts/openrouter-usage';s=p.read_text()
s=s.replace("   parts=con.execute(\"select data from session_part", "   parts=list(con.execute(\"select data from session_part")
s=s.replace("[parent,*message_ids])\n   for part in parts:", "[parent,*message_ids]))\n   inline=con.execute(\"select data from session_message where session_id=? and id in (\"+','.join('?' for _ in message_ids)+')',[parent,*message_ids])\n   for row in inline:\n    parts.extend((json.dumps(part),) for part in json.loads(row[0]).get('content',[]) if part.get('type')=='tool')\n   for part in parts:")
p.write_text(s)
p=Path('/tmp/test_scoped_usage.py');s=p.read_text().replace("c.commit()", "c.execute(\"update session_message set data=json_set(data,'$.content',json(?)) where id='a'\",(json.dumps([part]),));c.execute('delete from session_part');c.commit()")
p.write_text(s)
