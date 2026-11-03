import {
  type AuthedClientInfo,
  type HostInfo,
  MsgType,
  ServerCloseCodeAndReason,
  type SessionClientLeftMsg,
} from "@shellular/protocol";
import { nanoid } from "nanoid";
import type { WebSocket } from "ws";

export interface ClientInfoWithWebSocket {
  ws: WebSocket;
  info: AuthedClientInfo;
}

export type SocketRole = "host" | "client";

type SocketInfo = {
  session: Session;
} & ({ role: "host" } | { role: "client"; clientId: string });

/**
 * Dynamic CLI update status, re-checked by the host on each client approval.
 * Kept off `hostInfo` (which is stable host identity) because it changes over a
 * long-lived session as new versions are published.
 */
interface SessionUpdateInfo {
  updateAvailable?: boolean;
  latestCliVersion?: string;
}

export interface Session {
  id: string;
  hostId: string;
  host: WebSocket;
  hostInfo: HostInfo;
  updateInfo: SessionUpdateInfo;
  clients: Map<string, ClientInfoWithWebSocket>;
}

type ConnectionTracker = {
  hosts: Set<string>;
  clients: Set<string>;
};

const sessions = new Map<string, Session>();
const sessionsByHostId = new Map<string, Session>();
const socketToSession = new WeakMap<WebSocket, SocketInfo>();
const connections: ConnectionTracker = {
  hosts: new Set(),
  clients: new Set(),
};

export function createSession(
  hostId: string,
  host: WebSocket,
  hostInfo: HostInfo,
): Session {
  const session: Session = {
    id: nanoid(8),
    hostId,
    host,
    hostInfo,
    updateInfo: {},
    clients: new Map(),
  };
  sessions.set(session.id, session);
  sessionsByHostId.set(hostId, session);
  connections.hosts.add(hostId);
  socketToSession.set(host, { session, role: "host" });
  return session;
}

export function joinSession(
  sessionId: string,
  clientWs: WebSocket,
  clientInfo: AuthedClientInfo,
): Session | null {
  const session = sessions.get(sessionId);
  if (!session?.host) {
    return null;
  }

  const clientInfoWithWs: ClientInfoWithWebSocket = {
    ws: clientWs,
    info: clientInfo,
  };

  const existingClient = session.clients.get(clientInfo.clientId);
  if (existingClient && existingClient.ws !== clientWs) {
    socketToSession.delete(existingClient.ws);
    const { code, reason } = ServerCloseCodeAndReason.CLIENT_REPLACED;
    existingClient.ws.close(code, reason);
  }

  session.clients.set(clientInfo.clientId, clientInfoWithWs);
  socketToSession.set(clientWs, {
    session,
    role: "client",
    clientId: clientInfo.clientId,
  });
  return session;
}

/**
 * Admit a client into the presence set — the point at which it counts as
 * "connected" for `/stats` and analytics.
 *
 * Deliberately separate from `joinSession`: joining only wires up routing state,
 * and the socket can still be rejected afterwards (host denied it, or another socket
 * took this clientId) before the `session:joined` handshake is sent. Presence is
 * recorded only once that handshake actually completes, so relay-local state,
 * central's `/stats`, and the analytics event all agree on what "connected" means.
 *
 * Returns false if the socket is no longer the session's live socket for this
 * clientId, meaning the caller must reject it rather than complete the handshake.
 */
export function markClientConnected(ws: WebSocket): boolean {
  const entry = socketToSession.get(ws);
  if (entry?.role !== "client") {
    return false;
  }

  const clientInfo = entry.session.clients.get(entry.clientId);
  if (!clientInfo || clientInfo.ws !== ws) {
    return false;
  }

  connections.clients.add(entry.clientId);
  return true;
}

export function removeClient(sessionId: string, clientId: string): void {
  const session = sessions.get(sessionId);
  if (!session) {
    return;
  }

  const clientInfo = session.clients.get(clientId);
  if (!clientInfo) {
    return;
  }

  session.clients.delete(clientId);
  socketToSession.delete(clientInfo.ws);
  connections.clients.delete(clientId);
}

export function getActiveSessionForHost(hostId: string): Session | null {
  return sessionsByHostId.get(hostId) ?? null;
}

/** All currently-connected host sessions, for periodic sweeps (e.g. analytics). */
export function getActiveHostSessions(): Session[] {
  return [...sessionsByHostId.values()];
}

export function getSessionStats() {
  return {
    hosts: connections.hosts.size,
    clients: connections.clients.size,
  };
}

/**
 * Snapshot of everyone currently connected to THIS relay, for the presence
 * `hello` to central. Central rebuilds its (in-memory) registry from this on every
 * (re)connect — so a central restart, which wipes the registry, is repaired the
 * moment each relay's presence socket reconnects, without waiting for hosts/clients
 * to churn and re-report themselves individually.
 */
export function getPresenceSnapshot(): {
  hostIds: string[];
  clientIds: string[];
} {
  return {
    hostIds: [...connections.hosts],
    clientIds: [...connections.clients],
  };
}

export function getSessionForSocket(ws: WebSocket) {
  return socketToSession.get(ws) ?? null;
}

/**
 * What `removeSocket` actually tore down, so the caller can report the matching
 * presence-offline events to central. Empty fields mean "nothing to report" —
 * either the socket was already gone (double teardown) or it was superseded by a
 * newer connection for the same id.
 */
export interface RemovedSocketsResult {
  /** The host whose session ended, if this was a host socket. */
  hostId?: string;
  /**
   * Clients that went offline: the client itself for a client socket, or the
   * whole cascade of attached clients when a host socket dropped.
   */
  clientIds: string[];
}

export function removeSocket(ws: WebSocket): RemovedSocketsResult {
  const removed: RemovedSocketsResult = { clientIds: [] };

  const entry = socketToSession.get(ws);
  if (!entry) {
    // Already torn down (e.g. `error` fired then `close`, or the keepalive sweep
    // ran first). Report nothing so presence isn't double-reported.
    return removed;
  }

  // remove this socket from the session map
  socketToSession.delete(ws);

  if (entry.role === "host") {
    connections.hosts.delete(entry.session.hostId);
    removed.hostId = entry.session.hostId;

    // Close all WS clients that with host disconnected code
    for (const [, clientInfo] of entry.session.clients) {
      const { code, reason } = ServerCloseCodeAndReason.HOST_DISCONNECTED;
      clientInfo.ws.close(code, reason);
      socketToSession.delete(clientInfo.ws); // remove this client ws from the session map
      if (connections.clients.delete(clientInfo.info.clientId)) {
        removed.clientIds.push(clientInfo.info.clientId);
      }
    }
    entry.session.clients.clear();
    sessions.delete(entry.session.id);
    sessionsByHostId.delete(entry.session.hostId);
  } else if (entry.role === "client") {
    // Client disconnected
    const clientInfo = entry.session.clients.get(entry.clientId);
    if (clientInfo && clientInfo.ws === ws) {
      entry.session.clients.delete(entry.clientId);
      const wasConnected = connections.clients.delete(entry.clientId);
      if (wasConnected) {
        removed.clientIds.push(entry.clientId);
      }

      // Notify host/CLI that client disconnected
      const respMsg: SessionClientLeftMsg = {
        type: MsgType.SESSION_CLIENT_LEFT,
        data: { clientId: entry.clientId },
      };
      entry.session.host.send(
        JSON.stringify({
          id: `server_${nanoid(8)}`,
          ...respMsg,
        }),
      );
    }
  }

  return removed;
}
