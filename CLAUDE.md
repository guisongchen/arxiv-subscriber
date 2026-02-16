# CLAUDE.md - arXiv Subscriber Project

> Instructions for Claude Code when working on this project

## Project Overview
Python tool to subscribe to and track new Computer Science papers from arXiv.
Repository: https://github.com/guisongchen/arxiv-subscriber

## Development Preferences

### Git Workflow
- Use `gh` CLI for GitHub operations (already authorized)
- Use global git config: `guisongchen <guisongchen@163.com>`
- Write meaningful commit messages
- Push commits after completing logical units of work

### Code Style
- Python 3.8+
- Use type hints where helpful
- Follow PEP 8
- Use descriptive variable names

### Project Structure
- `arxiv_subscriber.py` - Main script
- `papers.json` - Local data file (gitignored)
- Keep it simple - avoid over-engineering

## Commands

### Run
```bash
python3 arxiv_subscriber.py
```

### Schedule (cron)
```bash
0 9 * * * cd /home/ccc/vibe_projects/arxiv_subscriber && python3 arxiv_subscriber.py
```

## Future Plans (To Be Implemented)
- [ ] Notification system (email/Discord/Slack)
- [ ] Keyword filtering for papers
- [ ] CLI for browsing stored papers
- [ ] Configuration file support

## Notes
- arXiv API rate limit: ~1 request per 3 seconds
- Data stored in `papers.json` (not tracked in git)
