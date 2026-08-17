import pyromod.listen
from pyromod.exceptions import ListenerTimeout
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database import db
import json
import os

command_filter = filters.create(lambda _, __, msg: bool(msg.text and msg.text.startswith("/")))

from functools import wraps

def authorized_only():
    def decorator(func):
        @wraps(func)
        async def wrapper(client, update, *args, **kwargs):
            is_cb = hasattr(update, "message")
            user_id = update.from_user.id if update.from_user else None
            if not user_id:
                return
            authorized = await db.is_user_authorized(user_id)
            if not authorized:
                if is_cb:
                    try:
                        await update.answer("❌ You are not authorized to use this bot.", show_alert=True)
                    except Exception:
                        pass
                else:
                    await update.reply_text("<b>❌ You are not authorized to use this bot. Please contact the Owner/Admin to authorize you.</b>")
                return
            return await func(client, update, *args, **kwargs)
        return wrapper
    return decorator

def render_settings_markup(upload_type, auto_channel_match, process_mode, button_mode):
    upload_label = "🎬 Video" if upload_type == "video" else ("📄 Document" if upload_type == "document" else "🔗 Button Links")
    routing_label = "ON ✅" if auto_channel_match == "on" else "OFF ❌"
    mode_label = "✏️ Rename Only" if process_mode == "rename_only" else ("🔄 Merge Audio" if process_mode == "merge" else "✂️ Extract Tracks")
    btn_mode_label = "ON ✅" if button_mode == "on" else "OFF ❌"
    
    markup_buttons = [
        [InlineKeyboardButton("🖼️ Thumbnail", callback_data="ui_thumb"),
         InlineKeyboardButton("📝 Rename Format", callback_data="ui_rename")],
        [InlineKeyboardButton("📝 Caption Format", callback_data="ui_caption"),
         InlineKeyboardButton("✏️ Prefix / Suffix", callback_data="ui_prefix_suffix")],
        [InlineKeyboardButton(f"📤 Upload As: {upload_label}", callback_data="toggle_upload_type"),
         InlineKeyboardButton(f"🔗 Button Mode: {btn_mode_label}", callback_data="toggle_button_mode")],
        [InlineKeyboardButton(f"⚙️ Auto Routing: {routing_label}", callback_data="toggle_routing_match"),
         InlineKeyboardButton(f"🛠️ Mode: {mode_label}", callback_data="toggle_process_mode")],
        [InlineKeyboardButton("🏷️ Metadata Settings", callback_data="ui_metadata"),
         InlineKeyboardButton("✨ Finish Sticker", callback_data="ui_finish_sticker")],
        [InlineKeyboardButton("📺 Routing Channels", callback_data="ui_channels"),
         InlineKeyboardButton("💾 Import / Export", callback_data="ui_import_export")],
    ]
    
    if button_mode == "on":
        markup_buttons.insert(6, [
            InlineKeyboardButton("🤖 File Store Bot", callback_data="ui_config_filestore"),
            InlineKeyboardButton("📁 Dump Channel", callback_data="ui_config_dumpchannel")
        ])
        markup_buttons.insert(7, [
            InlineKeyboardButton("🔗 Button Post Format", callback_data="ui_btn_post_format")
        ])
        
    markup_buttons.append([InlineKeyboardButton("❌ Close Menu", callback_data="close_settings")])
    return InlineKeyboardMarkup(markup_buttons)

