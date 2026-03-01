#!/usr/bin/env python3
"""
Simple arXiv subscriber for Computer Science papers.
Fetches new papers and tracks what has been seen.
"""

import glob
import json
import logging
import os
import re
import shutil
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import List, Set, Optional

# Load environment variables from .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Logging setup
DEBUG_MODE = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")
LOG_LEVEL = logging.DEBUG if DEBUG_MODE else logging.INFO

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# OpenAI import for translation (optional)
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Translation API (OpenRouter)
TRANSLATE_API_TOKEN = os.getenv("TRANSLATE_API_TOKEN", "")
TRANSLATE_API_URL = os.getenv("TRANSLATE_API_URL", "https://openrouter.ai/api/v1")
TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "google/gemini-2.5-flash")
TRANSLATION_AVAILABLE = bool(TRANSLATE_API_TOKEN)

# Topic filtering - comma-separated keywords in .env
TOPIC_KEYWORDS = [k.strip().lower() for k in os.getenv("TOPIC_KEYWORDS", "").split(",") if k.strip()]
EXCLUDE_KEYWORDS = [k.strip().lower() for k in os.getenv("EXCLUDE_KEYWORDS", "").split(",") if k.strip()]

# Fetch settings
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "300"))

def translate_with_llm(text: str) -> Optional[str]:
    """Translate text to Chinese using OpenRouter LLM API."""
    if not TRANSLATION_AVAILABLE:
        logger.debug("Translation skipped: TRANSLATION_AVAILABLE=False")
        return None
    if not text:
        logger.debug("Translation skipped: empty text")
        return None
    if not OPENAI_AVAILABLE:
        logger.debug("Translation skipped: openai module not available")
        return None

    logger.debug(f"Starting translation for text of {len(text)} chars")

    truncated = text[:3000] if len(text) > 3000 else text
    prompt = f"""Translate the following academic paper summary to Chinese. Keep it concise and accurate.

Text to translate:
{truncated}

Chinese translation:"""

    try:
        logger.debug(f"Calling translation API with model: {TRANSLATE_MODEL}")
        client = openai.OpenAI(
            api_key=TRANSLATE_API_TOKEN,
            base_url=TRANSLATE_API_URL,
            default_headers={
                "HTTP-Referer": "https://github.com/guisongchen/arxiv-subscriber",
                "X-Title": "arXiv Subscriber"
            }
        )
        response = client.chat.completions.create(
            model=TRANSLATE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.3,
        )
        if response.choices:
            translated = response.choices[0].message.content.strip()
            logger.debug(f"Translation successful, result length: {len(translated)} chars")
            return translated
        else:
            logger.warning("Translation API returned empty response")
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        if DEBUG_MODE:
            logger.exception("Translation error details:")

    return None

# arXiv API endpoint
ARXIV_API_URL = "https://export.arxiv.org/api/query"

# Notion API
NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")

# Computer Science categories - you can customize these
CS_CATEGORIES = [
    "cs.AI",   # Artificial Intelligence
    # "cs.CL",   # Computation and Language (NLP)
    "cs.CV",   # Computer Vision
    "cs.LG",   # Machine Learning
    # "cs.SE",   # Software Engineering
    # "cs.DB",   # Databases
    # "cs.DC",   # Distributed Computing
    # "cs.CR",   # Cryptography and Security
    # "cs.NE",   # Neural and Evolutionary Computing
    # "cs.OS",   # Operating Systems
    # "cs.PL",   # Programming Languages
    "cs.RO",   # Robotics
]


