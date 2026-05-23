"""
One-time Gmail OAuth2 token generator.

Run this once locally to authenticate and produce the GMAIL_TOKEN value
needed by gmail_fetch.py. After running, paste the printed JSON into your
GMAIL_TOKEN environment variable (or GitHub secret).

Usage:
    python3 auth_gmail.py path/to/client_secret.json
"""

import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 auth_gmail.py path/to/client_secret.json")
        sys.exit(1)

    creds_path = Path(sys.argv[1])
    if not creds_path.exists():
        print(f"File not found: {creds_path}")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)

    token_json = creds.to_json()

    print("\n" + "=" * 60)
    print("SUCCESS — copy the JSON below as your GMAIL_TOKEN value:")
    print("=" * 60)
    print(token_json)
    print("=" * 60)

    # Also save to a local file for convenience
    out = Path("gmail_token.json")
    out.write_text(token_json)
    print(f"\nAlso saved to: {out.resolve()}")
    print("Do not commit this file — add it to .gitignore if not already.")


if __name__ == "__main__":
    main()
