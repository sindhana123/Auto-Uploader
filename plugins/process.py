from pyrogram import Client, filters
from pyrogram.types import Message
from database import db
from utils.job_queue import process_queue
import os
import asyncio
from pyromod.exceptions import ListenerTimeout
from config import Config

command_filter = filters.create(lambda _, __, msg: bool(msg.text and msg.text.startswith("/")))

@Client.on_message(filters.command("set_name") & filters.private)
async def set_name_cmd(client: Client, message: Message):
    if not await db.is_user_authorized(message.from_user.id):
        await message.reply_text("<b>❌ You are not authorized to use this bot. Please contact the Owner/Admin to authorize you.</b>")
        return
    args = message.text.split(" ", 1)
    if len(args) < 2:
        await message.reply_text("Usage: `/set_name <anime name>`")
        return
        
    anime_name = args[1].strip()
    user_id = message.from_user.id
    chat_id = message.chat.id
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    
    # Retrieve user settings
    settings = await db.get_user_settings(user_id)
    auto_match_enabled = settings.get("auto_channel_match", "on") == "on"
    
    state = await db.get_user_state(user_id)
    job = state.get("current_job", {})
    job["anime_name"] = anime_name
    
    matched_channel = None
    if auto_match_enabled:
        matched_channel = await db.match_channel(user_id, anime_name)
        
    if matched_channel:
        job["target_channel_id"] = matched_channel["channel_id"]
        job["target_channel_title"] = matched_channel.get("title", f"Channel {matched_channel['channel_id']}")
        
        state["current_job"] = job
        await db.update_user_state(user_id, state)
        
        await message.reply_text(
            f"✅ **Anime Name Set:** `{anime_name}`\n"
            f"📺 **Auto-matched Target Channel:** {job['target_channel_title']} (`{job['target_channel_id']}`)\n\n"
            "Use `/start_process` to start processing."
        )
        return
        
    # If auto-match is enabled but no match was found:
    if auto_match_enabled:
        # Prompt for Hint and Channel ID manually, save it to DB (Auto + Manual -> Auto concept!)
        hint_prompt = await message.reply_text(
            f"🔍 **Auto-match enabled** but no mapped channel found for `{anime_name}`.\n\n"
            "Please send the **Hint** (keyword) to identify this anime in the future (e.g. `Tomb`):"
        )
        try:
            hint_res = await client.listen(chat_id=chat_id, user_id=user_id, filters=filters.text & ~command_filter, timeout=300)
            hint_val = hint_res.text.strip().lower()
            await hint_res.delete()
            await hint_prompt.delete()
            
            id_prompt = await message.reply_text(
                f"📺 Hint set to `{hint_val}`.\n\n"
                "Now, send the **Target Channel ID** (e.g., `-1002234032904`):"
            )
            id_res = await client.listen(chat_id=chat_id, user_id=user_id, filters=filters.text & ~command_filter, timeout=300)
            id_val = id_res.text.strip()
            await id_res.delete()
            await id_prompt.delete()
            
            try:
                target_chat_id = int(id_val)
                # Verify bot is admin or has send permission
                try:
                    chat_info = await client.get_chat(target_chat_id)
                    chat_title = chat_info.title
                except Exception:
                    chat_title = f"Channel {target_chat_id}"
                
                await db.add_channel(user_id, target_chat_id, chat_title, f"https://t.me/c/{abs(target_chat_id)}/1", hint_val)
                
                job["target_channel_id"] = target_chat_id
                job["target_channel_title"] = chat_title
                state["current_job"] = job
                await db.update_user_state(user_id, state)
                
                await message.reply_text(
                    f"✅ **Mapped & Configured Successfully!**\n\n"
                    f"• **Anime:** `{anime_name}`\n"
                    f"• **Hint:** `{hint_val}`\n"
                    f"• **Target Channel:** {chat_title} (`{target_chat_id}`)\n\n"
                    "Next time, this anime will auto-match automatically.\n"
                    "Use `/start_process` to start processing."
                )
            except ValueError:
                await message.reply_text("❌ Invalid Channel ID format. Please restart setup using `/set_name` and use a valid integer (e.g. -100...).")
                
        except Exception:
            await message.reply_text("⏰ Setup timed out or cancelled. Please run `/set_name` again.")
            
    else:
        # If auto-match is disabled, ask user command-by-command for the target channel ID directly, but DO NOT save it to mapping DB!
        id_prompt = await message.reply_text(
            f"⚙️ **Auto-matching is disabled (OFF).**\n\n"
            f"Please enter the **Target Channel ID** for uploading `{anime_name}`:"
        )
        try:
            id_res = await client.listen(chat_id=chat_id, user_id=user_id, filters=filters.text & ~command_filter, timeout=300)
            id_val = id_res.text.strip()
            await id_res.delete()
            await id_prompt.delete()
            
            try:
                target_chat_id = int(id_val)
                try:
                    chat_info = await client.get_chat(target_chat_id)
                    chat_title = chat_info.title
                except Exception:
                    chat_title = f"Channel {target_chat_id}"
                    
                job["target_chat_id"] = target_chat_id
                job["target_channel_id"] = target_chat_id
                job["target_channel_title"] = chat_title
                state["current_job"] = job
                await db.update_user_state(user_id, state)
                
                await message.reply_text(
                    f"✅ **Configure Success (No-Save Mode)!**\n\n"
                    f"• **Anime:** `{anime_name}`\n"
                    f"• **Target Channel:** {chat_title} (`{target_chat_id}`)\n\n"
                    "Use `/start_process` to start processing."
                )
            except ValueError:
                await message.reply_text("❌ Invalid Channel ID format. Please restart setup using `/set_name`.")
                
        except Exception:
            await message.reply_text("⏰ Setup timed out or cancelled. Please run `/set_name` again.")

