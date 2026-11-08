"""MCP server (stdio, newline JSON-RPC): bulk Gmail tidy-up by search query, done server-side.
Tools: count_matching (read), tidy_matching and tidy_ids (write: trash | archive | mark_read | mark_unread).
Why it exists: the model must not page through hundreds of message ids by hand (it loses its place, burns tokens and loops). It gives a Gmail search
query and this server pages, counts and applies the change in chunks.
Safety: Trash only (messages stay recoverable for 30 days); there is no permanent-delete path and no send path in this file. A change needs a real
narrowing query, is capped per call and says plainly when more remain. ROYVA_DRY_RUN=1 or the flag file runtime/gateway/dry_run makes it report instead of act."""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://gmail.googleapis.com/gmail/v1/users/me"
PAGE = 500
COUNT_CAP = 25000                      # exact below this; above it the answer says at_least
DEFAULT_LIMIT, MAX_LIMIT, MAX_IDS = 2000, 10000, 5000
DRY_FLAG = Path(os.environ.get("ROYVA_DRY_RUN_FLAG", Path(__file__).resolve().parents[2] / "runtime" / "gateway" / "dry_run"))
DRY = lambda: os.environ.get("ROYVA_DRY_RUN") == "1" or DRY_FLAG.exists()      # noqa: E731
TOO_BROAD = {"", "*", "all", "in:inbox", "in:anywhere", "label:inbox", "is:unread", "is:read", "in:all", "category:primary"}
ACTIONS = {"trash": ({"addLabelIds": ["TRASH"], "removeLabelIds": ["INBOX"]}, "Moved to Trash"),
           "archive": ({"removeLabelIds": ["INBOX"]}, "Archived"),
           "mark_read": ({"removeLabelIds": ["UNREAD"]}, "Marked as read"),
           "mark_unread": ({"addLabelIds": ["UNREAD"]}, "Marked as unread")}
RO = {"readOnlyHint": True, "destructiveHint": False}
HINT = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True}


def tool(name, desc, props, required, ann):
    return {"name": name, "description": desc, "inputSchema": {"type": "object", "properties": props, "required": required, "additionalProperties": False}, "annotations": ann}


QUERY = {"type": "string", "description": "Gmail search query, e.g. from:paypal.com or from:nextdoor.com older_than:30d or subject:webinar."}
TOOLS = [
    tool("count_matching", "Count the messages matching a Gmail search query (up to 5000) and show a few examples. Use this before changing anything so you can tell the user how many.",
         {"query": QUERY}, ["query"], RO),
    tool("tidy_ids", "Apply a change to specific messages by id (use when the user means messages you already listed or read): trash (recoverable for 30 days), archive, mark_read or mark_unread. One call handles up to 5000 ids.",
         {"ids": {"type": "array", "items": {"type": "string"}, "description": "Message ids from a previous list or search."}, "action": {"type": "string", "enum": sorted(ACTIONS)}},
         ["ids", "action"], HINT),
    tool("tidy_matching", "Apply a change to EVERY message matching a Gmail search query (up to a per-call limit): trash (recoverable for 30 days, never permanent delete), archive, mark_read or mark_unread. Does the paging itself; one call is enough.",
         {"query": QUERY, "action": {"type": "string", "enum": sorted(ACTIONS)}, "limit": {"type": "integer", "description": "Max messages this call (default 2000, max 10000)."}},
         ["query", "action"], HINT),
]


