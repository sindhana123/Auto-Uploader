import os
import time
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database import db
from utils.ffmpeg import get_media_info, extract_stream
import math

EXTRACT_STATE = {}

def humanbytes(size):
    if not size: return ""
    power = 2**10
    n = 0
    dic_powerN = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {dic_powerN[n]}B"

async def extract_progress(current, total, text, message, start_time):
    now = time.time()
    if not hasattr(extract_progress, "last_update_time"):
        extract_progress.last_update_time = 0
        
    diff = now - start_time
    if round(now - extract_progress.last_update_time) < 3 and current != total:
        return
        
    extract_progress.last_update_time = now
    
    speed = current / diff if diff > 0 else 0
    percent = (current / total) * 100 if total > 0 else 0
    
    bar_length = 15
    filled_length = int(bar_length * current / total) if total > 0 else 0
    bar = "█" * filled_length + "░" * (bar_length - filled_length)
    
    eta = round((total - current) / speed) if speed > 0 and total > 0 else 0
    eta_text = f"{eta}s" if eta > 0 else "0s"
    
    msg_text = f"**{text}**\n\n[{bar}] {percent:.1f}%\n"
    msg_text += f"{humanbytes(current)} of {humanbytes(total)}\n"
    msg_text += f"Speed: {humanbytes(speed)}/s\nETA: {eta_text}"
    
    try:
        await message.edit_text(msg_text)
    except Exception:
        pass

async def initiate_extraction(client: Client, message: Message):
    user_id = message.from_user.id
    m_reply = await message.reply_text("📥 **Downloading video to fetch streams...**\nPlease wait.")
    
    file_path = f"temp/{user_id}_{time.time()}_extract.mkv"
    os.makedirs("temp", exist_ok=True)
    
    start_time = time.time()
    await message.download(
        file_path, 
        progress=extract_progress, 
        progress_args=("📥 **Downloading File for Extraction...**", m_reply, start_time)
    )
    
    await m_reply.edit_text("🔍 **Scanning video for audio and subtitle streams...**")
    info = await get_media_info(file_path)
    streams = info.get("streams", [])
    
    valid_streams = []
    
    for s in streams:
        codec_type = s.get("codec_type")
        if codec_type in ["audio", "subtitle"]:
            valid_streams.append(s)
            
    if not valid_streams:
        await m_reply.edit_text("❌ No extractable **Audio** or **Subtitle** streams found in this video.")
        try: os.remove(file_path)
        except Exception: pass
        return
        
    orig_name = getattr(message.document, "file_name", getattr(message.video, "file_name", "Media_File"))
    if not orig_name:
        orig_name = "Media_File"
        
    EXTRACT_STATE[user_id] = {
        "file": file_path,
        "original_filename": orig_name,
        "streams": valid_streams,
        "selected": set(),
        "msg_id": m_reply.id,
        "source_msg": message
    }
    
    markup = build_extract_markup(user_id)
    await m_reply.edit_text("✂️ **Extract Mode Active**\n\nSelect the tracks you want to extract from the list below, then click **Finish & Extract**.", reply_markup=markup)

def build_extract_markup(user_id):
    state = EXTRACT_STATE.get(user_id)
    if not state: return None
    
    buttons = []
    selected = state["selected"]
    
    for i, s in enumerate(state["streams"]):
        codec_type = s.get("codec_type", "unknown").capitalize()
        lang = s.get("tags", {}).get("language", s.get("tags", {}).get("LANGUAGE", "und")).upper()
        title = s.get("tags", {}).get("title", s.get("tags", {}).get("TITLE", f"Track {s.get('index')}"))
        
        display_text = f"{codec_type} | {lang} | {title}"
        if i in selected:
            display_text = f"✅ {display_text}"
        else:
            display_text = f"❌ {display_text}"
            
        buttons.append([InlineKeyboardButton(display_text, callback_data=f"ext_toggle_{i}")])
        
    buttons.append([InlineKeyboardButton("🚀 Finish & Extract", callback_data="ext_process")])
    buttons.append([InlineKeyboardButton("🗑️ Cancel", callback_data="ext_cancel")])
    
    return InlineKeyboardMarkup(buttons)