async def show_main_menu(client, chat_id, message_id, user_id, cb=None):
    settings = await db.get_user_settings(user_id)
    upload_type = settings.get('upload_type', 'document')
    auto_channel_match = settings.get('auto_channel_match', 'on')
    prefix = settings.get('prefix', '')
    suffix = settings.get('suffix', '')
    rename_format = settings.get('rename_format', '')
    caption_format = settings.get('caption_format', '')
    finish_sticker = settings.get('finish_sticker')
    sticker_status = "✅ Configured" if finish_sticker else "❌ Not set"
    metadata_status = settings.get('metadata', 'Off')
    process_mode = settings.get('process_mode', 'merge')
    mode_status = "Rename Only" if process_mode == "rename_only" else ("Rename & Merge" if process_mode == "merge" else "Extract Tracks")
    
    filestore_username = settings.get("filestore_username", "not set")
    dump_channel_id = settings.get("dump_channel_id", "not set")
    
    routing_status = "ON (Auto + Manual Map)" if auto_channel_match == "on" else "OFF (Direct ID, no store)"
    
    button_mode = settings.get('button_mode', 'off')
    btn_status = "ON (Use File Store Bot)" if button_mode == "on" else "OFF (Direct file send)"
    
    text = (
        f"⚙️ **Advanced Settings Panel**\n\n"
        f"• **Process Mode:** `{mode_status}`\n"
        f"• **Upload Type:** `{upload_type}`\n"
        f"• **Button Mode:** `{btn_status}`\n"
        f"• **Auto Routing:** `{routing_status}`\n"
        f"• **Prefix:** `{prefix or 'None'}`\n"
        f"• **Suffix:** `{suffix or 'None'}`\n"
        f"• **Rename Template:** `{rename_format}`\n"
        f"• **Caption Template:** `{caption_format}`\n"
        f"• **Finish Sticker:** `{sticker_status}`\n"
        f"• **Metadata:** `{metadata_status}`\n"
    )
    if button_mode == "on":
        btn_post_fmt = settings.get("button_post_format", "")
        text += (
            f"• **File Store Bot:** `@{filestore_username}`\n"
            f"• **Dump Channel ID:** `{dump_channel_id}`\n"
            f"• **Button Post Template:** `{btn_post_fmt}`\n"
        )
    text += "\nTap any button below to configure."
    
    markup = render_settings_markup(upload_type, auto_channel_match, process_mode, button_mode)
    
    if cb:
        try:
            await cb.message.edit_text(text, reply_markup=markup)
        except Exception:
            pass
    else:
        await client.send_message(chat_id, text, reply_markup=markup)

@Client.on_message(filters.command("settings") & filters.private)
@authorized_only()
async def settings_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    await show_main_menu(client, chat_id, message.id, user_id)

@Client.on_callback_query(filters.regex(r"^close_settings$"))
@authorized_only()
async def close_settings_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    try:
        await query.message.delete()
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^toggle_upload_type$"))
@authorized_only()
async def toggle_upload_type_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    settings = await db.get_user_settings(user_id)
    current = settings.get("upload_type", "document")
    if current == "document":
        new_type = "video"
    else:
        new_type = "document"
        
    await db.update_user_settings(user_id, "upload_type", new_type)
    try:
        await query.answer(f"Upload type changed to {new_type}")
    except Exception:
        pass
    await show_main_menu(client, chat_id, query.message.id, user_id, cb=query)

@Client.on_callback_query(filters.regex(r"^toggle_button_mode$"))
@authorized_only()
async def toggle_button_mode_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    settings = await db.get_user_settings(user_id)
    current = settings.get("button_mode", "off")
    new_status = "on" if current == "off" else "off"
    await db.update_user_settings(user_id, "button_mode", new_status)
    try:
        await query.answer(f"Button Mode changed to {new_status}")
    except Exception:
        pass
    await show_main_menu(client, chat_id, query.message.id, user_id, cb=query)

@Client.on_callback_query(filters.regex(r"^toggle_routing_match$"))
@authorized_only()
async def toggle_routing_match_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    settings = await db.get_user_settings(user_id)
    current = settings.get("auto_channel_match", "on")
    new_status = "off" if current == "on" else "on"
    await db.update_user_settings(user_id, "auto_channel_match", new_status)
    try:
        await query.answer(f"Auto Routing changed to {new_status}")
    except Exception:
        pass
    await show_main_menu(client, chat_id, query.message.id, user_id, cb=query)

@Client.on_callback_query(filters.regex(r"^toggle_process_mode$"))
@authorized_only()
async def toggle_process_mode_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    settings = await db.get_user_settings(user_id)
    current = settings.get("process_mode", "merge")
    if current == "merge":
        new_mode = "rename_only"
    elif current == "rename_only":
        new_mode = "extract"
    else:
        new_mode = "merge"
    await db.update_user_settings(user_id, "process_mode", new_mode)
    try:
        await query.answer(f"Process mode changed to {new_mode}")
    except Exception:
        pass
    await show_main_menu(client, chat_id, query.message.id, user_id, cb=query)

