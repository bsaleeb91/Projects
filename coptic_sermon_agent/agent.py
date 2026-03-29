#!/usr/bin/env python3
"""
Coptic Orthodox Sermon Agent
Surfaces popular Arabic sermons by famous Coptic priests,
translated, ranked, and delivered as a monthly HTML digest via email.

Usage:
    python agent.py                  # Full run: fetch, rank, save HTML, email
    python agent.py --topic Prayer   # Filter results by topic
    python agent.py --no-email       # Skip email, just save HTML
    python agent.py --top 30         # Show top N results (default 25)
"""

import os
import base64
import json
import argparse
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

load_dotenv()
console = Console()

# ---------------------------------------------------------------------------
# Priest roster
# ---------------------------------------------------------------------------
PRIESTS = [
    {"name": "Pope Shenouda III",        "arabic": "البابا شنوده الثالث",        "weight": 1.0},
    {"name": "Bishop Moussa",             "arabic": "الأنبا موسى",                 "weight": 1.0},
    {"name": "Fr. Tadros Malaty",         "arabic": "القمص تادرس يعقوب ملطي",     "weight": 1.0},
    {"name": "Fr. Pishoy Kamel",          "arabic": "القمص بيشوي كامل",            "weight": 1.0},
    {"name": "Fr. Mina Aboud Sharoubeam", "arabic": "القمص مينا عبود شروبيم",      "weight": 1.0},
    {"name": "Bishop Youssef",            "arabic": "الأنبا يوسف",                 "weight": 1.0},
    {"name": "Fr. Daoud Lamei",           "arabic": "أبونا داود لمعي",             "weight": 1.4},
    {"name": "Fr. Bishoy Helmy",          "arabic": "أبونا بيشوى حلمى",            "weight": 1.0},
    {"name": "Fr. George Boules",         "arabic": "القمص بولس جورج",             "weight": 1.0},
    {"name": "Fr. Luka Maher",            "arabic": "أبونا لوقا ماهر",             "weight": 1.4},
    {"name": "Bishop Thomas",             "arabic": "الأنبا توماس",                "weight": 1.0},
]

VIDEOS_PER_PRIEST    = 50   # YouTube max per search call
PLAYLISTS_PER_PRIEST = 5    # Top playlists to inspect per priest
DEFAULT_TOP_N        = 25
REPORTS_DIR          = Path(__file__).parent / "reports"


# ---------------------------------------------------------------------------
# YouTube: individual videos
# ---------------------------------------------------------------------------

def search_videos(youtube, priest: dict) -> list[dict]:
    """Return up to VIDEOS_PER_PRIEST sermon videos for one priest."""
    query = f"{priest['arabic']} عظة"

    search_resp = youtube.search().list(
        q=query,
        part="snippet",
        maxResults=VIDEOS_PER_PRIEST,
        type="video",
        relevanceLanguage="ar",
        order="viewCount",
    ).execute()

    video_ids = [item["id"]["videoId"] for item in search_resp.get("items", [])]
    if not video_ids:
        return []

    stats_resp = youtube.videos().list(
        id=",".join(video_ids),
        part="statistics,snippet",
    ).execute()

    videos = []
    for item in stats_resp.get("items", []):
        stats   = item.get("statistics", {})
        snippet = item.get("snippet", {})
        videos.append({
            "video_id":       item["id"],
            "priest":         priest["name"],
            "priest_weight":  priest["weight"],
            "title_ar":       snippet.get("title", ""),
            "description_ar": snippet.get("description", "")[:600],
            "published_at":   snippet.get("publishedAt", ""),
            "views":          int(stats.get("viewCount", 0)),
            "likes":          int(stats.get("likeCount", 0)),
            "url":            f"https://youtube.com/watch?v={item['id']}",
            "playlist_id":    None,
        })

    return videos


# ---------------------------------------------------------------------------
# YouTube: series / playlists
# ---------------------------------------------------------------------------

