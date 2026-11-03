const callbacks=new Set();
export function onDiscard(fn){callbacks.add(fn);return ()=>callbacks.delete(fn);}
export async function forgetSessionMemory(id){for(const fn of callbacks)await fn(id);}
