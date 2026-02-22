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

#### Multi-Device Setup

The `papers.json` file tracks which papers you've already seen to prevent duplicates in Notion. To use this tool on multiple devices:

**Commit and push papers.json after each run:**

```bash
# After running the script
uv run python arxiv_subscriber.py
git add papers.json
git commit -m "Update papers.json"
git push

# On other devices - pull before running
git pull
uv run python arxiv_subscriber.py
```

The file is small (typically under 100KB) and git handles it well. The archive folder (`archive/`) remains gitignored - only the active `papers.json` needs to be synced.

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
# Using uv
uv run python arxiv_subscriber.py

# Or using python directly
python arxiv_subscriber.py
```

### Schedule it (run daily at 9 AM)

Add to your crontab:
```bash
0 9 * * * cd /path/to/arxiv_subscriber && uv run python arxiv_subscriber.py
```

## Data Storage

- `papers.json` - Active papers (last 30 days)
- `archive/papers_YYYY-MM.json` - Archived papers by month
- Both are gitignored and created automatically

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
