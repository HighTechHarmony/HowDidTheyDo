"""Core pipeline: fetch articles, classify predictions, analyse outcomes.

All output that was previously print()'d is captured in a debug_log list.
run_pipeline() returns a list of prediction dicts ready for DB insertion.
"""

import json
import os
import random
import re
import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dateutil import parser as dateparser
from openai import OpenAI

# Allow imports from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.config import (
    OPENAI_API_KEY, RSS_URL, WAYBACK_TIMEOUT, USE_BACKFEED,
    LLM_BACKEND, LLM_MODEL, OLLAMA_URL, OLLAMA_MODEL,
)
from src.prompts import PREDICTION_PROMPT, ANALYSIS_PROMPT

# ── LLM clients (initialised once at import time) ────────────────────────────
openai_client = OpenAI(api_key=OPENAI_API_KEY)


# ---------------------------------------------------------------------------
#  LLM call
# ---------------------------------------------------------------------------

def _llm_call(prompt, log, timeout=60):
    """Send a prompt to the configured LLM backend and return the raw text."""
    if LLM_BACKEND == "ollama":
        log.append(f"LLM call → ollama ({OLLAMA_MODEL})")
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")
    else:
        log.append(f"LLM call → openai ({LLM_MODEL})")
        response = openai_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            timeout=timeout,
        )
        return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
#  Wayback helpers
# ---------------------------------------------------------------------------

def _url_variants(url):
    """Return a list of URL variants to try against the Wayback Machine."""
    variants = []
    orig = url.strip()
    variants.append(orig)
    if not orig.endswith('/'):
        variants.append(orig + '/')
    else:
        variants.append(orig.rstrip('/'))

    if orig.startswith('https://'):
        variants.append('http://' + orig[len('https://'):])
    elif orig.startswith('http://'):
        variants.append('https://' + orig[len('http://'):])

    try:
        if '://' in orig:
            scheme, rest = orig.split('://', 1)
        else:
            scheme, rest = 'http', orig
        if rest.startswith('www.'):
            variants.append(f"{scheme}://{rest[4:]}")
            variants.append(f"http://{rest}")
        else:
            variants.append(f"{scheme}://www.{rest}")
            variants.append(f"http://www.{rest}")
    except Exception:
        pass

    seen = set()
    unique = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique.append(v)

    # prefer http first
    http  = [v for v in unique if v.startswith('http://')]
    other = [v for v in unique if not v.startswith('http://') and not v.startswith('https://')]
    https = [v for v in unique if v.startswith('https://')]
    return http + other + https


def check_wayback_availability(url, log):
    """Return a snapshot URL string or None."""
    for candidate in _url_variants(url):
        avail_url = f"http://archive.org/wayback/available?url={candidate}"
        log.append(f"Wayback availability URL: {avail_url}")
        try:
            r = requests.get(avail_url, timeout=WAYBACK_TIMEOUT)
            r.raise_for_status()
        except Exception as e:
            log.append(f"Wayback unavailable: {e}")
            return None

        try:
            data = r.json()
        except Exception:
            log.append("Wayback: could not parse availability response.")
            return None

        snap = data.get("archived_snapshots", {}).get("closest")
        if snap and snap.get("available"):
            archive_url = snap.get("url")
            timestamp = snap.get("timestamp")
            log.append(f"Wayback: found snapshot {timestamp} → {archive_url}")
            return archive_url

    log.append(f"Wayback: no archived snapshots found for {url} (tried variants).")
    return None


