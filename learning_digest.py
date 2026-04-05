"""
Learning Digest - Daily AI-curated learning email
Sends to bsaleeb@gmail.com at 7 AM ET every weekday
Sources: RSS feeds + YouTube Data API → Claude (ranked) → Gmail
Topics: Specialty Pharmacy · AI & Data · Independent Consulting
30-minute time budget, highest signal first

Requires in .env:
  ANTHROPIC_API_KEY
  YOUTUBE_API_KEY   (Google Cloud → YouTube Data API v3)
  MY_EMAIL          (optional, defaults to bsaleeb@gmail.com)

Shares token.json / credentials.json with morning_brief.py
"""

import os
import json
import base64
import datetime
import urllib.request
import urllib.parse
import re
import xml.etree.ElementTree as ET
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
YOUTUBE_API_KEY   = os.getenv("YOUTUBE_API_KEY")

SCOPES                = ["https://www.googleapis.com/auth/gmail.send"]
MAX_DIGEST_SECONDS    = 30 * 60   # 30-minute reading budget
MIN_CLAUDE_SCORE      = 6.0       # drop anything below this
YOUTUBE_LOOKBACK_DAYS = 7
MAX_PER_SOURCE        = 2         # max articles per domain per digest

# Domains that are largely paywalled — label so you know before clicking
PAYWALL_DOMAINS = {
    "www.statnews.com",
    "www.healthaffairs.org",
    "hbr.org",
    "www.technologyreview.com",
}

# ── RSS Sources (free sources first, paywalled at bottom) ─────────────────────
RSS_SOURCES = [
    # Specialty Pharmacy & Health Policy — FREE
    ("http://www.drugchannels.net/feeds/posts/default",       "Specialty Pharmacy"),
    ("https://www.fiercepharma.com/rss/xml",                  "Specialty Pharmacy"),
    ("https://www.fiercehealthcare.com/rss/xml",              "Healthcare"),
    ("https://www.fiercebiotech.com/rss/xml",                 "Biotech"),
    ("https://www.managedhealthcareexecutive.com/rss",        "Specialty Pharmacy"),
    ("https://kff.org/feed/",                                 "Health Policy"),
    ("https://www.anthropic.com/news/rss.xml",                "AI & Data"),
    ("https://news.ycombinator.com/rss",                      "AI & Data"),
    # Paywalled — included but flagged
    ("https://www.statnews.com/feed/",                        "Specialty Pharmacy"),
    ("https://www.healthaffairs.org/rss/site_5/41.xml",       "Health Policy"),
    ("https://hbr.org/subscriberservices/rss-feed",           "Consulting"),
    ("https://www.technologyreview.com/feed/",                "AI & Data"),
]

# ── YouTube Search Queries ────────────────────────────────────────────────────
YOUTUBE_QUERIES = [
    "specialty pharmacy infusion therapy trends",
    "PBM reform specialty drug pricing",
    "AI agents LLM practical applications",
    "AI healthcare clinical automation",
    "data analytics healthcare strategy",
    "healthcare independent consulting",
    "biosimilar specialty pharmacy 2025",
]


# ── Google Auth ───────────────────────────────────────────────────────────────
def get_gmail_service():
    creds      = None
    token_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json")
    creds_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


