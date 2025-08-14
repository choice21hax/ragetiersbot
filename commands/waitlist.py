import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from datetime import datetime, timezone
import tempfile

WAITLIST_PATH = os.path.join("data", "currentwaitlist.json")
SETTINGS_PATH = os.path.join("data", "settings.json")
QUEUE_STATE_PATH = os.path.join("data", "queue_state.json")

# Load or initialize queue state
if os.path.exists(QUEUE_STATE_PATH):
    with open(QUEUE_STATE_PATH, 'r') as f:
        try:
            queue_state = json.load(f)
        except Exception:
            queue_state = {}
else:
    queue_state = {}

def save_queue_state():
    with open(QUEUE_STATE_PATH, 'w') as f:
        json.dump(queue_state, f, indent=2)

def get_queue_key(channel_id):
    return str(channel_id)

def get_testers_for_queue(channel_id):
    key = get_queue_key(channel_id)
    return queue_state.get(key, {}).get('testers', [])

def set_testers_for_queue(channel_id, testers):
    key = get_queue_key(channel_id)
    if key not in queue_state:
        queue_state[key] = {}
    queue_state[key]['testers'] = testers
    save_queue_state()

def set_queue_message(channel_id, message_id):
    key = get_queue_key(channel_id)
    if key not in queue_state:
        queue_state[key] = {}
    queue_state[key]['message_id'] = message_id
    save_queue_state()

def get_queue_message(channel_id):
    key = get_queue_key(channel_id)
    return queue_state.get(key, {}).get('message_id')

async def update_queue_message(bot, channel_id):
    print(f"[update_queue_message] Called for channel_id={channel_id}")
    # Load settings and waitlist
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, 'r') as f:
            settings = json.load(f)
    else:
        print("[update_queue_message] No settings found.")
        return
    allowed_role_id = settings.get("queue_role")
    if allowed_role_id is not None:
        allowed_role_id = int(allowed_role_id)
    if os.path.exists(WAITLIST_PATH):
        with open(WAITLIST_PATH, 'r') as f:
            try:
                waitlist = json.load(f)
            except Exception as e:
                print(f"[update_queue_message] Failed to load waitlist: {e}")
                waitlist = []
    else:
        waitlist = []
    # Players section
    players = [entry["ign"] for entry in waitlist]
    players_lines = [f"{i+1}. {players[i] if i < len(players) else ''}" for i in range(10)]
    # Testers section
    testers = get_testers_for_queue(channel_id)
    testers_lines = []
    for i in range(3):
        if i < len(testers):
            user_id = testers[i]
            testers_lines.append(f"{i+1}. <@{user_id}>")
        else:
            testers_lines.append(f"{i+1}.")
    embed = discord.Embed(
        title="Testing Queue - DEFAULT",
        description="Please use the command /join to join the DEFAULT queue\n\n**Players:**\n" + "\n".join(players_lines) + "\n\n**Testers**\n" + "\n".join(testers_lines),
        color=discord.Color.purple()
    )
    embed.set_thumbnail(url="https://i.imgur.com/your-image.png")
    embed.timestamp = datetime.now(timezone.utc)
    # Edit the message
    message_id = get_queue_message(channel_id)
    print(f"[update_queue_message] message_id={message_id}")
    if message_id:
        channel = bot.get_channel(int(channel_id))
        print(f"[update_queue_message] Editing message in channel={channel}")
        if channel:
            try:
                msg = await channel.fetch_message(int(message_id))
                await msg.edit(embed=embed, view=QueueView())
                print(f"[update_queue_message] Successfully edited message {message_id}")
            except Exception as e:
                print(f"[update_queue_message] Failed to edit message: {e}")

async def try_matchmake(bot, channel_id):
    print(f"[try_matchmake] Called for channel_id={channel_id}")
    # Load settings and waitlist
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, 'r') as f:
            settings = json.load(f)
    else:
        print("[try_matchmake] No settings found.")
        return
    category_id = settings.get("queue_category")
    if category_id is not None:
        category_id = int(category_id)
    allowed_role_id = settings.get("queue_role")
    if allowed_role_id is not None:
        allowed_role_id = int(allowed_role_id)
    staff_role_id = settings.get("staff_role") if "staff_role" in settings else None
    if staff_role_id is not None:
        staff_role_id = int(staff_role_id)
    if os.path.exists(WAITLIST_PATH):
        with open(WAITLIST_PATH, 'r') as f:
            try:
                waitlist = json.load(f)
            except Exception as e:
                print(f"[try_matchmake] Failed to load waitlist: {e}")
                waitlist = []
    else:
        waitlist = []
    testers = get_testers_for_queue(channel_id)
    print(f"[try_matchmake] testers={testers}, waitlist={waitlist}")
    if not waitlist or not testers:
        print("[try_matchmake] Not enough players or testers.")
        return
    # Pop first player and tester
    player_entry = waitlist.pop(0)
    tester_id = testers.pop(0)
    set_testers_for_queue(channel_id, testers)
    atomic_write_json(WAITLIST_PATH, waitlist)
    # Update queue embed
    await update_queue_message(bot, channel_id)