def pick_random_snapshot(url, log):
    """Return a random CDX timestamp, or None."""
    if check_wayback_availability(url, log) is None:
        return None

    cdx_url = (
        "http://web.archive.org/cdx/search/cdx"
        f"?url={url}&output=json&fl=timestamp&collapse=digest"
    )
    log.append(f"Wayback CDX URL: {cdx_url}")
    try:
        r = requests.get(cdx_url, timeout=WAYBACK_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.append(f"Wayback CDX error: {e}")
        return None

    timestamps = [row[0] for row in data[1:]]
    if not timestamps:
        log.append("Wayback CDX returned no snapshots.")
        return None

    chosen = random.choice(timestamps)
    log.append(f"Randomly selected snapshot: {chosen} (from {len(timestamps)} available)")
    return chosen


def fetch_archived_rss(url, timestamp, log):
    """Fetch archived RSS XML from the Wayback Machine."""
    archive_url = f"http://web.archive.org/web/{timestamp}/{url}"
    log.append(f"Fetching archived RSS from: {archive_url}")
    try:
        r = requests.get(archive_url, timeout=WAYBACK_TIMEOUT)
    except Exception as e:
        log.append(f"Fetch error: {e}")
        return None
    if r.status_code != 200:
        log.append(f"Fetch returned HTTP {r.status_code}")
        return None
    return r.text


# ---------------------------------------------------------------------------
#  RSS parsing
# ---------------------------------------------------------------------------

def parse_rss_items(xml_text):
    """Extract RSS items (title, summary, pubDate)."""
    soup = BeautifulSoup(xml_text, "xml")
    items = []
    for item in soup.find_all("item"):
        title = item.title.text if item.title else ""
        summary = item.description.text if item.description else ""
        # try to extract the article URL from <link> or <guid>
        link = ""
        if item.link and item.link.text:
            link = item.link.text.strip()
        elif item.guid and item.guid.text:
            link = item.guid.text.strip()
        pub = item.pubDate.text if item.pubDate else ""
        try:
            pub_date = dateparser.parse(pub)
        except Exception:
            continue
        if pub_date and pub_date.tzinfo:
            pub_date = pub_date.replace(tzinfo=None)
        items.append({"title": title, "summary": summary, "published": pub_date, "link": link})
    return items


def get_items(log):
    """Return (items_list, snapshot_timestamp_or_None)."""
    if not USE_BACKFEED:
        log.append("USE_BACKFEED disabled — fetching live RSS feed directly.")
        try:
            r = requests.get(RSS_URL, timeout=WAYBACK_TIMEOUT)
        except Exception as e:
            log.append(f"Live RSS fetch error: {e}")
            return [], None
        if r.status_code != 200:
            log.append(f"Live RSS returned HTTP {r.status_code}")
            return [], None
        return parse_rss_items(r.text), None

    ts = pick_random_snapshot(RSS_URL, log)
    if not ts:
        return [], None

    xml = fetch_archived_rss(RSS_URL, ts, log)
    if not xml:
        log.append(f"Failed to fetch archived RSS for snapshot {ts}.")
        return [], None

    return parse_rss_items(xml), ts


# ---------------------------------------------------------------------------
#  Classification
# ---------------------------------------------------------------------------

def _extract_json(raw):
    """Extract the first JSON object from a string."""
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return None


def _jaccard(a, b):
    def norm(s):
        s = (s or "").lower()
        s = re.sub(r"[^a-z0-9\s]", "", s)
        return set(w for w in s.split() if w)
    A, B = norm(a), norm(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def classify_article(item, log):
    """Classify a single article. Returns a result dict or None."""
    pub = item.get("published")
    article_date = pub.strftime("%Y-%m-%d") if pub else "unknown"

    prompt = PREDICTION_PROMPT.format(
        headline=item.get("title", ""),
        summary=(item.get("summary") or "")[:500],
        article_date=article_date,
    )

    try:
        raw = _llm_call(prompt, log, timeout=60)
    except Exception as e:
        log.append(f"[LLM error] {e}")
        return None

    result = _extract_json(raw)
    if result is None:
        log.append(f"[LLM parse error] No JSON in response: {raw[:200]}")
        return None

    # Similarity post-processing
    pred = result.get("prediction_text")
    summary = item.get("summary") or ""
    title = item.get("title") or ""
    SIM = 0.8

    too_similar = False
    if pred:
        if pred.strip().lower() in (summary.strip().lower(), title.strip().lower()):
            too_similar = True
        elif _jaccard(pred, summary) >= SIM or _jaccard(pred, title) >= SIM:
            too_similar = True

    if too_similar:
        para_prompt = (
            f"Paraphrase the following prediction in different words, concise (5-20 words).\n"
            f"Original prediction: \"{pred}\"\nSummary: \"{summary}\"\nHeadline: \"{title}\"\n"
            "Return ONLY the paraphrase text with no extra commentary."
        )
        try:
            raw2 = _llm_call(para_prompt, log, timeout=30)
            para = None
            for line in raw2.splitlines():
                line = line.strip()
                if line:
                    para = line.strip('"')
                    break
            if para and _jaccard(para, summary) < SIM and _jaccard(para, title) < SIM:
                result["prediction_text"] = para
            else:
                result["is_prediction"] = False
                result["prediction_text"] = None
                result["timeframe_phrase"] = None
                result["target_year"] = None
        except Exception:
            result["is_prediction"] = False
            result["prediction_text"] = None
            result["timeframe_phrase"] = None
            result["target_year"] = None

    return result


# ---------------------------------------------------------------------------
#  Analysis
# ---------------------------------------------------------------------------

def analyze_prediction(classification, item, log):
    """Evaluate a prediction against real-world outcomes."""
    pub = item.get("published")
    article_date = pub.strftime("%Y-%m-%d") if pub else "unknown"
    prediction_text = classification.get("prediction_text") or ""
    target_year = classification.get("target_year")

    prompt = (
        ANALYSIS_PROMPT
        .replace("{{prediction}}", prediction_text)
        .replace("{{target_year}}", str(target_year) if target_year else "unknown")
        .replace("{{article_date}}", article_date)
    )

    try:
        raw = _llm_call(prompt, log, timeout=90)
    except Exception as e:
        log.append(f"[Analysis LLM error] {e}")
        return None

    result = _extract_json(raw)
    if result is None:
        log.append(f"[Analysis parse error] No JSON in response: {raw[:200]}")
    return result


# ---------------------------------------------------------------------------
#  Main pipeline entry point
# ---------------------------------------------------------------------------

def run_pipeline():
    """Run the full fetch → classify → analyse pipeline.

    Returns a list of prediction dicts ready for DB insertion.
    Each dict has: title, summary, published, snapshot_ts, rss_url,
                   prediction, timeframe, target_year,
                   score, explanation, facts, debug_log, created_at.
    """
    now = datetime.utcnow().isoformat()
    log = []
    log.append(f"Pipeline run started at {now}")
    log.append(f"Config: RSS_URL={RSS_URL}, USE_BACKFEED={USE_BACKFEED}, "
               f"LLM_BACKEND={LLM_BACKEND}")

    items, snapshot_ts = get_items(log)
    log.append(f"Fetched {len(items)} article(s)")

    if not items:
        log.append("No articles fetched — aborting run.")
        return []

    active_model = OLLAMA_MODEL if LLM_BACKEND == "ollama" else LLM_MODEL
    log.append(f"Classifying with {active_model} ({LLM_BACKEND})...")

    predictions = []
    for item in items:
        title_short = (item.get("title") or "")[:80]
        log.append(f"→ {title_short}")

        classification = classify_article(item, log)
        if not classification or not classification.get("is_prediction"):
            log.append(f"  [no prediction]")
            continue

        log.append(f"  [PREDICTION] {classification.get('prediction_text')}")
        if classification.get("target_year"):
            log.append(f"    Target year: {classification['target_year']} "
                       f"(phrase: \"{classification.get('timeframe_phrase')}\")")

        # Analyse
        analysis = analyze_prediction(classification, item, log)
        score = None
        explanation = None
        facts = []
        if analysis:
            score = analysis.get("score")
            explanation = analysis.get("explanation")
            facts = analysis.get("facts_used") or []
            log.append(f"  Score: {score}, Explanation: {explanation}")
        else:
            log.append("  Analysis unavailable.")

        pub = item.get("published")
        predictions.append({
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "published": pub.isoformat() if pub else None,
            "snapshot_ts": snapshot_ts,
            "rss_url": RSS_URL,
            "article_url": item.get("link") or None,
            "prediction": classification.get("prediction_text"),
            "timeframe": classification.get("timeframe_phrase"),
            "target_year": classification.get("target_year"),
            "score": score,
            "explanation": explanation,
            "facts": facts,
            "debug_log": list(log),  # snapshot of log up to this point
            "created_at": now,
        })

    log.append(f"Pipeline complete — {len(predictions)} prediction(s) found.")
    return predictions, log
