# Gmail sign-in relay page

`index.html` is a static page that only displays the sign-in code Google puts in the address bar, so a person can paste it back to their RoyVa
(the server is headless and cannot receive Google's redirect itself). It makes no network calls and stores nothing.

Publish (once per install, or share one): put `index.html` in a **public** repo, enable GitHub Pages, and use the page URL (with trailing slash) as the
authorized redirect URI of a Google **Web application** OAuth client. Save that client's JSON at `~/.royva/gmail-client.json` (or set `ROYVA_GMAIL_CLIENT`).
The page cannot do anything with the code: it is useless without the PKCE verifier that stays on your server.

Enroll a person: `scripts/royva-gmail start <name> [--manage]` -> open the link, sign in, paste the code: `scripts/royva-gmail finish '<code>'`
(read-only by default; `--manage` also allows trash/archive/label). Then restart OpenCode and set `"mail": "<name>"` on that user in `users.json`.

## Google Drive

The same client and relay page serve Drive. Enable the **Google Drive API** in the Google Cloud project and add the read-only scope
`https://www.googleapis.com/auth/drive.readonly` to the consent screen. A person connects with `/connect-drive` in Telegram (and removes it with
`/disconnect-drive`); the token is stored separately from Gmail (`runtime/gateway/drive/`). The Google app (project `<google-cloud-project-id>`) is **In production** (Audience page, checked 2026-11-22), so there is no 7-day token expiry and no test-user list; each person sees Google's
"unverified app" screen once (Advanced, then Go to app). Unverified apps are capped at 100 people over the lifetime of the project (2 used so far). Because `drive.readonly` and the
Gmail scopes are restricted, do not submit the app for verification; staying unverified is fine for a household.
