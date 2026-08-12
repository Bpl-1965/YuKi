import discord
from discord import app_commands
from discord.ext import commands

class UtilityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="測試延遲")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"延遲 {round(self.bot.latency * 1000)}ms")

async def setup(bot):
    await bot.add_cog(UtilityCog(bot))