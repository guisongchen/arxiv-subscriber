#!/usr/bin/env python3
"""
Simple arXiv subscriber for Computer Science papers.
Fetches new papers and tracks what has been seen.
"""

import xml.etree.ElementTree as ET
import urllib.request
import urllib.parse
import json
import os
import re
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Set, Optional
import time

# Translation API (OpenRouter)
TRANSLATE_API_TOKEN = os.getenv("TRANSLATE_API_TOKEN", "")
TRANSLATION_AVAILABLE = bool(TRANSLATE_API_TOKEN)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Initialize OpenAI for OpenRouter if token available
def translate_with_llm(text: str) -> Optional[str]:
    """Translate text to Chinese using OpenRouter LLM API."""
    if not TRANSLATION_AVAILABLE or not text:
        return None

    try:
        import openai
        # Set up OpenAI with OpenRouter base URL
        openai.api_key = TRANSLATE_API_TOKEN
        openai.api_base = OPENROUTER_BASE_URL
    except ImportError:
        return None

    # Truncate if too long
    truncated = text[:3000] if len(text) > 3000 else text

    prompt = f"""Translate the following academic paper summary to Chinese. Keep it concise and accurate.

Text to translate:
{truncated}

Chinese translation:"""

    try:
        response = openai.ChatCompletion.create(
            model="google/gemini-2.5-flash",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.3,
            headers={
                "HTTP-Referer": "https://github.com/guisongchen/arxiv-subscriber",
                "X-Title": "arXiv Subscriber"
            }
        )
        if response.choices and len(response.choices) > 0:
            translated = response.choices[0].message.content.strip()
            return translated
    except Exception as e:
        print(f"  ⚠️  Translation failed: {e}")

    return None

# Load environment variables from .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# arXiv API endpoint
ARXIV_API_URL = "http://export.arxiv.org/api/query"

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


def translate_to_chinese(text: str, max_retries: int = 2) -> Optional[str]:
    """Translate text to Chinese using OpenRouter LLM API.

    Returns translated text or None if translation fails.
    """
    return translate_with_llm(text)


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

    def __post_init__(self):
        if self.first_seen is None:
            self.first_seen = datetime.now().isoformat()
        # Auto-detect code URL if not already set
        if self.code_url is None:
            # Check both title and summary for code URLs
            combined_text = f"{self.title} {self.summary}"
            self.code_url = extract_code_url(combined_text)
        # Translate summary to Chinese if not already done
        if self.summary_zh is None and TRANSLATION_AVAILABLE:
            self.summary_zh = translate_to_chinese(self.summary)


class NotionClient:
    """Client for sending papers to Notion database."""

    def __init__(self, api_key: str, database_id: str):
        self.api_key = api_key
        self.database_id = database_id
        self.base_url = "https://api.notion.com/v1"

    def add_paper(self, paper: Paper) -> bool:
        """Add a paper to the Notion database."""
        if not self.api_key or not self.database_id:
            return False

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

        # Add Chinese summary if available
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
                    return True
        except Exception as e:
            print(f"  ⚠️  Failed to add to Notion: {e}")

        return False


