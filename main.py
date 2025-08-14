import discord
from discord.ext import commands
import os
from commands.waitlist import QueueView
from www.config_server import start_config_server
import asyncio
import threading

# Load credentials from env.txt
creds = {}
try:
    with open('env.txt', 'r') as f:
        for line in f:
            if '=' in line:
                key, value = line.strip().split('=', 1)
                creds[key] = value
except FileNotFoundError:
    print("env.txt not found! Please create the file with your credentials.")
    exit(1)

APP_ID = creds.get('APP_ID')
PUBLIC_KEY = creds.get('PUBLIC_KEY')
TOKEN = creds.get('TOKEN')

# Enable required privileged intents
intents = discord.Intents.default()
intents.members = True  # Required for role/member checks
intents.message_content = True  # Required for message content access (if needed)
# Make sure to enable these intents in the Discord Developer Portal as well!
bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    bot.add_view(QueueView())
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s) globally.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

async def main():
    # Start local configuration website
    try:
        start_config_server()
        print("Config server started on http://127.0.0.1:8765")
    except Exception as e:
        print(f"Failed to start config server: {e}")
    # Load the Results cog from the commands/results.py file
    await bot.load_extension("commands.results")
    await bot.load_extension("commands.settier")
    await bot.load_extension("commands.waitlist")
    await bot.start(TOKEN)


# ---- Helpers to control the bot from external processes (e.g., Streamlit) ----
_bot_thread = None
_bot_loop = None


def run_bot(block: bool = False):
    global _bot_thread, _bot_loop
    if block:
        asyncio.run(main())
        return

    if _bot_thread and _bot_thread.is_alive():
        print("Bot is already running.")
        return

    def _runner():
        global _bot_loop
        loop = asyncio.new_event_loop()
        _bot_loop = loop
        asyncio.set_event_loop(_bot_loop)
        try:
            _bot_loop.run_until_complete(main())
        finally:
            _bot_loop.run_until_complete(_bot_loop.shutdown_asyncgens())
            _bot_loop.close()

    _bot_thread = threading.Thread(target=_runner, name="ECTiersBot", daemon=True)
    _bot_thread.start()


def stop_bot():
    # Gracefully request the bot to close if running
    try:
        coro = bot.close()
        global _bot_loop
        if _bot_loop and _bot_loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, _bot_loop)
        else:
            asyncio.run(coro)
    except Exception as e:
        print(f"Failed to stop bot: {e}")


if __name__ == "__main__":
    run_bot(block=True)
