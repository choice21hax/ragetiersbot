import discord
from discord.ext import commands
import os
from commands.waitlist import QueueView
from www.config_server import start_config_server
import asyncio
import threading
import re
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None
try:
    import tomli  # Fallback for <3.11
except Exception:  # pragma: no cover
    tomli = None
try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

# ---- Secrets loading: supports OS env, .env, secrets.toml, and env.txt ----
SECRET_KEYS = ["APP_ID", "PUBLIC_KEY", "TOKEN"]


def _parse_env_file(path: str):
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, 'r') as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip()
    return values


def _load_toml(path: str):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'rb') as f:
            if tomllib is not None:
                data = tomllib.load(f)
            elif tomli is not None:
                data = tomli.load(f)
            else:
                # Minimal TOML not supported; return empty
                return {}
    except Exception:
        return {}
    # Support either top-level or [discord] table
    if isinstance(data, dict):
        if 'discord' in data and isinstance(data['discord'], dict):
            return data['discord']
        return data
    return {}


def _atomic_write_text(path: str, text: str):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, p)


def _maybe_migrate_env_to_toml(env_path: str, toml_path: str):
    if not os.path.exists(env_path) or os.path.exists(toml_path):
        return
    kv = _parse_env_file(env_path)
    # Filter known keys
    content_lines = ["[discord]"]
    for k in SECRET_KEYS:
        v = kv.get(k)
        if v is None:
            continue
        # Escape quotes in value
        v_esc = v.replace('"', '\\"')
        content_lines.append(f'{k} = "{v_esc}"')
    toml_text = "\n".join(content_lines) + "\n"
    _atomic_write_text(toml_path, toml_text)
    print(f"Migrated secrets from {env_path} to {toml_path}")


def load_secrets():
    # 1) OS environment has highest precedence
    secrets = {k: os.environ.get(k) for k in SECRET_KEYS}
    # 2) .env file (if python-dotenv installed)
    if load_dotenv is not None and os.path.exists('.env'):
        load_dotenv('.env', override=False)
        for k in SECRET_KEYS:
            if not secrets.get(k):
                secrets[k] = os.environ.get(k)
    else:
        # Fallback: ad-hoc parse .env without injecting into environment
        if os.path.exists('.env'):
            env_vals = _parse_env_file('.env')
            for k in SECRET_KEYS:
                secrets[k] = secrets.get(k) or env_vals.get(k)
    # 3) TOML file
    toml_path = 'secrets.toml'
    toml_vals = _load_toml(toml_path)
    for k in SECRET_KEYS:
        secrets[k] = secrets.get(k) or toml_vals.get(k)
    # 4) env.txt fallback
    txt_vals = _parse_env_file('env.txt')
    for k in SECRET_KEYS:
        secrets[k] = secrets.get(k) or txt_vals.get(k)
    # Ensure strings
    for k in SECRET_KEYS:
        if secrets.get(k) is not None:
            secrets[k] = str(secrets[k])
    return secrets


# Attempt migration from env.txt to secrets.toml if applicable
_maybe_migrate_env_to_toml('env.txt', 'secrets.toml')

_secrets = load_secrets()
APP_ID = _secrets.get('APP_ID')
PUBLIC_KEY = _secrets.get('PUBLIC_KEY')
TOKEN = _secrets.get('TOKEN')

if not TOKEN:
    print("Discord bot TOKEN is missing. Provide it via environment variables, .env, secrets.toml, or env.txt.")

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