@Client.on_message(filters.command("set_details") & filters.private)
async def set_details_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    if not await db.is_user_authorized(message.from_user.id):
        await message.reply_text("<b>❌ You are not authorized to use this bot. Please contact the Owner/Admin to authorize you.</b>")
        return
    args = message.text.split(" ", 1)
    if len(args) < 2:
        guide = (
            "📝 **Set Details Command Guide**\n\n"
            "This command helps you forcibly define the episode, season, and language in case they are missing from the filename.\n\n"
            "**Format:**\n"
            "`/set_details <episode>, <season>, <language>, <target_channel_id (optional)>`\n\n"
            "**Example:**\n"
            "`/set_details 3, 1, Tamil` (Set as Episode 3, Season 1, Tamil)\n"
            "*Note: Comma `,` is required to separate the values!*"
        )
        await message.reply_text(guide)
        return
        
    parts = [p.strip() for p in args[1].split(",")]
    if len(parts) < 3:
        await message.reply_text("❌ Please provide at least episode, season, and language separated by commas. Example: `/set_details 3, 1, Tamil`")
        return
        
    state = await db.get_user_state(message.from_user.id)
    job = state.get("current_job", {})
    job["episode"] = parts[0]
    job["season"] = parts[1]
    job["language"] = parts[2]
    if len(parts) > 3:
        job["target_channel_id"] = parts[3]
        
    state["current_job"] = job
    await db.update_user_state(message.from_user.id, state)
    await message.reply_text(f"Details saved: E{job['episode']} S{job['season']} [{job['language']}]")

@Client.on_message((filters.video | filters.document | filters.audio) & filters.private)
async def handle_files(client: Client, message: Message):
    if not await db.is_user_authorized(message.from_user.id):
        await message.reply_text("<b>❌ You are not authorized to use this bot. Please contact the Owner/Admin to authorize you.</b>")
        return
    is_audio = getattr(message, "audio", None) is not None
    is_video = getattr(message, "video", None) is not None
    
    # If it is a document, determine if it is audio or video or other
    if message.document:
        mime = message.document.mime_type or ""
        name = message.document.file_name or ""
        ext = os.path.splitext(name)[1].lower()
        
        audio_exts = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".aac"}
        video_exts = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".ts"}
        
        if mime.startswith("audio/") or ext in audio_exts:
            is_audio = True
        elif mime.startswith("video/") or ext in video_exts:
            is_video = True
        else:
            # Ignore other files (like JSON, text, etc.) from process queue
            message.continue_propagation()
            
    if not is_audio and not is_video:
        message.continue_propagation()
        return
        
    settings = await db.get_user_settings(message.from_user.id)
    process_mode = settings.get("process_mode", "merge")
    
    if is_video and process_mode == "extract":
        from plugins.extract import initiate_extraction
        await initiate_extraction(client, message)
        return
            
    if is_audio:
        audio_info = {"chat_id": message.chat.id, "msg_id": message.id}
        await db.set_current_job_audio(message.from_user.id, audio_info)
        resp = "Audio added to current job."
    else:
        video_info = {"chat_id": message.chat.id, "msg_id": message.id}
        await db.push_current_job_video(message.from_user.id, video_info)
        
        state = await db.get_user_state(message.from_user.id)
        job = state.get("current_job", {})
        videos = job.get("video_msgs", [])
        resp = f"Video added to current job. Total videos: {len(videos)} \n Use /set_name to set anime name for the file"
        
    await message.reply_text(resp)

@Client.on_message(filters.command("clear_queue") & filters.private)
async def clear_queue_cmd(client: Client, message: Message):
    if not await db.is_user_authorized(message.from_user.id):
        return
    state = await db.get_user_state(message.from_user.id)
    state["current_job"] = {}
    await db.update_user_state(message.from_user.id, state)
    await message.reply_text("✅ **Your queue has been cleared!** You can now send new files.")

@Client.on_message(filters.command("start_process") & filters.private)
async def start_process_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    if not await db.is_user_authorized(message.from_user.id):
        await message.reply_text("<b>❌ You are not authorized to use this bot. Please contact the Owner/Admin to authorize you.</b>")
        return
    settings = await db.get_user_settings(message.from_user.id)
    process_mode = settings.get("process_mode", "merge")
    state = await db.get_user_state(message.from_user.id)
    job = state.get("current_job", {})
    if "anime_name" not in job:
        job["anime_name"] = None
    if "video_msgs" not in job or not job["video_msgs"]:
        await message.reply_text("No videos added.")
        return
    if process_mode == "merge":
        if "audio_msg" not in job:
            await message.reply_text("No audio added.")
            return
        
    # Log triggering start process
    log_msg_id = None
    if Config.LOG_CHANNEL:
        try:
            log_msg = (
                f"🚀 **Bot Job Triggered**\n\n"
                f"• **Anime:** `{job.get('anime_name')}`\n"
                f"• **Videos Count:** `{len(job.get('video_msgs', []))}`"
            )
            sent_log_msg = await client.send_message(Config.LOG_CHANNEL, log_msg)
            log_msg_id = sent_log_msg.id
        except Exception as e:
            print(f"Error logging job start: {e}")
            
    status_msg = await message.reply_text("Queuing job...")
    
    full_job = {
        "user_id": message.from_user.id,
        "chat_id": message.chat.id,
        "status_msg_id": status_msg.id,
        "log_msg_id": log_msg_id,
        **job
    }
    
    await process_queue.put(full_job)
    
    # clear job
    state["current_job"] = {}
    await db.update_user_state(message.from_user.id, state)
    
    await status_msg.edit_text("Job queued successfully! Position in queue: " + str(process_queue.qsize()))
