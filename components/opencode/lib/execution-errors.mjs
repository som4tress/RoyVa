export function formatExecutionError(error,{toolActivity=false}={}){
 const text=typeof error==='string'?error:JSON.stringify(error);
 if(/deadline|time.?out|time budget|"status"\s*:\s*504|budget_or_upstream/i.test(text))return 'This request timed out before I could confirm completion.'+(toolActivity?' Some tool calls may have run; I have not replayed them.':' No completed action was confirmed.');
 if(/ECONNRESET|ECONNREFUSED|socket|fetch failed/i.test(text))return 'The connection to OpenCode or its model was interrupted. Completion is unconfirmed.';
 return 'OpenCode could not finish this request. '+text.slice(0,350);
}