@Client.on_callback_query(filters.regex(r"^ui_"))
@authorized_only()
async def ui_buttons_cb(client: Client, query: CallbackQuery):
    action = query.data.replace("ui_", "")
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    message_id = query.message.id
    
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    settings = await db.get_user_settings(user_id)
    
    try:
        await query.answer()
    except Exception:
        pass
        
    if action == "thumb":
        current_thumb = settings.get("thumbnail")
        text = "🖼️ **Thumbnail Config**\n\n"
        if current_thumb:
            text += "✅ Custom thumbnail is currently set.\n\n"
        else:
            text += "❌ No custom thumbnail set.\n\n"
        text += "Send a photo to set as thumbnail, or send `-` / reply `/del_thumb` to delete."
        
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings_back")]])
        )
        try:
            response = await client.listen(chat_id=chat_id, user_id=user_id, filters=~command_filter, timeout=300)
            if response:
                if response.photo:
                    await db.update_user_settings(user_id, "thumbnail", response.photo.file_id)
                    await query.message.reply_text("✅ Thumbnail saved successfully!")
                elif response.text and response.text.strip() == "-":
                    await db.update_user_settings(user_id, "thumbnail", None)
                    await query.message.reply_text("🗑️ Custom thumbnail cleared!")
                await response.delete()
        except Exception:
            pass
        await show_main_menu(client, chat_id, message_id, user_id, cb=query)
        
    elif action == "rename":
        current_rename = settings.get("rename_format")
        text = (
            f"📝 **Configure Rename Format**\n\n"
            f"**Current Format:** `{current_rename}`\n\n"
            f"**Variables:**\n"
            f"• `{{anime}}` - Anime Name\n"
            f"• `{{season}}` - Season number\n"
            f"• `{{episode}}` - Episode number\n"
            f"• `{{language}}` - Audio language\n"
            f"• `{{quality}}` - Video quality (480p, 720p, etc.)\n\n"
            f"Send the new template format, or send `-` to reset to default."
        )
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings_back")]])
        )
        try:
            response = await client.listen(chat_id=chat_id, user_id=user_id, filters=filters.text & ~command_filter, timeout=300)
            if response:
                text_val = response.text.strip()
                if text_val == "-":
                    default_rename = "{anime} - S{season}E{episode} [{language}] {quality} @suffix.mkv"
                    await db.update_user_settings(user_id, "rename_format", default_rename)
                    await query.message.reply_text("✅ Rename format reset to default!")
                else:
                    await db.update_user_settings(user_id, "rename_format", text_val)
                    await query.message.reply_text("✅ Rename format updated successfully!")
                await response.delete()
        except Exception as e:
            print(f"DEBUG RENAME LISTEN EXCEPTION: {e}", flush=True)
        await show_main_menu(client, chat_id, message_id, user_id, cb=query)
        
    elif action == "caption":
        current_caption = settings.get("caption_format")
        text = (
            f"📝 **Configure Caption Format**\n\n"
            f"**Current Caption:**\n`{current_caption}`\n\n"
            f"**Variables:**\n"
            f"• `{{filename}}` - Final Renamed Filename\n"
            f"• `{{anime}}` - Anime Name\n"
            f"• `{{season}}` - Season number\n"
            f"• `{{episode}}` - Episode number\n"
            f"• `{{language}}` - Language\n"
            f"• `{{quality}}` - Resoltuion\n\n"
            f"Send the new caption template, or send `-` to reset to default."
        )
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings_back")]])
        )
        try:
            response = await client.listen(chat_id=chat_id, user_id=user_id, filters=filters.text & ~command_filter, timeout=300)
            if response:
                text_val = response.text.strip()
                if text_val == "-":
                    await db.update_user_settings(user_id, "caption_format", "<b>{filename}</b>")
                    await query.message.reply_text("✅ Caption format reset to default!")
                else:
                    await db.update_user_settings(user_id, "caption_format", text_val)
                    await query.message.reply_text("✅ Caption format updated successfully!")
                await response.delete()
        except Exception:
            pass
        await show_main_menu(client, chat_id, message_id, user_id, cb=query)
        
    elif action == "finish_sticker":
        current_sticker = settings.get("finish_sticker")
        text = "✨ **Finish Sticker Config**\n\n"
        if current_sticker:
            text += "✅ Final sticker is currently configured.\n\n"
        else:
            text += "❌ No final sticker configured yet.\n\n"
        text += "Send a sticker to set it as the ending post, or send `-` to remove configuration."
        
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings_back")]])
        )
        try:
            response = await client.listen(chat_id=chat_id, user_id=user_id, filters=~command_filter, timeout=300)
            if response:
                if response.sticker:
                    await db.update_user_settings(user_id, "finish_sticker", response.sticker.file_id)
                    await query.message.reply_text("✅ Finish sticker saved successfully!")
                elif response.text and response.text.strip() == "-":
                    await db.update_user_settings(user_id, "finish_sticker", None)
                    await query.message.reply_text("🗑️ Finish sticker cleared!")
                await response.delete()
        except Exception:
            pass
        await show_main_menu(client, chat_id, message_id, user_id, cb=query)
        
    elif action == "btn_post_format":
        current_format = settings.get("button_post_format", "<b>{anime} | Tamil Dubbed #Official</b>\n\n<b>Season : {season} | Episode : {episode}</b>\n\n<b>‼️Note - Click The Below Button to Get Episodes 👇</b>")
        text = (
            f"🔗 **Configure Button Post Format**\n\n"
            f"**Current Format:**\n`{current_format}`\n\n"
            f"**Variables:**\n"
            f"• `{{anime}}` - Anime Name\n"
            f"• `{{season}}` - Season number\n"
            f"• `{{episode}}` - Episode number\n\n"
            f"Send the new template format containing html tags, or send `-` to reset to default."
        )
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings_back")]])
        )
        try:
            response = await client.listen(chat_id=chat_id, user_id=user_id, filters=filters.text & ~command_filter, timeout=300)
            if response:
                text_val = response.text.strip()
                if text_val == "-":
                    default_val = "<b>{anime} | Tamil Dubbed #Official</b>\n\n<b>Season : {season} | Episode : {episode}</b>\n\n<b>‼️Note - Click The Below Button to Get Episodes 👇</b>"
                    await db.update_user_settings(user_id, "button_post_format", default_val)
                    await query.message.reply_text("✅ Button post format reset to default!")
                else:
                    await db.update_user_settings(user_id, "button_post_format", text_val)
                    await query.message.reply_text("✅ Button post format updated successfully!")
                await response.delete()
        except Exception:
            pass
        await show_main_menu(client, chat_id, message_id, user_id, cb=query)
        
    elif action == "prefix_suffix":
        await show_prefix_suffix_menu(client, chat_id, message_id, user_id, cb=query)
        
    elif action == "import_export":
        await show_import_export_menu(client, chat_id, message_id, user_id, cb=query)
        
    elif action == "metadata":
        await show_metadata_menu(client, chat_id, message_id, user_id, cb=query)
        
    elif action == "channels":
        await show_channels_menu(client, chat_id, message_id, user_id, cb=query)
        
    elif action == "config_filestore":
        current_filestore = settings.get("filestore_username", "")
        text = (
            "🤖 **Configure File Store Bot**\n\n"
            f"• **Current Username:** `@{current_filestore or 'Not set'}`\n\n"
            "Send the username of your Telegram File Store Bot (e.g. `MyFileStoreBot`):"
        )
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="settings_back")]])
        )
        try:
            response = await client.listen(chat_id=chat_id, user_id=user_id, filters=filters.text & ~command_filter, timeout=300)
            if response:
                val = response.text.strip().replace("@", "")
                await db.update_user_settings(user_id, "filestore_username", val)
                await query.message.reply_text("✅ File Store Bot username updated successfully!")
                await response.delete()
        except Exception:
            pass
        await show_main_menu(client, chat_id, message_id, user_id, cb=query)
        
    elif action == "config_dumpchannel":
        current_dump = settings.get("dump_channel_id", "")
        text = (
            "📁 **Configure Dump Channel ID**\n\n"
            f"• **Current Dump Channel ID:** `{current_dump or 'Not set'}`\n\n"
            "Send the numerical ID of your Dump Channel (e.g. `-1002234032904`):"
        )
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="settings_back")]])
        )
        try:
            response = await client.listen(chat_id=chat_id, user_id=user_id, filters=filters.text & ~command_filter, timeout=300)
            if response:
                val = response.text.strip()
                try:
                    val_int = int(val)
                    await db.update_user_settings(user_id, "dump_channel_id", val_int)
                    await query.message.reply_text("✅ Dump Channel ID updated successfully!")
                except ValueError:
                    await query.message.reply_text("❌ Invalid ID! Please send a valid numerical ID starting with -100.")
                await response.delete()
        except Exception:
            pass
        await show_main_menu(client, chat_id, message_id, user_id, cb=query)

