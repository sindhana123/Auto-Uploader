import os
import html
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyromod.exceptions import ListenerTimeout
from database import db

EDIT_STATE = {}

@Client.on_message(filters.command("edit") & filters.private)
async def edit_cmd(client: Client, message: Message):
    if not await db.is_user_authorized(message.from_user.id):
        return
        
    await client.stop_listening(chat_id=message.chat.id, user_id=message.from_user.id)
    
    if message.reply_to_message and message.reply_to_message.forward_from_chat:
        fwd_msg = message.reply_to_message
    else:
        try:
            fwd_msg = await client.ask(
                chat_id=message.chat.id,
                text="**FORWARD a message from your channel here to edit its buttons:**\n\n(Or send /cancel to abort)",
                filters=filters.forwarded | filters.text,
                user_id=message.from_user.id,
                timeout=300
            )
        except ListenerTimeout:
            return
        except Exception:
            return
            
        if not fwd_msg.forward_from_chat and getattr(fwd_msg, "text", "") == "/cancel":
            await message.reply_text("❌ Cancelled edit operation.")
            return

    if not fwd_msg.forward_from_chat or fwd_msg.forward_from_chat.type != enums.ChatType.CHANNEL:
        await message.reply_text("❌ Please **forward a valid message from a Channel**.")
        return
        
    chat_id = fwd_msg.forward_from_chat.id
    msg_id = fwd_msg.forward_from_message_id
    
    try:
        orig_msg = await client.get_messages(chat_id, msg_id)
        if not orig_msg:
            await message.reply_text("❌ Could not fetch original message from channel.")
            return
    except Exception as e:
        await message.reply_text(f"❌ Error fetching message: {e}\n(Make sure Bot is Admin in the channel)")
        return
        
    # Extract existing inline buttons
    buttons = []
    if orig_msg.reply_markup and orig_msg.reply_markup.inline_keyboard:
        for row in orig_msg.reply_markup.inline_keyboard:
            for btn in row:
                if btn.url:
                    buttons.append({"text": btn.text, "url": btn.url})
                    
    EDIT_STATE[message.from_user.id] = {
        "chat_id": chat_id,
        "msg_id": msg_id,
        "buttons": buttons
    }
    
    await render_edit_menu(client, message.from_user.id, message.chat.id)


async def render_edit_menu(client, user_id, chat_id, m_edit=None):
    state = EDIT_STATE.get(user_id)
    if not state:
        return
        
    text = f"🛠 **Message Editor Mode**\n\n"
    text += f"**Channel ID:** `{state['chat_id']}`\n"
    text += f"**Message ID:** `{state['msg_id']}`\n\n"
    text += "**Current Buttons:**\n"
    
    if not state["buttons"]:
        text += "_No buttons attached to this message._\n"
    else:
        for i, btn in enumerate(state["buttons"]):
            text += f"{i+1}. {btn['text']} — `[URL Link]`\n"
            
    markup = []
    markup.append([InlineKeyboardButton("➕ Add New Button", callback_data="edbtn_add")])
    
    if state["buttons"]:
        markup.append([InlineKeyboardButton("➖ Remove Button", callback_data="edbtn_rem")])
        
    markup.append([InlineKeyboardButton("💾 Save & Apply To Channel", callback_data="edbtn_save")])
    markup.append([InlineKeyboardButton("🗑 Cancel", callback_data="edbtn_cancel")])
    
    if m_edit:
        await m_edit.edit_text(text, reply_markup=InlineKeyboardMarkup(markup))
    else:
        await client.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(markup))


@Client.on_callback_query(filters.regex(r"^edbtn_(.*)"))
async def edit_callback_handler(client: Client, query: CallbackQuery):
    action = query.matches[0].group(1)
    user_id = query.from_user.id
    state = EDIT_STATE.get(user_id)
    
    if not state:
        await query.answer("Session expired. Send /edit again.", show_alert=True)
        return
        
    if action == "cancel":
        del EDIT_STATE[user_id]
        await query.message.edit_text("❌ Edit Session Cancelled.")
        return
        
    elif action == "add":
        await query.answer()
        try:
            btn_info = await client.ask(
                chat_id=query.message.chat.id,
                text="**Send New Button Details:**\n\nFormat: `Button Name - https://yourlink.com`\n\n(Send /cancel to abort)",
                user_id=user_id,
                timeout=120
            )
        except ListenerTimeout:
            return
        except Exception:
            return
            
        if btn_info.text == "/cancel":
            await render_edit_menu(client, user_id, query.message.chat.id)
            return
            
        if "-" not in btn_info.text:
            await btn_info.reply_text("⚠️ Invalid Format. Missing hypen `-`.")
        else:
            parts = btn_info.text.split("-", 1)
            b_text = parts[0].strip()
            b_url = parts[1].strip()
            
            if b_url.startswith("http"):
                state["buttons"].append({"text": b_text, "url": b_url})
                await btn_info.reply_text("✅ Button added temporarily.")
            else:
                await btn_info.reply_text("⚠️ Invalid URL. URL must start with http/https")
                
        await render_edit_menu(client, user_id, query.message.chat.id)
        
    elif action == "rem":
        if not state["buttons"]:
            await query.answer("No buttons to remove.", show_alert=True)
            return
            
        await query.answer()
        rem_buttons = []
        for i, b in enumerate(state["buttons"]):
            rem_buttons.append([InlineKeyboardButton(f"Remove: {b['text']}", callback_data=f"edrem_{i}")])
        rem_buttons.append([InlineKeyboardButton("🔙 Back to Edit Menu", callback_data="edbtn_back")])
        
        await query.message.edit_text("✂️ **Select a button to remove:**", reply_markup=InlineKeyboardMarkup(rem_buttons))
        
    elif action == "back":
        await render_edit_menu(client, user_id, query.message.chat.id, m_edit=query.message)
        
    elif action == "save":
        await query.message.edit_text("⏳ Saving changes to channel...")
        chat_id = state["chat_id"]
        msg_id = state["msg_id"]
        
        final_markup = None
        if state["buttons"]:
            kb = []
            for b in state["buttons"]:
                # One button per row, or we can just pair them dynamically
                kb.append([InlineKeyboardButton(b["text"], url=b["url"])])
            final_markup = InlineKeyboardMarkup(kb)
            
        try:
            await client.edit_message_reply_markup(chat_id, msg_id, reply_markup=final_markup)
            await query.message.edit_text("✅ **Successfully updated the message buttons in the channel!**")
            del EDIT_STATE[user_id]
        except Exception as e:
            await query.message.edit_text(f"❌ Failed to update channel message: {e}")


@Client.on_callback_query(filters.regex(r"^edrem_(\d+)"))
async def edit_remove_handler(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    state = EDIT_STATE.get(user_id)
    if not state:
        await query.answer("Session expired.", show_alert=True)
        return
        
    idx = int(query.matches[0].group(1))
    if 0 <= idx < len(state["buttons"]):
        removed = state["buttons"].pop(idx)
        await query.answer(f"Removed: {removed['text']}")
        
    await render_edit_menu(client, user_id, query.message.chat.id, m_edit=query.message)
