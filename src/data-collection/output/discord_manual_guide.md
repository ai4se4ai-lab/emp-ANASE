# Discord Data Collection Guide
# ================================
# Discord does not provide a public API for academic scraping.
# The paper collected 31 discussions from LangChain, Cursor, and AutoGPT servers.
# Below is the compliant manual process + a helper script for structuring exports.

## Why no automated scraper?
# Discord's Terms of Service (https://discord.com/terms) prohibit automated
# scraping without explicit permission. Violations risk account bans and legal issues.
# The paper notes: "participant counts were obtained manually through server analytics."

## Step-by-step manual collection

### 1. Join the servers
# - LangChain:  https://discord.gg/langchain
# - Cursor:     https://discord.gg/cursor
# - AutoGPT:    https://discord.gg/autogpt

### 2. Use Discord's built-in search (Ctrl+F in each server)
# Search terms (one at a time):
#   analogy
#   metaphor
#   "like a"
#   "similar to"
#   "junior developer"
#   "power tool"
#   "autopilot"

### 3. For each relevant message thread, manually record:

DISCORD_FIELDS = [
    "server_name",          # e.g. LangChain
    "channel_name",         # e.g. #general
    "thread_id",            # right-click message → Copy ID (Developer Mode required)
    "message_id",
    "author_pseudonym",     # anonymise: use hash or role (e.g. "User_A")
    "message_content",      # copy the text
    "reply_count",          # visible in thread view
    "reaction_count",       # emoji reactions
    "timestamp",            # ISO 8601
    "analogy_keyword",      # which keyword triggered inclusion
    "agent_keyword",        # which AI agent was being discussed
    "notes",                # your qualitative annotation
]

### 4. Save to CSV using this helper
"""
import csv, hashlib, datetime
from pathlib import Path

def anonymise(username: str) -> str:
    return "User_" + hashlib.sha256(username.encode()).hexdigest()[:6].upper()

def create_discord_template(output_path: str = "output/discord_posts.csv"):
    Path("output").mkdir(exist_ok=True)
    fields = [
        "server_name", "channel_name", "thread_id", "message_id",
        "author_pseudonym", "message_content", "reply_count",
        "reaction_count", "timestamp", "analogy_keyword",
        "agent_keyword", "predicted_analogy_type", "predicted_sdlc_phase",
        "notes", "collected_at",
    ]
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        # Add one example row so the schema is clear
        writer.writerow({
            "server_name":            "LangChain",
            "channel_name":           "#general",
            "thread_id":              "REPLACE_WITH_ID",
            "message_id":             "REPLACE_WITH_ID",
            "author_pseudonym":       anonymise("example_user"),
            "message_content":        "I think of the agent like a junior developer...",
            "reply_count":            5,
            "reaction_count":         3,
            "timestamp":              datetime.datetime.utcnow().isoformat(),
            "analogy_keyword":        "like a",
            "agent_keyword":          "agent",
            "predicted_analogy_type": "process",
            "predicted_sdlc_phase":   "development",
            "notes":                  "Clear process analogy; positive sentiment",
            "collected_at":           datetime.datetime.utcnow().isoformat(),
        })
    print(f"Discord template created: {output_path}")

if __name__ == "__main__":
    create_discord_template()
"""

### 5. Ethics & IRB
# - Do NOT collect usernames — use anonymise() above
# - Only collect messages in PUBLIC channels
# - Note consent status in your IRB protocol
# - Retain raw data securely; share only anonymised exports

### 6. Merge with automated data
# After filling discord_posts.csv, run:
#   python merge_discord.py
# (see merge_discord.py in this folder)
