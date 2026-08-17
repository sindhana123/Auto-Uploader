from pyrogram import Client, filters
from pyrogram.types import Message
from database import db

@Client.on_message(filters.command("add_channel") & filters.private)
async def add_channel_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    if not await db.is_user_authorized(message.from_user.id):
        await message.reply_text("<b>❌ You are not authorized to use this bot. Please contact the Owner/Admin to authorize you.</b>")
        return
    chat = None
    hint = None
    
    # 1. Check if replying to a forwarded message from a channel
    if message.reply_to_message and message.reply_to_message.forward_from_chat:
        chat_obj = message.reply_to_message.forward_from_chat
        if chat_obj.type.name != "CHANNEL":
            await message.reply_text("The forwarded message is not from a channel.")
            return
        
        # Resolve full chat to get invite_link/username
        try:
            chat = await client.get_chat(chat_obj.id)
        except Exception as e:
            # Fallback to forwarded chat object itself if get_chat fails
            chat = chat_obj
            
        # Parse hint from the command text
        args = message.text.split(" ", 1)
        if len(args) > 1:
            hint = args[1].strip()
            
    else:
        # 2. Direct command: parse channel identifier & hint
        text = message.text.strip()
        parts = text.split()
        if len(parts) < 2:
            await message.reply_text(
                "Usage:\n"
                "1. Reply to forwarded message: `/add_channel [hint]`\n"
                "2. Or Direct: `/add_channel [channel_identifier] [hint]`\n"
                "Where `channel_identifier` is channel ID, username or link."
            )
            return
            
        args = parts[1:]
        channel_id_or_username = None
        hint_words = []
        
        for arg in args:
            # Check if this argument looks like a channel ID, @username, or t.me link
            if arg.startswith("-100") or arg.startswith("@") or "t.me/" in arg:
                channel_id_or_username = arg
            else:
                hint_words.append(arg)
                
        if not channel_id_or_username:
            # Fallback: assume first argument is the channel identifier
            channel_id_or_username = args[0]
            hint_words = args[1:]
            
        hint = " ".join(hint_words).strip() if hint_words else None
        
        # Clean username from link
        if "t.me/" in channel_id_or_username:
            parsed_name = channel_id_or_username.split("/")[-1].strip()
            if parsed_name:
                channel_id_or_username = f"@{parsed_name}"
                
        # Resolve channel via Pyrogram
        try:
            if channel_id_or_username.startswith("-") or channel_id_or_username.isdigit():
                resolved_id = int(channel_id_or_username)
            else:
                resolved_id = channel_id_or_username
            chat = await client.get_chat(resolved_id)
        except Exception as e:
            await message.reply_text(f"Could not fetch channel details. Ensure the bot is admin in the channel.\nError: {e}")
            return
            
    if chat.type.name != "CHANNEL":
        await message.reply_text("The resolved chat is not a channel.")
        return
        
    title = chat.title
    link = chat.invite_link or (f"https://t.me/{chat.username}" if chat.username else f"https://t.me/c/{str(chat.id).replace('-100', '')}")
    if not hint:
        hint = title
        
    await db.add_channel(message.from_user.id, chat.id, title, link, hint)
    await message.reply_text(f"Channel Added!\nTitle: **{title}**\nID: `{chat.id}`\nHint: `{hint}`\nLink: {link}")

@Client.on_message(filters.command("view_channel") & filters.private)
async def view_channel_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    if not await db.is_user_authorized(message.from_user.id):
        await message.reply_text("<b>❌ You are not authorized to use this bot. Please contact the Owner/Admin to authorize you.</b>")
        return
    channels = await db.get_channels(message.from_user.id)
    if not channels:
        await message.reply_text("No channels added yet.")
        return
        
    text = "**Your Saved Channels:**\n\n"
    for i, ch in enumerate(channels, 1):
        text += f"{i}. **{ch['title']}**\n"
        text += f"   - ID: `{ch['channel_id']}`\n"
        text += f"   - Hint: `{ch['hint']}`\n"
        text += f"   - Link: {ch['link']}\n"
        text += f"   - DB ID: `{ch['_id']}`\n\n"
        
    await message.reply_text(text, disable_web_page_preview=True)

@Client.on_message(filters.command("remove_channel") & filters.private)
async def remove_channel_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    if not await db.is_user_authorized(message.from_user.id):
        await message.reply_text("<b>❌ You are not authorized to use this bot. Please contact the Owner/Admin to authorize you.</b>")
        return
    args = message.text.split(" ")
    if len(args) < 2:
        await message.reply_text("Usage: `/remove_channel <db_id>`\nGet DB ID from /view_channel.")
        return
        
    db_id = args[1]
    try:
        await db.remove_channel(db_id)
        await message.reply_text(f"Channel removed successfully.")
    except Exception as e:
        await message.reply_text(f"Error removing channel. Is the ID correct?\nError: {e}")
