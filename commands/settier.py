import discord
from discord import app_commands
from discord.ext import commands
import json
import os

USERMETA_PATH = os.path.join("data", "usermetadata.json")

def load_usermeta():
    if os.path.exists(USERMETA_PATH):
        with open(USERMETA_PATH, 'r') as f:
            try:
                return json.load(f)
            except Exception:
                return {"discord_to_ign": {}, "ign_to_discord": {}}
    return {"discord_to_ign": {}, "ign_to_discord": {}}

def save_usermeta(usermeta):
    with open(USERMETA_PATH, 'w') as f:
        json.dump(usermeta, f, indent=2)

def update_usermeta(discord_id, ign_key, usermeta):
    # Remove IGN from any previous user
    prev_user = usermeta["ign_to_discord"].get(ign_key)
    if prev_user and prev_user != discord_id:
        if ign_key in usermeta["discord_to_ign"].get(prev_user, []):
            usermeta["discord_to_ign"][prev_user].remove(ign_key)
    # Remove IGN from all users (cleanup)
    for uid, igns in usermeta["discord_to_ign"].items():
        if ign_key in igns and uid != discord_id:
            igns.remove(ign_key)
    # Set new mapping
    usermeta["ign_to_discord"][ign_key] = discord_id
    if discord_id not in usermeta["discord_to_ign"]:
        usermeta["discord_to_ign"][discord_id] = []
    if ign_key not in usermeta["discord_to_ign"][discord_id]:
        usermeta["discord_to_ign"][discord_id].append(ign_key)
    save_usermeta(usermeta)

class ConfirmOverrideView(discord.ui.View):
    def __init__(self, discord_user_id, ign, command_args, usermeta, update_callback):
        super().__init__(timeout=60)
        self.discord_user_id = discord_user_id
        self.ign = ign
        self.command_args = command_args
        self.usermeta = usermeta
        self.update_callback = update_callback
        self.value = None

    @discord.ui.button(label="Override", style=discord.ButtonStyle.danger)
    async def override(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only allow the user who initiated the override to confirm
        if str(interaction.user.id) != self.discord_user_id:
            await interaction.response.send_message("You are not authorized to override this mapping.", ephemeral=True)
            return
        update_usermeta(self.discord_user_id, self.ign, self.usermeta)
        await interaction.response.send_message(f"Override confirmed. IGN `{self.ign}` is now mapped to you.", ephemeral=True)
        # Optionally, re-run the original command logic (e.g., update tierlist)
        if self.update_callback:
            await self.update_callback()
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_user_id:
            await interaction.response.send_message("You are not authorized to cancel this action.", ephemeral=True)
            return
        await interaction.response.send_message("Override cancelled.", ephemeral=True)
        self.value = False
        self.stop()

class SetTier(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="settier", description="Set a user's tier for a gamemode (admin only, does not broadcast)")
    @app_commands.describe(
        discord_user="Discord user to set tier for",
        ign="Minecraft IGN",
        new_tier="Tier to set (e.g., HT1, LT3)",
        gamemode="Gamemode (e.g., Sword, Mace)"
    )
    async def settier(self, interaction: discord.Interaction,
                      discord_user: discord.User,
                      ign: str,
                      new_tier: str,
                      gamemode: str):
        # Only allow admins to use this command
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You must be an administrator to use this command.", ephemeral=True)
            return
        # Load tierlist
        tierlist_path = os.path.join("data", "tierlist.json")
        if not os.path.exists(tierlist_path):
            await interaction.response.send_message("Tierlist file not found.", ephemeral=True)
            return
        with open(tierlist_path, 'r') as f:
            try:
                tierlist = json.load(f)
            except Exception:
                await interaction.response.send_message("Tierlist file is invalid.", ephemeral=True)
                return
        gamemode_key = gamemode.strip()
        new_tier_key = new_tier.strip()
        if gamemode_key not in tierlist:
            await interaction.response.send_message(f"Gamemode '{gamemode_key}' not found.", ephemeral=True)
            return
        if new_tier_key not in tierlist[gamemode_key]:
            await interaction.response.send_message(f"Tier '{new_tier_key}' not found in gamemode '{gamemode_key}'.", ephemeral=True)
            return
        # Remove IGN from all tiers in this gamemode
        for tier in tierlist[gamemode_key]:
            if ign in tierlist[gamemode_key][tier]:
                tierlist[gamemode_key][tier].remove(ign)
        # Add IGN to the new tier
        if ign not in tierlist[gamemode_key][new_tier_key]:
            tierlist[gamemode_key][new_tier_key].append(ign)
        # Save
        with open(tierlist_path, 'w') as f:
            json.dump(tierlist, f, indent=2)
        # --- User metadata logic ---
        usermeta = load_usermeta()
        discord_id = str(discord_user.id)
        ign_key = ign.strip()
        # Check for existing mapping
        existing_discord = usermeta["ign_to_discord"].get(ign_key)
        existing_igns = usermeta["discord_to_ign"].get(discord_id, [])
        if (existing_discord and existing_discord != discord_id) or (ign_key not in existing_igns and existing_igns):
            # Prompt for override
            async def update_callback():
                # After override, update mapping and inform user
                update_usermeta(discord_id, ign_key, usermeta)
            view = ConfirmOverrideView(discord_id, ign_key, None, usermeta, update_callback)
            await interaction.response.send_message(
                f"IGN `{ign_key}` is already mapped to another user or this user has a different IGN. Override?", view=view, ephemeral=True)
            return
        # Update mapping
        update_usermeta(discord_id, ign_key, usermeta)
        # --- End user metadata logic ---
        await interaction.response.send_message(f"Set {ign} to {new_tier_key} in {gamemode_key}.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(SetTier(bot)) 