async def show_prefix_suffix_menu(client, chat_id, message_id, user_id, cb):
    settings = await db.get_user_settings(user_id)
    text = (
        f"✏️ **Prefix & Suffix Configuration**\n\n"
        f"• **Current Prefix:** `{settings.get('prefix', 'None')}`\n"
        f"• **Current Suffix:** `{settings.get('suffix', 'None')}`\n\n"
        f"Select an option below to configure."
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("Set Prefix", callback_data="sub_prefix"),
         InlineKeyboardButton("Set Suffix", callback_data="sub_suffix")],
        [InlineKeyboardButton("Clear Prefix", callback_data="clear_prefix"),
         InlineKeyboardButton("Clear Suffix", callback_data="clear_suffix")],
        [InlineKeyboardButton("🔙 Back", callback_data="settings_back")]
    ])
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^sub_"))
async def sub_prefix_suffix_cb(client: Client, query: CallbackQuery):
    action = query.data.replace("sub_", "")
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    message_id = query.message.id
    
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    try:
        await query.answer()
    except Exception:
        pass
        
    text_prompt = f"Send the text for **{action}**. Send `-` to clear."
    await query.message.edit_text(
        text_prompt,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="sub_back")]])
    )
    
    try:
        response = await client.listen(chat_id=chat_id, user_id=user_id, filters=filters.text & ~command_filter, timeout=300)
        if response:
            text_val = response.text.strip()
            val = "" if text_val == "-" else text_val
            await db.update_user_settings(user_id, action, val)
            await query.message.reply_text(f"✅ {action.title()} updated successfully!")
            await response.delete()
    except Exception:
        pass
        
    await show_prefix_suffix_menu(client, chat_id, message_id, user_id, cb=query)

