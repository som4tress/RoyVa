"""Per-person Gmail enrollment (OAuth authorization-code flow with PKCE).

Why this shape: the server is headless. It never opens a browser or listens for the redirect. `start()` returns a Google link; the person signs in
on any device and Google redirects to a static relay page (see docs/oauth-relay/) that only DISPLAYS the code; the person pastes it back and
`finish()` exchanges it for tokens over HTTPS. PKCE makes a leaked code useless without the verifier that stays here.

Files (all under state_dir, mode 0600, never committed):
  gmail/<person>.credentials.json   what the Gmail MCP servers read (access_token, refresh_token, scope, token_type, expiry_date)
  gmail/<person>.keys.json          the OAuth client that ISSUED that token ({"web": {...}}); a refresh token only works with its own client
  gmail/accounts.json               person -> {email, client_id, scope, created}
  gmail/pending.json                state -> {person, verifier, expires}  (10 minutes)
Scopes: gmail.readonly by default; gmail.modify (read, label, trash) only when 'manage' is asked for. Never send or compose.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

SCOPE_READ = "https://www.googleapis.com/auth/gmail.readonly"
SCOPE_MANAGE = "https://www.googleapis.com/auth/gmail.modify"
SCOPE = SCOPE_MANAGE                                 # kept for older imports
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
PENDING_TTL_S = 600
PERSON_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")        # no underscore: server names are gmail-u-<person>_<tool> and the first underscore ends the name
RESERVED = {"default"}                       # "default" = the original account. Per-person servers are gmail-u-<name> / gmail-tidy-u-<name>: the fixed "-u-" marker cannot collide with a base server name


class EnrollError(Exception):
    """Raised with a message that is safe to show to the user."""


def _default_http(method: str, url: str, data: dict | None = None, headers: dict | None = None) -> dict:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            j = json.loads(e.read())
            detail = j.get("error_description") or j.get("error")
        except Exception:                                    # noqa: BLE001
            detail = None
        raise EnrollError(f"Google refused the request ({e.code}){': ' + str(detail) if detail else ''}") from None
    except OSError as e:
        raise EnrollError(f"could not reach Google: {e}") from None


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class Enroller:
    def __init__(self, state_dir: Path, client_file: Path | str | None = None, http: Callable = _default_http,
                 now: Callable[[], float] = time.time):
        self.dir = Path(state_dir) / "gmail"
        # Google OAuth client file: explicit arg > $ROYVA_GMAIL_CLIENT > ~/.royva/gmail-client.json > the Gmail MCP's own keys file (works out of the box).
        default = Path.home() / ".royva" / "gmail-client.json"
        legacy = Path.home() / ".gmail-mcp" / "gcp-oauth.keys.json"
        self.client_file = Path(client_file or os.environ.get("ROYVA_GMAIL_CLIENT") or (default if default.exists() or not legacy.exists() else legacy))
        self.http, self.now = http, now

    # ---- small file helpers -------------------------------------------------------------------------------------------
    def _write(self, path: Path, obj) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.dir, 0o700)
        tmp = path.with_suffix(path.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=1)
        os.replace(tmp, path)

    def _read(self, path: Path, default):
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return default

    def client(self) -> dict:
        """The Google OAuth client (Web application type): client_id, client_secret, redirect_uris[0] = the relay page."""
        raw = self._read(self.client_file, None)
        c = (raw or {}).get("web") or (raw or {}).get("installed")
        if not c or not c.get("client_id") or not c.get("client_secret") or not c.get("redirect_uris"):
            raise EnrollError(f"Gmail OAuth client not set up: expected a Google 'Web application' client JSON at {self.client_file} "
                              "with a redirect URI (the relay page).")
        return c

    # ---- flow ---------------------------------------------------------------------------------------------------------
    def start(self, person: str, manage: bool = False) -> str:
        person = (person or "").strip().lower()
        if not PERSON_RE.match(person) or person in RESERVED:
            raise EnrollError("person must be 1-32 chars: lowercase letters, digits or '-' (not 'default').")
        c = self.client()
        pending = {k: v for k, v in self._read(self.dir / "pending.json", {}).items() if v["expires"] > self.now()}
        state, verifier = secrets.token_hex(16), _b64url(secrets.token_bytes(48))
        pending = {k: v for k, v in pending.items() if v["person"] != person}          # one open request per person
        pending[state] = {"person": person, "verifier": verifier, "manage": bool(manage), "expires": self.now() + PENDING_TTL_S}
        self._write(self.dir / "pending.json", pending)
        q = {"client_id": c["client_id"], "redirect_uri": c["redirect_uris"][0], "response_type": "code", "scope": SCOPE_MANAGE if manage else SCOPE_READ,
             "access_type": "offline", "prompt": "consent", "state": state,
             "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256"}
        return AUTH_URL + "?" + urllib.parse.urlencode(q)

    @staticmethod
    def parse_pasted(pasted: str) -> tuple[str | None, str]:
        """Accept the relay page's 'state.code' string, a full redirect URL, or a bare code. Returns (state or None, code)."""
        s = (pasted or "").replace("&amp;", "&").strip().strip("`\"'<>")
        if not s:
            raise EnrollError("nothing to read: paste the code shown on the page.")
        if "://" in s or "code=" in s:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(s).query or s.split("?", 1)[-1])
            if "code" not in q:
                raise EnrollError("that address has no sign-in code in it.")
            return (q.get("state") or [None])[0], q["code"][0]
        if "." in s and re.match(r"^[0-9a-f]{32}\.", s):
            state, code = s.split(".", 1)
            return state, code
        return None, s

    def finish(self, pasted: str, person: str | None = None) -> dict:
        """Redeem a pasted code. When `person` is given the sign-in must have been started for that same person."""
        state, code = self.parse_pasted(pasted)
        pending = {k: v for k, v in self._read(self.dir / "pending.json", {}).items()}
        live = {k: v for k, v in pending.items() if v["expires"] > self.now()}
        if state is None and person is not None:
            mine = [k for k, v in live.items() if v["person"] == person]
            state = mine[0] if len(mine) == 1 else None
        elif state is None and len(live) == 1:
            state = next(iter(live))
        if state not in pending:
            raise EnrollError("that sign-in was not started here (or already used). Ask for a new link.")
        if pending[state]["expires"] <= self.now():
            raise EnrollError("that sign-in link expired (10 minutes). Ask for a new link.")
        if person is not None and pending[state]["person"] != person:
            raise EnrollError("that sign-in was not started here (or already used). Ask for a new link.")      # same wording: reveals nothing
        rec = pending.pop(state)
        self._write(self.dir / "pending.json", pending)                                   # single use, even if the exchange fails
        c = self.client()
        tok = self.http("POST", c.get("token_uri", TOKEN_URL), {
            "code": code, "client_id": c["client_id"], "client_secret": c["client_secret"], "redirect_uri": c["redirect_uris"][0],
            "grant_type": "authorization_code", "code_verifier": rec["verifier"]})
        if not tok.get("refresh_token"):
            raise EnrollError("Google did not return a long-lived token. Remove RoyVa under myaccount.google.com/permissions and try again.")
        granted = tok.get("scope", "")
        have = granted.split()
        if SCOPE_MANAGE not in have and SCOPE_READ not in have:
            raise EnrollError("Gmail access was not granted. Tick the Gmail permission box on the Google screen and try again.")
        if rec.get("manage") and SCOPE_MANAGE not in have:
            raise EnrollError("Only read access was granted. Tick every Gmail permission box and try again.")
        mode = "manage" if SCOPE_MANAGE in have else "readonly"
        prof = self.http("GET", PROFILE_URL, None, {"authorization": f"Bearer {tok['access_token']}"})
        email = prof.get("emailAddress")
        if not email:
            raise EnrollError("signed in, but could not read the mailbox address.")
        person = rec["person"]
        self._write(self.dir / f"{person}.credentials.json", {
            "access_token": tok["access_token"], "refresh_token": tok["refresh_token"], "scope": granted,
            "token_type": tok.get("token_type", "Bearer"), "expiry_date": int((self.now() + int(tok.get("expires_in", 3600))) * 1000)})
        self._write(self.dir / f"{person}.keys.json", {"web": {k: c[k] for k in ("client_id", "client_secret", "redirect_uris") if k in c}
                                                          | {"auth_uri": AUTH_URL, "token_uri": c.get("token_uri", TOKEN_URL)}})
        accts = self._read(self.dir / "accounts.json", {})
        accts[person] = {"email": email, "client_id": c["client_id"], "scope": granted, "mode": mode, "created": int(self.now())}
        self._write(self.dir / "accounts.json", accts)
        return {"person": person, "email": email, "mode": mode}

    # ---- management --------------------------------------------------------------------------------------------------
    def accounts(self) -> dict:
        return self._read(self.dir / "accounts.json", {})

    def paths(self, person: str) -> dict | None:
        """Credential/keys paths for a connected person (what that person's Gmail MCP servers are started with), or None."""
        if person not in self.accounts():
            return None
        return {"credentials": str(self.dir / f"{person}.credentials.json"), "keys": str(self.dir / f"{person}.keys.json")}

    def revoke(self, person: str) -> bool:
        accts = self.accounts()
        if person not in accts:
            return False
        cred = self._read(self.dir / f"{person}.credentials.json", {})
        if cred.get("refresh_token"):
            try:
                self.http("POST", REVOKE_URL, {"token": cred["refresh_token"]}, {"content-type": "application/x-www-form-urlencoded"})
            except EnrollError:
                pass                                           # local removal below is what matters
        for suffix in ("credentials", "keys"):
            (self.dir / f"{person}.{suffix}.json").unlink(missing_ok=True)
        accts.pop(person)
        self._write(self.dir / "accounts.json", accts)
        return True

    # ---- OpenCode wiring ----------------------------------------------------------------------------------------------
    def sync_opencode_config(self, config_path: Path | str) -> list[str]:
        """Make the OpenCode config hold one Gmail server pair per enrolled person (cloned from the base `gmail` / `gmail-tidy` entries with that
        person's credential paths), and drop pairs of people who are gone. Returns the server names now present. OpenCode must be restarted to load them."""
        cp = Path(config_path)
        cfg = json.loads(cp.read_text())
        servers = cfg.setdefault("mcp", {}).setdefault("servers", {})
        accts = self.accounts()
        wanted: dict[str, dict] = {}
        for person in accts:
            paths = self.paths(person)
            for base in ("gmail", "gmail-tidy"):
                if base not in servers:
                    continue
                entry = json.loads(json.dumps(servers[base]))
                entry.setdefault("environment", {}).update({"GMAIL_OAUTH_KEYS_PATH": paths["keys"], "GMAIL_CREDENTIALS_PATH": paths["credentials"]})
                wanted[f"{base}-u-{person}"] = entry
        for name in list(servers):
            if re.match(r"^(gmail|gmail-tidy)-u-", name) and name not in wanted:
                del servers[name]
        servers.update(wanted)
        tmp = cp.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, indent=2) + "\n")
        os.replace(tmp, cp)
        return sorted(wanted)