def search_playlists(youtube, priest: dict) -> list[dict]:
    """Return top playlists for one priest."""
    query = f"{priest['arabic']} سلسلة عظات"

    resp = youtube.search().list(
        q=query,
        part="snippet",
        maxResults=PLAYLISTS_PER_PRIEST,
        type="playlist",
        relevanceLanguage="ar",
    ).execute()

    playlists = []
    for item in resp.get("items", []):
        pid     = item["id"]["playlistId"]
        snippet = item.get("snippet", {})
        playlists.append({
            "playlist_id":    pid,
            "priest":         priest["name"],
            "priest_weight":  priest["weight"],
            "title_ar":       snippet.get("title", ""),
            "description_ar": snippet.get("description", "")[:400],
        })

    return playlists


def fetch_playlist_videos(youtube, playlist: dict) -> list[dict]:
    """Fetch all video IDs in a playlist, then get their stats."""
    items_resp = youtube.playlistItems().list(
        playlistId=playlist["playlist_id"],
        part="snippet",
        maxResults=50,
    ).execute()

    video_ids = [
        item["snippet"]["resourceId"]["videoId"]
        for item in items_resp.get("items", [])
        if item["snippet"].get("resourceId", {}).get("kind") == "youtube#video"
    ]
    if not video_ids:
        return []

    stats_resp = youtube.videos().list(
        id=",".join(video_ids),
        part="statistics,snippet",
    ).execute()

    videos = []
    for item in stats_resp.get("items", []):
        stats   = item.get("statistics", {})
        snippet = item.get("snippet", {})
        videos.append({
            "video_id":       item["id"],
            "priest":         playlist["priest"],
            "priest_weight":  playlist["priest_weight"],
            "title_ar":       snippet.get("title", ""),
            "description_ar": snippet.get("description", "")[:400],
            "published_at":   snippet.get("publishedAt", ""),
            "views":          int(stats.get("viewCount", 0)),
            "likes":          int(stats.get("likeCount", 0)),
            "url":            f"https://youtube.com/watch?v={item['id']}",
            "playlist_id":    playlist["playlist_id"],
        })

    # Sort episodes by publish date (oldest first = Ep. 1 at top)
    videos.sort(key=lambda v: v["published_at"])
    return videos


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def compute_score(video: dict, max_views: int) -> float:
    """
    score = priest_weight × (0.5·views + 0.3·like_ratio + 0.2·recency)
    """
    normalized_views = video["views"] / max_views if max_views > 0 else 0.0
    like_ratio       = video["likes"] / video["views"] if video["views"] > 0 else 0.0

    try:
        published = datetime.fromisoformat(video["published_at"].replace("Z", "+00:00"))
        days_old  = (datetime.now(timezone.utc) - published).days
    except Exception:
        days_old = 365
    recency = 1.0 / (1.0 + days_old / 365.0)

    composite = 0.5 * normalized_views + 0.3 * like_ratio + 0.2 * recency
    return video["priest_weight"] * composite


def score_series(playlist: dict, episodes: list[dict], max_views: int) -> float:
    """
    Series score = priest_weight × (total_views / max_views) × log-boost for episode count.
    More episodes = richer series, slight bonus.
    """
    import math
    total_views      = sum(e["views"] for e in episodes)
    normalized       = total_views / max_views if max_views > 0 else 0.0
    episode_boost    = math.log2(max(len(episodes), 1) + 1) / 5.0  # small bonus
    return playlist["priest_weight"] * (normalized + episode_boost)


# ---------------------------------------------------------------------------
# Claude: translate & summarize
# ---------------------------------------------------------------------------