@Client.on_callback_query(filters.regex(r"^clear_prefix$"))
async def clear_prefix_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    await db.update_user_settings(user_id, "prefix", "")
    try:
        await query.answer("Prefix cleared!")
    except Exception:
        pass
    await show_prefix_suffix_menu(client, chat_id, query.message.id, user_id, cb=query)

@Client.on_callback_query(filters.regex(r"^clear_suffix$"))
async def clear_suffix_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    await db.update_user_settings(user_id, "suffix", "")
    try:
        await query.answer("Suffix cleared!")
    except Exception:
        pass
    await show_prefix_suffix_menu(client, chat_id, query.message.id, user_id, cb=query)

@Client.on_callback_query(filters.regex(r"^sub_back$"))
async def sub_back_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    await show_prefix_suffix_menu(client, chat_id, query.message.id, user_id, cb=query)

@Client.on_callback_query(filters.regex(r"^settings_back$"))
async def settings_back_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    await show_main_menu(client, chat_id, query.message.id, user_id, cb=query)

def render_metadata_markup(metadata_status):
    status_label = "On ✅" if metadata_status == "On" else "Off ❌"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Toggle Status: {status_label}", callback_data="meta_toggle")],
        [InlineKeyboardButton("➕ Set Metadata", callback_data="meta_set_metadata_txt"),
         InlineKeyboardButton("🗑️ Clear Metadata", callback_data="meta_clear_all")],
        [InlineKeyboardButton("🔙 Back", callback_data="settings_back")]
    ])

