"""Discord bot for Life Agent proactive coaching.

Runs as a background asyncio task within the FastAPI app.
Receives DMs from any user who has connected their Discord account,
routes them to the agent system, and sends responses back.
Proactive messages are triggered by /api/discord/tick.
"""

import asyncio
import json
import re
import discord
from file_logger import logger
from config import DISCORD_BOT_TOKEN

DISCORD_SESSION_ID = "discord"

# Set by main.py after the graph runner is initialized
graph_runner = None


def _find_user_by_discord_id(discord_id: str) -> dict | None:
    """Look up a Life Agent user record by their Discord snowflake ID."""
    from database import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT id, data FROM users WHERE json_extract(data, '$.discord_user_id') = ?",
        (discord_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    d = {"id": row["id"]}
    try:
        d["data"] = json.loads(row["data"])
    except Exception:
        d["data"] = {}
    return d


class LifeAgentBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self._dm_channels: dict[str, discord.DMChannel] = {}

    async def on_ready(self):
        logger.info(f"[discord] Bot ready: {self.user}")

    async def _get_dm_channel(self, discord_user_id: str) -> discord.DMChannel | None:
        if discord_user_id not in self._dm_channels:
            try:
                user = await self.fetch_user(int(discord_user_id))
                self._dm_channels[discord_user_id] = await user.create_dm()
            except Exception as e:
                logger.error(f"[discord] Failed to open DM with {discord_user_id}: {e}")
                return None
        return self._dm_channels[discord_user_id]

    async def on_message(self, message: discord.Message):
        if not isinstance(message.channel, discord.DMChannel):
            return
        if message.author == self.user:
            return

        discord_id = str(message.author.id)
        app_user = _find_user_by_discord_id(discord_id)
        if app_user is None:
            return  # Not a registered Life Agent user

        text = message.content.strip()
        if not text:
            return

        logger.info(f"[discord] user={app_user['id']} received: {text[:80]}")
        async with message.channel.typing():
            await self._handle_message(message.channel, app_user["id"], text)

    async def _handle_message(self, channel, user_id: int, text: str):
        if graph_runner is None:
            await channel.send("Agent system not ready yet, try again in a moment.")
            return
        try:
            result = await graph_runner.run_stream(user_id, text, DISCORD_SESSION_ID)
            response = result.get("response", "")
            if response:
                for chunk in _chunk(_format_for_discord(response)):
                    await channel.send(chunk)
        except Exception as e:
            logger.error(f"[discord] Agent error for user={user_id}: {e}", exc_info=True)
            await channel.send("Something went wrong on my end, sorry.")

    async def send_dm(self, discord_user_id: str, text: str):
        """Send a proactive DM. Called by the tick endpoint."""
        channel = await self._get_dm_channel(discord_user_id)
        if channel is None:
            return
        for chunk in _chunk(_format_for_discord(text)):
            await channel.send(chunk)


def _format_for_discord(text: str) -> str:
    """Strip markdown heading syntax that doesn't render in Discord."""
    return re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE).strip()


def _chunk(text: str, limit: int = 1900) -> list[str]:
    """Split text into Discord-sized chunks at newline boundaries."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split = text.rfind('\n', 0, limit)
        if split == -1:
            split = limit
        chunks.append(text[:split])
        text = text[split:].lstrip('\n')
    return chunks


# --- Singleton lifecycle ---

_bot: LifeAgentBot | None = None


def get_bot() -> LifeAgentBot | None:
    return _bot


async def start_bot():
    global _bot
    if not DISCORD_BOT_TOKEN:
        logger.info("[discord] Disabled — set DISCORD_BOT_TOKEN to enable")
        return
    _bot = LifeAgentBot()
    try:
        await _bot.start(DISCORD_BOT_TOKEN)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[discord] Bot crashed: {e}", exc_info=True)


async def stop_bot():
    global _bot
    if _bot and not _bot.is_closed():
        await _bot.close()
