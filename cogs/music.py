import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import os
import random
import json
import time

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.music_queues = {}
        self.is_playing = {}
        self.loop = {}
        self.current_song_info = {}
        self.last_message_time = {}
        
        # 播放清單儲存
        self.playlists = {}
        self.playlist_file = "playlists.json"
        self.load_playlists()
        
        # ✅ FFmpeg 設定（Railway 專用）
        self.ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn',
            'executable': '/usr/bin/ffmpeg'  # ✅ 加上這行
        }
        
        # ✅ yt-dlp 設定（不下載，只串流）
        self.ydl_options = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'default_search': 'auto',
            'source_address': '0.0.0.0',
            'cookiefile': '/app/cookies.txt',
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                    'skip': ['dash', 'hls']
                }
            }
        }
        self.ytdl = yt_dlp.YoutubeDL(self.ydl_options)

    # ========== 播放清單儲存 ==========
    def load_playlists(self):
        if os.path.exists(self.playlist_file):
            try:
                with open(self.playlist_file, 'r', encoding='utf-8') as f:
                    self.playlists = json.load(f)
            except:
                self.playlists = {}
        else:
            self.playlists = {}

    def save_playlists(self):
        with open(self.playlist_file, 'w', encoding='utf-8') as f:
            json.dump(self.playlists, f, ensure_ascii=False, indent=2)

    # ========== 本地 MP3 管理 ==========
    def get_local_songs(self):
        mp3_folder = "mp3"
        if not os.path.exists(mp3_folder):
            return []
        
        songs = []
        for file in os.listdir(mp3_folder):
            if file.endswith(('.mp3', '.m4a', '.wav')):
                songs.append({
                    'title': os.path.splitext(file)[0],
                    'path': os.path.join(mp3_folder, file)
                })
        return songs

    # ========== 音訊獲取 ==========
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

    async def _send_message(self, channel, content):
        guild_id = channel.guild.id if channel.guild else None
        if guild_id:
            now = time.time()
            last = self.last_message_time.get(guild_id, 0)
            if now - last < 2:
                await asyncio.sleep(2 - (now - last))
            self.last_message_time[guild_id] = time.time()
        
        try:
            await channel.send(content)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                print(f"⚠️ Rate Limit，等待重試...")
                await asyncio.sleep(e.retry_after if hasattr(e, 'retry_after') else 5)
                await channel.send(content)
            else:
                raise e

    # ========== 播放核心 ==========
    async def play_next(self, guild, channel=None):
        guild_id = guild.id
        voice_client = guild.voice_client
        
        if not voice_client:
            return
        
        # ✅ 如果正在播放，跳過
        if voice_client.is_playing():
            print("⏳ 正在播放中")
            return
        
        # ✅ 如果佇列空了，等待新歌（不斷開）
        if guild_id not in self.music_queues or not self.music_queues[guild_id]:
            print("📭 佇列已空")
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
        
        audio = discord.FFmpegPCMAudio(audio_url, **self.ffmpeg_options)
        voice_client.play(audio, after=after_playing)
        
        if channel is None:
            channel = guild.system_channel or guild.text_channels[0]
        await self._send_message(channel, f"🎶 正在播放：**{title}** (要求者：{requester.mention})")

    async def _delayed_play_next(self, guild, channel):
        await asyncio.sleep(1.5)
        await self.play_next(guild, channel)

    # ========== /upload ==========
    @app_commands.command(name="upload", description="上傳 MP3 檔案到機器人")
    @app_commands.describe(file="上傳 MP3 檔案")
    async def upload(self, interaction: discord.Interaction, file: discord.Attachment):
        if not file.filename.endswith(('.mp3', '.m4a', '.wav')):
            await interaction.response.send_message("❌ 請上傳 MP3、M4A 或 WAV 檔案！", ephemeral=True)
            return
        
        if file.size > 10 * 1024 * 1024:
            await interaction.response.send_message("❌ 檔案太大！請上傳小於 10MB 的檔案。", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            import aiohttp
            import aiofiles
            mp3_folder = "mp3"
            if not os.path.exists(mp3_folder):
                os.makedirs(mp3_folder)
            
            file_path = os.path.join(mp3_folder, file.filename)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(file.url) as response:
                    if response.status == 200:
                        async with aiofiles.open(file_path, 'wb') as f:
                            await f.write(await response.read())
                        
                        await interaction.followup.send(f"✅ 已上傳：**{file.filename}**", ephemeral=True)
                    else:
                        await interaction.followup.send("❌ 下載失敗，請稍後再試。", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 上傳失敗：{e}", ephemeral=True)

    # ========== /local ==========
    @app_commands.command(name="local", description="隨機播放本地 MP3")
    async def play_local(self, interaction: discord.Interaction):
        local_songs = self.get_local_songs()
        
        if not local_songs:
            await interaction.response.send_message("❌ mp3 資料夾中沒有歌曲！")
            return
        
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
        
        song = random.choice(local_songs)
        
        if not os.path.exists(song['path']):
            await interaction.followup.send(f"❌ 檔案不存在：{song['path']}")
            return
        
        audio = discord.FFmpegPCMAudio(song['path'], **self.ffmpeg_options)
        
        def after_playing(error):
            if error:
                print(f"播放錯誤：{error}")
        
        voice_client.play(audio, after=after_playing)
        
        await interaction.followup.send(f"🎵 正在播放：**{song['title']}**")

    # ========== /play ==========
    @app_commands.command(name="play", description="播放音樂")
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
        
        # ✅ 檢查是否為本地播放指令
        local_songs = self.get_local_songs()
        if query.lower() in ["local", "隨機", "random"] and local_songs:
            song = random.choice(local_songs)
            audio = discord.FFmpegPCMAudio(song['path'], **self.ffmpeg_options)
            
            self.music_queues[guild_id].append({
                'audio_url': song['path'],
                'title': song['title'],
                'requester': interaction.user
            })
            
            await interaction.followup.send(f"🎵 已加入佇列：**{song['title']}** (本地檔案)")
            
            if not voice_client.is_playing():
                await self.play_next(interaction.guild, interaction.channel)
            return
        
        # YouTube 播放
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

    # ========== /loop ==========
    @app_commands.command(name="loop", description="切換單曲循環")
    async def loop(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        current = self.loop.get(guild_id, False)
        self.loop[guild_id] = not current
        
        if self.loop[guild_id] and guild_id not in self.current_song_info:
            await interaction.response.send_message("⚠️ 目前沒有正在播放的歌曲，循環已開啟但需要先播放歌曲")
            return
        
        status = "🔂 已開啟單曲循環" if self.loop[guild_id] else "🔂 已關閉單曲循環"
        await interaction.response.send_message(f"✅ {status}", ephemeral=True)

    # ========== /skip ==========
    @app_commands.command(name="skip", description="跳過當前歌曲")
    async def skip(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            await interaction.response.send_message("❌ 沒有正在播放的歌曲")
            return
        
        guild_id = interaction.guild.id
        self.loop[guild_id] = False
        voice_client.stop()
        await interaction.response.send_message("⏭️ 已跳過")

    # ========== /stop ==========
    @app_commands.command(name="stop", description="停止播放並清空佇列")
    async def stop(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message("❌ 沒有正在播放的歌曲")
            return
        self.music_queues[guild_id] = []
        self.loop[guild_id] = False
        self.current_song_info[guild_id] = None
        self.is_playing[guild_id] = False
        voice_client.stop()
        await voice_client.disconnect()
        await interaction.response.send_message("⏹️ 已停止")

    # ========== /pause ==========
    @app_commands.command(name="pause", description="暫停播放")
    async def pause(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            await interaction.response.send_message("❌ 沒有正在播放的歌曲")
            return
        voice_client.pause()
        await interaction.response.send_message("⏸️ 已暫停")

    # ========== /resume ==========
    @app_commands.command(name="resume", description="繼續播放")
    async def resume(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_paused():
            await interaction.response.send_message("❌ 沒有被暫停的歌曲")
            return
        voice_client.resume()
        await interaction.response.send_message("▶️ 已繼續")

    # ========== /join ==========
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

    # ========== /leave ==========
    @app_commands.command(name="leave", description="機器人離開語音頻道")
    async def leave(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        voice_client = interaction.guild.voice_client
        guild_id = interaction.guild.id
        
        if not voice_client:
            await interaction.followup.send("❌ 我沒有在任何語音頻道中！", ephemeral=True)
            return
        
        try:
            self.music_queues[guild_id] = []
            self.loop[guild_id] = False
            self.current_song_info[guild_id] = None
            self.is_playing[guild_id] = False
            await voice_client.disconnect()
            await interaction.followup.send("👋 已離開語音頻道！", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 離開失敗：{e}", ephemeral=True)

    # ========== 播放清單功能 ==========

    @app_commands.command(name="playlist_create", description="建立播放清單")
    @app_commands.describe(name="播放清單名稱")
    async def playlist_create(self, interaction: discord.Interaction, name: str):
        user_id = str(interaction.user.id)
        
        if user_id not in self.playlists:
            self.playlists[user_id] = {}
        
        if name in self.playlists[user_id]:
            await interaction.response.send_message(f"❌ 播放清單 '{name}' 已存在！", ephemeral=True)
            return
        
        self.playlists[user_id][name] = []
        self.save_playlists()
        await interaction.response.send_message(f"✅ 已建立播放清單：{name}", ephemeral=True)

    @app_commands.command(name="playlist_add", description="加入歌曲到播放清單")
    @app_commands.describe(name="播放清單名稱", query="歌曲名稱或 YouTube 網址")
    async def playlist_add(self, interaction: discord.Interaction, name: str, query: str):
        user_id = str(interaction.user.id)
        
        if user_id not in self.playlists or name not in self.playlists[user_id]:
            await interaction.response.send_message(f"❌ 找不到播放清單 '{name}'", ephemeral=True)
            return
        
        try:
            async with interaction.channel.typing():
                loop = asyncio.get_event_loop()
                extract_info = functools.partial(self.ytdl.extract_info, query, download=False)
                data = await loop.run_in_executor(None, extract_info)
                
                if 'entries' in data:
                    data = data['entries'][0]
                
                song_info = {
                    'title': data.get('title', '未知歌曲'),
                    'url': data.get('webpage_url', query)
                }
                
                self.playlists[user_id][name].append(song_info)
                self.save_playlists()
                
                await interaction.response.send_message(f"✅ 已加入 '{song_info['title']}' 到 '{name}'", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 找不到歌曲：{e}", ephemeral=True)

    @app_commands.command(name="playlist_play", description="播放播放清單")
    @app_commands.describe(name="播放清單名稱")
    async def playlist_play(self, interaction: discord.Interaction, name: str):
        user_id = str(interaction.user.id)
        
        if user_id not in self.playlists or name not in self.playlists[user_id]:
            await interaction.response.send_message(f"❌ 找不到播放清單 '{name}'", ephemeral=True)
            return
        
        songs = self.playlists[user_id][name]
        if not songs:
            await interaction.response.send_message(f"❌ 播放清單 '{name}' 是空的", ephemeral=True)
            return
        
        if not interaction.user.voice:
            await interaction.response.send_message("❌ 你沒有在語音頻道中！", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client
        if not voice_client:
            voice_client = await voice_channel.connect()
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)
        
        guild_id = interaction.guild.id
        if guild_id not in self.music_queues:
            self.music_queues[guild_id] = []
        
        count = 0
        for song in songs:
            try:
                audio_url, title = await self.get_audio_url(song['url'])
                self.music_queues[guild_id].append({
                    'audio_url': audio_url,
                    'title': title,
                    'requester': interaction.user
                })
                count += 1
            except Exception as e:
                print(f"❌ 加入歌曲失敗：{e}")
        
        await interaction.followup.send(f"✅ 已加入播放清單 '{name}' ({count} 首歌曲)")
        
        if not voice_client.is_playing():
            await self.play_next(interaction.guild, interaction.channel)

    @app_commands.command(name="playlist_list", description="顯示你的播放清單")
    async def playlist_list(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        
        if user_id not in self.playlists or not self.playlists[user_id]:
            await interaction.response.send_message("📭 你還沒有建立任何播放清單", ephemeral=True)
            return
        
        msg = "📋 **你的播放清單：**\n"
        for name, songs in self.playlists[user_id].items():
            msg += f"\n🎵 **{name}** ({len(songs)} 首歌曲)"
        
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="playlist_show", description="顯示播放清單內容")
    @app_commands.describe(name="播放清單名稱")
    async def playlist_show(self, interaction: discord.Interaction, name: str):
        user_id = str(interaction.user.id)
        
        if user_id not in self.playlists or name not in self.playlists[user_id]:
            await interaction.response.send_message(f"❌ 找不到播放清單 '{name}'", ephemeral=True)
            return
        
        songs = self.playlists[user_id][name]
        if not songs:
            await interaction.response.send_message(f"📭 播放清單 '{name}' 是空的", ephemeral=True)
            return
        
        msg = f"📋 **播放清單：{name}** ({len(songs)} 首歌曲)\n"
        for i, song in enumerate(songs, 1):
            msg += f"\n{i}. {song['title']}"
            if len(msg) > 1800:
                msg += "\n... 還有更多歌曲"
                break
        
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="playlist_delete", description="刪除播放清單")
    @app_commands.describe(name="播放清單名稱")
    async def playlist_delete(self, interaction: discord.Interaction, name: str):
        user_id = str(interaction.user.id)
        
        if user_id not in self.playlists or name not in self.playlists[user_id]:
            await interaction.response.send_message(f"❌ 找不到播放清單 '{name}'", ephemeral=True)
            return
        
        del self.playlists[user_id][name]
        self.save_playlists()
        await interaction.response.send_message(f"✅ 已刪除播放清單：{name}", ephemeral=True)

    @app_commands.command(name="playlist_remove", description="從播放清單移除歌曲")
    @app_commands.describe(name="播放清單名稱", index="歌曲編號")
    async def playlist_remove(self, interaction: discord.Interaction, name: str, index: int):
        user_id = str(interaction.user.id)
        
        if user_id not in self.playlists or name not in self.playlists[user_id]:
            await interaction.response.send_message(f"❌ 找不到播放清單 '{name}'", ephemeral=True)
            return
        
        songs = self.playlists[user_id][name]
        if index < 1 or index > len(songs):
            await interaction.response.send_message(f"❌ 編號無效，請輸入 1 到 {len(songs)}", ephemeral=True)
            return
        
        removed = songs.pop(index - 1)
        self.save_playlists()
        await interaction.response.send_message(f"✅ 已移除 '{removed['title']}' 從 '{name}'", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MusicCog(bot))