async def show_metadata_menu(client, chat_id, message_id, user_id, cb):
    settings = await db.get_user_settings(user_id)
    metadata_status = settings.get("metadata", "Off")
    
    text = (
        f"🏷️ **Metadata Configuration**\n\n"
        f"• **Status:** `{metadata_status}`\n"
        f"• **Metadata Value:** `{settings.get('metadata_txt') or 'Not set'}`\n\n"
        f"Tap buttons below to change configurations."
    )
    markup = render_metadata_markup(metadata_status)
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^meta_"))
async def metadata_cb_handler(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    message_id = query.message.id
    action = query.data.replace("meta_", "")
    
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    try:
        await query.answer()
    except Exception:
        pass
        
    settings = await db.get_user_settings(user_id)
    
    if action == "toggle":
        current = settings.get("metadata", "Off")
        new_status = "On" if current == "Off" else "Off"
        await db.update_user_settings(user_id, "metadata", new_status)
        await show_metadata_menu(client, chat_id, message_id, user_id, cb=query)
        
    elif action == "clear_all":
        await db.update_user_settings(user_id, "metadata_txt", "")
        await db.update_user_settings(user_id, "metadata", "Off")
        await query.message.reply_text("🗑️ Metadata settings cleared!")
        await show_metadata_menu(client, chat_id, message_id, user_id, cb=query)
        
    elif action.startswith("set_"):
        field = action.replace("set_", "")
        
        await query.message.edit_text(
            f"Please send the new value for **Metadata Text**. Send `-` to clear.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="meta_back")]])
        )
        try:
            response = await client.listen(chat_id=chat_id, user_id=user_id, filters=filters.text & ~command_filter, timeout=300)
            if response:
                text_val = response.text.strip()
                if text_val == "-":
                    await db.update_user_settings(user_id, field, "")
                    await query.message.reply_text("✅ Metadata cleared!")
                else:
                    await db.update_user_settings(user_id, field, text_val)
                    await db.update_user_settings(user_id, "metadata", "On")
                    await query.message.reply_text("✅ Metadata saved successfully!")
                await response.delete()
        except Exception:
            pass
        await show_metadata_menu(client, chat_id, message_id, user_id, cb=query)
        
    elif action == "back":
        await show_metadata_menu(client, chat_id, message_id, user_id, cb=query)

async def show_channels_menu(client, chat_id, message_id, user_id, cb):
    channels = await db.get_channels(user_id)
    text = "📺 **Routing Channels Configuration**\n\n"
    if channels:
        text += "Here are your mapped channels:\n"
        for i, ch in enumerate(channels, 1):
            text += f"**{i}.** Hint: `{ch['hint']}` ➔ <a href='{ch['link']}'>{ch['title']}</a> (ID: <code>{ch['channel_id']}</code>)\n"
    else:
        text += "❌ No routing channels configured yet.\n"
        
    text += "\nTo map a channel you can use `/add_channel` command, or tap **➕ Add Channel** below to configure one dynamically."
    
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(f"🗑️ Delete Hint: {ch['hint']}", callback_data=f"chan_del_{str(ch['_id'])}")])
        
    buttons.append([InlineKeyboardButton("➕ Add Channel", callback_data="chan_add_new")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="settings_back")])
    
    markup = InlineKeyboardMarkup(buttons)
    try:
        await cb.message.edit_text(text, reply_markup=markup, disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^chan_"))
async def channels_cb_handler(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    message_id = query.message.id
    action = query.data.replace("chan_", "")
    
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    try:
        await query.answer()
    except Exception:
        pass
        
    if action.startswith("del_"):
        db_id = action.replace("del_", "")
        await db.remove_channel(db_id)
        await query.message.reply_text("🗑️ Routing channel removed successfully!")
        await show_channels_menu(client, chat_id, message_id, user_id, cb=query)
        
    elif action == "add_new":
        await query.message.edit_text(
            "Please send the Target Channel username (e.g. `@mychannel`), channel invite link, or channel ID:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="chan_back")]])
        )
        try:
            chan_resp = await client.listen(chat_id=chat_id, user_id=user_id, filters=filters.text & ~command_filter, timeout=300)
            if chan_resp:
                chan_str = chan_resp.text.strip()
                hint_msg = await query.message.reply_text(
                    "Great! Now send the **hint keyword** (when this keyword matches the anime name, files will route to this channel):",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="chan_back")]])
                )
                
                hint_resp = await client.listen(chat_id=chat_id, user_id=user_id, filters=filters.text & ~command_filter, timeout=300)
                if hint_resp:
                    hint_str = hint_resp.text.strip().lower()
                    try:
                        resolved_chat = await client.get_chat(chan_str)
                        c_title = resolved_chat.title or "Target Channel"
                        c_id = resolved_chat.id
                        c_link = resolved_chat.invite_link or f"https://t.me/{resolved_chat.username}" if resolved_chat.username else "https://t.me"
                        
                        await db.add_channel(user_id, c_id, c_title, c_link, hint_str)
                        await query.message.reply_text(f"✅ Target channel **{c_title}** added successfully with hint `{hint_str}`!")
                    except Exception as e:
                        await query.message.reply_text(f"❌ Failed to resolve channel details: {e}")
                    
                    await chan_resp.delete()
                    await hint_resp.delete()
                    await hint_msg.delete()
        except Exception:
            pass
        await show_channels_menu(client, chat_id, message_id, user_id, cb=query)
        
    elif action == "back":
        await show_channels_menu(client, chat_id, message_id, user_id, cb=query)

async def show_import_export_menu(client, chat_id, message_id, user_id, cb):
    text = (
        "💾 **Backup & Restore settings**\n\n"
        "• **Export Config:** Generates a `.json` backup file of all configuration settings and channel links.\n"
        "• **Import Config:** Uploads and applies settings from a backup JSON file."
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Export Config", callback_data="action_export"),
         InlineKeyboardButton("📥 Import Config", callback_data="action_import")],
        [InlineKeyboardButton("🔙 Back", callback_data="settings_back")]
    ])
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^action_export$"))
async def action_export_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    try:
        await query.answer("Generating export file...")
    except Exception:
        pass
        
    settings = await db.get_user_settings(user_id)
    channels = await db.get_channels(user_id)
    
    cleaned_channels = []
    for ch in channels:
        ch['_id'] = str(ch['_id'])
        cleaned_channels.append(ch)
        
    export_data = {"settings": settings, "channels": cleaned_channels}
    
    # ensure temp folder
    os.makedirs("temp", exist_ok=True)
    file_path = f"temp/export_{user_id}.json"
    with open(file_path, "w") as f:
        json.dump(export_data, f, indent=4)
        
    try:
        await query.message.reply_document(
            document=file_path,
            caption="📤 **Your Bot Settings Configuration**\n\nYou can restore these settings anytime using the **Import Config** button."
        )
    except Exception as e:
        await query.message.reply_text(f"Failed to send config document: {e}")
        
    if os.path.exists(file_path):
        os.remove(file_path)

