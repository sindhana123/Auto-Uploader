import asyncio
from config import Config
from utils.ffmpeg import get_video_resolution, strip_and_mux_audio, get_media_info
from database import db
import os
import shutil
import time
import re
import html
from pyrogram import enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

SEASON_EPISODE_PATTERNS = [
    (re.compile(r'S(\d+)(?:E|EP)(\d+)'), ('season', 'episode')),
    (re.compile(r'S(\d+)[\s-]*(?:E|EP)(\d+)'), ('season', 'episode')),
    (re.compile(r'Season\s*(\d+)\s*Episode\s*(\d+)', re.IGNORECASE), ('season', 'episode')),
    (re.compile(r'\[S(\d+)\]\[E(\d+)\]'), ('season', 'episode')),
    (re.compile(r'S(\d+)[^\d]*(\d+)'), ('season', 'episode')),
    (re.compile(r'(?:E|EP|Episode)\s*(\d+)', re.IGNORECASE), (None, 'episode')),
    (re.compile(r'\b(\d+)\b'), (None, 'episode'))
]

def extract_season_episode(filename):
    for pattern, (season_group, episode_group) in SEASON_EPISODE_PATTERNS:
        match = pattern.search(filename)
        if match:
            season = match.group(1) if season_group else None
            episode = match.group(2 if season_group else 1)
            return season, episode
    return None, None