class Gmail:
    """Thin Gmail REST client using the same OAuth files as the read-only Gmail server (the token needs the gmail.modify scope)."""
    def __init__(self, http=None, now=time.time):
        self._http, self._now, self._tok, self._exp = http or self._real_http, now, None, 0

    def _creds(self):
        cred = json.load(open(os.environ["GMAIL_CREDENTIALS_PATH"]))
        keys = json.load(open(os.environ["GMAIL_OAUTH_KEYS_PATH"]))
        return cred, keys.get("installed") or keys.get("web") or keys

    def token(self):
        if self._tok and self._now() < self._exp - 60:
            return self._tok
        cred, keys = self._creds()
        data = urllib.parse.urlencode({"client_id": keys["client_id"], "client_secret": keys["client_secret"], "refresh_token": cred["refresh_token"], "grant_type": "refresh_token"}).encode()
        r = self._http("POST", keys.get("token_uri", "https://oauth2.googleapis.com/token"), None, data, {"content-type": "application/x-www-form-urlencoded"})
        self._tok, self._exp = r["access_token"], self._now() + int(r.get("expires_in", 3000))
        return self._tok

    @staticmethod
    def _real_http(method, url, token, body=None, headers=None):
        h = dict(headers or {})
        if token:
            h["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=body, method=method, headers=h)
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read()
        return json.loads(raw) if raw else {}

    def call(self, method, path, params=None, body=None):
        url = API + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
        data = json.dumps(body).encode() if body is not None else None
        return self._http(method, url, self.token(), data, {"content-type": "application/json"} if data else {})

    def ids(self, query, limit):
        """Message ids matching the query (never in Trash/Spam), up to limit; second value says more exist beyond the limit."""
        out, token = [], None
        while len(out) < limit:
            p = {"q": query, "maxResults": min(PAGE, limit - len(out))}
            if token:
                p["pageToken"] = token
            r = self.call("GET", "/messages", p)
            out += [m["id"] for m in r.get("messages", [])]
            token = r.get("nextPageToken")
            if not token:
                return out, False
        return out, bool(token)

    def sample(self, ids, n=5):
        rows = []
        for i in ids[:n]:
            r = self.call("GET", f"/messages/{i}", {"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]})
            h = {x["name"]: x["value"] for x in r.get("payload", {}).get("headers", [])}
            rows.append({"from": h.get("From", "")[:60], "subject": h.get("Subject", "")[:80], "date": h.get("Date", "")[:31]})
        return rows


def _split_terms(q):
    """Top-level terms of a Gmail query, keeping quoted phrases and {...} / (...) groups whole."""
    terms, cur, depth, quote = [], "", 0, False
    for ch in q:
        if ch == '"':
            quote = not quote
        elif not quote and ch in "{(":
            depth += 1
        elif not quote and ch in "})":
            depth = max(0, depth - 1)
        if ch.isspace() and not quote and depth == 0:
            if cur:
                terms.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        terms.append(cur)
    return terms


def normalize_query(q):
    """A message has one sender (and one recipient), so several bare from:/to: terms can only mean OR. Gmail would read them as AND and
    match nothing, which makes the model retry one sender at a time (one approval each). Group them into one {a b} OR group."""
    terms = _split_terms(q)
    out, groups = [], {}
    for t in terms:
        op = t.split(":", 1)[0].lower() if ":" in t else ""
        neg = t.startswith("-")
        if op in ("from", "to") and not neg:
            groups.setdefault(op, []).append(t)
            if len(groups[op]) == 1:
                out.append(("group", op, t))
            continue
        out.append(("term", None, t))
    res = []
    for kind, op, t in out:
        if kind == "group" and len(groups[op]) > 1:
            res.append("{" + " ".join(groups[op]) + "}")
        else:
            res.append(t)
    return " ".join(res)


def _check(query):
    q = normalize_query(str(query or "").strip())
    if q.lower() in TOO_BROAD or len(q) < 3:
        return None, "That search is too broad to change in bulk. Narrow it (for example by sender, subject, label or date)."
    return q, None


def count_matching(args, gm=None):
    gm = gm or Gmail()
    q = normalize_query(str(args.get("query") or "").strip())       # counting changes nothing, so broad queries such as is:unread are allowed here
    if not q:
        return {"ok": False, "error": "give a Gmail search query to count (for example is:unread)."}
    ids, more = gm.ids(q, COUNT_CAP)
    return {"ok": True, "query": q, "count": len(ids), "at_least": more, "examples": gm.sample(ids),
            "did": f"Counted {len(ids)}{'+' if more else ''} messages matching: {q}"}


def tidy_matching(args, gm=None):
    gm = gm or Gmail()
    q, err = _check(args.get("query"))
    if err:
        return {"ok": False, "error": err}
    action = args.get("action")
    if action not in ACTIONS:
        return {"ok": False, "error": f"unknown action '{action}' (use one of: {', '.join(sorted(ACTIONS))})"}
    limit = max(1, min(int(args.get("limit") or DEFAULT_LIMIT), MAX_LIMIT))
    labels, verb = ACTIONS[action]
    search = q + (" -in:trash" if action == "trash" else "") + (" in:inbox" if action == "archive" and "in:" not in q else "")
    ids, more = gm.ids(search, limit)
    if not ids:
        return {"ok": True, "changed": 0, "remaining": False, "dry_run": DRY() or None, "did": f"No messages matched: {q}"}
    if DRY():
        return {"ok": True, "changed": 0, "would_change": len(ids), "remaining": more, "dry_run": True,
                "did": f"[DRY RUN, nothing happened] Would have {verb.lower()} {len(ids)} messages matching: {q}"}
    for i in range(0, len(ids), 1000):
        gm.call("POST", "/messages/batchModify", None, {"ids": ids[i:i + 1000], **labels})
    note = " More messages still match; run it again to continue." if more else ""
    return {"ok": True, "changed": len(ids), "remaining": more, "dry_run": None, "did": f"{verb} {len(ids)} messages matching: {q}.{note}"}


def tidy_ids(args, gm=None):
    gm = gm or Gmail()
    action = args.get("action")
    if action not in ACTIONS:
        return {"ok": False, "error": f"unknown action '{action}' (use one of: {', '.join(sorted(ACTIONS))})"}
    raw = args.get("ids")
    if not isinstance(raw, list) or not raw or any(not isinstance(i, str) or not re.fullmatch(r"[0-9a-fA-F]{6,32}", i) for i in raw):
        return {"ok": False, "error": "ids must be a non-empty list of Gmail message ids (hex strings) from an earlier list or search"}
    ids = list(dict.fromkeys(raw))[:MAX_IDS]
    labels, verb = ACTIONS[action]
    if DRY():
        return {"ok": True, "changed": 0, "would_change": len(ids), "dry_run": True, "did": f"[DRY RUN, nothing happened] Would have {verb.lower()} {len(ids)} messages"}
    for i in range(0, len(ids), 1000):
        gm.call("POST", "/messages/batchModify", None, {"ids": ids[i:i + 1000], **labels})
    skipped = len(raw) - len(set(raw)) if len(set(raw)) > MAX_IDS else 0
    return {"ok": True, "changed": len(ids), "dry_run": None, "did": f"{verb} {len(ids)} messages" + (f" ({skipped} over the {MAX_IDS} limit were not included)" if skipped else "")}


FUNCS = {"count_matching": count_matching, "tidy_matching": tidy_matching, "tidy_ids": tidy_ids}


def handle(msg):
    method, ident = msg.get("method"), msg.get("id")
    if method == "initialize":
        result = {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-03-26"), "capabilities": {"tools": {}}, "serverInfo": {"name": "gmail-tidy", "version": "1.0.0"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        p = msg.get("params", {})
        try:
            result = {"content": [{"type": "text", "text": json.dumps(FUNCS[p.get("name")](p.get("arguments", {})))}]}
        except Exception as e:                                          # noqa: BLE001
            result = {"content": [{"type": "text", "text": json.dumps({"ok": False, "error": str(e)[:300]})}], "isError": True}
    elif ident is None:
        return
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": "Method not found"}}), flush=True)
        return
    print(json.dumps({"jsonrpc": "2.0", "id": ident, "result": result}), flush=True)


if __name__ == "__main__":
    for line in sys.stdin:
        if line.strip():
            try:
                handle(json.loads(line))
            except Exception as e:                                      # noqa: BLE001
                print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)[:200]}}), flush=True)
