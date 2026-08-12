import discord
from discord import app_commands
from discord.ext import commands
import datetime

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="kick", description="踢出成員")
    @app_commands.describe(member="要踢出的成員", reason="原因")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "未提供原因"):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 你沒有權限", ephemeral=True)
            return
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 {member.mention} 已被踢出！")

    @app_commands.command(name="timeout", description="禁言成員")
    @app_commands.describe(member="要禁言的成員", minutes="分鐘", reason="原因")
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int = 5, reason: str = "未提供原因"):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 你沒有權限", ephemeral=True)
            return
        await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
        await interaction.response.send_message(f"🔇 {member.mention} 已被禁言 {minutes} 分鐘！")

    @app_commands.command(name="ban", description="封鎖成員")
    @app_commands.describe(member="要封鎖的成員", reason="原因")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "未提供原因"):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 你沒有權限", ephemeral=True)
            return
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 {member.mention} 已被封鎖！")

    @app_commands.command(name="unban", description="解除封鎖")
    @app_commands.describe(user_id="使用者ID")
    async def unban(self, interaction: discord.Interaction, user_id: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 你沒有權限", ephemeral=True)
            return
        user = await self.bot.fetch_user(int(user_id))
        await interaction.guild.unban(user)
        await interaction.response.send_message(f"✅ {user.name} 已解除封鎖")
        
    @app_commands.command(name="clear", description="清除頻道訊息")
    @app_commands.describe(amount="數量（最多100）")
    async def clear(self, interaction: discord.Interaction, amount: int = 10):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ 你沒有權限", ephemeral=True)
            return
        if amount > 100:
            await interaction.response.send_message("❌ 最多清除100條", ephemeral=True)
            return
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.response.send_message(f"🧹 已清除 {len(deleted)} 條訊息", ephemeral=True)
# ✅ 新版寫法：async def setup
async def setup(bot):
    await bot.add_cog(AdminCog(bot))