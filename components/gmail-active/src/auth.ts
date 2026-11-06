#!/usr/bin/env node

import { createServer } from "http";
import { URL } from "url";
import { createOAuth2Client, saveCredentials, SCOPES } from "./oauth.js";

const PORT = 3000;

async function authenticate(): Promise<void> {
  const oauth2Client = createOAuth2Client();

  // Generate the auth URL
  const authUrl = oauth2Client.generateAuthUrl({
    access_type: "offline",
    scope: SCOPES,
    prompt: "consent", // Force consent to ensure we get a refresh token
  });

  console.log("\n=== Gmail MCP Authentication ===\n");
  console.log("Opening browser for authentication...");
  console.log("\nIf the browser doesn't open, visit this URL manually:\n");
  console.log(authUrl);
  console.log("\n");

  // Open browser
  const open = await import("open").catch(() => null);
  if (open) {
    await open.default(authUrl);
  }

  // Start local server to receive the callback
  return new Promise((resolve, reject) => {
    const server = createServer(async (req, res) => {
      try {
        const url = new URL(req.url!, `http://localhost:${PORT}`);
        
        if (url.pathname === "/oauth2callback") {
          const code = url.searchParams.get("code");
          const error = url.searchParams.get("error");

          if (error) {
            res.writeHead(400, { "Content-Type": "text/html" });
            res.end(`<html><body><h1>Authentication Failed</h1><p>${error}</p></body></html>`);
            server.close();
            reject(new Error(`Authentication failed: ${error}`));
            return;
          }

          if (!code) {
            res.writeHead(400, { "Content-Type": "text/html" });
            res.end("<html><body><h1>No authorization code received</h1></body></html>");
            server.close();
            reject(new Error("No authorization code received"));
            return;
          }

          // Exchange the code for tokens
          const { tokens } = await oauth2Client.getToken(code);

          if (!tokens.refresh_token) {
            console.warn("\nWarning: No refresh token received. You may need to revoke access and re-authenticate.");
          }

          // Save credentials
          saveCredentials({
            access_token: tokens.access_token!,
            refresh_token: tokens.refresh_token!,
            scope: tokens.scope!,
            token_type: tokens.token_type!,
            expiry_date: tokens.expiry_date!,
          });

          res.writeHead(200, { "Content-Type": "text/html" });
          res.end(`
            <html>
              <head><title>Gmail MCP - Authentication Successful</title></head>
              <body style="font-family: system-ui; padding: 40px; text-align: center;">
                <h1 style="color: #22c55e;">Authentication Successful!</h1>
                <p>You can close this window and return to your terminal.</p>
              </body>
            </html>
          `);

          console.log("\n✓ Authentication successful!");
          console.log("  Credentials saved. You can now use the Gmail MCP server.\n");

          server.close();
          resolve();
        } else {
          res.writeHead(404);
          res.end("Not found");
        }
      } catch (err) {
        console.error("Error during authentication:", err);
        res.writeHead(500);
        res.end("Internal server error");
        server.close();
        reject(err);
      }
    });

    server.listen(PORT, () => {
      console.log(`Waiting for authentication callback on port ${PORT}...`);
    });

    server.on("error", (err: NodeJS.ErrnoException) => {
      if (err.code === "EADDRINUSE") {
        console.error(`\nError: Port ${PORT} is already in use.`);
        console.error("Please stop any process using this port and try again.\n");
        reject(err);
      } else {
        reject(err);
      }
    });
  });
}

// Run if called directly
authenticate().catch((err) => {
  console.error("Authentication failed:", err.message);
  process.exit(1);
});