@Client.on_callback_query(filters.regex(r"^action_import$"))
async def action_import_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    message_id = query.message.id
    
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    try:
        await query.answer()
    except Exception:
        pass
        
    await query.message.edit_text(
        "📥 **Import Settings**\n\nPlease upload the JSON config backup file you previously exported.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="action_import_back")]])
    )
    
    try:
        response = await client.listen(chat_id=chat_id, user_id=user_id, filters=filters.document & ~command_filter, timeout=300)
        if response and response.document:
            if not response.document.file_name.endswith(".json"):
                await query.message.reply_text("❌ Invalid file format! Please upload a valid JSON config file.")
                await response.delete()
                await show_import_export_menu(client, chat_id, message_id, user_id, cb=query)
                return
            
            os.makedirs("temp", exist_ok=True)
            local_path = await client.download_media(response, file_name="temp/import_temp.json")
            try:
                with open(local_path, "r") as f:
                    data = json.load(f)
                
                settings_dict = data.get("settings", {})
                await db.update_full_settings(user_id, settings_dict)
                
                # Import channels
                imported_channels = data.get("channels", [])
                # Clear and insert channels
                for ch in imported_channels:
                    # check if already exists
                    linked_channels = await db.get_channels(user_id)
                    exists = False
                    for lc in linked_channels:
                        if lc['channel_id'] == ch['channel_id']:
                            exists = True
                            break
                    if not exists:
                        await db.add_channel(user_id, ch['channel_id'], ch['title'], ch['link'], ch['hint'])
                        
                await query.message.reply_text("✅ **Configuration and channel links imported successfully!**")
            except Exception as e:
                await query.message.reply_text(f"❌ Failed to parse config file: {e}")
            finally:
                if os.path.exists(local_path):
                    os.remove(local_path)
            
            await response.delete()
    except Exception:
        pass
        
    await show_import_export_menu(client, chat_id, message_id, user_id, cb=query)

