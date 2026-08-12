import discord
from discord import app_commands
from discord.ext import commands
import os
import sys

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    print("❌ 錯誤: DISCORD_TOKEN 環境變數未設定！")
    exit()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ 已登入為 {bot.user}")
    print(f"📡 延遲: {round(bot.latency * 1000)}ms")
    
    # 載入所有 Cog
    cogs = ["ai", "music", "admin", "utility"]
    for cog in cogs:
        try:
            await bot.load_extension(f"cogs.{cog}")
            print(f"✅ 已載入 cogs.{cog}")
        except Exception as e:
            print(f"❌ 載入 cogs.{cog} 失敗：{e}")
    
    await bot.tree.sync()
    print("✅ 已同步斜杠指令")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)