# Gmail sign-in relay page

`index.html` is a static page that only displays the sign-in code Google puts in the address bar, so a person can paste it back to their RoyVa
(the server is headless and cannot receive Google's redirect itself). It makes no network calls and stores nothing.

Publish (once per install, or share one): put `index.html` in a **public** repo, enable GitHub Pages, and use the page URL (with trailing slash) as the
authorized redirect URI of a Google **Web application** OAuth client. Save that client's JSON at `~/.royva/gmail-client.json` (or set `ROYVA_GMAIL_CLIENT`).
The page cannot do anything with the code: it is useless without the PKCE verifier that stays on your server.

Enroll a person: `scripts/royva-gmail start <name> [--manage]` -> open the link, sign in, paste the code: `scripts/royva-gmail finish '<code>'`
(read-only by default; `--manage` also allows trash/archive/label). Then restart OpenCode and set `"mail": "<name>"` on that user in `users.json`.
