// Product and assistant names come from the deployment config (scripts/lares_config.py exports them); nothing else in the bridge hardcodes a name.
export function brandFrom(env = process.env) {
  const clean = (value, fallback) => (String(value ?? '').trim() || fallback);
  const command = clean(env.LARES_COMMAND, 'roy').replace(/^\//, '').toLowerCase().replace(/[^a-z0-9_]/g, '') || 'roy';
  return {
    product: clean(env.LARES_PRODUCT, 'Lares'),
    assistant: clean(env.LARES_ASSISTANT_NAME, 'Roy'),
    command,
    // "/roy" (or the legacy "/royva" alias) switches back from Claude mode, optionally with @botname
    backPattern: new RegExp(`^\\s*\\/(?:${command}|royva)(?:@\\w+)?\\s*$`, 'i'),
  };
}
export const BRAND = brandFrom();