# ── RSS Fetching ──────────────────────────────────────────────────────────────
def _parse_date(date_str):
    """Parse RSS pubDate or Atom published into an aware datetime."""
    if not date_str:
        return None
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            dt = datetime.datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _strip_html(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _read_sec(text, min_sec=180):
    """Estimate read time from text; minimum min_sec."""
    words = len(_strip_html(text).split())
    return max(min_sec, int((words / 200) * 60))


def fetch_rss_articles(lookback_hours=24):
    cutoff   = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=lookback_hours)
    articles = []

    for feed_url, topic in RSS_SOURCES:
        try:
            req = urllib.request.Request(
                feed_url, headers={"User-Agent": "LearningDigest/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read()
            root = ET.fromstring(content)
            ns   = {"a": "http://www.w3.org/2005/Atom"}

            domain  = feed_url.split("/")[2]
            paywall = domain in PAYWALL_DOMAINS

            # RSS 2.0 items
            for item in root.findall(".//item"):
                pub_dt = _parse_date(item.findtext("pubDate", ""))
                if pub_dt and pub_dt < cutoff:
                    continue
                title = item.findtext("title", "").strip()
                link  = item.findtext("link",  "").strip()
                if not title or not link:
                    continue
                desc = item.findtext("description", "")
                articles.append({
                    "type":      "article",
                    "title":     title,
                    "url":       link,
                    "source":    domain,
                    "topic":     topic,
                    "summary":   _strip_html(desc)[:400],
                    "read_sec":  _read_sec(desc),
                    "published": pub_dt.strftime("%b %-d") if pub_dt else "",
                    "paywall":   paywall,
                    "score":     0,
                    "why":       "",
                })

            # Atom entries
            for entry in root.findall(".//a:entry", ns):
                pub_dt = _parse_date(entry.findtext("a:published", "", ns))
                if pub_dt and pub_dt < cutoff:
                    continue
                title    = entry.findtext("a:title", "", ns).strip()
                link_el  = entry.find("a:link", ns)
                link     = link_el.get("href", "") if link_el is not None else ""
                if not title or not link:
                    continue
                summary = entry.findtext("a:summary", "", ns)
                articles.append({
                    "type":      "article",
                    "title":     title,
                    "url":       link,
                    "source":    domain,
                    "topic":     topic,
                    "summary":   _strip_html(summary)[:400],
                    "read_sec":  _read_sec(summary),
                    "published": pub_dt.strftime("%b %-d") if pub_dt else "",
                    "paywall":   paywall,
                    "score":     0,
                    "why":       "",
                })

        except Exception as e:
            print(f"  RSS error ({feed_url.split('/')[2]}): {e}")

    # Cap at MAX_PER_SOURCE articles per domain to prevent any one source dominating
    from collections import defaultdict
    source_counts = defaultdict(int)
    capped = []
    for a in articles:
        if source_counts[a["source"]] < MAX_PER_SOURCE:
            capped.append(a)
            source_counts[a["source"]] += 1
    return capped


# ── YouTube Fetching ──────────────────────────────────────────────────────────
def _parse_duration(s):
    """PT1H2M30S → seconds."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    h, mn, sc = (int(x or 0) for x in m.groups())
    return h * 3600 + mn * 60 + sc


def _yt(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    url = "https://www.googleapis.com/youtube/v3/" + endpoint + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode())


def fetch_youtube_videos():
    if not YOUTUBE_API_KEY:
        print("  No YOUTUBE_API_KEY — skipping YouTube.")
        return []

    published_after = (
        datetime.datetime.utcnow() - datetime.timedelta(days=YOUTUBE_LOOKBACK_DAYS)
    ).strftime("%Y-%m-%dT00:00:00Z")

    video_ids = []
    seen      = set()

    for query in YOUTUBE_QUERIES:
        for duration_bucket in ("medium", "long"):  # 4-20 min, >20 min
            try:
                data = _yt("search", {
                    "part":              "id",
                    "q":                 query,
                    "type":              "video",
                    "publishedAfter":    published_after,
                    "videoDuration":     duration_bucket,
                    "maxResults":        5,
                    "order":             "relevance",
                    "relevanceLanguage": "en",
                })
                for item in data.get("items", []):
                    vid = item["id"].get("videoId")
                    if vid and vid not in seen:
                        seen.add(vid)
                        video_ids.append(vid)
            except Exception as e:
                print(f"  YouTube search error ({query}): {e}")

    if not video_ids:
        return []

    videos = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        try:
            data = _yt("videos", {
                "part": "snippet,contentDetails,statistics",
                "id":   ",".join(batch),
            })
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            for item in data.get("items", []):
                snippet  = item.get("snippet", {})
                details  = item.get("contentDetails", {})
                stats    = item.get("statistics", {})
                duration = _parse_duration(details.get("duration", ""))

                # Filter: 8 min - 90 min
                if not (8 * 60 <= duration <= 90 * 60):
                    continue

                pub_raw = snippet.get("publishedAt", "")
                try:
                    pub_dt    = datetime.datetime.fromisoformat(pub_raw.replace("Z", "+00:00"))
                    days_old  = max(1, (now_utc - pub_dt).days)
                    view_vel  = int(int(stats.get("viewCount", 0)) / days_old)
                    pub_label = pub_dt.strftime("%b %-d")
                except Exception:
                    view_vel  = 0
                    pub_label = pub_raw[:10]

                videos.append({
                    "type":          "video",
                    "title":         snippet.get("title", ""),
                    "url":           f"https://youtube.com/watch?v={item['id']}",
                    "source":        snippet.get("channelTitle", ""),
                    "topic":         "YouTube",
                    "summary":       snippet.get("description", "")[:300],
                    "read_sec":      duration,
                    "view_velocity": view_vel,
                    "published":     pub_label,
                    "paywall":       False,
                    "score":         0,
                    "why":           "",
                })
        except Exception as e:
            print(f"  YouTube details error: {e}")

    return videos


# ── Claude Ranking (two-pass) ─────────────────────────────────────────────────
def rank_with_claude(candidates):
    if not candidates:
        return []

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    slim = [
        {
            "id":       i,
            "type":     c["type"],
            "title":    c["title"],
            "source":   c.get("source", ""),
            "topic":    c["topic"],
            "summary":  c["summary"][:200],
            "read_min": round(c["read_sec"] / 60, 1),
        }
        for i, c in enumerate(candidates)
    ]

    prompt = f"""You are ranking content for Bishoy Saleeb's daily learning digest.

About Bishoy:
- Director of Data Strategy at InfuCareRx (specialty infusion pharmacy)
- Runs Saleeb Consulting (strategic advisory for specialty pharmacies)
- Core interests: specialty pharmacy operations, drug pricing/reimbursement (Part B, buy-and-bill),
  PBM reform, biosimilars, AI/LLM/agents, healthcare data analytics, Power BI, Python, SQL,
  independent consulting strategy, thought leadership, healthcare policy

Score each item 1-10:
  10   = must-read for his specific role - direct impact on his work or business
  7-9  = genuinely relevant and useful
  5-6  = mildly interesting, not essential
  1-4  = off-topic, generic, or low-signal

Rules:
- Write a tight 1-sentence "why this matters to Bishoy" for anything scored 7+.
- Omit items scored below {MIN_CLAUDE_SCORE} entirely.
- For YouTube videos, weight channel authority and view velocity heavily.
- Prefer primary sources and expert analysis over aggregator summaries.
- Return ONLY a valid JSON array - no markdown, no commentary:

[{{"id": 0, "score": 8.5, "why": "..."}}, ...]

Items:
{json.dumps(slim, indent=2)}"""

    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        ranked    = json.loads(msg.content[0].text)
        score_map = {r["id"]: r for r in ranked}
        for i, c in enumerate(candidates):
            if i in score_map:
                c["score"] = score_map[i]["score"]
                c["why"]   = score_map[i].get("why", "")
        result = [c for c in candidates if c["score"] >= MIN_CLAUDE_SCORE]
        result.sort(key=lambda x: x["score"], reverse=True)
        return result
    except Exception as e:
        print(f"  Claude ranking parse error: {e}")
        return candidates


# ── Time Budget ───────────────────────────────────────────────────────────────
def apply_budget(ranked, budget=MAX_DIGEST_SECONDS):
    in_budget, overflow, total = [], [], 0
    for item in ranked:
        if total + item["read_sec"] <= budget:
            in_budget.append(item)
            total += item["read_sec"]
        else:
            overflow.append(item)
    return in_budget, overflow, total


# ── HTML Generation ───────────────────────────────────────────────────────────
def _fmt(seconds):
    m = seconds // 60
    return f"{m} min" if m < 60 else f"{m // 60}h {m % 60}m"


def build_html(in_budget, overflow, total_sec, today_str):
    articles = [x for x in in_budget if x["type"] == "article"]
    videos   = [x for x in in_budget if x["type"] == "video"]

    H = "border-left:4px solid #1a2744; padding-left:12px; margin:24px 0 10px; font-size:15px; font-weight:700; color:#1a2744;"

    def row(item):
        score   = item["score"]
        color   = "#1b6b3a" if score >= 8.5 else "#1d4e7a" if score >= 7 else "#777"
        source  = item.get("source", "")
        pub     = item.get("published", "")
        paywall = item.get("paywall", False)
        meta    = " · ".join(x for x in [source, pub, item["topic"]] if x)
        why     = item.get("why", "")
        paywall_tag = (
            ' <span style="font-size:10px; background:#fff3cd; color:#856404; '
            'border-radius:3px; padding:1px 5px; font-weight:600;">$ paywall</span>'
            if paywall else ""
        )
        return (
            f'<tr><td style="padding:10px 0; border-bottom:1px solid #f0f0f0; vertical-align:top;">'
            f'<div style="display:flex; justify-content:space-between;">'
            f'<span style="font-size:11px; font-weight:700; color:{color};">&#9650; {score:.1f}</span>'
            f'<span style="font-size:11px; color:#aaa;">{_fmt(item["read_sec"])}</span></div>'
            f'<a href="{item["url"]}" style="font-size:14px; font-weight:600; color:#1a2744; text-decoration:none; display:block; margin:4px 0;">{item["title"]}</a>{paywall_tag}'
            f'<div style="font-size:11px; color:#999; margin-bottom:3px; margin-top:3px;">{meta}</div>'
            + (f'<div style="font-size:12px; color:#555; font-style:italic;">{why}</div>' if why else "")
            + "</td></tr>"
        )

    def section(label, items, empty_msg):
        rows = "".join(row(x) for x in items) if items else f'<tr><td style="padding:10px 0; font-size:13px; color:#aaa;">{empty_msg}</td></tr>'
        return f'<div style="{H}">{label}</div><table style="width:100%; border-collapse:collapse;"><tbody>{rows}</tbody></table>'

    overflow_html = ""
    if overflow:
        lis = "".join(
            f'<li style="margin-bottom:4px;"><a href="{x["url"]}" style="color:#555; font-size:12px;">{x["title"]}</a>'
            f' <span style="color:#bbb; font-size:11px;">({_fmt(x["read_sec"])})</span></li>'
            for x in overflow[:8]
        )
        overflow_html = (
            f'<div style="margin-top:24px; padding:12px 16px; background:#f8f9fa; border-radius:6px;">'
            f'<div style="font-size:11px; font-weight:700; color:#aaa; text-transform:uppercase; letter-spacing:.5px; margin-bottom:8px;">More if you have time</div>'
            f'<ul style="margin:0; padding-left:18px;">{lis}</ul></div>'
        )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0; padding:16px; background:#f5f5f5; font-family:Arial,sans-serif;">
<div style="max-width:600px; margin:0 auto; background:#fff; border-radius:8px; padding:24px;">
  <div style="border-bottom:2px solid #1a2744; padding-bottom:12px; margin-bottom:4px;">
    <div style="font-size:20px; font-weight:700; color:#1a2744;">&#128218; Learning Digest</div>
    <div style="font-size:13px; color:#999; margin-top:4px;">{today_str} &middot; &#9201; {_fmt(total_sec)} curated reading</div>
  </div>

  {section("&#128240; Articles &amp; News", articles, "No articles found today.")}
  {section("&#9654; Videos", videos, "No videos found this week.")}

  {overflow_html}

  <div style="margin-top:24px; padding-top:12px; border-top:1px solid #eee; font-size:11px; color:#ccc; text-align:center;">
    Learning Digest &middot; Curated by Claude Opus &middot; bsaleeb@gmail.com
  </div>
</div>
</body>
</html>"""


# ── Send Email ────────────────────────────────────────────────────────────────
def send_email(gmail_service, html_body, today_str):
    msg            = MIMEMultipart("alternative")
    msg["Subject"] = f"Learning Digest - {today_str}"
    msg["From"]    = MY_EMAIL
    msg["To"]      = MY_EMAIL
    msg.attach(MIMEText(html_body, "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    gmail_service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"✅ Learning Digest sent to {MY_EMAIL}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    today_str = datetime.datetime.now().strftime("%A, %B %-d, %Y")
    print(f"📚 Running Learning Digest - {today_str}")

    # Monday: look back 72h to catch weekend articles
    lookback_h = 72 if datetime.datetime.now().weekday() == 0 else 24

    print(f"📡 Fetching RSS ({lookback_h}h lookback)...")
    articles = fetch_rss_articles(lookback_hours=lookback_h)
    print(f"   {len(articles)} articles")

    print(f"▶  Fetching YouTube ({YOUTUBE_LOOKBACK_DAYS}-day window)...")
    videos = fetch_youtube_videos()
    print(f"   {len(videos)} videos")

    candidates = articles + videos
    if not candidates:
        print("No content found - skipping send.")
        return

    print(f"🤖 Ranking {len(candidates)} items with Claude...")
    ranked = rank_with_claude(candidates)
    print(f"   {len(ranked)} passed quality threshold (score >= {MIN_CLAUDE_SCORE})")

    in_budget, overflow, total_sec = apply_budget(ranked)
    print(f"   {len(in_budget)} items fit 30-min budget ({_fmt(total_sec)})")

    html  = build_html(in_budget, overflow, total_sec, today_str)
    gmail = get_gmail_service()
    send_email(gmail, html, today_str)


if __name__ == "__main__":
    main()
