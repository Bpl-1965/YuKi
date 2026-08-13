import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import os
import random

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.music_queues = {}
        self.is_playing = {}
        
        # ✅ FFmpeg 設定（Railway 專用）
        self.ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }
        
        # ✅ yt-dlp 設定（不下載，只串流）
        self.ydl_options = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'default_search': 'auto',
            'source_address': '0.0.0.0',
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                    'skip': ['dash', 'hls']
                }
            }
        }
        self.ytdl = yt_dlp.YoutubeDL(self.ydl_options)

    async def get_audio_url(self, query):
        """只獲取音訊串流 URL，不下載"""
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: self.ytdl.extract_info(query, download=False))
            
            if 'entries' in data:
                data = data['entries'][0]
            
            title = data.get('title', '未知歌曲')
            audio_url = data.get('url')
            
            if not audio_url:
                raise Exception("無法獲取音訊網址")
            
            return audio_url, title
        except Exception as e:
            print(f"❌ 獲取音訊失敗：{e}")
            raise e

    async def play_next(self, guild, channel=None):
        guild_id = guild.id
        voice_client = guild.voice_client
        
        if not voice_client:
            return
        
        if guild_id not in self.music_queues or not self.music_queues[guild_id]:
            return
        
        if self.is_playing.get(guild_id, False):
            return
        
        song = self.music_queues[guild_id].pop(0)
        audio_url = song['audio_url']
        title = song['title']
        requester = song['requester']
        
        self.is_playing[guild_id] = True
        
        def after_playing(error):
            self.is_playing[guild_id] = False
            if error:
                print(f"播放錯誤：{error}")
                return
            asyncio.run_coroutine_threadsafe(
                self.play_next(guild, channel), 
                self.bot.loop
            )
        
        # ✅ 直接串流播放
        audio = discord.FFmpegPCMAudio(audio_url, **self.ffmpeg_options)
        voice_client.play(audio, after=after_playing)
        
        if channel is None:
            channel = guild.system_channel or guild.text_channels[0]
        await channel.send(f"🎶 正在播放：**{title}** (要求者：{requester.mention})")

    @app_commands.command(name="play", description="播放 YouTube 音樂")
    @app_commands.describe(query="歌曲名稱或 YouTube 網址")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        
        if not interaction.user.voice:
            await interaction.followup.send("❌ 你沒有在語音頻道中！")
            return
        
        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client
        if not voice_client:
            voice_client = await voice_channel.connect()
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)
        
        guild_id = interaction.guild.id
        if guild_id not in self.music_queues:
            self.music_queues[guild_id] = []
        
        try:
            async with interaction.channel.typing():
                audio_url, title = await self.get_audio_url(query)
        except Exception as e:
            await interaction.followup.send(f"❌ 找不到歌曲：{e}")
            return
        
        self.music_queues[guild_id].append({
            'audio_url': audio_url,
            'title': title,
            'requester': interaction.user
        })
        
        await interaction.followup.send(f"🎵 已加入佇列：**{title}**")
        
        if not voice_client.is_playing():
            await self.play_next(interaction.guild, interaction.channel)

    @app_commands.command(name="skip", description="跳過當前歌曲")
    async def skip(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            await interaction.response.send_message("❌ 沒有正在播放的歌曲")
            return
        voice_client.stop()
        await interaction.response.send_message("⏭️ 已跳過")

    @app_commands.command(name="stop", description="停止播放並清空佇列")
    async def stop(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message("❌ 沒有正在播放的歌曲")
            return
        self.music_queues[guild_id] = []
        voice_client.stop()
        await voice_client.disconnect()
        await interaction.response.send_message("⏹️ 已停止")

    @app_commands.command(name="join", description="機器人加入語音頻道")
    async def join(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.voice:
            await interaction.followup.send("❌ 你沒有在語音頻道中！", ephemeral=True)
            return
        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client
        try:
            if voice_client:
                await voice_client.move_to(voice_channel)
            else:
                await voice_channel.connect()
            await interaction.followup.send(f"✅ 已加入 {voice_channel.name}！", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 加入失敗：{e}", ephemeral=True)

    @app_commands.command(name="leave", description="機器人離開語音頻道")
    async def leave(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.followup.send("❌ 我沒有在任何語音頻道中！", ephemeral=True)
            return
        await voice_client.disconnect()
        await interaction.followup.send("👋 已離開語音頻道！", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MusicCog(bot))
