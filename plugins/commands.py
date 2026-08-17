from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import os
from database import db

START_PIC = os.environ.get("START_PIC", "https://i.ibb.co/ZRH371N3/k-Sog-Qhd-A.jpg") # Set your image URL in .env or config if needed

def start_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Updates", url="https://t.me/AnimePiratesTamil"), 
            InlineKeyboardButton("Support", url="https://t.me/AnimePiratesTamil")
        ],
        [
            InlineKeyboardButton("Help", callback_data="cb_help"), 
            InlineKeyboardButton("About", callback_data="cb_about")
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="cb_close")
        ]
    ])

def back_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="cb_back")]
    ])

START_TEXT = """<b>Hello {first_name} 👋</b> 

<blockquote>➻ This Is An Advanced Video Uploader Bot.
➻ Using This Bot You Can Upload, Mux, and Rename Files.
➻ Automate Your Target Channel Routing Easily.</blockquote>"""

ABOUT_TEXT = """<b>📝 Language :</b> Python3
<b>📚 Library :</b> Pyrogram
<b>🚀 Server :</b> VPS
<b>📢 Channel :</b> Anime Pirates
   
<b>😈 Bot Made By :</b> Motherbasha"""

HELP_TEXT = """<b>📙 Manual Guide: <a href="https://telegra.ph/Auto-Uploader-Manual-08-17">Click Here To View</a></b>

<b>Available User Commands & Usage:</b>

<blockquote>/start - Start the bot & view main menu.
/settings - Core settings panel to configure everything.
/set_name <anime> - Set the anime name for processing.
/set_details <ep>, <szn>, <lang> - Set current file details.
/start_process - Queues your videos and audio for uploading.
/clear_queue - Clear your currently queued files.</blockquote>

<b>Template / Style Modifiers:</b>
<blockquote>/set_prefix  |  /set_suffix
/set_rename  |  /set_caption
/set_btn_format
/set_thumb   |  /set_sticker</blockquote>

<b>Channel Routing:</b>
<blockquote>/add_channel <hint> <link> - (Reply) Link hint to channel.
/view_channel - View your saved upload channels.
/remove_channel <id> - Remove a tracked channel.</blockquote>"""

from config import Config

@Client.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    user_id = message.from_user.id
    
    # Check if user is already in DB
    is_new = await db.users.find_one({"_id": user_id}) is None
    if is_new:
        # Create user record
        await db.update_user_state(user_id, {"mode": "normal", "current_job": {}})
        # Auto authorize owners
        if user_id in Config.OWNERS:
            await db.authorize_user(user_id)
            
        # Log new user starting the bot
        if Config.LOG_CHANNEL:
            try:
                usr = message.from_user
                log_msg = (
                    f"👤 **New User Started Bot**\n\n"
                    f"• **Name:** {usr.first_name} {usr.last_name or ''}\n"
                    f"• **ID:** `{usr.id}`\n"
                    f"• **Username:** @{usr.username or 'None'}"
                )
                await client.send_message(Config.LOG_CHANNEL, log_msg)
            except Exception as e:
                print(f"Error logging start event: {e}")
                
    # Check authorization
    if not await db.is_user_authorized(user_id):
        await message.reply_text("<b>❌ You are not authorized to use this bot. Please contact the Owner/Admin to authorize you.</b>")
        return
        
    text = START_TEXT.format(first_name=message.from_user.first_name)
    if START_PIC:
        try:
            await message.reply_photo(photo=START_PIC, caption=text, reply_markup=start_markup())
        except Exception:
            await message.reply_text(text, reply_markup=start_markup())
    else:
        await message.reply_text(text, reply_markup=start_markup())

@Client.on_callback_query(filters.regex(r"^cb_"))
async def cb_handler(client: Client, query: CallbackQuery):
    data = query.data
    
    try:
        if data == "cb_help":
            await query.message.edit_caption(caption=HELP_TEXT, reply_markup=back_markup())
        elif data == "cb_about":
            await query.message.edit_caption(caption=ABOUT_TEXT, reply_markup=back_markup())
        elif data == "cb_back":
            text = START_TEXT.format(first_name=query.from_user.first_name)
            await query.message.edit_caption(caption=text, reply_markup=start_markup())
        elif data == "cb_close":
            await query.message.delete()
    except Exception:
        if data == "cb_help":
            await query.message.edit_text(text=HELP_TEXT, reply_markup=back_markup())
        elif data == "cb_about":
            await query.message.edit_text(text=ABOUT_TEXT, reply_markup=back_markup())
        elif data == "cb_back":
            text = START_TEXT.format(first_name=query.from_user.first_name)
            await query.message.edit_text(text=text, reply_markup=start_markup())
        elif data == "cb_close":
            await query.message.delete()
    except Exception:
        pass


