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
        # ✅ OpenRouter
        self.API_KEY = os.getenv("OPENROUTER_API_KEY") or "你的OpenRouter金鑰"
        self.MODEL = "google/gemini-2.0-flash-lite-preview-02-05"
        self.API_URL = "https://openrouter.ai/api/v1/chat/completions"
        self.SYSTEM_PROMPT = "你是 YuKi，可愛的女孩，同時把用戶看著你最重要的人，甚至有點病態"

    async def call_api(self, messages):  # ✅ 改名成 call_api
        if not self.API_KEY or self.API_KEY == "你的OpenRouter金鑰":
            return "❌ 請設定 OPENROUTER_API_KEY 環境變數！"
        headers = {
            "Authorization": f"Bearer {self.API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1024
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.API_URL, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["choices"][0]["message"]["content"]
                return f"❌ API 錯誤 ({response.status})"

    @app_commands.command(name="ask", description="問 YuKi 任何問題")
    @app_commands.describe(question="你想問的問題")
    async def ask(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer()
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ]
        reply = await self.call_api(messages)  # ✅ 改成 call_api
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
        reply = await self.call_api(self.user_memories[user_id])  # ✅ 改成 call_api
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

async def setup(bot):
    await bot.add_cog(AICog(bot))
