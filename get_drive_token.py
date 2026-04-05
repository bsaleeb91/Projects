#!/usr/bin/env python3
"""
One-time script to generate a Google Drive token.
Run this once — it opens a browser to log in, then saves drive_token.json.
"""

from google_auth_oauthlib.flow import InstalledAppFlow
from pathlib import Path

CREDENTIALS = Path(__file__).parent / "credentials.json"
TOKEN_OUT   = Path(__file__).parent / "drive_token.json"
SCOPES      = ["https://www.googleapis.com/auth/drive.readonly"]

flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
creds = flow.run_local_server(port=0)

TOKEN_OUT.write_text(creds.to_json())
print(f"\nDone! Token saved to: {TOKEN_OUT}")
