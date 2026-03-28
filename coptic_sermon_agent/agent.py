#!/usr/bin/env python3
"""
Coptic Orthodox Sermon Agent
Surfaces popular Arabic sermons by famous Coptic priests,
translated and ranked for English-speaking audiences.

Usage:
    python agent.py                  # Top 20 sermons across all priests
    python agent.py --topic Prayer   # Filter by topic
    python agent.py --top 10         # Show top N results
"""

import os
import json
import argparse
from datetime import datetime, timezone

import anthropic
from dotenv import load_dotenv
from googleapiclient.discovery import build
from rich import box
from rich.console import Console
from rich.table import Table

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
    {"name": "Fr. Daoud Lamei",           "arabic": "أبونا داود لمعي",             "weight": 1.4},  # prioritized
    {"name": "Fr. Bishoy Helmy",          "arabic": "أبونا بيشوى حلمى",            "weight": 1.0},
    {"name": "Fr. George Boules",         "arabic": "القمص بولس جورج",             "weight": 1.0},
    {"name": "Fr. Luka Maher",            "arabic": "أبونا لوقا ماهر",             "weight": 1.4},  # prioritized
    {"name": "Bishop Thomas",             "arabic": "الأنبا توماس",                "weight": 1.0},
]

RESULTS_PER_PRIEST = 8   # YouTube searches per priest
DEFAULT_TOP_N       = 20  # Final results to display


# ---------------------------------------------------------------------------
# YouTube helpers
# ---------------------------------------------------------------------------

def search_sermons(youtube, priest: dict) -> list[dict]:
    """Return sermon videos for one priest with view/like statistics."""
    query = f"{priest['arabic']} عظة"

    search_resp = youtube.search().list(
        q=query,
        part="snippet",
        maxResults=RESULTS_PER_PRIEST,
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
            "video_id":      item["id"],
            "priest":        priest["name"],
            "priest_weight": priest["weight"],
            "title_ar":      snippet.get("title", ""),
            "description_ar": snippet.get("description", "")[:600],
            "published_at":  snippet.get("publishedAt", ""),
            "views":         int(stats.get("viewCount", 0)),
            "likes":         int(stats.get("likeCount", 0)),
            "url":           f"https://youtube.com/watch?v={item['id']}",
        })

    return videos


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def compute_score(video: dict, max_views: int) -> float:
    """
    Composite score formula (before priest weight):
        0.5 × normalized_views  (raw popularity)
      + 0.3 × like_ratio        (engagement quality)
      + 0.2 × recency_score     (freshness: decays over ~1 year)

    Final score = priest_weight × composite
    """
    # Views (normalised against the most-viewed video in the set)
    normalized_views = video["views"] / max_views if max_views > 0 else 0.0

    # Like ratio — engagement quality signal
    like_ratio = video["likes"] / video["views"] if video["views"] > 0 else 0.0

    # Recency — decays to ~0.5 at 1 year, ~0.33 at 2 years
    try:
        published = datetime.fromisoformat(video["published_at"].replace("Z", "+00:00"))
        days_old  = (datetime.now(timezone.utc) - published).days
    except Exception:
        days_old = 365
    recency = 1.0 / (1.0 + days_old / 365.0)

    composite   = 0.5 * normalized_views + 0.3 * like_ratio + 0.2 * recency
    return video["priest_weight"] * composite


# ---------------------------------------------------------------------------
# Claude: Arabic → English translation & summarization
# ---------------------------------------------------------------------------

