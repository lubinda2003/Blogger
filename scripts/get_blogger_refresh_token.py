#!/usr/bin/env python3
"""Supported Google OAuth2 refresh token generator for Google Blogger API v3.

Replaces deprecated out-of-band (urn:ietf:wg:oauth:2.0:oob) flow with Google's
recommended local loopback server (http://localhost:8080) for Desktop applications.

Prerequisites:
1. Google Cloud Console > APIs & Services > Credentials
2. OAuth client ID with type "Desktop application"
   (Desktop client IDs support http://localhost redirect automatically)
3. Blogger API v3 enabled in your project
4. Your email added under OAuth Consent Screen > Test Users (if app is in Testing mode)

Usage:
    python scripts/get_blogger_refresh_token.py --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
"""

import argparse
import html
import http.server
import json
import socketserver
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

BLOGGER_SCOPE = "https://www.googleapis.com/auth/blogger"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
LOOPBACK_PORT = 8080
REDIRECT_URI = f"http://localhost:{LOOPBACK_PORT}"


class OAuthCallbackHandler(http.server.SimpleHTTPRequestHandler):
    """Handles the redirect from Google OAuth consent and extracts authorization code."""

    auth_code = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            success_html = """
            <!DOCTYPE html>
            <html>
            <head><title>Authorization Successful</title></head>
            <body style="font-family:sans-serif; text-align:center; padding:50px; background:#0f172a; color:#f8fafc;">
                <h1 style="color:#38bdf8;">Authorization Successful</h1>
                <p>Google has granted access to your Blogger blog.</p>
                <p>You can close this browser tab and return to your terminal.</p>
            </body>
            </html>
            """
            self.wfile.write(success_html.encode("utf-8"))
        elif "error" in params:
            error_desc = params.get("error_description", params.get("error", ["Unknown error"]))[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            err_html = f"""
            <!DOCTYPE html>
            <html>
            <body style="font-family:sans-serif; text-align:center; padding:50px; background:#0f172a; color:#f8fafc;">
                <h1 style="color:#f43f5e;">Authorization Denied</h1>
                <p>{html.escape(error_desc)}</p>
            </body>
            </html>
            """
            self.wfile.write(err_html.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Silence standard HTTP access logging to prevent credential leakage
        pass


def exchange_code_for_token(code: str, client_id: str, client_secret: str, redirect_uri: str) -> str:
    """Exchange authorization code for refresh token."""
    token_data = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode("utf-8")

    req = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            token_response = json.loads(resp.read().decode("utf-8"))
            refresh_token = token_response.get("refresh_token")

            if not refresh_token:
                print("\nWarning: No refresh token returned. Did you include prompt=consent?", file=sys.stderr)
                sys.exit(1)

            return refresh_token

    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        print(f"\nError exchanging code for token (HTTP {e.code}): {err_msg}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Generate Google Blogger OAuth2 Refresh Token")
    parser.add_argument("--client-id", required=True, help="Google Cloud OAuth Client ID")
    parser.add_argument("--client-secret", required=True, help="Google Cloud OAuth Client Secret")
    parser.add_argument("--port", type=int, default=LOOPBACK_PORT, help="Local loopback port (default 8080)")
    parser.add_argument("--manual", action="store_true", help="Manual mode (paste redirect URL or code)")
    args = parser.parse_args()

    redirect_uri = f"http://localhost:{args.port}"

    auth_params = {
        "client_id": args.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": BLOGGER_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(auth_params)}"

    print("=" * 75)
    print("GOOGLE BLOGGER OAUTH2 TOKEN GENERATOR (Loopback Flow)")
    print("=" * 75)
    print("\n1. Opening your web browser for Google Authorization...")
    print("   If it does not open automatically, visit this URL:\n")
    print(auth_url)
    print("\n" + "=" * 75)

    if not args.manual:
        # Start local HTTP server to receive callback
        try:
            with socketserver.TCPServer(("localhost", args.port), OAuthCallbackHandler) as httpd:
                try:
                    webbrowser.open(auth_url)
                except Exception:
                    pass

                print(f"Waiting for authorization callback on {redirect_uri} ...")
                httpd.handle_request()  # Handle single callback request
                auth_code = OAuthCallbackHandler.auth_code
        except OSError as e:
            print(f"Could not bind to port {args.port} ({e}). Switching to manual code entry.")
            args.manual = True

    if args.manual or not auth_code:
        print("\nPaste the full redirect URL or the 'code' parameter value:")
        raw_input = input("Code or Redirect URL: ").strip()
        if "code=" in raw_input:
            parsed = urllib.parse.urlparse(raw_input)
            auth_code = urllib.parse.parse_qs(parsed.query).get("code", [raw_input])[0]
        else:
            auth_code = raw_input

    if not auth_code:
        print("Error: No authorization code obtained.", file=sys.stderr)
        sys.exit(1)

    print("\nExchanging authorization code with Google OAuth endpoint...")
    refresh_token = exchange_code_for_token(
        code=auth_code,
        client_id=args.client_id,
        client_secret=args.client_secret,
        redirect_uri=redirect_uri,
    )

    masked_token = f"{refresh_token[:6]}...[MASKED]...{refresh_token[-4:]}" if len(refresh_token) > 14 else "***[MASKED]***"
    token_file = ".blogger_refresh_token.txt"

    # Write token strictly to a local file with 0600 permissions (user-read/write only)
    import os
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    mode = 0o600
    try:
        fd = os.open(token_file, flags, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(refresh_token.strip() + "\n")
        file_saved = True
    except Exception as e:
        file_saved = False
        print(f"Warning: Could not write token file ({e})", file=sys.stderr)

    print("\n" + "=" * 75)
    print("SUCCESS: Blogger Refresh Token generated successfully!")
    print("=" * 75)
    print("For security, raw secrets and tokens are NEVER echoed in terminal logs.")
    print(f"Token Status: Generated successfully (length: {len(refresh_token)} chars)")
    print(f"Token Preview: {masked_token}")
    print("=" * 75)
    if file_saved:
        print(f"\nThe full token was saved to local file: {token_file}")
        print("File permissions set to 0600 (owner read/write only, excluded by .gitignore).")
        print("\nNext step:")
        print("1. Copy the token into your GitHub Repository Secrets:")
        print("   GitHub Repository > Settings > Secrets and variables > Actions > New repository secret")
        print("   Name:  BLOGGER_REFRESH_TOKEN")
        print("   Value: [Contents of .blogger_refresh_token.txt]")
        print(f"2. Delete the temporary file once added to GitHub Secrets:")
        print(f"   rm {token_file}\n")


if __name__ == "__main__":
    main()

