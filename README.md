# arXiv CS Subscriber

A simple Python tool to track new Computer Science papers from arXiv.

## Features

- Fetches papers from 12 CS categories (AI, ML, NLP, CV, SE, etc.)
- Tracks which papers you've already seen
- Stores paper metadata locally in JSON format
- Search functionality
- No notifications (to be implemented later)

## Usage

### Run once to fetch new papers

```bash
python arxiv_subscriber.py
```

### Schedule it (run daily at 9 AM)

Add to your crontab:
```bash
0 9 * * * cd /path/to/arxiv_subscriber && python arxiv_subscriber.py
```

## Data Storage

- `papers.json` - Stores all tracked papers and their metadata
- Automatically created on first run

## Customization

Edit `CS_CATEGORIES` in `arxiv_subscriber.py` to change which categories you subscribe to:

| Category | Description |
|----------|-------------|
| cs.AI | Artificial Intelligence |
| cs.CL | Computation and Language (NLP) |
| cs.CV | Computer Vision |
| cs.LG | Machine Learning |
| cs.SE | Software Engineering |
| cs.DB | Databases |
| cs.DC | Distributed Computing |
| cs.CR | Cryptography and Security |
| cs.NE | Neural and Evolutionary Computing |
| cs.OS | Operating Systems |
| cs.PL | Programming Languages |
| cs.RO | Robotics |

## API Notes

- Uses arXiv's public API
- Rate limited to ~1 request every 3 seconds
- Respects arXiv's terms of service