def _translate_batch(client: anthropic.Anthropic, batch: list[dict], offset: int) -> dict:
    """Translate a single batch of items. Returns enriched_map keyed by original index."""
    payload = [
        {
            "index":          offset + i,
            "priest":         v["priest"],
            "title_ar":       v["title_ar"],
            "description_ar": v.get("description_ar", ""),
        }
        for i, v in enumerate(batch)
    ]

    system = (
        "You are an expert in Coptic Orthodox theology, fluent in Arabic. "
        "Translate Arabic sermon metadata into clear, natural English. "
        "Be concise and faithful to the original meaning."
    )

    user_prompt = f"""For each sermon below, return a JSON array. Each object must have:
- "index"         : same integer as in input
- "english_title" : natural English translation of title_ar
- "summary"       : exactly 2 sentences describing the sermon topic and key message
- "topic_tag"     : exactly one of:
    Repentance | Prayer | Fasting | Love | Salvation | Marriage |
    Youth | Theology | Spiritual Life | Saints | Bible Study |
    Confession | Holy Spirit | Other

Input:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Return ONLY a valid JSON array — no markdown, no commentary."""

    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        response = stream.get_final_message()

    raw = next(b.text for b in response.content if b.type == "text").strip()

    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()

    return {e["index"]: e for e in json.loads(raw)}


def translate_and_summarize(client: anthropic.Anthropic, items: list[dict], batch_size: int = 30) -> list[dict]:
    """
    Translate Arabic sermon metadata in batches to avoid hitting max_tokens.
    Returns items enriched with: english_title, summary, topic_tag.
    """
    enriched_map = {}
    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        enriched_map.update(_translate_batch(client, batch, offset=i))

    for i, item in enumerate(items):
        info = enriched_map.get(i, {})
        item["english_title"] = info.get("english_title", item["title_ar"])
        item["summary"]       = info.get("summary", "")
        item["topic_tag"]     = info.get("topic_tag", "Other")

    return items


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

TOPIC_COLORS = {
    "Repentance":    "#ef4444",
    "Prayer":        "#8b5cf6",
    "Fasting":       "#f59e0b",
    "Love":          "#ec4899",
    "Salvation":     "#10b981",
    "Marriage":      "#f97316",
    "Youth":         "#06b6d4",
    "Theology":      "#6366f1",
    "Spiritual Life":"#14b8a6",
    "Saints":        "#a78bfa",
    "Bible Study":   "#84cc16",
    "Confession":    "#fb923c",
    "Holy Spirit":   "#38bdf8",
    "Other":         "#94a3b8",
}


def _topic_badge(tag: str) -> str:
    color = TOPIC_COLORS.get(tag, "#94a3b8")
    return f'<span class="badge" style="background:{color}">{tag}</span>'


def _star(weight: float) -> str:
    return ' <span class="star">★</span>' if weight > 1.0 else ""


