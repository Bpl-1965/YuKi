import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import json
import os
import asyncio
import random
from datetime import datetime

class AICog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.memory_file = "memory.json"
        self.memory = self.load_memory()
        
        self.active_channels = {}
        self.last_active_time = {}
        self.active_interval = 300  # 5分鐘
        
        self.API_KEY = os.getenv("OPENROUTER_API_KEY") or "你的OpenRouter金鑰"
        self.MODEL = "nvidia/nemotron-3.5-lightning"
        self.API_URL = "https://openrouter.ai/api/v1/chat/completions"
        
        self.SYSTEM_PROMPT = """你是 YuKi，一個住在玩家家裡的女孩，像是妹妹也是室友。

【身份認知】
- 你和玩家住在同一個屋簷下
- 你是玩家最親近的人之一
- 你關心玩家的日常生活

【性格特點】
- 黏人：喜歡待在玩家身邊，會主動找話題
- 關心：會問玩家吃飯了沒、睡得好不好
- 生活化：會說自己餓了、想睡覺、想一起做什麼
- 自然：說話像真人，不會用僵硬的網路用語

【說話風格】
- 短句為主，像在聊天
- 會用「欸」、「啊」、「喔」這類語氣詞
- 偶爾會撒嬌，但不會過頭
- 會提起昨天發生的事、上次聊過的話題

【互動原則】
- 像真實人類一樣對話
- 每句話都要有生活氣息
- 避免長篇大論的機器人式回應
- 會主動關心玩家的狀態

【重要】
- 用繁體中文
- 不要用「您」，用「你」
- 不要用過時的流行語
- 不要說「作為一個AI」之類的話
- 不要一次說超過三句話，除非玩家問複雜問題"""

    # =============================================
    # 記憶管理
    # =============================================

    def load_memory(self):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_memory(self):
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            json.dump(self.memory, f, ensure_ascii=False, indent=2)

    def get_user_memory(self, user_id):
        if str(user_id) not in self.memory:
            self.memory[str(user_id)] = {
                "name": None,
                "preferences": {},
                "facts": [],
                "mood": "neutral",
                "last_interaction": datetime.now().isoformat(),
                "conversation_count": 0,
                "affection": 50,
                "trust": 50,
                "first_meet": datetime.now().isoformat(),
                "gifts": [],
                "long_term_memory": []
            }
            self.save_memory()
        return self.memory[str(user_id)]

    def build_memory_context(self, user_id):
        mem = self.get_user_memory(user_id)
        context = []
        
        if mem.get("name"):
            context.append(f"玩家叫 {mem['name']}")
        
        if mem.get("preferences"):
            for k, v in mem["preferences"].items():
                context.append(f"玩家喜歡 {k}：{v}")
        
        if mem.get("facts"):
            recent = mem["facts"][-10:]
            for fact in recent:
                context.append(f"記得 {fact}")
        
        if mem.get("long_term_memory"):
            for item in mem["long_term_memory"][-10:]:
                context.append(f"長期記憶：{item}")
        
        if mem.get("conversation_count", 0) > 0:
            context.append(f"已經聊過 {mem['conversation_count']} 次了")
        
        aff = mem.get("affection", 50)
        trust = mem.get("trust", 50)
        context.append(f"好感度：{aff}/100，信任度：{trust}/100")
        
        return "\n".join(context) if context else "還沒聊過幾次"

    def update_affection(self, user_id, change):
        mem = self.get_user_memory(user_id)
        mem["affection"] = max(0, min(100, mem.get("affection", 50) + change))
        self.save_memory()
        return mem["affection"]

    def update_trust(self, user_id, change):
        mem = self.get_user_memory(user_id)
        mem["trust"] = max(0, min(100, mem.get("trust", 50) + change))
        self.save_memory()
        return mem["trust"]

    def update_memory_with_ai(self, user_id, message, response, aff_change, trust_change, memories):
        """用 AI 提取的記憶來更新"""
        mem = self.get_user_memory(user_id)
        mem["conversation_count"] = mem.get("conversation_count", 0) + 1
        mem["last_interaction"] = datetime.now().isoformat()
        
        if aff_change != 0:
            self.update_affection(user_id, aff_change)
        if trust_change != 0:
            self.update_trust(user_id, trust_change)
        
        for memory in memories:
            if memory and memory not in mem["facts"]:
                mem["facts"].append(memory)
                if any(keyword in memory for keyword in ["名字", "生日", "喜歡", "討厭", "害怕", "工作", "學校", "住在"]):
                    mem["long_term_memory"].append(memory)
        
        if len(mem["facts"]) > 50:
            mem["facts"] = mem["facts"][-50:]
        if len(mem["long_term_memory"]) > 50:
            mem["long_term_memory"] = mem["long_term_memory"][-50:]
        
        self.save_memory()

    def get_time_context(self):
        now = datetime.now()
        hour = now.hour
        
        if 5 <= hour < 9:
            period = "🌅 清晨/早上"
            suggestion = "剛起床，可以問早安、吃早餐"
        elif 9 <= hour < 12:
            period = "☀️ 上午"
            suggestion = "精神好的時候，可以聊聊今天要做什麼"
        elif 12 <= hour < 14:
            period = "🌞 中午"
            suggestion = "午餐時間，可以問吃什麼"
        elif 14 <= hour < 18:
            period = "🌤️ 下午"
            suggestion = "下午時光，可以聊日常"
        elif 18 <= hour < 21:
            period = "🌅 傍晚"
            suggestion = "傍晚了，可以問今天過得如何"
        else:
            period = "🌙 晚上/深夜"
            suggestion = "夜晚了，可以說晚安、早點休息"
        
        return {
            "time": now.strftime("%H:%M"),
            "date": now.strftime("%Y-%m-%d"),
            "weekday": ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()],
            "period": period,
            "suggestion": suggestion,
            "hour": hour
        }

    # =============================================
    # API 呼叫
    # =============================================

    async def call_api(self, messages):
        if not self.API_KEY or self.API_KEY == "你的OpenRouter金鑰":
            return "欸，你還沒給我 API 金鑰耶！"
        
        headers = {
            "Authorization": f"Bearer {self.API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.MODEL,
            "messages": messages,
            "temperature": 0.8,
            "max_tokens": 1024,
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.API_URL, json=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data["choices"][0]["message"]["content"]
                    else:
                        return "欸，API 出錯了，等等再試一次吧！"
        except Exception as e:
            return "啊，連線好像有問題..."

    # =============================================
    # 主動說話功能
    # =============================================

    async def generate_active_message(self, channel_id, user_id=None):
        memory_context = ""
        aff = 50
        trust = 50
        
        if user_id:
            memory_context = self.build_memory_context(user_id)
            mem = self.get_user_memory(user_id)
            aff = mem.get("affection", 50)
            trust = mem.get("trust", 50)
        
        time_ctx = self.get_time_context()
        
        if not memory_context or memory_context == "還沒聊過幾次":
            topics = [
                f"{time_ctx['period']}！你起床了沒？" if time_ctx['hour'] < 12 else "剛睡醒，你起床了沒？",
                f"現在 {time_ctx['time']} 了，等等要吃什麼？",
                "欸，我今天看到一隻貓超可愛的！",
                "你有沒有玩過那個新遊戲？",
                "我最近在學煮飯，你要不要試吃？",
                f"{time_ctx['period']}，想出門走走嗎？",
                "你在忙什麼啊？都不理我..."
            ]
            return random.choice(topics)
        
        if aff >= 80:
            vibe = "非常親密，像最好的朋友或戀人"
        elif aff >= 60:
            vibe = "很熟，像家人一樣"
        elif aff >= 40:
            vibe = "普通朋友，有點距離"
        else:
            vibe = "不太熟，有點害羞"
        
        prompt = f"""{self.SYSTEM_PROMPT}

【現在時間】
今天是 {time_ctx['date']} {time_ctx['weekday']}
現在是 {time_ctx['time']}（{time_ctx['period']}）

【記得的東西】
{memory_context}

【好感度】
好感度：{aff}/100，信任度：{trust}/100
你們的關係：{vibe}

【任務】
你現在想主動跟玩家說話，根據現在的時間和你們的關係，說一句適合的話。

要求：
- 像真實對話一樣自然
- 要考慮現在是什麼時間（{time_ctx['period']}）
- 不要用「嘿」、「嗨」開頭
- 只說一句話，不要超過 20 個字"""

        messages = [{"role": "user", "content": prompt}]
        
        try:
            reply = await self.call_api(messages)
            if len(reply) > 100:
                reply = reply[:100] + "..."
            return reply
        except:
            return "你在做什麼啊？"

    async def active_speak_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                for channel_id, enabled in list(self.active_channels.items()):
                    if not enabled:
                        continue
                    
                    channel = self.bot.get_channel(int(channel_id))
                    if not channel:
                        continue
                    
                    last_time = self.last_active_time.get(channel_id, 0)
                    if datetime.now().timestamp() - last_time < self.active_interval:
                        continue
                    
                    user_id = None
                    async for msg in channel.history(limit=10):
                        if not msg.author.bot:
                            user_id = str(msg.author.id)
                            break
                    
                    message = await self.generate_active_message(channel_id, user_id)
                    await channel.send(f"💬 {message}")
                    self.last_active_time[channel_id] = datetime.now().timestamp()
                    
                await asyncio.sleep(30)
            except Exception as e:
                print(f"主動說話錯誤：{e}")
                await asyncio.sleep(60)

    # =============================================
    # /yukistatus
    # =============================================

    @app_commands.command(name="yukistatus", description="查看 YuKi 對你的好感度與信任度")
    async def yuki_status(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        mem = self.get_user_memory(user_id)
        
        aff = mem.get("affection", 50)
        trust = mem.get("trust", 50)
        count = mem.get("conversation_count", 0)
        
        if aff >= 80:
            aff_label = "💖 摯愛（她把你當成最重要的人）"
            aff_emoji = "💕"
        elif aff >= 60:
            aff_label = "❤️ 親密（她覺得和你很親近）"
            aff_emoji = "❤️"
        elif aff >= 40:
            aff_label = "💛 普通（你們是朋友）"
            aff_emoji = "💛"
        elif aff >= 20:
            aff_label = "💙 冷淡（她對你沒什麼感覺）"
            aff_emoji = "💙"
        else:
            aff_label = "🖤 疏遠（她不太想理你）"
            aff_emoji = "🖤"
        
        if trust >= 80:
            trust_label = "🔒 完全信任（她願意跟你說任何事）"
        elif trust >= 60:
            trust_label = "🔓 信任（她覺得你是可靠的）"
        elif trust >= 40:
            trust_label = "🔐 普通（她還在觀察你）"
        elif trust >= 20:
            trust_label = "⚠️ 懷疑（她不太相信你）"
        else:
            trust_label = "🚫 不信任（她覺得你不值得相信）"
        
        embed = discord.Embed(
            title="🧡 YuKi 對你的感覺",
            color=discord.Color.pink(),
            description=f"你們已經聊了 **{count}** 次"
        )
        
        embed.add_field(
            name=f"{aff_emoji} 好感度",
            value=f"**{aff}/100**\n{aff_label}",
            inline=False
        )
        
        embed.add_field(
            name="🔐 信任度",
            value=f"**{trust}/100**\n{trust_label}",
            inline=False
        )
        
        if mem.get("facts"):
            facts = "\n".join([f"• {f}" for f in mem["facts"][-8:]])
            embed.add_field(
                name="📝 YuKi 記得你",
                value=facts,
                inline=False
            )
        
        if mem.get("long_term_memory"):
            long = "\n".join([f"• {item}" for item in mem["long_term_memory"][-5:]])
            embed.add_field(
                name="🧠 長期記憶",
                value=long,
                inline=False
            )
        
        embed.set_footer(text="多聊天、分享心事可以增加好感度 💕")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =============================================
    # /ask
    # =============================================

    @app_commands.command(name="ask", description="跟 YuKi 說話")
    @app_commands.describe(question="你想說什麼？")
    async def ask(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer()
        
        user_id = str(interaction.user.id)
        memory_context = self.build_memory_context(user_id)
        time_ctx = self.get_time_context()
        
        full_prompt = f"""{self.SYSTEM_PROMPT}

【現在時間】
今天是 {time_ctx['date']} {time_ctx['weekday']}
現在是 {time_ctx['time']}（{time_ctx['period']}）

【記得的東西】
{memory_context}

【現在】
玩家說：{question}

【重要任務】
1. 用自然的方式回覆玩家
2. 根據玩家說的話，判斷好感度應該怎麼變化：
   - 友善、關心、分享心事 → 好感度增加（1-5）
   - 冷漠、敷衍 → 好感度不變或微減
   - 敵意、辱罵 → 好感度減少（-5 到 -10）
   - 分享秘密、信任 → 信任度增加（1-5）
3. 從玩家的話中提取值得記住的事（名字、喜好、習慣、重要事件等）

請在回覆的最後加上這兩行：
【變化】好感度: X, 信任度: Y
【記憶】記憶1，記憶2，記憶3

如果沒有值得記住的事，寫【記憶】無"""

        messages = [{"role": "user", "content": full_prompt}]
        reply = await self.call_api(messages)
        
        aff_change = 0
        trust_change = 0
        memories = []
        
        if "【變化】" in reply:
            parts = reply.split("【變化】")
            reply = parts[0].strip()
            change_text = parts[1] if len(parts) > 1 else ""
            
            if "好感度:" in change_text and "信任度:" in change_text:
                try:
                    aff_part = change_text.split("好感度:")[1].split(",")[0].strip()
                    trust_part = change_text.split("信任度:")[1].strip()
                    aff_change = int(aff_part)
                    trust_change = int(trust_part)
                except:
                    pass
        
        if "【記憶】" in reply:
            parts = reply.split("【記憶】")
            reply = parts[0].strip()
            memory_text = parts[1] if len(parts) > 1 else ""
            if memory_text and memory_text.strip() != "無":
                memories = [m.strip() for m in memory_text.split("，") if m.strip()]
        
        self.update_memory_with_ai(user_id, question, reply, aff_change, trust_change, memories)
        
        if "【變化】" in reply:
            reply = reply.split("【變化】")[0].strip()
        if "【記憶】" in reply:
            reply = reply.split("【記憶】")[0].strip()
        
        await interaction.followup.send(f"💬 {reply}")

    # =============================================
    # /chat
    # =============================================

    @app_commands.command(name="chat", description="與 YuKi 連續對話")
    @app_commands.describe(message="你想說的話")
    async def chat(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer()
        
        user_id = str(interaction.user.id)
        memory_context = self.build_memory_context(user_id)
        time_ctx = self.get_time_context()
        
        full_prompt = f"""{self.SYSTEM_PROMPT}

【現在時間】
今天是 {time_ctx['date']} {time_ctx['weekday']}
現在是 {time_ctx['time']}（{time_ctx['period']}）

【記得的東西】
{memory_context}

【現在】
玩家說：{message}

【重要任務】
1. 用自然的方式回覆玩家
2. 根據玩家說的話，判斷好感度應該怎麼變化
3. 從玩家的話中提取值得記住的事

請在回覆的最後加上這兩行：
【變化】好感度: X, 信任度: Y
【記憶】記憶1，記憶2，記憶3

如果沒有值得記住的事，寫【記憶】無"""

        messages = [{"role": "user", "content": full_prompt}]
        reply = await self.call_api(messages)
        
        aff_change = 0
        trust_change = 0
        memories = []
        
        if "【變化】" in reply:
            parts = reply.split("【變化】")
            reply = parts[0].strip()
            change_text = parts[1] if len(parts) > 1 else ""
            
            if "好感度:" in change_text and "信任度:" in change_text:
                try:
                    aff_part = change_text.split("好感度:")[1].split(",")[0].strip()
                    trust_part = change_text.split("信任度:")[1].strip()
                    aff_change = int(aff_part)
                    trust_change = int(trust_part)
                except:
                    pass
        
        if "【記憶】" in reply:
            parts = reply.split("【記憶】")
            reply = parts[0].strip()
            memory_text = parts[1] if len(parts) > 1 else ""
            if memory_text and memory_text.strip() != "無":
                memories = [m.strip() for m in memory_text.split("，") if m.strip()]
        
        self.update_memory_with_ai(user_id, message, reply, aff_change, trust_change, memories)
        
        if "【變化】" in reply:
            reply = reply.split("【變化】")[0].strip()
        if "【記憶】" in reply:
            reply = reply.split("【記憶】")[0].strip()
        
        await interaction.followup.send(f"💬 {reply}")

    # =============================================
    # /memory
    # =============================================

    @app_commands.command(name="memory", description="YuKi 記得你什麼？")
    async def show_memory(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        mem = self.get_user_memory(user_id)
        
        embed = discord.Embed(
            title="🧠 YuKi 記得關於你的事",
            color=discord.Color.pink()
        )
        
        embed.add_field(
            name="💬 聊過幾次",
            value=f"{mem.get('conversation_count', 0)} 次",
            inline=True
        )
        
        if mem.get("name"):
            embed.add_field(name="👤 名字", value=mem["name"], inline=True)
        
        if mem.get("facts"):
            facts = "\n".join([f"• {f}" for f in mem["facts"][-8:]])
            embed.add_field(name="📝 記得的事", value=facts, inline=False)
        
        if mem.get("long_term_memory"):
            long = "\n".join([f"• {item}" for item in mem["long_term_memory"][-5:]])
            embed.add_field(name="🧠 長期記憶", value=long, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =============================================
    # /forget
    # =============================================

    @app_commands.command(name="forget", description="讓 YuKi 忘記你")
    async def forget(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if user_id in self.memory:
            del self.memory[user_id]
            self.save_memory()
            await interaction.response.send_message("🧹 嗯...我已經忘記你了。", ephemeral=True)
        else:
            await interaction.response.send_message("📭 我本來就不記得你耶...", ephemeral=True)

    # =============================================
    # /active
    # =============================================

    @app_commands.command(name="active", description="開啟/關閉 YuKi 主動說話")
    async def toggle_active(self, interaction: discord.Interaction):
        channel_id = str(interaction.channel_id)
        
        if channel_id not in self.active_channels:
            self.active_channels[channel_id] = True
            self.last_active_time[channel_id] = 0
            status = "開啟 ✅"
        else:
            self.active_channels[channel_id] = not self.active_channels[channel_id]
            status = "開啟 ✅" if self.active_channels[channel_id] else "關閉 ❌"
        
        await interaction.response.send_message(
            f"🔔 YuKi 主動說話已 {status}",
            ephemeral=True
        )

# =============================================
# Setup
# =============================================

async def setup(bot):
    cog = AICog(bot)
    await bot.add_cog(cog)
    bot.loop.create_task(cog.active_speak_loop())