def extract_code_url(text: str) -> Optional[str]:
    """Extract code repository URL from text (summary/title).

    Looks for common code hosting platforms like GitHub, GitLab, HuggingFace.
    Also detects shortened URLs and validates context with code-related keywords.
    Returns the first match found, or None if no code URL detected.
    """
    # Code-related keywords that suggest the URL is actually code
    code_keywords = [
        'code', 'source', 'implementation', 'repository', 'repo',
        'github', 'gitlab', 'huggingface', 'model', 'checkpoint',
        'script', 'available at', 'released', 'open-sourced'
    ]

    # Pattern for common code hosting platforms
    # Group 1: platform domain, Group 2: org/user (required), Group 3: repo (optional)
    patterns = [
        (r'(https?://github\.com)/([a-zA-Z0-9_-]+)(?:/([a-zA-Z0-9_.-]+))?', 'github'),
        (r'(https?://gitlab\.com)/([a-zA-Z0-9_-]+)(?:/([a-zA-Z0-9_.-]+))?', 'gitlab'),
        (r'(https?://huggingface\.co)/([a-zA-Z0-9_-]+)(?:/([a-zA-Z0-9_.-]+))?', 'huggingface'),
    ]

    # Shortened URL patterns
    short_patterns = [
        r'https?://git\.io/[a-zA-Z0-9]+',
        r'https?://bit\.ly/[a-zA-Z0-9]+',
        r'https?://tinyurl\.com/[a-zA-Z0-9]+',
        r'https?://t\.co/[a-zA-Z0-9]+',
    ]

    # Check shortened URLs first
    for pattern in short_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)

    # Check main platforms
    for pattern, platform in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            url = match.group(0)
            org = match.group(2)
            repo = match.group(3)

            # For GitHub/GitLab: require a specific repo (user/repo format)
            # For HuggingFace: user/model format is valid (allow these)
            if not repo and platform in ('github', 'gitlab'):
                continue

            # Skip common non-code paths
            if repo and repo.lower() in ['issues', 'pulls', 'discussions', 'wiki', 'blob', 'tree']:
                continue

            # Check for code context in surrounding text (200 chars window)
            start_pos = max(0, match.start() - 100)
            end_pos = min(len(text), match.end() + 100)
            context = text[start_pos:end_pos].lower()

            if any(kw in context for kw in code_keywords):
                return url

    return None


@dataclass
class Paper:
    """Represents an arXiv paper."""
    arxiv_id: str
    title: str
    authors: List[str]
    summary: str
    published: str
    updated: str
    categories: List[str]
    link: str
    first_seen: str = None
    code_url: str = None
    summary_zh: str = None
    notion_synced: bool = False

    def __post_init__(self):
        if self.first_seen is None:
            self.first_seen = datetime.now().isoformat()
        # Auto-detect code URL if not already set
        if self.code_url is None:
            # Check both title and summary for code URLs
            combined_text = f"{self.title} {self.summary}"
            self.code_url = extract_code_url(combined_text)