def generate_html(
    sermons: list[dict],
    series_list: list[dict],
    run_date: str,
    topic_filter: str | None,
) -> str:

    # ── Individual sermon cards ────────────────────────────────────────────
    sermon_cards = ""
    for rank, s in enumerate(sermons, 1):
        sermon_cards += f"""
        <div class="card">
          <div class="card-header">
            <span class="rank">#{rank}</span>
            <span class="priest">{s['priest']}{_star(s['priest_weight'])}</span>
            {_topic_badge(s['topic_tag'])}
          </div>
          <h3 class="sermon-title">
            <a href="{s['url']}" target="_blank">{s['english_title']}</a>
          </h3>
          <p class="summary">{s['summary']}</p>
          <div class="meta">
            <span>👁 {s['views']:,} views</span>
            <span>Score: {s['final_score']:.3f}</span>
            <a class="watch-btn" href="{s['url']}" target="_blank">Watch ▶</a>
          </div>
        </div>"""

    # ── Series cards ───────────────────────────────────────────────────────
    series_cards = ""
    for rank, s in enumerate(series_list, 1):
        episodes_html = ""
        for ep_num, ep in enumerate(s["episodes"], 1):
            episodes_html += f"""
            <div class="episode">
              <span class="ep-num">Ep.{ep_num}</span>
              <a href="{ep['url']}" target="_blank">{ep.get('english_title', ep['title_ar'])}</a>
              <span class="ep-views">{ep['views']:,} views</span>
            </div>"""

        total_views = sum(e["views"] for e in s["episodes"])
        series_cards += f"""
        <div class="card series-card">
          <div class="card-header">
            <span class="rank">#{rank}</span>
            <span class="priest">{s['priest']}{_star(s['priest_weight'])}</span>
            {_topic_badge(s.get('topic_tag', 'Other'))}
          </div>
          <h3 class="sermon-title">{s.get('english_title', s['title_ar'])}</h3>
          <p class="summary">{s.get('summary', '')}</p>
          <div class="meta">
            <span>📺 {len(s['episodes'])} episodes</span>
            <span>👁 {total_views:,} total views</span>
            <span>Score: {s['series_score']:.3f}</span>
          </div>
          <div class="episodes">{episodes_html}</div>
        </div>"""

    if not series_cards:
        series_cards = '<p class="empty">No series detected this month.</p>'

    filter_note = f"<p class='filter-note'>Filtered by topic: <strong>{topic_filter}</strong></p>" if topic_filter else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Coptic Sermon Digest — {run_date}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      line-height: 1.6;
      padding: 2rem 1rem;
    }}
    .container {{ max-width: 860px; margin: 0 auto; }}

    /* Header */
    header {{ text-align: center; margin-bottom: 3rem; }}
    header h1 {{
      font-size: 2rem;
      color: #f59e0b;
      letter-spacing: 0.05em;
      margin-bottom: 0.3rem;
    }}
    header .cross {{ font-size: 2rem; display: block; margin-bottom: 0.5rem; }}
    header p {{ color: #94a3b8; font-size: 0.95rem; }}
    .filter-note {{
      display: inline-block;
      margin-top: 0.5rem;
      background: #1e293b;
      padding: 0.3rem 0.8rem;
      border-radius: 1rem;
      font-size: 0.85rem;
      color: #f59e0b;
    }}

    /* Section headings */
    .section-title {{
      font-size: 1.3rem;
      color: #f59e0b;
      border-bottom: 1px solid #1e3a5f;
      padding-bottom: 0.5rem;
      margin: 2.5rem 0 1.2rem;
    }}

    /* Cards */
    .card {{
      background: #1e293b;
      border: 1px solid #1e3a5f;
      border-radius: 12px;
      padding: 1.2rem 1.4rem;
      margin-bottom: 1rem;
      transition: border-color 0.2s;
    }}
    .card:hover {{ border-color: #f59e0b44; }}
    .series-card {{ border-left: 3px solid #f59e0b; }}

    .card-header {{
      display: flex;
      align-items: center;
      gap: 0.6rem;
      margin-bottom: 0.6rem;
      flex-wrap: wrap;
    }}
    .rank {{
      color: #475569;
      font-weight: 700;
      font-size: 0.85rem;
      min-width: 2rem;
    }}
    .priest {{
      color: #38bdf8;
      font-weight: 600;
      font-size: 0.9rem;
    }}
    .star {{ color: #f59e0b; }}

    .badge {{
      font-size: 0.7rem;
      font-weight: 700;
      padding: 0.2rem 0.55rem;
      border-radius: 999px;
      color: #fff;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}

    .sermon-title {{ font-size: 1.05rem; margin-bottom: 0.5rem; }}
    .sermon-title a {{ color: #e2e8f0; text-decoration: none; }}
    .sermon-title a:hover {{ color: #f59e0b; }}

    .summary {{ color: #94a3b8; font-size: 0.88rem; margin-bottom: 0.8rem; }}

    .meta {{
      display: flex;
      align-items: center;
      gap: 1rem;
      font-size: 0.82rem;
      color: #64748b;
      flex-wrap: wrap;
    }}
    .watch-btn {{
      margin-left: auto;
      background: #f59e0b;
      color: #0f172a;
      font-weight: 700;
      padding: 0.3rem 0.9rem;
      border-radius: 6px;
      text-decoration: none;
      font-size: 0.82rem;
    }}
    .watch-btn:hover {{ background: #fbbf24; }}

    /* Episodes */
    .episodes {{
      margin-top: 1rem;
      border-top: 1px solid #1e3a5f;
      padding-top: 0.8rem;
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
    }}
    .episode {{
      display: flex;
      align-items: center;
      gap: 0.7rem;
      font-size: 0.85rem;
    }}
    .ep-num {{ color: #f59e0b; font-weight: 700; min-width: 2.5rem; }}
    .episode a {{ color: #cbd5e1; text-decoration: none; flex: 1; }}
    .episode a:hover {{ color: #f59e0b; }}
    .ep-views {{ color: #475569; white-space: nowrap; }}

    .empty {{ color: #475569; font-style: italic; padding: 1rem 0; }}

    /* Footer */
    footer {{
      margin-top: 3rem;
      padding-top: 1.5rem;
      border-top: 1px solid #1e293b;
      text-align: center;
      font-size: 0.78rem;
      color: #334155;
      line-height: 2;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <span class="cross">☩</span>
      <h1>Coptic Orthodox Sermon Digest</h1>
      <p>{run_date}</p>
      {filter_note}
    </header>

    <h2 class="section-title">📺 Top Series</h2>
    {series_cards}

    <h2 class="section-title">🎙 Top Individual Sermons</h2>
    {sermon_cards}

    <footer>
      ★ = prioritized priest (1.4× weight) &nbsp;|&nbsp;
      Score = priest_weight × (0.5·views + 0.3·like_ratio + 0.2·recency)<br>
      Generated by Claude Opus 4.6 · YouTube Data API v3
    </footer>
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Email delivery (Google OAuth2 — same credentials as morning_brief.py)
# ---------------------------------------------------------------------------

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# Resolve paths relative to the *project root* (one level up from this file)
_PROJECT_ROOT   = Path(__file__).parent.parent
CREDENTIALS_FILE = _PROJECT_ROOT / "credentials.json"
TOKEN_FILE       = _PROJECT_ROOT / "token.json"


def _get_gmail_service():
    """Return an authenticated Gmail service, refreshing the token if needed."""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_FILE}. "
                    "Copy it from the morning brief setup."
                )
            flow  = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def send_email(html: str, run_date: str) -> None:
    my_email  = os.getenv("MY_EMAIL")
    recipient = os.getenv("EMAIL_RECIPIENT", my_email)

    if not my_email:
        console.print("[yellow]Email skipped — MY_EMAIL not set in .env[/yellow]")
        return

    msg            = MIMEMultipart("alternative")
    msg["Subject"] = f"☩ Coptic Sermon Digest — {run_date}"
    msg["From"]    = my_email
    msg["To"]      = recipient
    msg.attach(MIMEText(html, "html"))

    raw     = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service = _get_gmail_service()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()

    console.print(f"[green]Email sent to {recipient}[/green]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Coptic Orthodox Sermon Agent")
    parser.add_argument("--topic",    type=str,  default=None,  help="Filter by topic tag")
    parser.add_argument("--top",      type=int,  default=DEFAULT_TOP_N, help="Top N individual sermons")
    parser.add_argument("--no-email", action="store_true", help="Skip email delivery")
    args = parser.parse_args()

    youtube_key   = os.getenv("YOUTUBE_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if not youtube_key:
        console.print("[bold red]Error:[/bold red] YOUTUBE_API_KEY not set in .env"); return
    if not anthropic_key:
        console.print("[bold red]Error:[/bold red] ANTHROPIC_API_KEY not set in .env"); return

    youtube = build("youtube", "v3", developerKey=youtube_key)
    claude  = anthropic.Anthropic(api_key=anthropic_key)
    run_date = datetime.now().strftime("%B %Y")

    # ── 1. Fetch individual videos ─────────────────────────────────────────
    all_videos: list[dict] = []
    all_playlists: list[dict] = []

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("Fetching sermons from YouTube...", total=len(PRIESTS))
        for priest in PRIESTS:
            progress.update(task, description=f"Fetching: {priest['name']}...")
            videos    = search_videos(youtube, priest)
            playlists = search_playlists(youtube, priest)
            all_videos.extend(videos)
            all_playlists.extend(playlists)
            progress.advance(task)

    console.print(f"[green]Found {len(all_videos)} videos and {len(all_playlists)} playlists.[/green]")

    # ── 2. Score & rank individual videos ─────────────────────────────────
    max_views = max((v["views"] for v in all_videos), default=1)
    for v in all_videos:
        v["final_score"] = compute_score(v, max_views)

    all_videos.sort(key=lambda v: v["final_score"], reverse=True)
    candidates = all_videos[: args.top * 2]   # oversample before topic filter

    # ── 3. Fetch & score series ────────────────────────────────────────────
    series_data: list[dict] = []
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("Fetching playlist episodes...", total=len(all_playlists))
        for pl in all_playlists:
            progress.update(task, description=f"Playlist: {pl['title_ar'][:40]}...")
            episodes = fetch_playlist_videos(youtube, pl)
            if len(episodes) >= 2:           # only treat as series if 2+ episodes
                pl["episodes"]     = episodes
                pl["series_score"] = score_series(pl, episodes, max_views)
                series_data.append(pl)
            progress.advance(task)

    # Deduplicate playlists (same playlist_id) and sort
    seen_pids = set()
    unique_series = []
    for s in sorted(series_data, key=lambda x: x["series_score"], reverse=True):
        if s["playlist_id"] not in seen_pids:
            seen_pids.add(s["playlist_id"])
            unique_series.append(s)
    top_series = unique_series[:8]

    # ── 4. Translate with Claude ───────────────────────────────────────────
    console.print("[dim]Translating Arabic content with Claude Opus 4.6...[/dim]")

    # Translate individual sermons
    candidates = translate_and_summarize(claude, candidates)

    # Translate series titles + episode titles
    if top_series:
        series_meta = [{"title_ar": s["title_ar"], "description_ar": s.get("description_ar", "")} for s in top_series]
        series_meta = translate_and_summarize(claude, series_meta)
        for s, meta in zip(top_series, series_meta):
            s["english_title"] = meta.get("english_title", s["title_ar"])
            s["summary"]       = meta.get("summary", "")
            s["topic_tag"]     = meta.get("topic_tag", "Other")

        all_episodes = [ep for s in top_series for ep in s["episodes"]]
        if all_episodes:
            all_episodes = translate_and_summarize(claude, all_episodes)
            idx = 0
            for s in top_series:
                count = len(s["episodes"])
                s["episodes"] = all_episodes[idx : idx + count]
                idx += count

    # ── 5. Optional topic filter ───────────────────────────────────────────
    if args.topic:
        candidates  = [v for v in candidates  if args.topic.lower() in v["topic_tag"].lower()]
        top_series  = [s for s in top_series  if args.topic.lower() in s.get("topic_tag", "").lower()]

    top_sermons = candidates[: args.top]

    # ── 6. Generate HTML ───────────────────────────────────────────────────
    html = generate_html(top_sermons, top_series, run_date, args.topic)

    REPORTS_DIR.mkdir(exist_ok=True)
    filename = datetime.now().strftime("%Y-%m") + (".html" if not args.topic else f"-{args.topic.lower()}.html")
    report_path = REPORTS_DIR / filename
    report_path.write_text(html, encoding="utf-8")
    console.print(f"[green]HTML report saved → {report_path}[/green]")

    # ── 7. Email ───────────────────────────────────────────────────────────
    if not args.no_email:
        send_email(html, run_date)


if __name__ == "__main__":
    main()