def extract_quality_from_filename(filename):
    match = re.search(r'(360p|480p|720p|1080p|1440p|2160p|4k)', filename, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return "-"

def humanbytes(size):
    if not size:
        return "0 B"
    power = 2**10
    n = 0
    Dic_powerN = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size > power and n < 4:
        size /= power
        n += 1
    return f"{round(size, 2)} {Dic_powerN[n]}"

process_queue = asyncio.Queue()
USER_CANCELLATIONS = set()

async def worker(client):
    while True:
        job = await process_queue.get()
        user_id = job.get('user_id')
        try:
            await process_job(client, job)
        except Exception as e:
            print(f"Error processing job: {e}")
        finally:
            if user_id in USER_CANCELLATIONS:
                USER_CANCELLATIONS.discard(user_id)
            process_queue.task_done()

def get_progress_text(ep, state, anime, s_and_e, quality, filename):
    return (
        f"**[ Episode : {ep} ]**\n"
        f"**state** - {state}\n"
        f"**anime name** - {anime}\n"
        f"**season and episode** - {s_and_e}\n"
        f"**quality** - {quality}\n"
        f"**Filename** - `{filename}`"
    )

def sort_key(res_str):
    if "480" in res_str: return 1
    if "720" in res_str: return 2
    if "1080" in res_str: return 3
    if "4k" in res_str.lower(): return 4
    return 10

def safe_format(template, **kwargs):
    temp_tpl = template
    # Force 02d formatting specifiers for season and episode placeholders
    temp_tpl = re.sub(r'\{season(?::[^}]+)?\}', '{season:02d}', temp_tpl)
    temp_tpl = re.sub(r'\{episode(?::[^}]+)?\}', '{episode:02d}', temp_tpl)
    
    formatted_kwargs = dict(kwargs)
    try:
        if 'season' in formatted_kwargs:
            formatted_kwargs['season'] = int(str(formatted_kwargs['season']).strip())
    except Exception:
        pass
    try:
        if 'episode' in formatted_kwargs:
            formatted_kwargs['episode'] = int(str(formatted_kwargs['episode']).strip())
    except Exception:
        pass
        
    try:
        return temp_tpl.format(**formatted_kwargs)
    except Exception:
        # Fallback to simple replace
        res = template
        for k, v in kwargs.items():
            val_str = str(v)
            if k in ['season', 'episode']:
                try:
                    if int(v) < 10:
                        val_str = f"{int(v):02d}"
                except Exception:
                    pass
            res = re.sub(r'\{' + k + r'(?::[^}]+)?\}', val_str, res)
        return res

async def apply_metadata(input_path, output_path, user_id):
    settings = await db.get_user_settings(user_id)
    if settings.get("metadata", "Off") == "Off":
        shutil.copy2(input_path, output_path)
        return True
        
    metadata_txt = settings.get("metadata_txt", "")
    if not metadata_txt:
        shutil.copy2(input_path, output_path)
        return True
        
    cmd_args = ["ffmpeg", "-y", "-i", input_path]
    cmd_args.extend(["-metadata", f"title={metadata_txt}"])
    cmd_args.extend(["-metadata", f"artist={metadata_txt}"])
    cmd_args.extend(["-metadata", f"author={metadata_txt}"])
    cmd_args.extend(["-metadata:s:v", f"title={metadata_txt}"])
    cmd_args.extend(["-metadata:s:a", f"title={metadata_txt}"])
    cmd_args.extend(["-metadata:s:s", f"title={metadata_txt}"])
    
    cmd_args.extend(["-map", "0"])
        
    cmd_args.extend(["-c", "copy", output_path])
    
    process = await asyncio.create_subprocess_exec(
        *cmd_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return process.returncode == 0

async def process_job(client, job):
    user_id = job['user_id']
    status_msg = job['status_msg_id']
    chat_id = job['chat_id']
    settings = await db.get_user_settings(user_id)
    
    # 1. Fetch first video details context for filename extraction
    original_name = "Unknown.mkv"
    try:
        first_v_msg = await client.get_messages(job['video_msgs'][0]['chat_id'], job['video_msgs'][0]['msg_id'])
        original_name = getattr(first_v_msg.video or first_v_msg.document, "file_name", "Unknown.mkv")
    except Exception as e:
        print(f"Error fetching first video message profile: {e}")
        
    # 2. Extract season and episode dynamically
    season_ext, episode_ext = extract_season_episode(original_name)
    if season_ext:
        job['season'] = season_ext
    if episode_ext:
        job['episode'] = episode_ext
        
    for key in ['season', 'episode']:
        val = job.get(key, '01')
        try:
            if int(val) < 10:
                job[key] = f"{int(val):02d}"
            else:
                job[key] = str(int(val))
        except (ValueError, TypeError):
            pass
        
    # 3. Channel resolution based on auto routing settings
    auto_routing = settings.get('auto_channel_match', 'on') == 'on'
    target_chat = job.get('target_channel_id')
    channel = None
    
    if auto_routing:
        # If not set in the job already, try auto matching
        channel = await db.match_channel(user_id, original_name)
        if channel and not target_chat:
            target_chat = channel['channel_id']
            
    if not target_chat:
        target_chat = chat_id
        
    if isinstance(target_chat, str) and (target_chat.startswith("-") or target_chat.isdigit()):
        try:
            target_chat = int(target_chat)
        except ValueError:
            pass
            
    # 4. Pre-post "Episode : {episode_number}" to target chat
    try:
        await client.send_message(target_chat, f"**Episode : {job.get('episode', '01')}**")
    except Exception as e:
        print(f"Error pre-posting episode header to chat: {e}")
        
    # Create the progress status message DIRECTLY inside the target channel!
    status_msg_node = None
    try:
        status_msg_node = await client.send_message(target_chat, text="⏳ Starting process...")
    except Exception as e:
        print(f"Error sending progress message to channel: {e}")
        
    status_msg_node_id = status_msg_node.id if status_msg_node else None
    
    ep = str(job.get('episode', '?')).zfill(2)
    s = str(job.get('season', '?')).zfill(2)
    
    # Dynamic anime name guessing
    anime = job.get('anime_name')
    if not anime:
        if channel:
            anime = channel.get('title', 'Unknown')
        else:
            try:
                parts = original_name.split(' - ')
                if len(parts) > 1:
                    s_first, ep_first = extract_season_episode(parts[0])
                    if s_first or ep_first:
                        anime = parts[1].split('[')[0].strip()
                    else:
                        anime = parts[0].split('[')[0].strip()
                else:
                    anime = original_name.split('.')[0].strip()
            except Exception:
                anime = "Unknown"
    s_e = f"S{s}E{ep}"
    
    async def update_state(state_header, progress_bar="", quality="-", filename="-"):
        disp_filename = filename
            
        esc_header = html.escape(str(state_header))
        esc_anime = html.escape(str(anime))
        esc_quality = html.escape(str(quality))
        esc_ep = html.escape(str(ep))
        esc_filename = html.escape(str(disp_filename))
        
        text = (
            f"<blockquote>{esc_header}</blockquote>\n\n"
            f"<blockquote>🎬 <b>𝗔𝗻𝗶𝗺𝗲 :</b> {esc_anime}\n"
            f"📦 <b>𝗤𝘂𝗮𝗹𝗶𝘁𝘆 :</b> {esc_quality}\n"
            f"🔢 <b>𝗘𝗽𝗶𝘀𝗼𝗱𝗲 :</b> {esc_ep}\n"
            f"📁 <b>𝗙𝗶𝗹𝗲 :</b> <code>{esc_filename}</code>"
        )
        if progress_bar:
            esc_progress = html.escape(str(progress_bar))
            text += f"\n\n<b>{esc_progress}</b>"
        text += "</blockquote>"
            
        if status_msg_node_id:
            try:
                await client.edit_message_text(target_chat, status_msg_node_id, text, parse_mode=enums.ParseMode.HTML)
                return
            except Exception:
                pass
        # Fallback to PM if channel edit fails
        try:
            await client.edit_message_text(chat_id, status_msg, text, parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass

    # Process start
    loop = asyncio.get_running_loop()
    dl_start = [0]
    last_dl_update = [0]
    
    def dl_progress_cb(current, total, file_label="", quality_label="-"):
        if job.get('user_id') in USER_CANCELLATIONS:
            raise RuntimeError("TaskCancelledByUser")
        now = time.time()
        if dl_start[0] == 0:
            dl_start[0] = now
        if now - last_dl_update[0] < 8 and current < total:
            return
        last_dl_update[0] = now
        
        percent = (current / total) * 100 if total else 0
        filled = int(percent / 10)
        bar = "■" * filled + "□" * (10 - filled)
        
        elapsed = now - dl_start[0]
        speed = current / elapsed if elapsed > 0 else 0
        eta = ""
        if speed > 0:
            eta_seconds = (total - current) / speed
            eta = f" | ETA: {int(eta_seconds)}s"
            
        speed_text = f"{humanbytes(speed)}/s" if speed else "—/s"
        progress_bar = f"[{bar}] {percent:.1f}% ({humanbytes(current)} of {humanbytes(total)} @ {speed_text}{eta})"
        
        asyncio.run_coroutine_threadsafe(
            update_state("📥 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱𝗶𝗻𝗴 𝗔𝗻𝗶𝗺𝗲 𝗙𝗶𝗹𝗲...", progress_bar, quality_label, file_label),
            loop
        )

    await update_state("⏳ Starting resource downloads...")
    
    # 2. Fetch video messages sequentially by message ID (preserving chronological forwarding order)
    resolved_videos = []
    in_order_msgs = sorted(job['video_msgs'], key=lambda x: x['msg_id'])
    for vm in in_order_msgs:
        try:
            v_msg = await client.get_messages(vm['chat_id'], vm['msg_id'])
            v_orig_name = getattr(v_msg.video or v_msg.document, "file_name", "")
            q = extract_quality_from_filename(v_orig_name)
        except Exception:
            v_msg = None
            q = "-"
        resolved_videos.append((vm, q, v_msg))
        
    # Preserve the exact sequence the user sent the videos in
    # (Removed quality sorting as requested by user)
    
    # Update job['video_msgs'] and cache messages list
    job['video_msgs'] = [rv[0] for rv in resolved_videos]
    cached_video_msgs = [rv[2] for rv in resolved_videos]
    
    original_qualities = {}
    predicted_filenames = {}
    
    prefix = settings.get('prefix', '')
    suffix = settings.get('suffix', '')
    fmt = settings.get("rename_format", "{anime} - S{season:02d}E{episode:02d} [{language}] {quality} @suffix.mkv")
    
    ext = ".mkv"
    base_fmt = fmt
    if fmt.lower().endswith(".mkv"):
        base_fmt = fmt[:-4]
        ext = ".mkv"
    elif fmt.lower().endswith(".mp4"):
        base_fmt = fmt[:-4]
        ext = ".mp4"
        
    for i, rv in enumerate(resolved_videos):
        q = rv[1]
        original_qualities[i] = q
        try:
            filename_base = safe_format(
                base_fmt,
                anime=anime,
                season=job.get('season', '01'),
                episode=job.get('episode', '01'),
                language=job.get('language', 'Unknown'),
                quality=q
            )
            if prefix: filename_base = f"{prefix} {filename_base}"
            if suffix: filename_base = f"{filename_base} {suffix}"
            predicted_filenames[i] = f"{filename_base}{ext}"
        except Exception:
            predicted_filenames[i] = "video.mkv"
            
    job_id = f"job_{user_id}_{status_msg}"
    work_dir = os.path.join("temp", job_id)
    os.makedirs(work_dir, exist_ok=True)
    
    # Download custom thumbnail if configured
    custom_thumb = settings.get("thumbnail")
    thumb_path = None
    if custom_thumb:
        try:
            thumb_path = await client.download_media(message=custom_thumb, file_name=os.path.join(work_dir, "thumb.jpg"))
        except Exception as e:
            print(f"Error downloading user thumbnail: {e}")
            
    try:
        process_mode = settings.get("process_mode", "merge")
        audio_path = None
        if process_mode != "rename_only":
            audio_msg = await client.get_messages(job['audio_msg']['chat_id'], job['audio_msg']['msg_id'])
            dl_start[0] = time.time()
            last_dl_update[0] = 0
            audio_path = await audio_msg.download(
                file_name=os.path.join(work_dir, "audio.m4a"),
                progress=lambda c, t: dl_progress_cb(c, t, "audio_stream", "-")
            )
        
        upload_type = settings.get('upload_type', 'document')
        button_mode = settings.get('button_mode', 'off') == 'on'
        prefix = settings.get('prefix', '')
        suffix = settings.get('suffix', '')
        
        filestore_username = settings.get("filestore_username", "").strip()
        dump_channel_id = settings.get("dump_channel_id")
        
        # Verify button parameters before continuing, fallback to regular if not configured
        if button_mode and (not filestore_username or not dump_channel_id):
            button_mode = False
            try:
                await client.send_message(chat_id, "⚠️ **Warning:** Button Mode is enabled, but File Store Bot credentials are not configured in settings. Falling back to regular upload.")
            except Exception:
                pass
                
        generated_links = []
            
        for i, rv in enumerate(resolved_videos):
            vm = rv[0]
            q = rv[1]
            v_msg = rv[2]
            
            try:
                if not v_msg:
                    v_msg = await client.get_messages(vm['chat_id'], vm['msg_id'])
                    
                v_orig_name = getattr(v_msg.video or v_msg.document, "file_name", f"video_{i}.mkv")
                
                # Update progress info for downloading this specific quality path
                dl_start[0] = time.time()
                last_dl_update[0] = 0
                await update_state("📥 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱𝗶𝗻𝗴 𝗩𝗶𝗱𝗲𝗼...", "", q, predicted_filenames.get(i, v_orig_name))
                
                v_path = await v_msg.download(
                    file_name=os.path.join(work_dir, f"video_{i}.mkv"),
                    progress=lambda c, t: dl_progress_cb(c, t, predicted_filenames.get(i, v_orig_name), q)
                )
                
                # Probe video resolution if not found in filename
                if q != "-":
                    res = q
                else:
                    await update_state("🔍 𝗣𝗿𝗼𝗯𝗶𝗻𝗴 𝗥𝗲𝘀𝗼𝗹𝘂𝘁𝗶𝗼𝗻...", "", q, predicted_filenames.get(i, v_orig_name))
                    res = await get_video_resolution(v_path)
                    if res == "Unknown":
                        res = q
                    
                # Format final filename
                fmt = settings.get("rename_format", "{anime} - S{season:02d}E{episode:02d} [{language}] {quality} @suffix.mkv")
                ext = ".mkv"
                base_fmt = fmt
                if fmt.lower().endswith(".mkv"):
                    base_fmt = fmt[:-4]
                    ext = ".mkv"
                elif fmt.lower().endswith(".mp4"):
                    base_fmt = fmt[:-4]
                    ext = ".mp4"
                    
                filename_base = safe_format(
                    base_fmt,
                    anime=anime,
                    season=job.get('season', '01'),
                    episode=job.get('episode', '01'),
                    language=job.get('language', 'Unknown'),
                    quality=res
                )
                if prefix: filename_base = f"{prefix} {filename_base}"
                if suffix: filename_base = f"{filename_base} {suffix}"
                filename = f"{filename_base}{ext}"
                
                if process_mode == "rename_only":
                    await update_state("⚙️ 𝗘𝗻𝗰𝗼𝗱𝗶𝗻𝗴 𝗩𝗶𝗱𝗲𝗼...", "", res, filename)
                    out_path = os.path.join(work_dir, f"out_{res}.mkv")
                    shutil.copy2(v_path, out_path)
                    success = True
                else:
                    await update_state("⚙️ 𝗘𝗻𝗰𝗼𝗱𝗶𝗻𝗴 𝗩𝗶𝗱𝗲𝗼...", "", res, filename)
                    out_path = os.path.join(work_dir, f"out_{res}.mkv")
                    success = await strip_and_mux_audio(v_path, audio_path, out_path)
                
                if success:
                    final_path = os.path.join(work_dir, filename)
                    meta_ok = await apply_metadata(out_path, final_path, user_id)
                    if not meta_ok:
                        os.rename(out_path, final_path)
                    
                    upload_label = "📤 𝗨𝗽𝗹𝗼𝗮𝗱𝗶𝗻𝗴 𝗧𝗼 𝗗𝘂𝗺𝗽..." if button_mode else "📤 𝗨𝗽𝗹𝗼𝗮𝗱𝗶𝗻𝗴 𝗧𝗼 𝗖𝗵𝗮𝗻𝗻𝗲𝗹..."
                    await update_state(upload_label, "", res, filename)
                    
                    # Calculate new metadata formats
                    languages_eng = "Unknown"
                    languages_reg = "Unknown"
                    duration_str = "00:00"
                    duration_sec = 0
                    file_size_str = "0 B"
                    
                    try:
                        file_size_str = humanbytes(os.path.getsize(final_path))
                        m_info = await get_media_info(final_path)
                        
                        f_info = m_info.get("format", {})
                        if "duration" in f_info:
                            duration_sec = int(float(f_info["duration"]))
                            hours = duration_sec // 3600
                            minutes = (duration_sec % 3600) // 60
                            seconds = duration_sec % 60
                            if hours > 0:
                                duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                            else:
                                duration_str = f"{minutes}:{seconds:02d}"
                                
                        streams = m_info.get("streams", [])
                        found_langs = []
                        for s in streams:
                            if s.get("codec_type") == "audio":
                                lang = s.get("tags", {}).get("language", "und").lower()
                                if lang != "und":
                                    found_langs.append(lang)
                                    
                        if found_langs:
                            seen = set()
                            unique_langs = [x for x in found_langs if not (x in seen or seen.add(x))]
                            
                            lang_map_eng = {"tam": "Tamil", "hin": "Hindi", "tel": "Telugu", "eng": "English", "jpn": "Japanese", "mal": "Malayalam", "kan": "Kannada", "kor": "Korean"}
                            lang_map_reg = {"tam": "தமிழ்", "hin": "हिन्दी", "tel": "తెలుగు", "eng": "English", "jpn": "日本語", "mal": "മലയാളం", "kan": "ಕನ್ನಡ", "kor": "한국어"}
                            
                            languages_eng = ", ".join([lang_map_eng.get(l, l.title()) for l in unique_langs])
                            languages_reg = ", ".join([lang_map_reg.get(l, lang_map_eng.get(l, l.title())) for l in unique_langs])
                    except Exception as e:
                        print(f"Error parsing advanced media info: {e}")
                    
                    cap_fmt = settings.get("caption_format", "<b>{filename}</b>")
                    if not cap_fmt or cap_fmt == "{filename}":
                        cap_fmt = "<b>{filename}</b>"
                    caption = safe_format(
                        cap_fmt,
                        filename=filename,
                        anime=anime,
                        season=job.get('season', '01'),
                        episode=job.get('episode', '01'),
                        language=job.get('language', 'Unknown'),
                        quality=res,
                        size=file_size_str,
                        duration=duration_str,
                        languages=languages_eng,
                        languagesr=languages_reg
                    )
                    
                    # Upload with progress bar
                    uploaded_msg = None
                    try:
                        upload_start = time.time()
                        last_update_time = [0]
                        
                        def progress_cb(current, total):
                            if total < 2 * 1024 * 1024:
                                return
                            now = time.time()
                            if now - last_update_time[0] < 8 and current < total:
                                return
                            last_update_time[0] = now
                            
                            percent = (current / total) * 100 if total else 0
                            filled = int(percent / 10)
                            bar = "■" * filled + "□" * (10 - filled)
                            
                            elapsed = now - upload_start
                            speed = current / elapsed if elapsed > 0 else 0
                            eta = ""
                            if speed > 0:
                                eta_seconds = (total - current) / speed
                                eta = f" | ETA: {int(eta_seconds)}s"
                                
                            speed_text = f"{humanbytes(speed)}/s" if speed else "—/s"
                            progress_bar_text = f"[{bar}] {percent:.1f}% ({humanbytes(current)} of {humanbytes(total)} @ {speed_text}{eta})"
                            
                            asyncio.run_coroutine_threadsafe(
                                update_state(upload_label, progress_bar_text, res, filename),
                                loop
                            )
                        
                        upload_chat_id = int(dump_channel_id) if button_mode else target_chat
                        actual_type = upload_type
                        
                        if actual_type == "video":
                            uploaded_msg = await client.send_video(
                                chat_id=upload_chat_id,
                                video=final_path,
                                caption=caption,
                                parse_mode=enums.ParseMode.HTML,
                                thumb=thumb_path,
                                duration=duration_sec,
                                progress=progress_cb
                            )
                        else:
                            uploaded_msg = await client.send_document(
                                chat_id=upload_chat_id,
                                document=final_path,
                                caption=caption,
                                parse_mode=enums.ParseMode.HTML,
                                thumb=thumb_path,
                                progress=progress_cb
                            )
                    except Exception as e:
                        print(f"Error during progress upload: {e}. Retrying standard upload...")
                        upload_chat_id = int(dump_channel_id) if button_mode else target_chat
                        actual_type = upload_type
                        if actual_type == "video":
                            uploaded_msg = await client.send_video(upload_chat_id, video=final_path, caption=caption, parse_mode=enums.ParseMode.HTML, thumb=thumb_path, duration=duration_sec)
                        else:
                            uploaded_msg = await client.send_document(upload_chat_id, document=final_path, caption=caption, parse_mode=enums.ParseMode.HTML, thumb=thumb_path)
                    
                    if button_mode and uploaded_msg:
                        import base64
                        msg_id_val = uploaded_msg.id
                        payload_str = f"get-{msg_id_val * abs(int(dump_channel_id))}"
                        payload_bytes = payload_str.encode("ascii")
                        base64_bytes = base64.urlsafe_b64encode(payload_bytes)
                        base64_string = base64_bytes.decode("ascii").strip("=")
                        
                        bot_link = f"https://t.me/{filestore_username}?start={base64_string}"
                        generated_links.append((res, bot_link))
                        
                # Clean up this resolution files immediately to conserve disk space
                try:
                    if os.path.exists(v_path): os.remove(v_path)
                    if os.path.exists(out_path): os.remove(out_path)
                    if success and os.path.exists(final_path): os.remove(final_path)
                except Exception:
                    pass
                    
            except Exception as e:
                print(f"Error processing video resolution quality {q}: {e}")
                try:
                    await client.send_message(chat_id, f"⚠️ **Error processing/uploading {q} resolution:** `{e}`")
                except Exception:
                    pass
                    
        # Delete temporary status message from channel to keep channel feed clean
        if status_msg_node_id:
            try:
                await client.delete_messages(target_chat, status_msg_node_id)
            except Exception as e:
                print(f"Error deleting status message: {e}")
                
        # Send buttons message/poster if button_mode is on
        if button_mode and generated_links:
            btn_post_fmt = settings.get("button_post_format")
            if not btn_post_fmt:
                btn_post_fmt = "<b>{anime} | Tamil Dubbed #Official</b>\n\n<b>Season : {season} | Episode : {episode}</b>\n\n<b>‼️Note - Click The Below Button to Get Episodes 👇</b>"
            
            post_caption = safe_format(
                btn_post_fmt,
                anime=anime,
                season=job.get('season', '01'),
                episode=job.get('episode', '01')
            )
            
            inline_buttons = []
            for qual, link in generated_links:
                inline_buttons.append(InlineKeyboardButton(f"📥 {qual}", url=link))
                
            rows = [inline_buttons[x:x+2] for x in range(0, len(inline_buttons), 2)]
            reply_markup = InlineKeyboardMarkup(rows)
            
            if custom_thumb:
                try:
                    await client.send_photo(
                        chat_id=target_chat,
                        photo=custom_thumb,
                        caption=post_caption,
                        parse_mode=enums.ParseMode.HTML,
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    print(f"Error posting photo to channel: {e}. Falling back to text.")
                    await client.send_message(
                        chat_id=target_chat,
                        text=post_caption,
                        parse_mode=enums.ParseMode.HTML,
                        reply_markup=reply_markup
                    )
            else:
                await client.send_message(
                    chat_id=target_chat,
                    text=post_caption,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=reply_markup
                )
                
        # 5. Post completion sticker if configured
        finish_sticker = settings.get("finish_sticker")
        if finish_sticker:
            try:
                # Send to target chat
                await client.send_sticker(target_chat, sticker=finish_sticker)
            except Exception as e:
                print(f"Error sending final sticker: {e}")
                
        # Final notification in user's PM
        try:
            if job.get('user_id') in USER_CANCELLATIONS:
                await client.edit_message_text(chat_id, status_msg, "❌ **Task was cancelled by user.**")
            else:
                await client.edit_message_text(chat_id, status_msg, f"✅ **Processing Completed!**\nFiles successfully posted in target channel.")
        except Exception:
            pass

    except RuntimeError as re_err:
        if str(re_err) == "TaskCancelledByUser":
            try:
                await client.edit_message_text(chat_id, status_msg, "❌ **Task Cancelled.** Moving next...")
            except Exception: pass
            print(f"Job cancelled for user {job.get('user_id')}")
        else:
            raise re_err
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        log_msg_id = job.get("log_msg_id")
        if log_msg_id and Config.LOG_CHANNEL:
            try:
                await client.delete_messages(Config.LOG_CHANNEL, log_msg_id)
            except Exception as e:
                print(f"Error deleting job trigger log message: {e}")
