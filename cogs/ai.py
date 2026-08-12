import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import json
import os 

class AICog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_memories = {}
        self.DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
        self.DEEPSEEK_MODEL = "deepseek-chat"
        self.DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
        self.SYSTEM_PROMPT = "你是 YuKi，一個可愛的 AI 助手。"

    async def call_deepseek(self, messages):
        if not self.DEEPSEEK_API_KEY or self.DEEPSEEK_API_KEY == "你的DeepSeek金鑰":
            return "❌ 請設定 DeepSeek API 金鑰！"
        headers = {"Authorization": f"Bearer {self.DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": self.DEEPSEEK_MODEL, "messages": messages, "temperature": 0.7, "max_tokens": 1024}
        async with aiohttp.ClientSession() as session:
            async with session.post(self.DEEPSEEK_URL, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["choices"][0]["message"]["content"]
                return f"❌ API 錯誤 ({response.status})"

    @app_commands.command(name="ask", description="問 YuKi 任何問題")
    @app_commands.describe(question="你想問的問題")
    async def ask(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer()
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}, {"role": "user", "content": question}]
        reply = await self.call_deepseek(messages)
        await interaction.followup.send(f"💬 {reply}")

    @app_commands.command(name="chat", description="與 YuKi 連續對話")
    @app_commands.describe(message="你想說的話")
    async def chat(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        if user_id not in self.user_memories:
            self.user_memories[user_id] = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        self.user_memories[user_id].append({"role": "user", "content": message})
        if len(self.user_memories[user_id]) > 20:
            self.user_memories[user_id] = [self.user_memories[user_id][0]] + self.user_memories[user_id][-18:]
        reply = await self.call_deepseek(self.user_memories[user_id])
        self.user_memories[user_id].append({"role": "assistant", "content": reply})
        await interaction.followup.send(f"💬 {reply}")

    @app_commands.command(name="clearbot", description="清除你的對話記憶")
    async def clear(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if user_id in self.user_memories:
            self.user_memories[user_id] = [{"role": "system", "content": self.SYSTEM_PROMPT}]
            await interaction.response.send_message("🧹 已清除你的對話記憶！")
        else:
            await interaction.response.send_message("📭 你還沒有對話記錄")

# ✅ 新版寫法：async def setup
async def setup(bot):
    await bot.add_cog(AICog(bot))