class NotionClient:
    """Client for sending papers to Notion database."""

    def __init__(self, api_key: str, database_id: str):
        self.api_key = api_key
        self.database_id = database_id
        self.base_url = "https://api.notion.com/v1"

    def add_paper(self, paper: Paper) -> bool:
        """Add a paper to the Notion database."""
        if not self.api_key or not self.database_id:
            logger.debug("Notion credentials missing, skipping add_paper")
            return False

        logger.debug(f"Adding paper to Notion: {paper.arxiv_id} - {paper.title[:50]}...")

        url = f"{self.base_url}/pages"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }

        # Prepare the data
        data = {
            "parent": {"database_id": self.database_id},
            "properties": {
                "Name": {
                    "title": [{"text": {"content": paper.title[:100]}}]
                },
                "Has Code": {
                    "checkbox": paper.code_url is not None
                },
                "Published": {
                    "date": {"start": paper.published[:10]}
                },
                "Link": {
                    "url": paper.link
                },
                "Summary": {
                    "rich_text": [{"text": {"content": paper.summary[:2000]}}]
                }
            }
        }

        # Add Chinese summary if available (translate now if not already cached)
        if paper.summary_zh is None and TRANSLATION_AVAILABLE:
            logger.debug(f"Translating summary for {paper.arxiv_id}")
            paper.summary_zh = translate_with_llm(paper.summary)
        if paper.summary_zh:
            data["properties"]["Summary (中文)"] = {
                    "rich_text": [{"text": {"content": paper.summary_zh[:2000]}}]
                }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode('utf-8'),
                headers=headers,
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    logger.info(f"Successfully added paper to Notion: {paper.arxiv_id}")
                    paper.notion_synced = True
                    return True
        except Exception as e:
            logger.error(f"Failed to add paper {paper.arxiv_id} to Notion: {e}")
            if DEBUG_MODE:
                logger.exception("Notion API error details:")

        return False

    def _request(self, method: str, path: str, data: dict = None) -> Optional[dict]:
        """Make a Notion API request."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(data).encode('utf-8') if data is not None else None,
            headers=headers,
            method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.error(f"Notion API {method} {path} failed: {e}")
            if DEBUG_MODE:
                logger.exception("Notion API error details:")
            return None

    def get_pages_missing_translation(self) -> list[tuple[str, str]]:
        """Query Notion for pages with empty Summary (中文). Returns list of (page_id, pdf_link)."""
        results = []
        cursor = None
        while True:
            body = {
                "filter": {"property": "Summary (中文)", "rich_text": {"is_empty": True}},
                "page_size": 100
            }
            if cursor:
                body["start_cursor"] = cursor
            data = self._request("POST", f"/databases/{self.database_id}/query", body)
            if not data:
                break
            for page in data.get("results", []):
                link_prop = page.get("properties", {}).get("Link", {})
                link = link_prop.get("url", "")
                results.append((page["id"], link))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        return results

    def update_translation(self, page_id: str, summary_zh: str) -> bool:
        """Patch a Notion page with the Chinese translation."""
        data = {"properties": {"Summary (中文)": {
            "rich_text": [{"text": {"content": summary_zh[:2000]}}]
        }}}
        result = self._request("PATCH", f"/pages/{page_id}", data)
        return result is not None


class ArxivSubscriber:
    """Main class for subscribing to arXiv papers."""

    def __init__(self, data_dir: str = "papers", notion_client: NotionClient = None):
        self.data_dir = data_dir
        self.seen_ids: Set[str] = set()
        self.papers: List[Paper] = []
        self.notion = notion_client
        self._load_data()

    def _get_month_file(self, date_str: str) -> str:
        """Get the filename for a given date string (ISO format)."""
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            month_key = dt.strftime("%Y-%m")
        except:
            month_key = "unknown"
        return os.path.join(self.data_dir, f"{month_key}.json")

    def _load_data(self):
        """Load previously seen papers from disk (all month files in papers/)."""
        logger.debug(f"Loading data from: {self.data_dir}/")

        if not os.path.exists(self.data_dir):
            logger.info("No papers directory found, starting fresh")
            return

        # Find all YYYY-MM.json files in the papers directory
        pattern = os.path.join(self.data_dir, "[0-9][0-9][0-9][0-9]-[0-9][0-9].json")
        month_files = glob.glob(pattern)

        if not month_files:
            logger.info("No month files found in papers/, starting fresh")
            return

        for filepath in sorted(month_files):
            filename = os.path.basename(filepath)
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    file_papers = []
                    for p in data.get('papers', []):
                        paper = Paper(**p)
                        file_papers.append(paper)
                        self.papers.append(paper)
                        self.seen_ids.add(paper.arxiv_id)
                logger.debug(f"Loaded {len(file_papers)} papers from {filename}")
            except Exception as e:
                logger.warning(f"Failed to load {filename}: {e}")

        logger.info(f"Loaded {len(self.papers)} previously seen papers from {len(month_files)} month files")

    def _save_data(self):
        """Save papers to disk, organized by month."""
        os.makedirs(self.data_dir, exist_ok=True)

        # Group papers by month
        by_month: dict[str, List[Paper]] = {}
        for paper in self.papers:
            filepath = self._get_month_file(paper.first_seen)
            if filepath not in by_month:
                by_month[filepath] = []
            by_month[filepath].append(paper)

        # Save each month to its own file
        saved_count = 0
        for filepath, papers in by_month.items():
            data = {
                'last_updated': datetime.now().isoformat(),
                'paper_count': len(papers),
                'papers': [asdict(p) for p in papers]
            }
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            saved_count += len(papers)
            logger.debug(f"Saved {len(papers)} papers to {os.path.basename(filepath)}")

        logger.debug(f"Saved {saved_count} papers total to {len(by_month)} month files")

    def _archive_old_papers(self, months_to_keep: int = 3):
        """Move month files older than N months to archive/ folder.

        Returns number of papers archived.
        """
        if not os.path.exists(self.data_dir):
            return 0

        # Calculate cutoff month
        now = datetime.now()
        cutoff = now.replace(day=1)
        for _ in range(months_to_keep):
            # Go back one month
            if cutoff.month == 1:
                cutoff = cutoff.replace(year=cutoff.year - 1, month=12)
            else:
                cutoff = cutoff.replace(month=cutoff.month - 1)

        cutoff_str = cutoff.strftime("%Y-%m")
        logger.debug(f"Archiving month files older than {cutoff_str}")

        pattern = os.path.join(self.data_dir, "[0-9][0-9][0-9][0-9]-[0-9][0-9].json")
        month_files = glob.glob(pattern)

        to_archive = []
        for filepath in month_files:
            filename = os.path.basename(filepath)
            month_key = filename.replace('.json', '')
            if month_key < cutoff_str:
                to_archive.append(filepath)

        if not to_archive:
            logger.debug("No month files to archive")
            return 0

        # Create archive folder
        archive_dir = os.path.join(self.data_dir, 'archive')
        os.makedirs(archive_dir, exist_ok=True)

        archived_count = 0
        for filepath in to_archive:
            filename = os.path.basename(filepath)
            dest = os.path.join(archive_dir, filename)

            # If destination exists, merge the files
            if os.path.exists(dest):
                try:
                    with open(filepath, 'r') as f:
                        src_data = json.load(f)
                    with open(dest, 'r') as f:
                        dest_data = json.load(f)

                    # Merge papers, avoiding duplicates
                    existing_ids = {p['arxiv_id'] for p in dest_data.get('papers', [])}
                    new_papers = [p for p in src_data.get('papers', []) if p['arxiv_id'] not in existing_ids]
                    dest_data['papers'].extend(new_papers)
                    dest_data['last_updated'] = datetime.now().isoformat()
                    dest_data['paper_count'] = len(dest_data['papers'])

                    with open(dest, 'w') as f:
                        json.dump(dest_data, f, indent=2)
                    archived_count += len(new_papers)
                except Exception as e:
                    logger.warning(f"Failed to merge {filename}: {e}")
            else:
                shutil.move(filepath, dest)
                try:
                    with open(dest, 'r') as f:
                        data = json.load(f)
                        archived_count += len(data.get('papers', []))
                except Exception:
                    pass

            logger.info(f"Archived {filename} to papers/archive/")

        # Reload data to reflect archived papers being removed
        self.papers = []
        self.seen_ids = set()
        self._load_data()

        return archived_count

    def _fetch_papers(self, categories: List[str], max_results: int = 50) -> List[Paper]:
        """Fetch papers from arXiv API for given categories."""
        papers = []

        # Build query: OR all categories
        cat_query = " OR ".join([f"cat:{cat}" for cat in categories])
        logger.debug(f"Fetching from categories: {categories}, max_results={max_results}")

        params = {
            'search_query': cat_query,
            'sortBy': 'submittedDate',
            'sortOrder': 'descending',
            'max_results': max_results
        }

        url = f"{ARXIV_API_URL}?{urllib.parse.urlencode(params)}"

        try:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'arxiv-subscriber/1.0'}
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read()

            logger.debug(f"Received response of {len(data)} bytes")

            # Parse Atom feed
            root = ET.fromstring(data)

            # Define namespaces
            ns = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }

            for entry in root.findall('atom:entry', ns):
                # Skip the arXiv query result entry
                if entry.find('atom:title', ns) is None:
                    continue

                arxiv_id = entry.find('atom:id', ns)
                if arxiv_id is None:
                    continue

                # Extract ID from URL
                id_text = arxiv_id.text.split('/')[-1]
                if 'v' in id_text:
                    id_text = id_text.split('v')[0]  # Remove version

                title = entry.find('atom:title', ns)
                summary = entry.find('atom:summary', ns)
                published = entry.find('atom:published', ns)
                updated = entry.find('atom:updated', ns)
                link = entry.find('atom:link[@title="pdf"]', ns)

                # Get authors
                authors = []
                for author in entry.findall('atom:author', ns):
                    name = author.find('atom:name', ns)
                    if name is not None:
                        authors.append(name.text)

                # Get categories
                entry_categories = []
                for cat in entry.findall('atom:category', ns):
                    term = cat.get('term')
                    if term:
                        entry_categories.append(term)

                paper = Paper(
                    arxiv_id=id_text,
                    title=title.text.strip() if title is not None else "",
                    authors=authors,
                    summary=summary.text.strip() if summary is not None else "",
                    published=published.text if published is not None else "",
                    updated=updated.text if updated is not None else "",
                    categories=entry_categories,
                    link=link.get('href') if link is not None else ""
                )

                papers.append(paper)

            logger.info(f"Fetched {len(papers)} papers from arXiv")

            # Rate limiting - be nice to arXiv
            time.sleep(3)

        except Exception as e:
            logger.error(f"Error fetching papers: {e}")
            if DEBUG_MODE:
                logger.exception("Fetch error details:")

        return papers

    def check_for_new_papers(self) -> List[Paper]:
        """Check for new papers and return any that haven't been seen."""
        logger.info(f"Checking for new papers from {len(CS_CATEGORIES)} categories")
        logger.debug(f"Categories: {CS_CATEGORIES}")
        if TOPIC_KEYWORDS:
            logger.info(f"Topic filter active: {', '.join(TOPIC_KEYWORDS)}")
        if EXCLUDE_KEYWORDS:
            logger.info(f"Exclusion filter active: {', '.join(EXCLUDE_KEYWORDS)}")

        logger.info(f"Fetching up to {MAX_RESULTS} papers from arXiv (this may take a moment)...")
        fetched_papers = self._fetch_papers(CS_CATEGORIES, max_results=MAX_RESULTS)
        logger.debug(f"Fetched {len(fetched_papers)} papers, {len(self.seen_ids)} already seen")

        new_papers = []
        filtered_count = 0

        for paper in fetched_papers:
            if paper.arxiv_id not in self.seen_ids:
                # Check topic filter
                if not self.matches_topics(paper):
                    filtered_count += 1
                    self.seen_ids.add(paper.arxiv_id)  # Mark as seen to skip next time
                    logger.debug(f"Filtered out paper {paper.arxiv_id}: '{paper.title[:60]}...' - no topic match")
                    continue

                new_papers.append(paper)
                self.papers.append(paper)
                self.seen_ids.add(paper.arxiv_id)
                logger.info(f"New paper found: {paper.arxiv_id} - {paper.title[:60]}...")

                # Send to Notion if configured
                if self.notion:
                    success = self.notion.add_paper(paper)
                    time.sleep(0.5)  # Rate limit for Notion API

        # Save updated data
        self._save_data()

        # Sync any previously-seen papers that were never sent to Notion
        # (e.g. fetched on a device without Notion credentials)
        if self.notion:
            unsynced = [p for p in self.papers if not p.notion_synced and p not in new_papers]
            if unsynced:
                logger.info(f"Found {len(unsynced)} existing papers not yet synced to Notion, syncing now...")
                for paper in unsynced:
                    if self.matches_topics(paper):
                        self.notion.add_paper(paper)
                        time.sleep(0.5)
                self._save_data()

        if filtered_count > 0:
            logger.info(f"Filtered out {filtered_count} papers not matching topics")

        logger.info(f"Found {len(new_papers)} new papers matching criteria")
        return new_papers

    def list_categories(self):
        """List all categories we've seen papers from."""
        cats = set()
        for paper in self.papers:
            cats.update(paper.categories)
        return sorted(cats)

    def matches_topics(self, paper: Paper) -> bool:
        """Check if paper matches topic keywords. Returns True if no keywords configured."""
        if not TOPIC_KEYWORDS:
            return True

        text = (paper.title + " " + paper.summary).lower()

        # Check exclude keywords first
        for kw in EXCLUDE_KEYWORDS:
            if kw in text:
                logger.debug(f"Paper {paper.arxiv_id} excluded by keyword: '{kw}'")
                return False

        # Check include keywords - must match at least one
        for kw in TOPIC_KEYWORDS:
            if kw in text:
                logger.debug(f"Paper {paper.arxiv_id} matched topic keyword: '{kw}'")
                return True

        logger.debug(f"Paper {paper.arxiv_id} did not match any topic keywords")
        return False

    def backfill_translations(self):
        """Find Notion pages missing Chinese translation and fill them in."""
        if not self.notion or not TRANSLATION_AVAILABLE:
            return

        logger.info("Querying Notion for pages missing Chinese translation...")
        pages = self.notion.get_pages_missing_translation()
        if not pages:
            logger.info("All Notion pages already have Chinese translations")
            return

        logger.info(f"Found {len(pages)} pages missing translation, backfilling...")
        # Build a lookup from arxiv_id to local paper
        paper_by_id = {p.arxiv_id: p for p in self.papers}

        updated = 0
        for page_id, link in pages:
            # Extract arxiv_id from PDF link (e.g. https://arxiv.org/pdf/2602.17632v1)
            match = re.search(r'(\d{4}\.\d{4,5})', link)
            if not match:
                continue
            arxiv_id = match.group(1)
            paper = paper_by_id.get(arxiv_id)
            if not paper:
                continue

            if paper.summary_zh is None:
                paper.summary_zh = translate_with_llm(paper.summary)
            if not paper.summary_zh:
                continue

            if self.notion.update_translation(page_id, paper.summary_zh):
                logger.info(f"Backfilled translation for {arxiv_id}")
                updated += 1
            time.sleep(0.5)

        if updated:
            self._save_data()
        logger.info(f"Backfilled translations for {updated}/{len(pages)} pages")


