import { google, Auth } from "googleapis";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

const SCOPES = [
  "https://www.googleapis.com/auth/gmail.readonly",
  "https://www.googleapis.com/auth/gmail.send",
  "https://www.googleapis.com/auth/gmail.compose",
  "https://www.googleapis.com/auth/gmail.modify",
  "https://www.googleapis.com/auth/gmail.labels",
];

interface Credentials {
  access_token: string;
  refresh_token: string;
  scope: string;
  token_type: string;
  expiry_date: number;
}

interface OAuthKeys {
  client_id: string;
  client_secret: string;
  redirect_uris: string[];
}

/**
 * Resolves ~ to home directory and normalizes path
 */
function resolvePath(p: string): string {
  if (p.startsWith("~")) {
    return path.join(os.homedir(), p.slice(1));
  }
  return path.resolve(p);
}

/**
 * Gets the credentials file path from environment or default
 */
function getCredentialsPath(): string {
  const envPath = process.env.GMAIL_CREDENTIALS_PATH;
  if (envPath) {
    return resolvePath(envPath);
  }
  return path.join(os.homedir(), ".gmail-mcp", "credentials.json");
}

/**
 * Gets the OAuth keys file path
 */
function getOAuthKeysPath(): string {
  const envPath = process.env.GMAIL_OAUTH_KEYS_PATH;
  if (envPath) {
    return resolvePath(envPath);
  }
  return path.join(os.homedir(), ".gmail-mcp", "gcp-oauth.keys.json");
}

/**
 * Loads OAuth client keys from file
 */
function loadOAuthKeys(): OAuthKeys {
  const keysPath = getOAuthKeysPath();
  if (!fs.existsSync(keysPath)) {
    throw new Error(`OAuth keys file not found: ${keysPath}`);
  }

  const content = JSON.parse(fs.readFileSync(keysPath, "utf-8"));
  
  // Handle both web and installed app credential formats
  const keys = content.web || content.installed;
  if (!keys) {
    throw new Error("Invalid OAuth keys file format. Expected 'web' or 'installed' credentials.");
  }

  return {
    client_id: keys.client_id,
    client_secret: keys.client_secret,
    redirect_uris: keys.redirect_uris || ["http://localhost:3000/oauth2callback"],
  };
}

/**
 * Loads credentials from file - always reads fresh from disk
 */
function loadCredentials(): Credentials | null {
  const credPath = getCredentialsPath();
  if (!fs.existsSync(credPath)) {
    return null;
  }

  try {
    return JSON.parse(fs.readFileSync(credPath, "utf-8"));
  } catch {
    return null;
  }
}

/**
 * Saves credentials to file
 */
function saveCredentials(credentials: Credentials): void {
  const credPath = getCredentialsPath();
  const dir = path.dirname(credPath);
  
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  fs.writeFileSync(credPath, JSON.stringify(credentials, null, 2));
}

/**
 * Creates an OAuth2 client with the loaded keys
 */
function createOAuth2Client(): Auth.OAuth2Client {
  const keys = loadOAuthKeys();
  return new google.auth.OAuth2(
    keys.client_id,
    keys.client_secret,
    keys.redirect_uris[0]
  );
}

/**
 * Refreshes the access token using the refresh token
 * This is the KEY function that the other MCP got wrong
 */
async function refreshAccessToken(oauth2Client: Auth.OAuth2Client, credentials: Credentials): Promise<Credentials> {
  // Set the refresh token on the client
  oauth2Client.setCredentials({
    refresh_token: credentials.refresh_token,
  });

  // Request a new access token
  const { credentials: newCreds } = await oauth2Client.refreshAccessToken();

  const updatedCredentials: Credentials = {
    access_token: newCreds.access_token!,
    refresh_token: credentials.refresh_token, // Keep the original refresh token
    scope: credentials.scope,
    token_type: credentials.token_type,
    expiry_date: newCreds.expiry_date!,
  };

  // Save to disk immediately
  saveCredentials(updatedCredentials);

  return updatedCredentials;
}

/**
 * Gets a valid OAuth2 client with fresh credentials
 * This function ALWAYS reads from disk and refreshes if needed
 */
export async function getAuthenticatedClient(): Promise<Auth.OAuth2Client> {
  const oauth2Client = createOAuth2Client();

  // Always load fresh credentials from disk
  const credentials = loadCredentials();
  if (!credentials) {
    throw new Error(
      "No credentials found. Run 'gmail-mcp auth' to authenticate first."
    );
  }

  if (!credentials.refresh_token) {
    throw new Error(
      "No refresh token found. Run 'gmail-mcp auth' to re-authenticate."
    );
  }

  // Check if token is expired or will expire in the next 5 minutes
  const now = Date.now();
  const expiryBuffer = 5 * 60 * 1000; // 5 minutes
  const isExpired = credentials.expiry_date < now + expiryBuffer;

  let validCredentials = credentials;

  if (isExpired) {
    try {
      validCredentials = await refreshAccessToken(oauth2Client, credentials);
    } catch (error) {
      throw new Error(
        `Failed to refresh access token: ${error}. Run 'gmail-mcp auth' to re-authenticate.`
      );
    }
  }

  // Set all credentials on the client
  oauth2Client.setCredentials({
    access_token: validCredentials.access_token,
    refresh_token: validCredentials.refresh_token,
    expiry_date: validCredentials.expiry_date,
  });

  return oauth2Client;
}

/**
 * Gets the Gmail API client
 */
export async function getGmailClient() {
  const auth = await getAuthenticatedClient();
  return google.gmail({ version: "v1", auth });
}

export { SCOPES, createOAuth2Client, saveCredentials, loadCredentials };
