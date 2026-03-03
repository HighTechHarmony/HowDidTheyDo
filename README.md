# How Did They Do?

Fetches old news headlines from the [Wayback Machine](https://web.archive.org/),
uses an LLM to identify articles that made specific predictions, and then
evaluates those predictions against real-world outcomes — scoring each one on a
−10 to +10 scale.

## How It Works

1. **Fetch** — Either pulls a live RSS feed directly, or picks a random
   historical snapshot from the Wayback Machine CDX index.
2. **Classify** — Each headline + summary is sent to the LLM with a structured
   prompt. Articles that contain a clear, specific prediction (especially in
   tech or finance) are flagged, along with the prediction text, timeframe
   phrase, and target year.
3. **Analyze** — Each flagged prediction is re-sent to the LLM, which retrieves
   facts, compares the prediction to reality, assigns a score, and explains its
   reasoning.

## Requirements

- Python 3.10+
- An OpenAI API key **or** a local [Ollama](https://ollama.com/) server

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copy `config.py` and fill in your key (it is git-ignored):

```python
# config.py
OPENAI_API_KEY = "sk-..."
```

## Key Variables (`main2.py`)

| Variable | Default | Purpose |
|---|---|---|
| `RSS_URL` | MarketWatch top stories | RSS feed to analyse |
| `USE_BACKFEED` | `1` | `1` = random Wayback snapshot, `0` = live feed |
| `LLM_BACKEND` | `"openai"` | `"openai"` or `"ollama"` |
| `LLM_MODEL` | `"gpt-4.1"` | OpenAI model name |
| `OLLAMA_MODEL` | `"granite4:350m"` | Ollama model name (when backend is `"ollama"`) |
| `WAYBACK_TIMEOUT` | `60` | Request timeout in seconds (Wayback is slow) |

## Usage

```bash
# Run with a random historical snapshot (USE_BACKFEED = 1)
.venv/bin/python main2.py

# Run against the live feed (set USE_BACKFEED = 0 in main2.py)
.venv/bin/python main2.py
```

### Example Output

```
Fetching articles...

Wayback availability URL: http://archive.org/wayback/available?url=http://www.marketwatch.com/rss/topstories
Wayback Machine: found snapshot 20120727220238 → http://web.archive.org/web/...
Randomly selected snapshot: 20120727220238 (from 1498 available)

Classifying 10 article(s) with gpt-4.1 (openai)...

  -> Apple planning significant AI features for next iPhone cycle
     [PREDICTION] Apple intends to ship major AI capabilities in the next iPhone.
       Target year: 2013 (phrase: "next year")

----------------------------------------------------------------------

Found 1 prediction article(s). Analyzing outcomes...

1. Apple planning significant AI features for next iPhone cycle
   Published  : 2012-07-27 21:00:00
   Prediction : Apple intends to ship major AI capabilities in the next iPhone.
   Timeframe  : next year -> 2013
   Score      : +4/10  [          >████]
   Analysis   : Apple introduced Siri improvements in iOS 7 (2013) but fell
                short of "significant AI features" by later standards.
   Facts      :
     • iOS 7 shipped September 2013 with incremental Siri updates.
     • Dedicated neural hardware did not arrive until the A11 Bionic in 2017.
```

## Files

| File | Purpose |
|---|---|
| `main2.py` | Main script — fetch, classify, analyse |
| `prompts.py` | LLM prompt templates (`PREDICTION_PROMPT`, `ANALYSIS_PROMPT`) |
| `config.py` | API keys (git-ignored) |
| `requirements.txt` | Python dependencies |

## Notes

- The Wayback Machine can be slow or rate-limited. `WAYBACK_TIMEOUT = 60` helps
  but you may still see occasional failures. Set `USE_BACKFEED = 0` to bypass it.
- The availability endpoint tries several URL variants (http/https, www, trailing
  slash) to maximise the chance of finding a snapshot.
- Both LLM calls (classification and analysis) show a spinner while waiting.
