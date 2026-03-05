import json
import random
import re
import requests
import sys
import threading
import time
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dateutil import parser as dateparser
from openai import OpenAI
from prompts import PREDICTION_PROMPT, ANALYSIS_PROMPT
from config import OPENAI_API_KEY

# Pick any RSS feed you want to test.
RSS_URL = "https://www.marketwatch.com/rss/topstories"
# Timeout (seconds) for requests to web.archive.org (Wayback Machine)
WAYBACK_TIMEOUT = 60
# Set to 1 to fetch historical articles from the Wayback Machine
# Set to 0 to disable backfeed and fetch the live RSS feed directly
USE_BACKFEED = 1

# ── LLM backend settings ─────────────────────────────────────────────────────
# Set LLM_BACKEND to "openai" to use ChatGPT, or "ollama" for a local model.
#LLM_BACKEND  = "ollama"
LLM_BACKEND  = "openai"

# OpenAI
LLM_MODEL    = "gpt-4.1"
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Ollama (used when LLM_BACKEND = "ollama")
OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "granite4:350m"


def _llm_call(prompt, timeout=60):
    """Send a prompt to the configured LLM backend and return the raw text response."""
    # spinner helper
    def _spinner(stop_event, message="Waiting for LLM..."):
        chars = "|/-\\"
        idx = 0
        while not stop_event.is_set():
            sys.stdout.write(f"\r{message} {chars[idx % len(chars)]}")
            sys.stdout.flush()
            idx += 1
            time.sleep(0.12)
        # clear line on stop
        sys.stdout.write("\r" + " " * (len(message) + 4) + "\r")
        sys.stdout.flush()

    stop_evt = threading.Event()
    spinner_thread = threading.Thread(target=_spinner, args=(stop_evt, f"Waiting for {LLM_BACKEND}..."))
    spinner_thread.daemon = True
    spinner_thread.start()
    if LLM_BACKEND == "ollama":
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        resp.raise_for_status()
        out = resp.json().get("response", "")
        stop_evt.set()
        spinner_thread.join()
        return out
    else:  # openai
        response = openai_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            timeout=timeout,
        )
        out = response.choices[0].message.content or ""
        stop_evt.set()
        spinner_thread.join()
        return out


def check_wayback_availability(url):
    """Check if the Wayback Machine has an archived snapshot for the given URL.

    Returns the closest snapshot URL string on success, or None on failure.
    Prints a human-readable reason if the archive is unavailable.
    """
    avail_url = f"https://archive.org/wayback/available?url={url}"
    # Try a set of normalized URL variants to improve availability hits.
    variants = []
    orig = url.strip()
    # ensure no duplicate
    variants.append(orig)

    # trailing slash variants
    if not orig.endswith('/'):
        variants.append(orig + '/')
    else:
        variants.append(orig.rstrip('/'))

    # swap http/https
    if orig.startswith('https://'):
        variants.append('http://' + orig[len('https://'):])
    elif orig.startswith('http://'):
        variants.append('https://' + orig[len('http://'):])
    else:
        variants.append('http://' + orig)
        variants.append('https://' + orig)

    # add/remove www
    hostless = orig
    try:
        # quick parse: split scheme
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

    # unique preserve order
    seen = set()
    tried = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            tried.append(v)

    # Prefer http variants first (older snapshots often use http)
    http_first = [v for v in tried if v.startswith('http://')]
    others = [v for v in tried if not v.startswith('http://') and not v.startswith('https://')]
    https_rest = [v for v in tried if v.startswith('https://')]
    tried = http_first + others + https_rest

    for candidate in tried:
        avail_url = f"http://archive.org/wayback/available?url={candidate}"
        print(f"Wayback availability URL: {avail_url}")
        try:
            r = requests.get(avail_url, timeout=WAYBACK_TIMEOUT)
            r.raise_for_status()
        except requests.exceptions.ConnectionError:
            print("Wayback Machine unavailable: could not connect to archive.org.")
            return None
        except requests.exceptions.Timeout:
            print("Wayback Machine unavailable: request timed out.")
            return None
        except requests.exceptions.HTTPError as e:
            print(f"Wayback Machine unavailable: HTTP error {e.response.status_code}.")
            return None
        except Exception as e:
            print(f"Wayback Machine unavailable: {e}")
            return None

        try:
            data = r.json()
        except Exception:
            print("Wayback Machine unavailable: could not parse availability response.")
            return None

        snap = data.get("archived_snapshots", {}).get("closest")
        if not snap:
            # try next candidate
            continue
        if not snap.get("available"):
            # try next candidate
            continue

        archive_url = snap.get("url")
        timestamp   = snap.get("timestamp")
        print(f"Wayback Machine: found snapshot {timestamp} → {archive_url}")
        return archive_url

    print(f"Wayback Machine: no archived snapshots found for {url} (after trying variants).")
    return None
    print(f"Wayback availability URL: {avail_url}")
    try:
        r = requests.get(avail_url, timeout=WAYBACK_TIMEOUT)
        r.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("Wayback Machine unavailable: could not connect to archive.org.")
        return None
    except requests.exceptions.Timeout:
        print("Wayback Machine unavailable: request timed out.")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"Wayback Machine unavailable: HTTP error {e.response.status_code}.")
        return None
    except Exception as e:
        print(f"Wayback Machine unavailable: {e}")
        return None

    try:
        data = r.json()
    except Exception:
        print("Wayback Machine unavailable: could not parse availability response.")
        return None

    snap = data.get("archived_snapshots", {}).get("closest")
    if not snap:
        print(f"Wayback Machine: no archived snapshots found for {url}.")
        return None
    if not snap.get("available"):
        print(f"Wayback Machine: closest snapshot is not available (status={snap.get('status')}).")
        return None

    archive_url = snap.get("url")
    timestamp   = snap.get("timestamp")
    print(f"Wayback Machine: found snapshot {timestamp} → {archive_url}")
    return archive_url


