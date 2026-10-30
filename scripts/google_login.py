"""One time sign-in as the author, for AdMob reports and sending the report email.

Opens the browser for consent with the OAuth client in `config/oauth-client.json` and saves the
refresh token to `config/oauth-token.json`. Both files are gitignored. Sign in with the Google
account that owns AdMob and should send the report.
"""

from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_FILE = Path("config/oauth-client.json")
TOKEN_FILE = Path("config/oauth-token.json")
SCOPES = [
    "https://www.googleapis.com/auth/admob.report",
    "https://www.googleapis.com/auth/gmail.send",
]


def main() -> None:
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    TOKEN_FILE.write_text(credentials.to_json())
    print(f"Saved the sign-in to {TOKEN_FILE}")


if __name__ == "__main__":
    main()
