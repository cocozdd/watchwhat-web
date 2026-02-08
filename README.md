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
cd /Users/cocodzh/Documents/资料整理/笔记整理/watchwhat-web
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>.

## Notes

- Database path defaults to `/Users/cocodzh/.watchwhat/data/watchwhat.db`
- Cookie is memory-only for sync requests and is never persisted
- Data persists across app restarts unless DB file is deleted or moved
- Optional auto-cookie capture (opens a browser for Douban login) requires:
  - `pip install playwright`
  - `playwright install chromium`