def get_wayback_snapshots(url, limit=10):
    """Return a list of CDX snapshot timestamps, but only after confirming availability.

    Returns an empty list (with a printed reason) if the Wayback Machine is
    unreachable or has no snapshot for the URL.
    """
    # Gate on availability first — fail fast with a clear message.
    if check_wayback_availability(url) is None:
        return []

    cdx_url = (
        "http://web.archive.org/cdx/search/cdx"
        f"?url={url}&output=json&fl=timestamp&collapse=digest"
    )
    try:
        r = requests.get(cdx_url, timeout=WAYBACK_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Wayback Machine CDX error: {e}")
        return []

    # First row is the header
    timestamps = [row[0] for row in data[1:]]
    return timestamps[:limit]


def pick_random_snapshot(url):
    """Return a single randomly chosen timestamp from the full CDX snapshot list.

    Returns None (with a printed reason) if availability check fails or no
    snapshots exist.
    """
    # Confirm the archive is reachable before doing heavier CDX work.
    if check_wayback_availability(url) is None:
        return None

    cdx_url = (
        "http://web.archive.org/cdx/search/cdx"
        f"?url={url}&output=json&fl=timestamp&collapse=digest"
    )
    print(f"Wayback CDX URL: {cdx_url}")
    try:
        r = requests.get(cdx_url, timeout=WAYBACK_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Wayback Machine CDX error: {e}")
        return None

    timestamps = [row[0] for row in data[1:]]
    if not timestamps:
        print("Wayback Machine: CDX returned no snapshots.")
        return None

    chosen = random.choice(timestamps)
    print(f"Randomly selected snapshot: {chosen} (from {len(timestamps)} available)")
    return chosen

def fetch_archived_rss(url, timestamp):
    """Fetch archived RSS XML from the Wayback Machine."""
    archive_url = f"http://web.archive.org/web/{timestamp}/{url}"
    print(f"Fetching archived RSS from: {archive_url}")
    r = requests.get(archive_url, timeout=WAYBACK_TIMEOUT)
    if r.status_code != 200:
        return None
    return r.text

def parse_rss_items(xml_text):
    """Extract RSS items (title, summary, pubDate)."""
    soup = BeautifulSoup(xml_text, "xml")
    items = []

    for item in soup.find_all("item"):
        title = item.title.text if item.title else ""
        summary = item.description.text if item.description else ""
        pub = item.pubDate.text if item.pubDate else ""

        try:
            pub_date = dateparser.parse(pub)
        except:
            continue
        # Normalize to naive datetime for consistent comparisons
        try:
            if getattr(pub_date, "tzinfo", None) is not None:
                pub_date = pub_date.replace(tzinfo=None)
        except Exception:
            pass
        items.append({
            "title": title,
            "summary": summary,
            "published": pub_date
        })

    return items

def get_items_from_timeframe():
    """Return RSS items either from the live feed or a random Wayback snapshot."""
    # If user disabled backfeed, fetch the live RSS feed directly.
    if not USE_BACKFEED:
        print("USE_BACKFEED disabled — fetching live RSS feed directly.\n")
        try:
            r = requests.get(RSS_URL, timeout=WAYBACK_TIMEOUT)
        except Exception:
            return []

        if r.status_code != 200:
            return []

        return parse_rss_items(r.text)

    ts = pick_random_snapshot(RSS_URL)
    if not ts:
        return []

    xml = fetch_archived_rss(RSS_URL, ts)
    if not xml:
        print(f"Failed to fetch archived RSS for snapshot {ts}.")
        return []

    return parse_rss_items(xml)


def classify_article(item):
    """Classify an article using the configured LLM and return parsed classification JSON.

    Returns a dict with keys: is_prediction, prediction_text, timeframe_phrase, target_year.
    Returns None if the API call fails or the response cannot be parsed.
    """
    pub = item.get("published")
    article_date = pub.strftime("%Y-%m-%d") if pub else "unknown"

    prompt = PREDICTION_PROMPT.format(
        headline=item.get("title", ""),
        summary=(item.get("summary") or "")[:500],
        article_date=article_date,
    )

    try:
        raw = _llm_call(prompt, timeout=60)
    except Exception as e:
        print(f"  [LLM error] {e}")
        return None

    # Extract the first JSON object from the response (model may include surrounding text)
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end == 0:
        print(f"  [LLM parse error] No JSON found in response:\n    {raw[:200]}")
        return None

    try:
        result = json.loads(raw[start:end])
    except json.JSONDecodeError as e:
        print(f"  [LLM parse error] {e}\n    {raw[start:end][:200]}")
        return None

    # Post-process to avoid verbatim copying: if the predicted text is too similar
    # to the headline or summary, request a concise paraphrase. If paraphrase still
    # looks like a copy, mark as no strong prediction.
    def _normalize(s):
        s = (s or "").lower()
        s = re.sub(r"[^a-z0-9\s]", "", s)
        return set([w for w in s.split() if w])

    def _jaccard(a, b):
        A = _normalize(a)
        B = _normalize(b)
        if not A or not B:
            return 0.0
        return len(A & B) / len(A | B)

    pred = result.get("prediction_text")
    summary = (item.get("summary") or "")
    title = (item.get("title") or "")

    SIM_THRESHOLD = 0.8

    too_similar = False
    if pred:
        if pred.strip().lower() == summary.strip().lower() or pred.strip().lower() == title.strip().lower():
            too_similar = True
        elif _jaccard(pred, summary) >= SIM_THRESHOLD or _jaccard(pred, title) >= SIM_THRESHOLD:
            too_similar = True

    if too_similar:
        # ask the LLM to paraphrase the prediction in different words
        para_prompt = (
            f"Paraphrase the following prediction in different words, concise (5-20 words)."
            f"\nOriginal prediction: \"{pred}\"\nSummary: \"{summary}\"\nHeadline: \"{title}\"\n"
            "Return ONLY the paraphrase text with no extra commentary."
        )
        try:
            raw2 = _llm_call(para_prompt, timeout=30)
            # take first non-empty line
            para = None
            for line in raw2.splitlines():
                line = line.strip()
                if line:
                    para = line
                    break
            if para:
                # strip surrounding quotes
                para = para.strip('"')
                if _jaccard(para, summary) < SIM_THRESHOLD and _jaccard(para, title) < SIM_THRESHOLD:
                    result["prediction_text"] = para
                else:
                    result["is_prediction"] = False
                    result["prediction_text"] = None
                    result["timeframe_phrase"] = None
                    result["target_year"] = None
            else:
                result["is_prediction"] = False
                result["prediction_text"] = None
                result["timeframe_phrase"] = None
                result["target_year"] = None
        except Exception:
            # if paraphrase attempt fails, conservatively drop
            result["is_prediction"] = False
            result["prediction_text"] = None
            result["timeframe_phrase"] = None
            result["target_year"] = None

    return result


def analyze_prediction(classification, item):
    """Evaluate a prediction against real-world outcomes using the LLM.

    Returns a dict with keys: score, explanation, facts_used.
    Returns None if the call fails or the response cannot be parsed.
    """
    pub = item.get("published")
    article_date = pub.strftime("%Y-%m-%d") if pub else "unknown"
    prediction_text = classification.get("prediction_text") or ""
    target_year = classification.get("target_year")

    # ANALYSIS_PROMPT uses {{double_braces}} for variables so the raw JSON
    # block inside the prompt doesn't interfere with Python .format().
    prompt = (
        ANALYSIS_PROMPT
        .replace("{{prediction}}", prediction_text)
        .replace("{{target_year}}", str(target_year) if target_year else "unknown")
        .replace("{{article_date}}", article_date)
    )

    try:
        raw = _llm_call(prompt, timeout=90)
    except Exception as e:
        print(f"  [Analysis LLM error] {e}")
        return None

    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end == 0:
        print(f"  [Analysis parse error] No JSON found:\n    {raw[:200]}")
        return None

    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError as e:
        print(f"  [Analysis parse error] {e}\n    {raw[start:end][:200]}")
        return None


def _score_bar(score):
    """Return a small ASCII bar visualising a -10..+10 score."""
    if score is None:
        return ""
    clamped = max(-10, min(10, int(score)))
    filled  = abs(clamped)
    if clamped >= 0:
        return "[" + " " * 10 + ">" + "█" * filled + "]  ✓" * (clamped >= 7)
    else:
        return "[" + "█" * filled + "<" + " " * 10 + "]  ✗" * (clamped <= -7)


def main():
    print("Fetching articles...\n")
    items = get_items_from_timeframe()

    if not items:
        print("No items found in this timeframe.")
        return

    active_model = OLLAMA_MODEL if LLM_BACKEND == "ollama" else LLM_MODEL
    print(f"Classifying {len(items)} article(s) with {active_model} ({LLM_BACKEND})...\n")
    predictions = []

    for item in items:
        print(f"  -> {item['title'][:80]}")
        result = classify_article(item)
        if result and result.get("is_prediction"):
            predictions.append({"item": item, "classification": result})
            print(f"     [PREDICTION] {result.get('prediction_text')}")
            if result.get("target_year"):
                print(f"       Target year: {result['target_year']} "
                      f"(phrase: \"{result.get('timeframe_phrase')}\")"
                     )
        else:
            print(f"     [no prediction]")
        print()

    print("-" * 70)
    print(f"\nFound {len(predictions)} prediction article(s). Analyzing outcomes...\n")
    for i, p in enumerate(predictions, 1):
        item   = p["item"]
        result = p["classification"]

        print(f"{i}. {item['title']}")
        print(f"   Published  : {item['published']}")
        print(f"   Prediction : {result.get('prediction_text')}")
        print(f"   Timeframe  : {result.get('timeframe_phrase')} -> {result.get('target_year')}")
        if item.get("summary"):
            print(f"   Summary    : {item['summary'][:200]}")

        analysis = analyze_prediction(result, item)
        if analysis:
            score = analysis.get("score")
            bar   = _score_bar(score)
            print(f"   Score      : {score:+d}/10  {bar}")
            print(f"   Analysis   : {analysis.get('explanation')}")
            facts = analysis.get("facts_used") or []
            if facts:
                print(f"   Facts      :")
                for fact in facts:
                    print(f"     • {fact}")
        else:
            print("   Analysis   : (unavailable)")
        print()

if __name__ == "__main__":
    main()
