# CLAUDE.md - arXiv Subscriber Project

> Instructions for Claude Code when working on this project

## Project Overview
Python tool to subscribe to and track new Computer Science papers from arXiv with Notion integration.
Repository: https://github.com/guisongchen/arxiv-subscriber

## Features Implemented

- **Paper fetching** from arXiv CS categories (AI, CV, ML, Robotics)
- **Notion integration** - syncs papers to Notion database automatically
- **Code repository detection** - auto-detects GitHub/GitLab/HuggingFace URLs in summaries
- **Chinese translation** - translates paper summaries using OpenRouter LLM API
- **Automatic archiving** - moves papers older than 3 months to `papers/archive/`
- **Git auto-sync** - `run.sh` wrapper script for multi-device sync with auto-commit/push
- **Duplicate prevention** - tracks seen paper IDs to avoid duplicates
- **Debug logging** - structured logging with DEBUG environment variable for troubleshooting

## Project Structure

| File | Description |
|------|-------------|
| `arxiv_subscriber.py` | Main script - fetches, processes, and syncs papers |
| `run.sh` | Wrapper script with auto git pull/commit/push for multi-device sync |
| `papers/YYYY-MM.json` | Papers organized by month (tracked in git) |
| `papers/archive/YYYY-MM.json` | Archived papers older than 3 months (gitignored) |
| `.githooks/` | Git hooks for reminders (post-commit, post-merge) |
| `pyproject.toml` | Python dependencies (managed by uv) |
| `.env` | Environment variables (gitignored) |

## Notion Database Schema

Required properties:
- `Name` (Title) - paper title
- `Has Code` (Checkbox) - true if code URL detected
- `Published` (Date) - original arXiv publication date
- `Link` (URL) - PDF link
- `Summary` (Rich Text) - paper abstract
- `Summary (中文)` (Rich Text) - Chinese translation (optional)

## Environment Variables

### Required
- `NOTION_API_KEY` - Notion integration token
- `NOTION_DATABASE_ID` - Notion database ID

### Optional (for translation)
- `TRANSLATE_API_TOKEN` - OpenRouter API token
- `TRANSLATE_API_URL` - Base URL (default: https://openrouter.ai/api/v1)
- `TRANSLATE_MODEL` - Model name (default: google/gemini-2.5-flash)

### Optional (for debugging)
- `DEBUG` - Set to "1" or "true" to enable verbose debug output with timestamps

## Development Preferences

### Git Workflow
- Use `gh` CLI for GitHub operations (already authorized)
- Use global git config: `guisongchen <guisongchen@163.com>`
- Write meaningful commit messages
- Push commits after completing logical units of work

### Code Style
- Python 3.12+
- Use type hints where helpful
- Follow PEP 8
- Use descriptive variable names

### Dependencies
- Managed with `uv` (modern Python package manager)
- Key deps: `openai`, `python-dotenv`

## Commands

### Run
```bash
# Using wrapper script (recommended - auto-syncs with git)
./run.sh

# Using uv (manual)
uv run python3 arxiv_subscriber.py

# Direct
python3 arxiv_subscriber.py

# With debug logging
DEBUG=1 uv run python3 arxiv_subscriber.py
```

### Install dependencies
```bash
uv sync
```

### Schedule (cron)
```bash
0 9 * * * cd /home/ccc/vibe_projects/arxiv_subscriber && ./run.sh
```

## Architecture Notes

- `Paper` dataclass: stores paper metadata, auto-detects code URLs on init
- `ArxivSubscriber`: main class, handles fetch/store/archive lifecycle
- `NotionClient`: sends papers to Notion with rate limiting
- Storage: papers organized by month in `papers/YYYY-MM.json`
- Archive logic: month files older than 3 months moved to `papers/archive/`
- Translation: lazy-loaded only when sending to Notion (not during fetch)
- Debug logging: use `DEBUG=1` to see detailed execution trace and filtered paper reasons
- Multi-device: use `./run.sh` for auto-sync, or manually commit/push `papers/` directory
- Git hooks: enable with `git config core.hooksPath .githooks` for push reminders

## API Limits

- arXiv: ~1 request per 3 seconds (built-in rate limiting)
- Notion: 0.5s delay between requests
- OpenRouter: depends on account credits

## Future Plans

- [x] Keyword filtering for papers
- [ ] CLI for browsing stored papers
- [ ] Web interface
