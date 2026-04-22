"""
Discord Collector - ETHICAL USE ONLY

WARNING: Discord's Terms of Service and Developer Policy strictly regulate data
access. This collector requires:
1. Bot token with explicit server owner permission
2. Compliance with Discord's Developer Terms of Service
3. Adherence to server-specific rules and privacy policies
4. Informed consent from server administrators

Public Discord content is NOT indexable by search engines. You cannot legally
scrape Discord without bot access and permission.

This template is provided for researchers who have obtained proper authorization.
It will NOT function without a valid bot token and guild permissions.

Reference: https://discord.com/developers/docs/legal
"""

import os
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime

# discord.py is optional; import fails gracefully if not installed
try:
    import discord
    from discord.ext import commands
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False

from base_collector import BaseCollector


class DiscordCollector(BaseCollector):
    """
    Discord data collector.

    ETHICAL REQUIREMENTS:
    - Must obtain written permission from server owners
    - Must comply with Discord Developer Terms of Service
    - Must respect user privacy and server rules
    - Should only collect from public channels with consent
    - Must anonymize all user identifiers
    """

    def __init__(self, config_path: str = "config.yaml"):
        super().__init__(config_path)

        if not DISCORD_AVAILABLE:
            raise ImportError(
                "discord.py is required for Discord collection. "
                "Install with: pip install discord.py\n"
                "Note: Discord collection requires server owner permission."
            )

        self.token = self.platform_config.get('token') or os.environ.get('DISCORD_BOT_TOKEN')
        self.servers = self.platform_config.get('servers', [])
        self.channels = self.platform_config.get('channels', [])
        self.rate_limit = self.config['rate_limits'].get('discord', 1.0)

        if not self.token:
            raise ValueError(
                "Discord bot token required. Set DISCORD_BOT_TOKEN.\n"
                "You MUST obtain server owner permission before collecting data."
            )

        self.intents = discord.Intents.default()
        self.intents.message_content = True
        self.client = commands.Bot(command_prefix='!', intents=self.intents)
        self.collected_records = []

    async def _process_message(self, message: discord.Message) -> Optional[Dict[str, Any]]:
        """Process a single Discord message."""
        content = message.content

        if not content or self.should_exclude(content):
            return None

        has_analogy, confidence = self.contains_analogy(content)
        if not has_analogy:
            return None

        analogy_types = self.classify_analogy_type(content)
        analogy_quote = self.extract_analogy_quote(content)
        sdlc_phase = self.determine_sdlc_phase(content)

        return self.create_record(
            record_id=f"DC-{message.id}",
            source_type='discord_message',
            url=f"https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id}",
            archive_url='',
            title=f"Message in #{message.channel.name}",
            author_handle=str(message.author),
            post_date=message.created_at.isoformat(),
            content=content,
            analogy_present=True,
            analogy_types=analogy_types,
            analogy_quote=analogy_quote or '',
            analogy_confidence=confidence,
            target_domain=self._extract_target_domain(content),
            source_domain=self._extract_source_domain(analogy_quote) if analogy_quote else '',
            sldc_phase=sdlc_phase,
            engagement_score=0,
            upvotes=0,
            replies=0,
            views=0,
            verified_by='authorized_bot'
        )

    def _extract_target_domain(self, text: str) -> str:
        text_lower = text.lower()
        agents = {
            'github copilot': 'GitHub Copilot',
            'copilot': 'GitHub Copilot',
            'cursor': 'Cursor',
            'claude code': 'Claude Code',
            'claude': 'Claude',
            'chatgpt': 'ChatGPT',
            'ai agent': 'Generic AI Agent'
        }
        for key, value in agents.items():
            if key in text_lower:
                return value
        return 'Unspecified AI Tool'

    def _extract_source_domain(self, quote: str) -> str:
        if not quote:
            return ''
        import re
        match = re.search(r'like a[n]?\s+([^,.;]+)', quote.lower())
        if match:
            return match.group(1).strip()
        return ''

    async def collect_from_guild(self, guild: discord.Guild):
        """Collect messages from permitted channels in a guild."""
        self.logger.info(f"Collecting from guild: {guild.name} (ID: {guild.id})")

        for channel in guild.text_channels:
            # Only collect from channels explicitly configured
            if self.channels and channel.name not in self.channels:
                continue

            try:
                self.logger.info(f"Scanning channel: #{channel.name}")

                async for message in channel.history(limit=1000, oldest_first=False):
                    record = await self._process_message(message)
                    if record:
                        self.collected_records.append(record)

                    await asyncio.sleep(self.rate_limit)

            except discord.Forbidden:
                self.logger.warning(f"No access to #{channel.name}")
                continue
            except Exception as e:
                self.logger.error(f"Error in #{channel.name}: {e}")
                continue

    async def on_ready(self):
        """Event triggered when bot is ready."""
        self.logger.info(f"Logged in as {self.client.user}")

        for guild in self.client.guilds:
            if not self.servers or str(guild.id) in self.servers or guild.name in self.servers:
                await self.collect_from_guild(guild)

        self.logger.info(f"Discord collection complete. {len(self.collected_records)} records found.")
        self.save_records(self.collected_records, "discord_analogies.csv")
        await self.client.close()

    def collect(self) -> List[Dict[str, Any]]:
        """Run Discord collector."""
        self.logger.info("=" * 60)
        self.logger.info("DISCORD COLLECTION STARTING")
        self.logger.info("Ensure you have written permission from server owners!")
        self.logger.info("=" * 60)

        @self.client.event
        async def ready_event():
            await self.on_ready()

        self.client.event(ready_event)
        self.client.run(self.token)

        return self.collected_records


if __name__ == "__main__":
    collector = DiscordCollector()
    collector.collect()