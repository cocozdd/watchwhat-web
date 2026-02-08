# WatchWhat Web

Local-first private recommendation web app.

## Features

- Sync Douban movie/tv/book history by username
- Persist data locally with SQLite WAL enabled
- Recommend unseen items based on history + natural-language intent
- Optional one-turn follow-up when confidence is low
- DeepSeek API integration (OpenAI-compatible)

## Quick start

```bash
git clone https://github.com/cocozdd/watchwhat-web.git
cd watchwhat-web
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Edit .env and set WATCHWHAT_DEEPSEEK_API_KEY if you want LLM reranking.
./start_watchwhat.sh
```

Open <http://127.0.0.1:8000>.

Stop service:

```bash
./stop_watchwhat.sh
```

Manual run (without helper scripts):

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Notes

- Python 3.9+ is required.
- Default database path is `~/.watchwhat/data/watchwhat.db` (configurable via `WATCHWHAT_DB_PATH`).
- Login cookie can be persisted locally by default (`WATCHWHAT_PERSIST_COOKIE_ON_DISK=true`) to avoid re-login.
- Cookie is stored in local JSON file (`WATCHWHAT_COOKIE_STORE_PATH`) and is not written into SQLite.
- Data persists across app restarts unless DB file is deleted or moved
- Optional auto-cookie capture (opens a browser for Douban login) requires:
  - `pip install playwright`
  - `playwright install chromium`