@Client.on_message(filters.command("authorize") & filters.private)
async def authorize_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    if not await db.is_user_admin(message.from_user.id):
        await message.reply_text("<b>❌ Only owners/admins can use this command.</b>")
        return
    if len(message.command) < 2:
        await message.reply_text("<b>Usage: /authorize <user_id></b>")
        return
    try:
        target_id = int(message.command[1])
        await db.authorize_user(target_id)
        await message.reply_text(f"<b>✅ User `{target_id}` has been authorized successfully!</b>")
    except ValueError:
        await message.reply_text("<b>❌ Invalid User ID. Please provide a numeric ID.</b>")


@Client.on_message(filters.command("unauthorize") & filters.private)
async def unauthorize_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    if not await db.is_user_admin(message.from_user.id):
        await message.reply_text("<b>❌ Only owners/admins can use this command.</b>")
        return
    if len(message.command) < 2:
        await message.reply_text("<b>Usage: /unauthorize <user_id></b>")
        return
    try:
        target_id = int(message.command[1])
        await db.unauthorize_user(target_id)
        await message.reply_text(f"<b>✅ User `{target_id}` has been unauthorized!</b>")
    except ValueError:
        await message.reply_text("<b>❌ Invalid User ID. Please provide a numeric ID.</b>")


@Client.on_message(filters.command("add_admin") & filters.private)
async def add_admin_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    if message.from_user.id not in Config.OWNERS:
        await message.reply_text("<b>❌ Only bot owners can use this command.</b>")
        return
    if len(message.command) < 2:
        await message.reply_text("<b>Usage: /add_admin <user_id></b>")
        return
    try:
        target_id = int(message.command[1])
        if target_id == message.from_user.id:
            await message.reply_text("<b>❌ You're already an Owner.</b>")
            return
        await db.add_admin(target_id)
        await message.reply_text(f"<b>✅ User `{target_id}` has been promoted to Admin!</b>")
    except ValueError:
        await message.reply_text("<b>❌ Invalid User ID. Please provide a numeric ID.</b>")


@Client.on_message(filters.command("del_admin") & filters.private)
async def del_admin_cmd(client: Client, message: Message):
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    if message.from_user.id not in Config.OWNERS:
        await message.reply_text("<b>❌ Only bot owners can use this command.</b>")
        return
    if len(message.command) < 2:
        await message.reply_text("<b>Usage: /del_admin <user_id></b>")
        return
    try:
        target_id = int(message.command[1])
        await db.remove_admin(target_id)
        await message.reply_text(f"<b>✅ User `{target_id}` is no longer an Admin!</b>")
    except ValueError:
        await message.reply_text("<b>❌ Invalid User ID. Please provide a numeric ID.</b>")


@Client.on_message(filters.command("clear_cache") & filters.private)
async def clear_cache_cmd(client: Client, message: Message):
    if not await db.is_user_admin(message.from_user.id):
        return
    import shutil
    try:
        shutil.rmtree("temp")
    except Exception:
        pass
    os.makedirs("temp", exist_ok=True)
    await message.reply_text("✅ **Server cache and temporary processing files cleared!**")


@Client.on_message(filters.command("restart") & filters.private)
async def restart_cmd(client: Client, message: Message):
    if message.from_user.id not in Config.OWNERS:
        return
    await message.reply_text("🔄 **Restarting bot... Please wait!**")
    import sys
    os.execl(sys.executable, sys.executable, "main.py")


@Client.on_message(filters.command("cc") & filters.private)
async def cc_cmd(client: Client, message: Message):
    if message.from_user.id not in Config.OWNERS:
        return
    cc_text = """🛠️ **Complete Bot Commands Reference (Owner):**

**Admin Management:**
`/add_admin [id]` - Promote user to Admin.
`/del_admin [id]` - Demote Admin.
`/authorize [id]` - Grant access to bot (Owner/Admin).
`/unauthorize [id]` - Revoke access (Owner/Admin).

**System:**
`/restart` - Restart bot securely.
`/clear_cache` - Clean up temp dir (Admin/Owner).
`/cc` - Show this list.

**General Use:**
`/start` - Main menu.
`/settings` - Open main settings UI.
`/set_name [anime]` - Identify series.
`/set_details [ep], [szn], [lang]` - Fill data manually.
`/start_process` - Trigger queue processing.
`/clear_queue` - Clear user's queued tasks.

**Configs:**
`/set_thumb` (Reply) | `/view_thumb` | `/del_thumb`
`/set_sticker` (Reply) | `/del_sticker`
`/set_prefix [text]` | `/see_prefix` | `/del_prefix`
`/set_suffix [text]` | `/see_suffix` | `/del_suffix`
`/set_rename [text]` | `/see_rename` | `/del_rename`
`/set_caption [text]` | `/see_caption` | `/del_caption`
`/set_btn_format [text]` | `/see_btn_format` | `/del_btn_format`

**Channels:**
`/add_channel [hint] [link]` (Reply)
`/view_channel`
`/remove_channel [id]`"""
    await message.reply_text(cc_text)