class QueueView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Join", style=discord.ButtonStyle.success, custom_id="queue_join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel_id = str(interaction.channel.id)
        print(f"[QueueView] Join button pressed by user {interaction.user.id} in channel {channel_id}")
        # Load allowed_role_id from settings
        allowed_role_id = None
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, 'r') as f:
                settings = json.load(f)
                allowed_role_id = settings.get("queue_role")
        if allowed_role_id is not None:
            allowed_role_id = int(allowed_role_id)
        if allowed_role_id and allowed_role_id not in [role.id for role in interaction.user.roles]:
            print(f"[QueueView] User {interaction.user.id} not allowed to join as tester.")
            await interaction.response.send_message("You are not allowed to join as a tester.", ephemeral=True)
            return
        testers = get_testers_for_queue(channel_id)
        if interaction.user.id not in testers:
            testers.append(interaction.user.id)
            set_testers_for_queue(channel_id, testers)
        await update_queue_message(interaction.client, channel_id)
        await try_matchmake(interaction.client, channel_id)
        await interaction.response.send_message("You joined as a tester!", ephemeral=True)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.danger, custom_id="queue_leave")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel_id = str(interaction.channel.id)
        print(f"[QueueView] Leave button pressed by user {interaction.user.id} in channel {channel_id}")
        testers = get_testers_for_queue(channel_id)
        if interaction.user.id in testers:
            testers.remove(interaction.user.id)
            set_testers_for_queue(channel_id, testers)
        await update_queue_message(interaction.client, channel_id)
        await interaction.response.send_message("You left the tester queue.", ephemeral=True)

class WaitlistModal(discord.ui.Modal, title="Join Waitlist"):
    ign = discord.ui.TextInput(label="Minecraft IGN", placeholder="Enter your Minecraft username", required=True)
    gamemode = discord.ui.TextInput(label="Gamemode", placeholder="e.g., Sword, Mace, Crystal", required=True)

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        entry = {
            "discord_id": str(self.user_id),
            "ign": self.ign.value.strip(),
            "gamemode": self.gamemode.value.strip(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        if os.path.exists(WAITLIST_PATH):
            with open(WAITLIST_PATH, 'r') as f:
                try:
                    waitlist = json.load(f)
                except Exception:
                    waitlist = []
        else:
            waitlist = []
        waitlist.append(entry)
        atomic_write_json(WAITLIST_PATH, waitlist)
        await interaction.response.send_message(f"You have been added to the waitlist! (IGN: {self.ign.value}, Gamemode: {self.gamemode.value})", ephemeral=True)

class WaitlistView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="✅ Verify Account Details", style=discord.ButtonStyle.success)
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Account verification coming soon!", ephemeral=True)

    @discord.ui.button(label="Join Waitlist", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WaitlistModal(interaction.user.id))

class Waitlist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Register persistent view ONCE in on_ready, not here
        # (moved to main.py)

    @app_commands.command(name="waitlist", description="Apply to the tierlist waitlist")
    async def waitlist(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Tierlist APP",
            description=(
                "Upon applying, you will be added to a gamemode-specific queue channel.\n"
                "Here you will be pinged when a tester is available.\n\n"
                "• Region should be the region of the server you wish to test on (e.g., AS, EU, NA)\n"
                "• Username should be the name of the account you will be testing on\n"
                "• Gamemode should be your preferred testing gamemode (if available)"
            ),
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url="https://i.imgur.com/your-image.png")
        await interaction.response.send_message(embed=embed, view=WaitlistView())

    @app_commands.command(name="createqueue", description="Create a testing queue embed")
    async def createqueue(self, interaction: discord.Interaction):
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, 'r') as f:
                settings = json.load(f)
        else:
            await interaction.response.send_message("Settings not configured. Use /setup first.", ephemeral=True)
            return
        allowed_role_id = settings.get("queue_role")
        if allowed_role_id is not None:
            allowed_role_id = int(allowed_role_id)
        if os.path.exists(WAITLIST_PATH):
            with open(WAITLIST_PATH, 'r') as f:
                try:
                    waitlist = json.load(f)
                except Exception:
                    waitlist = []
        else:
            waitlist = []
        players = [entry["ign"] for entry in waitlist]
        players_lines = [f"{i+1}. {players[i] if i < len(players) else ''}" for i in range(10)]
        testers = get_testers_for_queue(interaction.channel.id)
        testers_lines = []
        for i in range(3):
            if i < len(testers):
                user_id = testers[i]
                testers_lines.append(f"{i+1}. <@{user_id}>")
            else:
                testers_lines.append(f"{i+1}.")
        embed = discord.Embed(
            title="Testing Queue - DEFAULT",
            description="Please use the command /join to join the DEFAULT queue\n\n**Players:**\n" + "\n".join(players_lines) + "\n\n**Testers**\n" + "\n".join(testers_lines),
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url="https://i.imgur.com/your-image.png")
        embed.timestamp = datetime.now(timezone.utc)
        view = QueueView()
        msg = await interaction.response.send_message(embed=embed, view=view)
        # Store the queue state
        set_testers_for_queue(interaction.channel.id, [])
        # Store the message ID for future updates
        sent_msg = await interaction.original_response()
        set_queue_message(interaction.channel.id, sent_msg.id)

async def setup(bot):
    await bot.add_cog(Waitlist(bot)) 

# Helper for atomic write

def atomic_write_json(path, data):
    dir_name = os.path.dirname(path)
    with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False) as tf:
        json.dump(data, tf, indent=2)
        tempname = tf.name
    os.replace(tempname, path) 