def translate_and_summarize(client: anthropic.Anthropic, videos: list[dict]) -> list[dict]:
    """
    Send Arabic sermon metadata to Claude Opus 4.6.
    Returns each video enriched with:
      - english_title
      - summary (2 sentences)
      - topic_tag
    """
    payload = [
        {
            "index":          i,
            "priest":         v["priest"],
            "title_ar":       v["title_ar"],
            "description_ar": v["description_ar"],
        }
        for i, v in enumerate(videos)
    ]

    system = (
        "You are an expert in Coptic Orthodox theology and fluent in Arabic. "
        "You translate Arabic sermon metadata into clear, natural English. "
        "Be concise and faithful to the original meaning."
    )

    user_prompt = f"""For each sermon below, return a JSON array. Each object must have:
- "index"         : same integer as in input
- "english_title" : natural English translation of title_ar
- "summary"       : exactly 2 sentences describing the sermon's topic and key message
- "topic_tag"     : exactly one of:
    Repentance | Prayer | Fasting | Love | Salvation | Marriage |
    Youth | Theology | Spiritual Life | Saints | Bible Study |
    Confession | Holy Spirit | Other

Input:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Return ONLY a valid JSON array — no markdown, no commentary."""

    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        response = stream.get_final_message()

    raw_text = next(b.text for b in response.content if b.type == "text")

    # Strip accidental markdown fences if present
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```", 2)[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.rsplit("```", 1)[0].strip()

    enriched = json.loads(raw_text)
    enriched_map = {item["index"]: item for item in enriched}

    for i, video in enumerate(videos):
        info = enriched_map.get(i, {})
        video["english_title"] = info.get("english_title", video["title_ar"])
        video["summary"]       = info.get("summary", "")
        video["topic_tag"]     = info.get("topic_tag", "Other")

    return videos


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def display_results(videos: list[dict], topic_filter: str | None) -> None:
    title = "Coptic Orthodox Sermons"
    if topic_filter:
        title += f" — Topic: {topic_filter}"

    table = Table(
        title=title,
        box=box.ROUNDED,
        show_lines=True,
        title_style="bold white",
        expand=False,
    )

    table.add_column("#",            style="dim",        width=3,  justify="right")
    table.add_column("Priest",       style="cyan",        width=22)
    table.add_column("Sermon (EN)",  style="bold white",  width=34)
    table.add_column("Topic",        style="yellow",      width=14)
    table.add_column("Views",        style="green",       width=9,  justify="right")
    table.add_column("Score",        style="magenta",     width=6,  justify="right")
    table.add_column("Summary",      style="white",       width=50)
    table.add_column("Link",         style="blue",        width=42)

    for rank, v in enumerate(videos, 1):
        star   = " [bold yellow]★[/bold yellow]" if v["priest_weight"] > 1.0 else ""
        priest = v["priest"] + star
        views  = f"{v['views']:,}"
        score  = f"{v['final_score']:.3f}"

        table.add_row(
            str(rank),
            priest,
            v["english_title"],
            v["topic_tag"],
            views,
            score,
            v["summary"],
            v["url"],
        )

    console.print()
    console.print(table)
    console.print(
        "\n[dim]"
        "★ = prioritized priest (1.4× weight)  |  "
        "Score = priest_weight × (0.5·views + 0.3·likes + 0.2·recency)"
        "[/dim]\n"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Coptic Orthodox Sermon Agent")
    parser.add_argument("--topic", type=str, default=None,
                        help="Filter by topic tag (e.g. Prayer, Repentance, Youth)")
    parser.add_argument("--top",   type=int, default=DEFAULT_TOP_N,
                        help=f"Number of results to display (default: {DEFAULT_TOP_N})")
    args = parser.parse_args()

    youtube_key   = os.getenv("YOUTUBE_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if not youtube_key:
        console.print("[bold red]Error:[/bold red] YOUTUBE_API_KEY not set in .env")
        return
    if not anthropic_key:
        console.print("[bold red]Error:[/bold red] ANTHROPIC_API_KEY not set in .env")
        return

    youtube = build("youtube", "v3", developerKey=youtube_key)
    claude  = anthropic.Anthropic(api_key=anthropic_key)

    # ── 1. Fetch from YouTube ──────────────────────────────────────────────
    all_videos: list[dict] = []
    for priest in PRIESTS:
        console.print(f"[dim]  Searching: {priest['name']}...[/dim]")
        videos = search_sermons(youtube, priest)
        all_videos.extend(videos)
        console.print(f"[dim]    → {len(videos)} videos found[/dim]")

    if not all_videos:
        console.print("[bold red]No sermons found. Check your YOUTUBE_API_KEY.[/bold red]")
        return

    console.print(f"\n[green]Fetched {len(all_videos)} sermons total.[/green]")

    # ── 2. Score & rank ───────────────────────────────────────────────────
    max_views = max(v["views"] for v in all_videos)
    for v in all_videos:
        v["final_score"] = compute_score(v, max_views)

    all_videos.sort(key=lambda v: v["final_score"], reverse=True)

    # Take more than needed before topic filter so we still get top N after
    candidates = all_videos[: args.top * 3]

    # ── 3. Translate & summarize with Claude ──────────────────────────────
    console.print("[dim]Translating Arabic content with Claude Opus 4.6...[/dim]")
    candidates = translate_and_summarize(claude, candidates)

    # ── 4. Optional topic filter ──────────────────────────────────────────
    if args.topic:
        candidates = [
            v for v in candidates
            if args.topic.lower() in v["topic_tag"].lower()
        ]
        if not candidates:
            console.print(
                f"[yellow]No results matched topic '[bold]{args.topic}[/bold]'. "
                f"Try one of: Repentance, Prayer, Fasting, Love, Salvation, "
                f"Marriage, Youth, Theology, Spiritual Life, Saints, "
                f"Bible Study, Confession, Holy Spirit, Other[/yellow]"
            )
            return

    top_results = candidates[: args.top]

    # ── 5. Display ────────────────────────────────────────────────────────
    display_results(top_results, args.topic)


if __name__ == "__main__":
    main()
