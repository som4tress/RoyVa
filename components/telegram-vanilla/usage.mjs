export function tokenUsage(messages) {
  return messages.filter(message => message.type === 'assistant').reduce((sum, message) => {
    const tokens = message.tokens;
    if (!tokens) return sum;
    sum.input += Number(tokens.input || 0) + Number(tokens.cache?.read || 0);
    sum.cached += Number(tokens.cache?.read || 0);
    sum.output += Number(tokens.output || 0);
    sum.reasoning += Number(tokens.reasoning || 0);
    sum.passes++;
    sum.peak = Math.max(sum.peak, Number(tokens.input || 0) + Number(tokens.cache?.read || 0));
    return sum;
  }, { input: 0, cached: 0, output: 0, reasoning: 0, passes: 0, peak: 0 });
}

export function formatUsage(usage) {
  const number = value => value.toLocaleString('en-US');
  return `Tokens (local): in ${number(usage.input)} (${number(usage.cached)} cached) · out ${number(usage.output)}${usage.reasoning ? ` · think ${number(usage.reasoning)}` : ''} · passes ${usage.passes} · peak input ${number(usage.peak)}`;
}

export async function streamingTokens(text) {
  if (!text) return 0;
  const response = await fetch('http://127.0.0.1:8000/tokenize', {
    method: 'POST', headers: { 'content-type': 'application/json', authorization: `Bearer ${process.env.VLLM_API_KEY}` },
    body: JSON.stringify({ content: text, add_special: false }), signal: AbortSignal.timeout(3000),
  });
  if (!response.ok) return null;
  return (await response.json()).tokens.length;
}
