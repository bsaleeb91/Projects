"""
Morning Brief - Daily automated email digest
Sends to bsaleeb@gmail.com at 7 AM ET every weekday
Sources: Gmail + Google Calendar + Todoist → Claude → Gmail
"""

import os
import base64
import datetime
import json
import urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import anthropic

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)

# ── Config ────────────────────────────────────────────────────────────────────
MY_EMAIL          = os.getenv("MY_EMAIL", "bsaleeb@gmail.com")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TODOIST_API_KEY   = os.getenv("TODOIST_API_KEY")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
]

# ── Google Auth ───────────────────────────────────────────────────────────────
def get_google_services():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    gmail    = build("gmail", "v1", credentials=creds)
    calendar = build("calendar", "v3", credentials=creds)
    return gmail, calendar


# ── Gmail: Fetch last 24 hours ────────────────────────────────────────────────
def fetch_recent_emails(gmail_service, hours=24):
    since  = int((datetime.datetime.utcnow() - datetime.timedelta(hours=hours)).timestamp())
    query  = f"after:{since} -category:promotions -category:social"
    results = gmail_service.users().messages().list(
        userId="me", q=query, maxResults=30
    ).execute()

    messages = results.get("messages", [])
    emails = []
    for msg in messages:
        detail = gmail_service.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
        emails.append({
            "from":    headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date":    headers.get("Date", ""),
            "snippet": detail.get("snippet", "")[:300],
        })
    return emails


# ── Calendar: Fetch today's events ───────────────────────────────────────────
def fetch_todays_events(calendar_service):
    now   = datetime.datetime.utcnow()
    start = datetime.datetime(now.year, now.month, now.day).isoformat() + "Z"
    end   = datetime.datetime(now.year, now.month, now.day, 23, 59).isoformat() + "Z"
    result = calendar_service.events().list(
        calendarId="primary", timeMin=start, timeMax=end,
        singleEvents=True, orderBy="startTime"
    ).execute()
    events = []
    for e in result.get("items", []):
        start_time = e["start"].get("dateTime", e["start"].get("date", ""))
        events.append({
            "title":    e.get("summary", "Untitled"),
            "start":    start_time,
            "location": e.get("location", ""),
        })
    return events


# ── Todoist: Fetch today + overdue tasks ──────────────────────────────────────
def fetch_todoist_tasks():
    if not TODOIST_API_KEY:
        return []
    try:
        req = urllib.request.Request(
            "https://api.todoist.com/api/v1/tasks?filter=today%7Coverdue",
            headers={"Authorization": f"Bearer {TODOIST_API_KEY}"}
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            tasks = data.get("results", data) if isinstance(data, dict) else data
        today = datetime.date.today().isoformat()
        result = []
        for t in tasks:
            due     = t.get("due", {}) or {}
            due_str = due.get("date", "")
            result.append({
                "content":  t.get("content", ""),
                "priority": t.get("priority", 1),   # 4=urgent, 3=high, 2=medium, 1=normal
                "due":      due_str,
                "overdue":  bool(due_str and due_str < today),
                "project":  t.get("project_id", ""),
            })
        # Sort: overdue first, then by priority descending
        result.sort(key=lambda x: (not x["overdue"], -x["priority"]))
        return result
    except Exception as e:
        print(f"Todoist error: {e}")
        return []


# ── Claude: Synthesize the brief ──────────────────────────────────────────────
def generate_brief(emails, events, tasks, today_str):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system_prompt = """You are Bishoy's personal morning brief assistant.

About Bishoy:
- Director of Data Strategy at InfuCareRx (specialty infusion pharmacy)
- Also runs Saleeb Consulting (strategic advisory for specialty pharmacies)
- Young son Mac — first birthday party April 25, 2026 at Pat White Center, Manassas VA
- Active in church (teaches Sunday school, developing adult lecture content)
- Follows Washington sports: Capitals, Nationals, Commanders

Produce a clean, scannable morning brief in HTML with inline styles. Structure:

1. 📅 TODAY'S CALENDAR — list events with time and any location
2. 🔴 ACTION REQUIRED — emails needing a reply, decision, or with a deadline. One line each with enough context to act. After each item, append a small "+ Todoist" link styled as a pill button (background #db4035, white text, border-radius 4px, font-size 11px, padding 1px 6px, no underline, margin-left 8px). The href must be: https://app.todoist.com/app/task/new?content= followed by a URL-encoded version of a concise task description (e.g., "Reply%20to%20sender%20re%3A%20subject"). Only use letters, numbers, spaces encoded as %20, and basic punctuation — no special characters.
3. 💸 BILLS & FINANCIAL — any email from lenders, servicers, or billers (MOHELA, student loans,
   credit cards, utilities, insurance, bank alerts, payment confirmations, due-date notices).
   Flag overdue or past-due items in red. One line each with amount and due date if present.
4. 📖 WORTH READING — emails relevant to his interests:
   Healthcare data, specialty pharmacy, AI/ML, analytics, Power BI, SQL, Python,
   health policy, faith, parenting, Washington sports, productivity, Notion, family
4. ✅ OPEN TASKS — from Todoist, overdue first (flagged 🔴), then due today. Flag any Mac party tasks prominently with 🎂.
5. 🗑️ NOISE — briefly list senders/subjects that are pure noise, no detail needed.

Design rules:
- Mobile-friendly HTML, max-width 600px, centered
- White background, clean sans-serif font (Arial)
- Section headers: dark navy (#1a2744), bold, with a colored left border
- Action items: light red background (#fff5f5)
- Tasks: light background (#f8f9fa), overdue items in red
- No fluff, no preamble — start directly with the brief content
- Each action item or task = one tight line"""

    user_content = f"""Today is {today_str}.

CALENDAR EVENTS:
{json.dumps(events, indent=2)}

EMAILS (last 24 hours):
{json.dumps(emails, indent=2)}

TODOIST TASKS (today + overdue):
{json.dumps(tasks, indent=2)}

Generate the morning brief HTML."""

    for attempt in range(5):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
            return message.content[0].text
        except Exception as e:
            if "overloaded" in str(e).lower() and attempt < 4:
                wait = 30 * (attempt + 1)
                print(f"   API overloaded, retrying in {wait}s... (attempt {attempt+1}/5)")
                import time; time.sleep(wait)
            else:
                raise


# ── Gmail: Send the brief ─────────────────────────────────────────────────────
def send_email(gmail_service, html_body, today_str):
    msg            = MIMEMultipart("alternative")
    msg["Subject"] = f"☀️ Morning Brief — {today_str}"
    msg["From"]    = MY_EMAIL
    msg["To"]      = MY_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    gmail_service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()
    print(f"✅ Morning Brief sent to {MY_EMAIL}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    today_str = datetime.datetime.now().strftime("%A, %B %#d, %Y")
    print(f"🌅 Running Morning Brief for {today_str}...")

    gmail, calendar = get_google_services()

    print("📧 Fetching emails...")
    emails = fetch_recent_emails(gmail)

    print("📅 Fetching calendar...")
    events = fetch_todays_events(calendar)

    print("✅ Fetching Todoist tasks...")
    tasks = fetch_todoist_tasks()

    print(f"   {len(emails)} emails | {len(events)} events | {len(tasks)} tasks")

    print("🤖 Generating brief with Claude...")
    html_body = generate_brief(emails, events, tasks, today_str)

    print("📨 Sending email...")
    send_email(gmail, html_body, today_str)


if __name__ == "__main__":
    main()
