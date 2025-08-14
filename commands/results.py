import discord
from discord import app_commands
from discord.ext import commands
import json
import os

SETTINGS_FILE = "data/settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

class Results(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.settings = load_settings()

    @app_commands.command(name="setup", description="Setup a command's configuration (admin only)")
    @app_commands.describe(
        command="The command to setup (e.g., results, createqueue)",
        channel="Channel to use for the command (for results)",
        roles="Roles allowed to use the command (for results, comma-separated names or mentions)",
        role="Role allowed to use Join/Leave for createqueue (mention or name)",
        category="Category channel for ticket creation (mention)"
    )
    async def setup(self, interaction: discord.Interaction, command: str, channel: discord.TextChannel = None, roles: str = None, role: discord.Role = None, category: discord.CategoryChannel = None):
        # Only allow admins to use this command
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You must be an administrator to use this command.", ephemeral=True)
            return
        if command.lower() == "results":
            if channel is not None:
                self.settings['results_channel'] = channel.id
            if roles is not None:
                allowed_role_ids = []
                for r in roles.split(','):
                    r = r.strip()
                    if r.startswith('<@&') and r.endswith('>'):
                        try:
                            role_id = int(r[3:-1])
                            allowed_role_ids.append(role_id)
                        except ValueError:
                            continue
                    else:
                        role_obj = discord.utils.find(lambda role: role.name.lower() == r.lower(), interaction.guild.roles)
                        if role_obj:
                            allowed_role_ids.append(role_obj.id)
                self.settings['results_roles'] = allowed_role_ids
            save_settings(self.settings)
            await interaction.response.send_message(f"/results command configured. Channel: {channel.mention if channel else 'unchanged'}, Roles: {roles if roles else 'unchanged'}", ephemeral=True)
        elif command.lower() == "createqueue":
            if role is not None:
                self.settings['queue_role'] = role.id
            if category is not None:
                self.settings['queue_category'] = category.id
            save_settings(self.settings)
            await interaction.response.send_message(f"/createqueue configured. Role: {role.mention if role else 'unchanged'}, Category: {category.mention if category else 'unchanged'}", ephemeral=True)
        else:
            await interaction.response.send_message(f"Unknown command '{command}'.", ephemeral=True)

    @app_commands.command(name="results", description="Post a tier test result embed.")
    @app_commands.describe(
        tester="Discord user who tested",
        discord_user="Discord user tested",
        ign="Minecraft IGN",
        device="Device used",
        previous_tier="Previous tier",
        new_tier="New tier",
        gamemode="Gamemode (e.g., Mace)"
    )
    async def results(self, interaction: discord.Interaction,
                      tester: discord.User,
                      discord_user: discord.User,
                      ign: str,
                      device: str,
                      previous_tier: str,
                      new_tier: str,
                      gamemode: str):
        # Reload settings to reflect any changes made via the web config
        self.settings = load_settings()
        # Check if channel and roles are set
        channel_id = self.settings.get('results_channel')
        allowed_role_ids = self.settings.get('results_roles')
        # If roles are set, check if user has one of the allowed role IDs
        if allowed_role_ids:
            user_role_ids = [role.id for role in interaction.user.roles]
            print("User role IDs:", user_role_ids)
            print("Allowed role IDs:", allowed_role_ids)
            if not any(role_id in allowed_role_ids for role_id in user_role_ids):
                await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
                return
        embed = discord.Embed(
            title=f"Test Results of {ign}",
            color=discord.Color.green()
        )
        embed.add_field(name="Tester", value=tester.mention, inline=False)
        embed.add_field(name="Discord", value=discord_user.mention, inline=False)
        embed.add_field(name="IGN", value=ign, inline=False)
        embed.add_field(name="Device", value=device, inline=False)
        embed.add_field(name="Previous Tier", value=previous_tier, inline=False)
        embed.add_field(name="New Tier", value=new_tier, inline=False)
        embed.add_field(name="Gamemode", value=gamemode, inline=False)
        embed.set_thumbnail(url=f"https://minotar.net/helm/{ign}/100.png")
        embed.set_footer(text="Bot created by choice21")
        # If a channel is set, send there, else send error
        if channel_id:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                await channel.send(embed=embed)
                await interaction.response.send_message(f"Result posted in {channel.mention}", ephemeral=True)
            else:
                await interaction.response.send_message("Configured results channel not found or I lack permission to post there.", ephemeral=True)
            return
        else:
            await interaction.response.send_message("No results channel configured. Please use /setup to set one.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Results(bot)) 