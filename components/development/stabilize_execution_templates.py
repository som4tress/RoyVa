from pathlib import Path
h=Path.home();p=h/'.config/opencode/lib/execution-templates.mjs';s=p.read_text().replace(" if(!code||!validRecipe(recipe))return false;", " if(!code||!validRecipe(recipe))return false;\n recipe={...recipe,args:{...recipe.args}};delete recipe.query;")
s=s.replace("return d.version===1&&Array.isArray(d.templates)?d:{version:1,templates:[]}","return d.version===1&&Array.isArray(d.templates)?{...d,templates:d.templates.filter(t=>t&&typeof t.key==='string'&&typeof t.query==='string'&&t.recipe)}:{version:1,templates:[]}")
p.write_text(s)
p=h/'.config/opencode/mcp/ha_template_runner.py';s=p.read_text().replace('import json,sys,re,os,datetime as dt,urllib.request,difflib,time','import json,sys,re,datetime as dt,urllib.request,time')
s=s.replace('tonight|later|minutes?', 'tonight|later|briefly|temporarily|restore|revert|minutes?')
s=s.replace('power|watt|who|how|when|since)', 'power|watt|who|how|when|since|yesterday|ago|historical|history|past|week|month|hours|minutes)')
s=s.replace("  if data.get('date')!=expected:raise ValueError('History date mismatch.')", "  if data.get('date')!=expected:raise ValueError('History date mismatch.')\n  if re.search(r'\\b(today|yesterday)\\b',q,re.I):\n   recipe['datePolicy']='yesterday' if re.search(r'\\byesterday\\b',q,re.I) else 'today'\n   recipe['args'].pop('date',None)")
p.write_text(s)
