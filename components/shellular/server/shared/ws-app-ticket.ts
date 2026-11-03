import {
  type AuthedClientInfo,
  AuthedClientInfoSchema,
} from "@shellular/protocol";

import { createToken, verifyToken } from "./jwt";

// The app reuses one ticket across a whole reconnect run rather than minting
// per attempt — this TTL is about avoiding needless mints, not correctness.
const APP_WEBSOCKET_TOKEN_TTL_SECONDS = 120;

export async function createAppWebSocketToken(
  clientInfo: AuthedClientInfo,
): Promise<{ token: string; ttlSeconds: number }> {
  const token = await createToken(clientInfo, APP_WEBSOCKET_TOKEN_TTL_SECONDS);
  return { token, ttlSeconds: APP_WEBSOCKET_TOKEN_TTL_SECONDS };
}

export async function verifyAppWebSocketToken(
  token: string,
): Promise<AuthedClientInfo | null> {
  return verifyToken(token, AuthedClientInfoSchema);
}