def print_paper(paper: Paper, show_summary: bool = False):
    """Pretty print a paper."""
    print(f"\n{'='*70}")
    print(f"ID: {paper.arxiv_id}")
    print(f"Title: {paper.title}")
    print(f"Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
    print(f"Categories: {', '.join(paper.categories)}")
    print(f"Published: {paper.published}")
    print(f"Link: {paper.link}")
    if paper.code_url:
        print(f"Code: {paper.code_url}")
    if show_summary:
        print(f"\nSummary:\n{paper.summary[:500]}...")
        if paper.summary_zh:
            print(f"\nSummary (中文):\n{paper.summary_zh[:500]}...")


def main():
    """Main entry point."""
    logger.info("Starting arXiv CS Subscriber")
    logger.debug(f"DEBUG mode enabled")

    # Initialize Notion client if credentials are available
    notion_client = None
    if NOTION_API_KEY and NOTION_DATABASE_ID:
        notion_client = NotionClient(NOTION_API_KEY, NOTION_DATABASE_ID)
        logger.info("Notion integration enabled")
    else:
        logger.info("Notion integration disabled (missing credentials)")

    subscriber = ArxivSubscriber(data_dir="papers", notion_client=notion_client)
    logger.info(f"ArxivSubscriber initialized with {len(subscriber.papers)} existing papers")

    # Warn about potential multi-device sync issues
    if len(subscriber.seen_ids) == 0:
        logger.warning("First run detected - papers/ directory is empty. If you've run this before on another device, run 'git pull' to sync and avoid duplicates in Notion.")

    if TRANSLATION_AVAILABLE:
        logger.info("Translation enabled")
    else:
        logger.info("Translation disabled")

    # Archive papers older than 3 months
    archived = subscriber._archive_old_papers(months_to_keep=3)
    if archived > 0:
        logger.info(f"Archived {archived} old papers to papers/archive/")

    # Check for new papers
    new_papers = subscriber.check_for_new_papers()

    # Backfill any Notion pages missing Chinese translation
    subscriber.backfill_translations()

    if new_papers:
        logger.info(f"Found {len(new_papers)} new papers!")
        for paper in new_papers[:5]:  # Show first 5
            print_paper(paper)

        if len(new_papers) > 5:
            print(f"\n... and {len(new_papers) - 5} more")
    else:
        logger.info("No new papers found")

    logger.info(f"Run complete. Total tracked: {len(subscriber.papers)}, Categories: {len(subscriber.list_categories())}")


if __name__ == "__main__":
    main()
