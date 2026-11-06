#!/usr/bin/env node

import { createServer } from "http";
import { randomBytes } from "crypto";
import { Auth } from "googleapis";
import { URL } from "url";
import { createOAuth2Client, saveCredentials, SCOPES } from "./oauth.js";

const PORT = 3000;

async function authenticate(): Promise<void> {
  const redirectUri = `http://127.0.0.1:${PORT}/oauth2callback`;
  const oauth2Client = createOAuth2Client(redirectUri);
  const state = randomBytes(32).toString("hex");
  const { codeVerifier, codeChallenge } = await oauth2Client.generateCodeVerifierAsync();

  // Generate the auth URL
  const authUrl = oauth2Client.generateAuthUrl({
    access_type: "offline",
    state,
    code_challenge: codeChallenge,
    code_challenge_method: Auth.CodeChallengeMethod.S256,
    scope: SCOPES,
    prompt: "consent", // Force consent to ensure we get a refresh token
  });

  console.log("\n=== Gmail MCP Authentication ===\n");
  console.log("Opening browser for authentication...");
  console.log("\nIf the browser doesn't open, visit this URL manually:\n");
  console.log(authUrl);
  console.log("\n");

  // Start local server to receive the callback
  return new Promise((resolve, reject) => {
    const server = createServer(async (req, res) => {
      try {
        const url = new URL(req.url!, `http://localhost:${PORT}`);
        
        if (url.pathname === "/") {
          res.writeHead(302, { Location: authUrl, "Cache-Control": "no-store" });
          res.end();
          return;
        }
        if (url.pathname === "/oauth2callback") {
          if (req.method !== "GET" || url.searchParams.get("state") !== state) {
            res.writeHead(400, { "Content-Type": "text/plain" });
            res.end("Invalid authentication state. Restart sign-in from the original link.");
            return;
          }
          const code = url.searchParams.get("code");
          const error = url.searchParams.get("error");

          if (error) {
            res.writeHead(400, { "Content-Type": "text/html" });
            res.end("Authentication was declined or failed.");
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
          const { tokens } = await oauth2Client.getToken({ code, codeVerifier, redirect_uri: redirectUri });

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

    const timeout = setTimeout(() => { server.close(); reject(new Error("Sign-in expired after 15 minutes.")); }, 15 * 60 * 1000);
    server.on("close", () => clearTimeout(timeout));
    server.listen(PORT, "127.0.0.1", () => {
      console.log(`Waiting for authentication callback on port ${PORT}...`);
      if (process.env.GMAIL_OPEN_BROWSER !== "false") {
        void import("open").then(module => module.default(`http://127.0.0.1:${PORT}/`))
          .catch(() => console.log("Open http://127.0.0.1:3000/ in your browser to continue."));
      }
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
