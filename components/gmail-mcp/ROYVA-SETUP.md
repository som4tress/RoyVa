> Inactive prepared alternative. RoyVa uses `gmail-active`; these are setup/recovery notes, not an instruction to replace the working connection.

# RoyVa Gmail MCP setup

Upstream: https://github.com/vaughngit/gmail-mcp-server
Revision: 361c976198ca5628769c54070a14da162c4195a1
Runtime: /home/somdutta/.local/share/royva-gmail-mcp
Node: /home/somdutta/.nvm/versions/node/v24.22.1/bin/node

Local changes: updated SDK/Google APIs/open dependencies; Desktop OAuth loopback redirect on127.0.0.1:3000, listener before browser launch, PKCE/S256, CSRF state checking,15-minute sign-in timeout, fixed error output and private token file permissions. npm audit reported0vulnerabilities at setup; this is not a complete source-security audit.

Credentials are outside this repository: ~/.gmail-mcp/gcp-oauth.keys.json and credentials.json, directory0700/files0600. Never copy them into Git. Gmail writes/drafts/label changes require OpenCode permission approval.

Mac sign-in: run `ssh -N -L 3000:127.0.0.1:3000 somdutta@<linux-host>`, leave it open, then open http://127.0.0.1:3000/ on the Mac. OAuth process expires after15minutes. Restart using `GMAIL_OPEN_BROWSER=false /home/somdutta/.nvm/versions/node/v24.22.1/bin/node /home/somdutta/.local/share/royva-gmail-mcp/dist/auth.js` if expired. No password or Google authorization code should be pasted into chat.

After authorization, verify the account through a read-only MCP call, then enable the prepared gmail MCP config entry by removing disabled:true. Keep the live and public configuration mirrors synchronized and capture deployed sources.
