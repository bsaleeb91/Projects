import fitz
import json
import io
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

index = json.loads(open("commentary_index.json").read())
creds = Credentials.from_authorized_user_file(
    index["_token"], scopes=["https://www.googleapis.com/auth/drive.readonly"]
)
svc = build("drive", "v3", credentials=creds)

results = svc.files().list(
    q="name contains 'Ephesians' and mimeType='application/pdf' and trashed=false",
    fields="files(id, name)",
).execute()
print("Found:", results["files"])

f = next(r for r in results["files"] if r["name"] == "049 Ephesians.pdf")
print("Downloading:", f["name"])
buf = io.BytesIO()
dl = MediaIoBaseDownload(buf, svc.files().get_media(fileId=f["id"]))
done = False
while not done:
    _, done = dl.next_chunk()

doc = fitz.open(stream=buf.getvalue(), filetype="pdf")
print("Pages:", doc.page_count)
for i, page in enumerate(doc):
    t = page.get_text()
    print(f"Page {i+1}: {len(t)} chars — {repr(t[:100])}")
    if i >= 4:
        print("...")
        break
