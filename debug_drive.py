import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

idx = json.loads(Path("commentary_index.json").read_text())
fid   = idx.get("_folder_id")
creds = idx.get("_credentials")
tok   = idx.get("_token")

print(f"Folder ID: {fid}")

c   = Credentials.from_authorized_user_file(tok)
svc = build("drive", "v3", credentials=c)
r   = svc.files().list(
    q=f"'{fid}' in parents and trashed=false",
    fields="files(id,name,mimeType)"
).execute()

files = r.get("files", [])
if files:
    for f in files:
        print(f["mimeType"], " | ", f["name"])
else:
    print("(empty — nothing found in this folder)")
