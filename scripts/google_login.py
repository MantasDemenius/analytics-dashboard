"""One time sign-in as the author, for AdMob reports or for sending the report email.

  google_login.py admob   sign in with the Google account that owns AdMob
  google_login.py gmail   sign in with the Google account the report is sent from

Each sign-in holds one scope and saves its refresh token to its own gitignored file in
`config/`, using the OAuth client in `config/oauth-client.json`. The two may be different
accounts.
"""

import sys
from pathlib import Path
from typing import NamedTuple

from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_FILE = Path("config/oauth-client.json")


class SignIn(NamedTuple):
    scopes: list[str]
    token_file: Path


SIGN_INS = {
    "admob": SignIn(
        ["https://www.googleapis.com/auth/admob.report"],
        Path("config/admob-token.json"),
    ),
    "gmail": SignIn(
        ["https://www.googleapis.com/auth/gmail.send"],
        Path("config/gmail-token.json"),
    ),
}


def sign_in_for(argv: list[str]) -> SignIn:
    if len(argv) != 2 or argv[1] not in SIGN_INS:
        raise SystemExit(__doc__)
    return SIGN_INS[argv[1]]


def main() -> None:
    sign_in = sign_in_for(sys.argv)
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), sign_in.scopes)
    credentials = flow.run_local_server(
        port=0, access_type="offline", prompt="select_account consent"
    )
    sign_in.token_file.write_text(credentials.to_json())
    print(f"Saved the sign-in to {sign_in.token_file}")


if __name__ == "__main__":
    main()
