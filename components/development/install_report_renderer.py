from pathlib import Path
h=Path.home();base=h/'.config/opencode';backup=h/'opencode-migration-backup/report-renderer';backup.mkdir(exist_ok=True)
for name in ['mcp/ha_history.py','plugins/ha-mcp-routing/index.js','lib/media-deadline-proxy.mjs']:
 p=base/name;(backup/p.name).write_text(p.read_text())
p=base/'mcp/ha_history.py';s=p.read_text().replace('from ha_device_status import TOOL as STATUS_TOOL, collect as collect_status','from ha_device_status import TOOL as STATUS_TOOL, collect as collect_status\nfrom ha_status_report import TOOL as REPORT_TOOL, collect as collect_report').replace('[TOOL,CONTEXT_TOOL,STATUS_TOOL]','[TOOL,CONTEXT_TOOL,STATUS_TOOL,REPORT_TOOL]').replace("   elif name==STATUS_TOOL['name']:","   elif name==REPORT_TOOL['name']:data=collect_report(args,read_api)\n   elif name==STATUS_TOOL['name']:");p.write_text(s)
p=base/'plugins/ha-mcp-routing/index.js';s=p.read_text();s="import {isStatusReport,REPORT_TOOL} from '../../lib/ha-reports.mjs';\n"+s
s=s.replace("   if(kind){\n", "   if(kind){\n    const reportOnly=kind==='devices'&&isStatusReport(text);\n")
s=s.replace("const requiredReady=kind==='devices'", "const requiredReady=reportOnly?catalog.some(tool=>tool.id===REPORT_TOOL):kind==='devices'")
s=s.replace('    state.requestText=text;', '    state.requestText=text;state.reportOnly=reportOnly;')
s=s.replace("    if(state.fastStatus)state.requiredTool='ha-history_get_device_status';", "    if(state.fastStatus)state.requiredTool='ha-history_get_device_status';\n    if(state.reportOnly)state.requiredTool=REPORT_TOOL;")
s=s.replace("    if(state.fastStatus)body.tools=", "    if(state.reportOnly)body.tools=(body.tools||[]).filter(t=>t.function?.name===REPORT_TOOL);\n    else if(state.fastStatus)body.tools=")
s=s.replace('body.max_tokens=state.fastStatus?384:1024;', 'body.max_tokens=state.reportOnly?256:state.fastStatus?384:1024;')
s=s.replace("    if(state.fastStatus)instruction+=", "    if(state.reportOnly)instruction+='\\nFor this read-only current status report, call get_device_status_report once with the appropriate domains and optional name/state filters. Default domains mean controllable devices, not every diagnostic sensor. Explicitly include sensor/binary_sensor domains when requested. This produces a complete formatted report automatically. No other tool calls or device actions.';\n    if(state.fastStatus&&!state.reportOnly)instruction+=")
p.write_text(s)
p=base/'lib/media-deadline-proxy.mjs';s=p.read_text();s="import {reportFromRequest,reportWire} from './ha-reports.mjs';\n"+s
needle="  const payload=cloud?Buffer.concat(chunks)"
assert needle in s
s=s.replace(needle,"""  const report=ha&&!cloud?reportFromRequest(incoming):null;
  if(report!==null){
   const wire=reportWire(incoming,report);
   res.writeHead(200,{'content-type':wire.type});res.end(wire.body);
   console.log(JSON.stringify({at:new Date().toISOString(),route:'ha-report-renderer',status:200,session:req.headers['x-media-session'],chars:report.length}));return;
  }
  const payload=cloud?Buffer.concat(chunks)""")
p.write_text(s)
print('Shared deterministic report path installed; Telegram bridge unchanged.')
