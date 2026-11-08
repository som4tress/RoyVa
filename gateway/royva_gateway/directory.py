"""Who may use RoyVa: owner, invited members, invite codes, join approvals, and per-person Gmail connection.

One writer: the gateway. The bridge and the CLI call it over HTTP; nothing else edits users.json.

users.json   "<channel>:<id>" -> {person, role: owner|member, scopes: [...], mail?: <account>, expected_gmail?: str, joined: ts}  (+ "_policy")
invites.json code -> {name, expected_gmail, by, expires}                    single use, 24 h
joins.json   "<channel>:<id>" -> {name, expected_gmail, display, requested}   waiting for the owner's decision

Defaults are least privilege: an approved member gets no private scopes (no Gmail); connecting their own mailbox grants them "email" for THEIR mailbox only.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Callable

from .gmail_enroll import PERSON_RE, RESERVED, EnrollError, Enroller

INVITE_TTL_S = 24 * 3600
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"            # no 0/O/1/I/L: easy to read out loud
CODE_RE = re.compile(r"^[A-Z0-9]{4}-[A-Z0-9]{4}$")
MAX_FAILS, FAIL_WINDOW_S = 5, 600
GMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class DirectoryError(Exception):
    """Message is safe to show to the person who triggered it."""


class Directory:
    def __init__(self, users_file: Path, state_dir: Path, enroller: Enroller | None = None, opencode_config: Path | None = None,
                 now: Callable[[], float] = time.time):
        self.users_file = Path(users_file)
        self.dir = Path(state_dir)
        self.enroller = enroller or Enroller(self.dir)
        self.opencode_config = opencode_config
        self.now = now
        self._fails: dict[str, list[float]] = {}

    # ---- storage -----------------------------------------------------------------------------------------------------
    def _read(self, path: Path, default):
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return default

    def _write(self, path: Path, obj) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=1)
        os.replace(tmp, path)

    def users(self) -> dict:
        return self._read(self.users_file, {})

    def _invites(self) -> dict:
        return {k: v for k, v in self._read(self.dir / "invites.json", {}).items() if v.get("expires", 0) > self.now()}

    def _joins(self) -> dict:
        return self._read(self.dir / "joins.json", {})

    # ---- roles -------------------------------------------------------------------------------------------------------
    def is_owner(self, user: str) -> bool:
        u = self.users().get(user) or {}
        return u.get("role") == "owner" or (u.get("role") is None and "*" in u.get("scopes", []))

    def _need_owner(self, user: str) -> None:
        if not self.is_owner(user):
            raise DirectoryError("Only the owner can do that.")

    def is_active(self, user: str) -> bool:
        return user in self.users() and not user.startswith("_")

    def active_ids(self, channel: str = "telegram") -> list[str]:
        """Channel ids that may talk to RoyVa right now (the bridge uses this as its live allowlist)."""
        return sorted(k.split(":", 1)[1] for k in self.users() if k.startswith(channel + ":"))

    def owner_ids(self, channel: str = "telegram") -> list[str]:
        return sorted(k.split(":", 1)[1] for k in self.users() if k.startswith(channel + ":") and self.is_owner(k))

    def name_of(self, user: str) -> str | None:
        return (self.users().get(user) or {}).get("person") or None

    # ---- invite / join / decide -------------------------------------------------------------------------------------
    def invite(self, owner: str, name: str, expected_gmail: str | None = None) -> dict:
        self._need_owner(owner)
        name = (name or "").strip().lower()
        if not PERSON_RE.match(name) or name in RESERVED:
            raise DirectoryError("Use a short name: lowercase letters, digits or '-' (for example: alice).")
        if any(u.get("person") == name for u in self.users().values()) or any(j["name"] == name for j in self._joins().values()):
            raise DirectoryError(f"'{name}' is already enrolled or waiting for approval.")
        if expected_gmail is not None and not GMAIL_RE.match(expected_gmail.strip()):
            raise DirectoryError("That Gmail address does not look right.")
        invites = {k: v for k, v in self._invites().items() if v["name"] != name}
        raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        code = f"{raw[:4]}-{raw[4:]}"
        invites[code] = {"name": name, "expected_gmail": (expected_gmail or "").strip().lower() or None, "by": owner,
                         "expires": self.now() + INVITE_TTL_S}
        self._write(self.dir / "invites.json", invites)
        return {"code": code, "name": name, "expires_in_hours": INVITE_TTL_S // 3600}

    def _rate_limited(self, user: str) -> bool:
        recent = [t for t in self._fails.get(user, []) if t > self.now() - FAIL_WINDOW_S]
        self._fails[user] = recent
        return len(recent) >= MAX_FAILS

    def join(self, user: str, display: str, code: str) -> dict:
        """A stranger presents an invite code. Nothing is granted: the request waits for the owner. Errors never say which part was wrong."""
        if user in self.users():
            raise DirectoryError("You are already enrolled.")
        if self._rate_limited(user):
            raise DirectoryError("Too many wrong codes. Try again in a few minutes.")
        code = (code or "").strip().upper()
        inv = self._invites().get(code) if CODE_RE.match(code) else None
        if inv is None:
            self._fails.setdefault(user, []).append(self.now())
            raise DirectoryError("That code is not valid (it may have expired or been used). Ask the owner for a new one.")
        invites = self._invites()
        invites.pop(code)                                              # single use, consumed even if the owner later declines
        self._write(self.dir / "invites.json", invites)
        joins = self._joins()
        joins[user] = {"name": inv["name"], "expected_gmail": inv["expected_gmail"], "display": (display or "")[:60], "requested": int(self.now())}
        self._write(self.dir / "joins.json", joins)
        return {"name": inv["name"], "display": joins[user]["display"]}

    def pending(self, owner: str) -> list[dict]:
        self._need_owner(owner)
        return [{"user": u, **j} for u, j in self._joins().items()]

    def decide(self, owner: str, name: str, approve: bool) -> dict:
        self._need_owner(owner)
        joins = self._joins()
        user = next((u for u, j in joins.items() if j["name"] == (name or "").strip().lower()), None)
        if user is None:
            raise DirectoryError(f"No one named '{name}' is waiting.")
        j = joins.pop(user)
        self._write(self.dir / "joins.json", joins)
        if approve:
            users = self.users()
            users[user] = {"person": j["name"], "role": "member", "scopes": [], "expected_gmail": j["expected_gmail"], "joined": int(self.now())}
            self._write(self.users_file, users)
        return {"user": user, "name": j["name"], "approved": approve}

    # ---- people / revoke ---------------------------------------------------------------------------------------------
    def people(self, owner: str) -> list[dict]:
        self._need_owner(owner)
        accts = self.enroller.accounts()
        out = []
        for key, u in self.users().items():
            if key.startswith("_"):
                continue
            mail = u.get("mail")
            out.append({"name": u.get("person") or key, "role": u.get("role") or ("owner" if "*" in u.get("scopes", []) else "member"),
                        "mail": "default" if mail == "default" else (accts.get(mail, {}).get("mode") if mail in accts else None)})
        out += [{"name": j["name"], "role": "waiting", "mail": None} for j in self._joins().values()]
        return out

    def revoke(self, owner: str, name: str) -> dict:
        self._need_owner(owner)
        name = (name or "").strip().lower()
        users = self.users()
        user = next((k for k, u in users.items() if not k.startswith("_") and u.get("person") == name), None)
        if user is None:
            raise DirectoryError(f"No one named '{name}'.")
        if self.is_owner(user):
            raise DirectoryError("The owner cannot be removed.")
        users.pop(user)
        self._write(self.users_file, users)
        had_mail = self.enroller.revoke(name)
        self._sync()
        invites = {k: v for k, v in self._invites().items() if v["name"] != name}
        self._write(self.dir / "invites.json", invites)
        return {"user": user, "name": name, "mailbox_removed": had_mail}

    # ---- Gmail connection for the member themself -------------------------------------------------------------------
    def _sync(self) -> None:
        if self.opencode_config:
            self.enroller.sync_opencode_config(self.opencode_config)

    def gmail_start(self, user: str, manage: bool = False) -> str:
        name = self.name_of(user)
        if not name or not self.is_active(user):
            raise DirectoryError("You are not enrolled.")
        if (self.users().get(user) or {}).get("mail") == "default":
            raise DirectoryError("Your mailbox is already connected.")
        try:
            return self.enroller.start(name, manage=manage)
        except EnrollError as e:
            raise DirectoryError(str(e)) from None

    def looks_like_signin(self, text: str) -> bool:
        """True for a pasted redirect address or a relay-page code: the bridge sends these here and never to the model."""
        t = (text or "").strip()
        return bool(re.search(r"[?&]code=", t) and "state=" in t) or bool(re.match(r"^[0-9a-f]{32}\.\S+$", t))

    def gmail_finish(self, user: str, pasted: str) -> dict:
        name = self.name_of(user)
        if not name or not self.is_active(user):
            raise DirectoryError("You are not enrolled.")
        try:
            r = self.enroller.finish(pasted, person=name)
        except EnrollError as e:
            raise DirectoryError(str(e)) from None
        users = self.users()
        want = (users[user].get("expected_gmail") or "").lower()
        if want and r["email"].lower() != want:
            self.enroller.revoke(name)                                  # wrong mailbox: undo everything
            self._sync()
            raise DirectoryError("That Gmail account is not the one you were invited with. Nothing was connected.")
        u = users[user]
        u["mail"] = name
        u["scopes"] = sorted(set(u.get("scopes", [])) | {"gmail"})
        self._write(self.users_file, users)
        self._sync()
        return {"name": name, "email": r["email"], "mode": r["mode"], "needs_restart": True, "owners": self.owner_ids()}

    def gmail_stop(self, user: str) -> dict:
        """A member disconnects their own Gmail: token deleted and revoked at Google, servers removed, Gmail scope dropped."""
        name = self.name_of(user)
        if not name or not self.is_active(user):
            raise DirectoryError("You are not enrolled.")
        users = self.users()
        if users[user].get("mail") == "default":
            raise DirectoryError("That is the owner's original mailbox; it cannot be disconnected from chat.")
        had = self.enroller.revoke(name)
        users[user].pop("mail", None)
        users[user]["scopes"] = [s for s in users[user].get("scopes", []) if s != "gmail"]
        self._write(self.users_file, users)
        self._sync()
        return {"name": name, "had_connection": had, "needs_restart": had}
