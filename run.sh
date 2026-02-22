#!/bin/bash
# arxiv-subscriber wrapper script with auto-git-sync

set -e

cd "$(dirname "$0")"

echo "🔄 Pulling latest papers..."
git pull

echo "📚 Running arxiv-subscriber..."
uv run python arxiv_subscriber.py

echo "💾 Checking for paper changes..."
git add papers/

if git diff --cached --quiet; then
    echo "✅ No new papers to commit"
else
    echo "📝 Committing papers changes..."
    git commit -m "Update papers - $(date '+%Y-%m-%d %H:%M')"
    echo "📤 Pushing to remote..."
    git push
    echo "✅ Papers synced successfully!"
fi
