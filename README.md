# arXiv CS Subscriber

A simple Python tool to track new Computer Science papers from arXiv with Notion integration and Chinese translation.

## Features

- Fetches papers from CS categories (AI, ML, CV, Robotics)
- Tracks which papers you've already seen
- **Notion integration** - automatically sync papers to Notion database
- **Code repository detection** - auto-detects GitHub/GitLab/HuggingFace URLs
- **Chinese translation** - translates summaries using LLM
- **Automatic archiving** - archives papers older than 30 days
- Search functionality

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/guisongchen/arxiv-subscriber.git
cd arxiv-subscriber

# Using uv (recommended)
uv sync

# Or using pip
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
# Required for Notion integration
NOTION_API_KEY=your_notion_integration_token
NOTION_DATABASE_ID=your_database_id

# Optional - for Chinese translation
TRANSLATE_API_TOKEN=your_openrouter_token
TRANSLATE_API_URL=https://openrouter.ai/api/v1
TRANSLATE_MODEL=google/gemini-2.5-flash
```

Get your Notion integration token: https://www.notion.so/my-integrations

Get your OpenRouter token: https://openrouter.ai/keys

#### Multi-Device Setup (Git Sync)

The `papers/` directory stores which papers you've already seen to prevent duplicates in Notion, organized by month (e.g., `papers/2026-02.json`). To use this tool on multiple devices, the papers are automatically tracked in git.

**Quick Start - Use the wrapper script:**

```bash
# Run the subscriber with auto-sync
./run.sh
```

This will:
1. Pull latest papers from remote
2. Run the subscriber
3. Auto-commit any new papers
4. Push to remote

**Manual workflow** (if not using `run.sh`):

```bash
# On other devices - pull before running
git pull
uv run python arxiv_subscriber.py

# After running the script
git add papers/
git commit -m "Update papers"
git push
```

**Install git hooks for reminders:**

```bash
# Enable the version-controlled hooks
git config core.hooksPath .githooks
```

This adds:
- **post-commit**: Reminds you to push after committing papers
- **post-merge**: Shows papers sync status after pull

Each month's papers are stored in a separate file (`YYYY-MM.json`). Git handles these small files efficiently. Old months are automatically moved to `papers/archive/` (gitignored) after 3 months.

**Note**: `.env` files should still be configured separately on each device (they contain device-specific paths and API keys).

### 3. Setup Notion Database

Create a database with these properties:

| Property | Type |
|----------|------|
| Name | Title |
| Has Code | Checkbox |
| Published | Date |
| Link | URL |
| Summary | Rich Text |
| Summary (中文) | Rich Text |

## Usage

### Run once to fetch new papers

```bash
# Using the wrapper script (recommended - auto-syncs papers)
./run.sh

# Or manually with uv
uv run python arxiv_subscriber.py

# Or using python directly
python arxiv_subscriber.py
```

### Schedule it (run daily at 9 AM)

Add to your crontab:
```bash
0 9 * * * cd /path/to/arxiv_subscriber && ./run.sh
```

## Data Storage

- `papers/YYYY-MM.json` - Papers organized by month (tracked in git)
- `papers/archive/YYYY-MM.json` - Archived papers older than 3 months (gitignored)
- Files are created automatically

## Customization

### Categories

Edit `CS_CATEGORIES` in `arxiv_subscriber.py`:

| Category | Description |
|----------|-------------|
| cs.AI | Artificial Intelligence |
| cs.CV | Computer Vision |
| cs.LG | Machine Learning |
| cs.RO | Robotics |

### Translation Settings

All translation settings are configurable via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `TRANSLATE_API_TOKEN` | - | API token for translation service |
| `TRANSLATE_API_URL` | `https://openrouter.ai/api/v1` | Base API URL |
| `TRANSLATE_MODEL` | `google/gemini-2.5-flash` | Model to use |

## API Notes

- Uses arXiv's public API (rate limited to ~1 request every 3 seconds)
- Uses OpenRouter for translation (OpenAI-compatible API)
- Respects arXiv's terms of service