class ArxivSubscriber:
    """Main class for subscribing to arXiv papers."""

    def __init__(self, data_file: str = "papers.json", notion_client: NotionClient = None):
        self.data_file = data_file
        self.seen_ids: Set[str] = set()
        self.papers: List[Paper] = []
        self.notion = notion_client
        self._load_data()

    def _load_data(self):
        """Load previously seen papers from disk."""
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r') as f:
                data = json.load(f)
                for p in data.get('papers', []):
                    paper = Paper(**p)
                    self.papers.append(paper)
                    self.seen_ids.add(paper.arxiv_id)
            print(f"Loaded {len(self.papers)} previously seen papers")

    def _save_data(self):
        """Save papers to disk."""
        data = {
            'last_updated': datetime.now().isoformat(),
            'papers': [asdict(p) for p in self.papers]
        }
        with open(self.data_file, 'w') as f:
            json.dump(data, f, indent=2)

    def _archive_old_papers(self, days: int = 30):
        """Archive papers older than N days to separate files in archive/ folder.

        Organizes archives by month (e.g., archive/papers_2026-02.json).
        Returns number of papers archived.
        """
        cutoff = datetime.now() - timedelta(days=days)
        to_archive = []
        to_keep = []

        for paper in self.papers:
            try:
                first_seen = datetime.fromisoformat(paper.first_seen.replace('Z', '+00:00'))
                if first_seen < cutoff:
                    to_archive.append(paper)
                else:
                    to_keep.append(paper)
            except:
                # If date parsing fails, keep the paper
                to_keep.append(paper)

        if not to_archive:
            return 0

        # Create archive folder if it doesn't exist
        archive_dir = os.path.join(os.path.dirname(self.data_file) or '.', 'archive')
        os.makedirs(archive_dir, exist_ok=True)

        # Group papers by month
        by_month = {}
        for paper in to_archive:
            try:
                first_seen = datetime.fromisoformat(paper.first_seen.replace('Z', '+00:00'))
                month_key = first_seen.strftime("%Y-%m")
            except:
                month_key = "unknown"

            if month_key not in by_month:
                by_month[month_key] = []
            by_month[month_key].append(paper)

        # Save each month to separate archive file
        archived_count = 0
        for month_key, papers in by_month.items():
            archive_file = os.path.join(archive_dir, f"papers_{month_key}.json")

            # Load existing archive if present
            existing_papers = []
            if os.path.exists(archive_file):
                with open(archive_file, 'r') as f:
                    try:
                        data = json.load(f)
                        existing_papers = data.get('papers', [])
                    except:
                        pass

            # Merge and save
            all_papers = existing_papers + [asdict(p) for p in papers]
            data = {
                'archived_at': datetime.now().isoformat(),
                'paper_count': len(all_papers),
                'papers': all_papers
            }

            with open(archive_file, 'w') as f:
                json.dump(data, f, indent=2)

            archived_count += len(papers)

        # Update in-memory list to only keep recent papers
        self.papers = to_keep
        self.seen_ids = {p.arxiv_id for p in to_keep}

        # Save the reduced main file
        self._save_data()

        return archived_count

    def _fetch_papers(self, categories: List[str], max_results: int = 50) -> List[Paper]:
        """Fetch papers from arXiv API for given categories."""
        papers = []

        # Build query: OR all categories
        cat_query = " OR ".join([f"cat:{cat}" for cat in categories])

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
                categories = []
                for cat in entry.findall('atom:category', ns):
                    term = cat.get('term')
                    if term:
                        categories.append(term)

                paper = Paper(
                    arxiv_id=id_text,
                    title=title.text.strip() if title is not None else "",
                    authors=authors,
                    summary=summary.text.strip() if summary is not None else "",
                    published=published.text if published is not None else "",
                    updated=updated.text if updated is not None else "",
                    categories=categories,
                    link=link.get('href') if link is not None else ""
                )

                papers.append(paper)

            # Rate limiting - be nice to arXiv
            time.sleep(3)

        except Exception as e:
            print(f"Error fetching papers: {e}")

        return papers

    def check_for_new_papers(self) -> List[Paper]:
        """Check for new papers and return any that haven't been seen."""
        print(f"Fetching papers from {len(CS_CATEGORIES)} CS categories...")

        fetched_papers = self._fetch_papers(CS_CATEGORIES, max_results=100)
        new_papers = []

        for paper in fetched_papers:
            if paper.arxiv_id not in self.seen_ids:
                new_papers.append(paper)
                self.papers.append(paper)
                self.seen_ids.add(paper.arxiv_id)

                # Send to Notion if configured
                if self.notion:
                    success = self.notion.add_paper(paper)
                    if success:
                        print(f"  ✓ Sent to Notion: {paper.title[:50]}...")
                    time.sleep(0.5)  # Rate limit for Notion API

        # Save updated data
        self._save_data()

        return new_papers

    def get_recent_papers(self, days: int = 7) -> List[Paper]:
        """Get papers published in the last N days."""
        cutoff = datetime.now() - timedelta(days=days)
        recent = []

        for paper in self.papers:
            try:
                published = datetime.fromisoformat(paper.published.replace('Z', '+00:00'))
                if published > cutoff:
                    recent.append(paper)
            except:
                pass

        return recent

    def list_categories(self):
        """List all categories we've seen papers from."""
        cats = set()
        for paper in self.papers:
            cats.update(paper.categories)
        return sorted(cats)

    def search_papers(self, keyword: str) -> List[Paper]:
        """Search papers by keyword in title or summary."""
        keyword = keyword.lower()
        results = []

        for paper in self.papers:
            if keyword in paper.title.lower() or keyword in paper.summary.lower():
                results.append(paper)

        return results


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
    if show_summary and paper.summary_zh:
        print(f"\nSummary (中文):\n{paper.summary_zh[:500]}...")


def main():
    """Main entry point."""
    # Initialize Notion client if credentials are available
    notion_client = None
    if NOTION_API_KEY and NOTION_DATABASE_ID:
        notion_client = NotionClient(NOTION_API_KEY, NOTION_DATABASE_ID)
        print("Notion integration enabled")

    subscriber = ArxivSubscriber(notion_client=notion_client)

    if TRANSLATION_AVAILABLE:
        print("Translation enabled (DeepL)")

    print("=" * 70)
    print("arXiv CS Subscriber")
    print("=" * 70)

    # Archive papers older than 30 days
    archived = subscriber._archive_old_papers(days=30)
    if archived > 0:
        print(f"📦 Archived {archived} old papers to archive/ folder")

    # Check for new papers
    new_papers = subscriber.check_for_new_papers()

    if new_papers:
        print(f"\n📬 Found {len(new_papers)} new papers!")
        for paper in new_papers[:5]:  # Show first 5
            print_paper(paper)

        if len(new_papers) > 5:
            print(f"\n... and {len(new_papers) - 5} more")
    else:
        print("\n📭 No new papers found.")

    print(f"\nTotal papers tracked: {len(subscriber.papers)}")
    print(f"Categories tracked: {len(subscriber.list_categories())}")


if __name__ == "__main__":
    main()