@Client.on_callback_query(filters.regex(r"^ext_toggle_(\d+)"))
async def extract_toggle_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    idx = int(query.matches[0].group(1))
    
    state = EXTRACT_STATE.get(user_id)
    if not state:
        await query.answer("State lost.", show_alert=True)
        return
        
    if idx in state["selected"]:
        state["selected"].remove(idx)
        await query.answer("Removed from selection.")
    else:
        state["selected"].add(idx)
        await query.answer("Added to selection.")
        
    markup = build_extract_markup(user_id)
    await query.message.edit_reply_markup(markup)

@Client.on_callback_query(filters.regex(r"^ext_cancel$"))
async def extract_cancel_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    state = EXTRACT_STATE.get(user_id)
    if state:
        try: os.remove(state["file"])
        except Exception: pass
        del EXTRACT_STATE[user_id]
        
    await query.message.edit_text("❌ Extraction cancelled.")

@Client.on_callback_query(filters.regex(r"^ext_process$"))
async def extract_process_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    state = EXTRACT_STATE.get(user_id)
    if not state:
        await query.answer("State lost.", show_alert=True)
        return
        
    selected = state["selected"]
    if not selected:
        await query.answer("Please select at least 1 track!", show_alert=True)
        return
        
    await query.message.edit_text("⏳ **Extracting selected tracks...**\nProcessing via FFmpeg, please wait...")
    
    file_path = state["file"]
    streams = state["streams"]
    source_msg = state["source_msg"]
    orig_name = state.get("original_filename", "Media_File")
    base_name, _ = os.path.splitext(orig_name)
    
    extracted_files = []
    
    for idx in selected:
        s = streams[idx]
        codec_type = s.get("codec_type")
        codec_name = s.get("codec_name", "")
        lang = s.get("tags", {}).get("language", s.get("tags", {}).get("LANGUAGE", "und")).upper()
        stream_index = s.get("index")
        
        # Determine logical extension
        ext = ".mka" if codec_type == "audio" else ".srt"
        if codec_type == "audio":
            if "aac" in codec_name: ext = ".m4a"
            elif "mp3" in codec_name: ext = ".mp3"
            elif "ac3" in codec_name: ext = ".ac3"
            elif "flac" in codec_name: ext = ".flac"
        elif codec_type == "subtitle":
            if "ass" in codec_name: ext = ".ass"
            elif "vtt" in codec_name: ext = ".vtt"
            elif "subrip" in codec_name: ext = ".srt"
            
        track_ty_label = "Audio" if codec_type == "audio" else "Sub"
        target_file_name = f"{base_name} - {track_ty_label} ({lang}){ext}"
        
        # Temp path for ffmpeg extraction MUST HAVE proper extension for muxer to work
        tmp_out_path = f"temp/{user_id}_{time.time()}_track_{stream_index}{ext}"
        
        success = await extract_stream(file_path, stream_index, tmp_out_path)
        if success and os.path.exists(tmp_out_path):
            final_out_path = f"temp/{user_id}_{target_file_name}"
            os.rename(tmp_out_path, final_out_path)
            extracted_files.append((final_out_path, target_file_name))
            
    if not extracted_files:
        await query.message.edit_text("❌ Failed to extract any tracks. Format might not be supported directly.")
    else:
        await query.message.edit_text("✅ Extraction successful! Uploading individual tracks now...")
        for file_to_send, custom_file_name in extracted_files:
            start_time = time.time()
            try:
                await client.send_document(
                    chat_id=query.message.chat.id,
                    document=file_to_send,
                    file_name=custom_file_name,
                    caption=f"📁 **Extracted Track:** `{custom_file_name}`",
                    reply_to_message_id=source_msg.id,
                    progress=extract_progress,
                    progress_args=(f"📤 **Uploading {custom_file_name}...**", query.message, start_time)
                )
            except Exception as e:
                print(f"Failed to send extracted track: {e}")
            try: os.remove(file_to_send)
            except Exception: pass
            
        await query.message.edit_text("🎉 **All selected tracks have been extracted and uploaded successfully!**")
        
    try: os.remove(file_path)
    except Exception: pass
    if user_id in EXTRACT_STATE:
        del EXTRACT_STATE[user_id]