@Client.on_callback_query(filters.regex(r"^action_import_back$"))
async def action_import_back_cb(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    await client.stop_listening(chat_id=chat_id, user_id=user_id)
    await show_import_export_menu(client, chat_id, query.message.id, user_id, cb=query)


# ─── Commands Fallbacks ──────────────────────────────────────────────────────────

@Client.on_message(filters.command("set_caption") & filters.private)
@authorized_only()
async def set_caption_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    if len(message.command) == 1:
        await message.reply_text("Usage: `/set_caption [your custom caption template]`\nE.g.: `/set_caption {filename}`")
        return
    caption = message.text.split(" ", 1)[1].strip()
    await db.update_user_settings(message.from_user.id, "caption_format", caption)
    await message.reply_text(f"**Caption set successfully:**\n\n`{caption}`")

@Client.on_message(filters.command(["see_caption", "view_caption"]) & filters.private)
@authorized_only()
async def see_caption_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    settings = await db.get_user_settings(message.from_user.id)
    caption = settings.get("caption_format")
    if caption:
        await message.reply_text(f"**Your Current Caption Template:**\n\n`{caption}`")
    else:
        await message.reply_text("You have not set any custom caption yet.")

@Client.on_message(filters.command("del_caption") & filters.private)
@authorized_only()
async def del_caption_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    await db.update_user_settings(message.from_user.id, "caption_format", "<b>{filename}</b>")
    await message.reply_text("Custom caption reset to default (`<b>{filename}</b>`)!")

@Client.on_message(filters.command("set_rename") & filters.private)
@authorized_only()
async def set_rename_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    if len(message.command) == 1:
        await message.reply_text("Usage: `/set_rename [your custom rename format]`\nE.g.: `/set_rename {anime} - S{season}E{episode} [{language}] {quality} @suffix.mkv`")
        return
    rename = message.text.split(" ", 1)[1].strip()
    await db.update_user_settings(message.from_user.id, "rename_format", rename)
    await message.reply_text(f"**Rename format set successfully:**\n\n`{rename}`")

@Client.on_message(filters.command(["see_rename", "view_rename"]) & filters.private)
@authorized_only()
async def see_rename_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    settings = await db.get_user_settings(message.from_user.id)
    rename = settings.get("rename_format")
    if rename:
        await message.reply_text(f"**Your Current Rename Format Template:**\n\n`{rename}`")
    else:
        await message.reply_text("You have not set any custom rename template yet.")

@Client.on_message(filters.command("del_rename") & filters.private)
@authorized_only()
async def del_rename_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    default_rename = "{anime} - S{season}E{episode} [{language}] {quality} @suffix.mkv"
    await db.update_user_settings(message.from_user.id, "rename_format", default_rename)
    await message.reply_text("Custom rename format reset to default!")

@Client.on_message(filters.command("set_prefix") & filters.private)
@authorized_only()
async def set_prefix_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    if len(message.command) == 1:
        await message.reply_text("Usage: `/set_prefix [prefix text]`")
        return
    prefix = message.text.split(" ", 1)[1].strip()
    await db.update_user_settings(message.from_user.id, "prefix", prefix)
    await message.reply_text(f"**Prefix set successfully:**\n\n`{prefix}`")

@Client.on_message(filters.command("del_prefix") & filters.private)
@authorized_only()
async def del_prefix_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    await db.update_user_settings(message.from_user.id, "prefix", "")
    await message.reply_text("Custom prefix cleared!")

@Client.on_message(filters.command("set_suffix") & filters.private)
@authorized_only()
async def set_suffix_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    if len(message.command) == 1:
        await message.reply_text("Usage: `/set_suffix [suffix text]`")
        return
    suffix = message.text.split(" ", 1)[1].strip()
    await db.update_user_settings(message.from_user.id, "suffix", suffix)
    await message.reply_text(f"**Suffix set successfully:**\n\n`{suffix}`")

@Client.on_message(filters.command("del_suffix") & filters.private)
@authorized_only()
async def del_suffix_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    await db.update_user_settings(message.from_user.id, "suffix", "")
    await message.reply_text("Custom suffix cleared!")

@Client.on_message(filters.command(["view_thumb", "viewthumb"]) & filters.private)
@authorized_only()
async def view_thumb_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    settings = await db.get_user_settings(message.from_user.id)
    thumb = settings.get("thumbnail")
    if thumb:
        try:
            await client.send_photo(chat_id=message.chat.id, photo=thumb, caption="Your current custom thumbnail")
        except Exception as e:
            await message.reply_text(f"Failed to send thumbnail. It might have expired or been deleted. Details: {e}")
    else:
        await message.reply_text("You don't have any custom thumbnail saved.")

@Client.on_message(filters.command(["del_thumb", "delthumb"]) & filters.private)
@authorized_only()
async def del_thumb_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    await db.update_user_settings(message.from_user.id, "thumbnail", None)
    await message.reply_text("Thumbnail deleted successfully!")

@Client.on_message(filters.command("set_sticker") & filters.private)
@authorized_only()
async def set_sticker_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    if message.reply_to_message and message.reply_to_message.sticker:
        sticker_id = message.reply_to_message.sticker.file_id
        await db.update_user_settings(message.from_user.id, "finish_sticker", sticker_id)
        await message.reply_text("✅ Finish sticker saved successfully!")
        return
    await message.reply_text("Usage:\nReply `/set_sticker` to the sticker you want to set as the final upload confirmation.")

@Client.on_message(filters.command("del_sticker") & filters.private)
@authorized_only()
async def del_sticker_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    await db.update_user_settings(message.from_user.id, "finish_sticker", None)
    await message.reply_text("Finish sticker cleared!")


@Client.on_message(filters.command("set_btn_format") & filters.private)
@authorized_only()
async def set_btn_format_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    if len(message.command) == 1:
        await message.reply_text("Usage: `/set_btn_format [your custom format]`\nPlaceholders: `{anime}`, `{season}`, `{episode}`")
        return
    fmt = message.text.split(" ", 1)[1].strip()
    await db.update_user_settings(message.from_user.id, "button_post_format", fmt)
    await message.reply_text(f"**Button post format set successfully:**\n\n`{fmt}`")


@Client.on_message(filters.command("del_btn_format") & filters.private)
@authorized_only()
async def del_btn_format_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    default_val = "<b>{anime} | Tamil Dubbed #Official</b>\n\n<b>Season : {season} | Episode : {episode}</b>\n\n<b>‼️Note - Click The Below Button to Get Episodes 👇</b>"
    await db.update_user_settings(message.from_user.id, "button_post_format", default_val)
    await message.reply_text("Custom button post format reset to default!")


@Client.on_message(filters.command("see_btn_format") & filters.private)
@authorized_only()
async def see_btn_format_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    settings = await db.get_user_settings(message.from_user.id)
    fmt = settings.get("button_post_format", "<b>{anime} | Tamil Dubbed #Official</b>\n\n<b>Season : {season} | Episode : {episode}</b>\n\n<b>‼️Note - Click The Below Button to Get Episodes 👇</b>")
    await message.reply_text(f"**Your Current Button Post Format:**\n\n`{fmt}`")
