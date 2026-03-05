# How Did They Do?

Fetches old news headlines from the [Wayback Machine](https://web.archive.org/),
uses an LLM to identify articles that made specific predictions, and evaluates
those predictions against real-world outcomes — scoring each one on a −10 to +10
scale. Results are stored in a SQLite database and presented in a React web UI
with upvote/downvote voting.

## Architecture

```
┌─────────────────────┐     SQLite      ┌────────────────────┐
│   backend/daemon.py │ ──────────────► │  data/predictions  │
│  (runs periodically)│                 │       .db          │
└─────────────────────┘                 └────────┬───────────┘
                                                 │
                                        ┌────────▼───────────┐
                                        │  backend/api.py    │
                                        │  Flask REST API    │
                                        │  :5000             │
                                        └────────┬───────────┘
                                                 │ /api/predictions/*
                                        ┌────────▼───────────┐
                                        │  frontend/         │
                                        │  React + Tailwind  │
                                        │  Vite dev :5173    │
                                        └────────────────────┘
```

### Pipeline (one run)

1. **Fetch** — Picks a random historical snapshot from the Wayback Machine CDX
   index, or falls back to the live RSS feed (`USE_BACKFEED = 0`).
2. **Classify** — Each headline + summary is sent to the LLM. Articles
   containing a clear, specific prediction are flagged, with the prediction text,
   timeframe phrase, and target year extracted.
3. **Analyse** — Each flagged prediction is sent back to the LLM, which
   compares it to real-world outcomes, assigns a score (−10 to +10), and
   explains its reasoning.
4. **Store** — Results are written to SQLite (duplicates silently ignored).

The daemon runs the pipeline up to `MAX_RUNS_PER_INTERVAL` times per interval,
stopping early once `TARGET_PREDICTIONS_PER_INTERVAL` new predictions are
inserted.

---

## Requirements

- Python 3.10+
- Node.js 18+
- An OpenAI API key **or** a local [Ollama](https://ollama.com/) server

---

## Setup

### 1. Python environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configuration

Edit `src/config.py` (git-ignored) and set your API key and preferences:

```python
OPENAI_API_KEY = "sk-..."
```

See the [Configuration reference](#configuration-reference) below for all options.

### 3. Frontend

```bash
cd frontend
npm install
```

---

## Running

### Start / stop all services

```bash
# Start API + daemon in background (logs → logs/)
./scripts/manage_services.sh start

# Stop both
./scripts/manage_services.sh stop

# Restart
./scripts/manage_services.sh restart

# Check what's running
./scripts/manage_services.sh status
```

Logs are written to `logs/api.log` and `logs/daemon.log`.
PID files live in `data/api.pid` and `data/daemon.pid`.

### Frontend dev server

```bash
cd frontend
npm run dev        # http://localhost:5173  (proxies /api → :5000)
```

### Run the CLI pipeline once (no daemon)

```bash
.venv/bin/python src/main.py
```

---

## Configuration reference

All settings live in `src/config.py`.

| Variable                          | Default                               | Purpose                                                         |
| --------------------------------- | ------------------------------------- | --------------------------------------------------------------- |
| `OPENAI_API_KEY`                  | —                                     | OpenAI API key (required when `LLM_BACKEND = "openai"`)         |
| `RSS_URL`                         | MarketWatch top stories               | RSS feed to analyse                                             |
| `WAYBACK_TIMEOUT`                 | `60`                                  | HTTP timeout in seconds for Wayback requests                    |
| `USE_BACKFEED`                    | `1`                                   | `1` = random Wayback snapshot · `0` = live feed                 |
| `LLM_BACKEND`                     | `"openai"`                            | `"openai"` or `"ollama"`                                        |
| `LLM_MODEL`                       | `"gpt-4.1"`                           | OpenAI model name                                               |
| `OLLAMA_URL`                      | `http://localhost:11434/api/generate` | Ollama endpoint (when `LLM_BACKEND = "ollama"`)                 |
| `OLLAMA_MODEL`                    | `"granite4:350m"`                     | Ollama model name                                               |
| `RUN_INTERVAL_SECONDS`            | `7200`                                | How often the daemon runs (seconds)                             |
| `MAX_RUNS_PER_INTERVAL`           | `4`                                   | Maximum pipeline attempts per interval                          |
| `TARGET_PREDICTIONS_PER_INTERVAL` | `4`                                   | Stop attempts early once this many new predictions are inserted |
| `RUN_ATTEMPT_DELAY_SECONDS`       | `10`                                  | Pause between repeated attempts within one interval             |
| `DB_PATH`                         | `data/predictions.db`                 | SQLite database path                                            |

---

## API endpoints

| Method | Path                         | Description                                |
| ------ | ---------------------------- | ------------------------------------------ | -------- |
| GET    | `/api/predictions/recent`    | Latest 10 predictions, sorted by net votes |
| GET    | `/api/predictions/top`       | Top 10 all-time by net votes               |
| POST   | `/api/predictions/<id>/vote` | Cast a vote — body: `{"direction":"up"     | "down"}` |

---

## Project structure

```
howdidtheydo/
├── backend/
│   ├── api.py          Flask REST API (port 5000)
│   ├── daemon.py       Background loop: pipeline → SQLite
│   ├── db.py           SQLite helpers (init, insert, vote, query)
│   └── pipeline.py     Core fetch / classify / analyse logic
├── frontend/
│   └── src/
│       ├── App.jsx                 Tab layout, polling
│       ├── components/
│       │   ├── PredictionCard.jsx  Card layout with date prefix
│       │   ├── ScoreBar.jsx        −10 … +10 colour bar
│       │   ├── VoteButtons.jsx     Up/down with localStorage dedup
│       │   └── DebugLog.jsx        Collapsible pipeline log
│       └── hooks/useVote.js        Vote state persisted to localStorage
├── src/
│   ├── config.py       All settings (git-ignored)
│   ├── prompts.py      LLM prompt templates
│   └── main.py         Standalone CLI pipeline script
├── scripts/
│   └── manage_services.sh   start / stop / restart / status
├── data/               SQLite DB + PID files (git-ignored)
├── logs/               Service logs (git-ignored)
└── requirements.txt
```

---

## Notes

- **Wayback rate limits** — The Wayback Machine can be slow. `WAYBACK_TIMEOUT = 60`
  helps, but occasional failures are normal. Set `USE_BACKFEED = 0` to use the
  live feed instead.
- **URL variant probing** — The availability check tries http/https, www/no-www,
  and trailing-slash variants to maximise snapshot discovery.
- **Duplicate suppression** — `INSERT OR IGNORE` on `(title, published, rss_url)`
  means re-running the pipeline on the same snapshot is safe.
- **LLM verbatim check** — If the LLM returns a prediction that is too similar
  to the article summary (Jaccard ≥ 0.8), a paraphrase is requested automatically.
- **Switching LLM backends** — Change `LLM_BACKEND` in `src/config.py` and
  restart the daemon. The frontend has no control over the model.

### Building the frontend (production)

1. Ensure Node.js 18+ is installed on the server.

2. From the project root, install deps and build the static assets:

   cd frontend
   npm install # installs Vite and frontend dependencies locally
   npm run build # produces production assets in frontend/dist

3. Preview or serve the built files (optional):

   # quick preview (uses local vite preview)

   npx vite preview --port 5173

   # or configure your webserver (nginx) or Flask/Gunicorn to serve frontend/dist as static files
