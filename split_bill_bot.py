# split_bill_bot.py
# python-telegram-bot v20+
import logging, math, os
from dotenv import load_dotenv
from typing import Dict, List, Tuple

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
)
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("billbot")

# Conversation states
MENU, CURRENCY, TOTAL, GST, SERVICE, NUM_PEOPLE = range(6)

# Session store per chat
# chat_id -> {
#   currency: "SGD"/"MYR",
#   total: float, gst: float, service: float,
#   num_people: int,
#   people: Dict[str, float],   # name -> subtotal (before gst/service)
#   messages: List[int],        # bot message_ids to delete later
#   finalized_msg_id: int|None,
# }
SESSIONS: Dict[int, Dict] = {}

# -------- helpers --------
def get_session(chat_id: int) -> Dict:
    if chat_id not in SESSIONS:
        SESSIONS[chat_id] = {
            "currency": "SGD",
            "total": 0.0,
            "gst": 0.0,
            "service": 0.0,
            "num_people": 0,
            "people": {},
            "messages": [],
            "finalized_msg_id": None,
        }
    return SESSIONS[chat_id]

async def send_and_track(update_or_context, chat_id: int, text: str, **kwargs) -> Message:
    """Send a message and remember its id for later deletion."""
    if hasattr(update_or_context, "message") and update_or_context.message:
        msg = await update_or_context.message.reply_text(text, **kwargs)
    else:
        # Fallback via bot
        msg = await update_or_context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
    get_session(chat_id)["messages"].append(msg.message_id)
    return msg

async def delete_setup_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int, keep_ids: List[int]):
    """Delete all tracked messages except those in keep_ids."""
    session = get_session(chat_id)
    to_delete = [mid for mid in session["messages"] if mid not in keep_ids]
    # attempt deletions; ignore failures (e.g., missing admin rights)
    for mid in to_delete:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception as e:
            logger.debug(f"Delete fail (msg {mid}): {e}")
    # keep only the 'keep' ids
    session["messages"] = [mid for mid in session["messages"] if mid in keep_ids]

def currency_code(label: str) -> str:
    return "SGD" if "SGD" in label.upper() else "MYR"

def fmt_money(code: str, amount: float) -> str:
    return f"{code} {amount:.2f}"

def close_enough(a: float, b: float, tol: float = 0.01) -> bool:
    return abs(a - b) <= tol

def allocate_cents(shares: List[float], grand_total: float) -> List[float]:
    """
    Convert raw float shares into 2dp amounts that sum exactly to grand_total,
    by distributing remainder cents.
    """
    cents = [int(math.floor(x * 100.0)) for x in shares]
    diff = int(round(grand_total * 100)) - sum(cents)
    # add 1 cent to first 'diff' participants
    idx = 0
    while diff > 0 and idx < len(cents):
        cents[idx] += 1
        diff -= 1
        idx += 1
    return [c / 100.0 for c in cents]

# -------- start/help --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    SESSIONS.pop(chat_id, None)  # fresh session
    get_session(chat_id)  # init

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start", callback_data="START_FLOW")],
        [InlineKeyboardButton("ℹ Help", callback_data="HELP_FLOW")],
    ])
    await send_and_track(update, chat_id,
        "👋 Hello! Please choose an option:\n"
        "• *Start* — Begin splitting your bill\n"
        "• *Help* — Instructions on how to use this bot",
        parse_mode="Markdown",
        reply_markup=kb
    )
    # Enter MENU so the next button press is handled by the ConversationHandler
    return MENU

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_help_text(), parse_mode="Markdown")

def get_help_text() -> str:
    return (
        "📖 *How to use Bill Split Bot*\n\n"
        "1️⃣ Type /start and select 'Start' to begin.\n"
        "2️⃣ Choose your currency (SGD or MYR).\n"
        "3️⃣ Enter the total bill amount (before GST/Service).\n"
        "4️⃣ Enter GST % and Service Charge %.\n"
        "5️⃣ Enter the number of people splitting the bill.\n\n"
        "💡 *Custom amounts* (before GST/Service):\n"
        "• `/addamount <name> <amount>` — Add a person's subtotal\n"
        "• `/editamount <name> <amount>` — Change someone's subtotal\n"
        "• `/remove <name>` — Remove a person\n"
        "• `/list` — Show current entries\n"
        "• `/settotal <amount>` — Change bill total\n"
        "• `/calculate` — Finalize and show breakdown\n"
        "• `/reset` — Start over (shows setup again)\n"
        "• `/stop` — Stop and clear everything\n"
        "• `/delete` — Clean up setup messages\n\n"
        "Example:\n"
        "`/addamount Alice 18.5`\n"
        "`/addamount Bob 22`\n"
    )

async def main_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles Start/Help buttons while in MENU state."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id

    if query.data == "START_FLOW":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇸🇬 SGD", callback_data="SGD")],
            [InlineKeyboardButton("🇲🇾 MYR", callback_data="MYR")],
        ])
        await query.message.reply_text("Choose a currency:", reply_markup=kb)
        return CURRENCY  # move to currency selection state

    elif query.data == "HELP_FLOW":
        await query.message.reply_text(get_help_text(), parse_mode="Markdown")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Start", callback_data="START_FLOW")]])
        await query.message.reply_text("Ready to start?", reply_markup=kb)
        return MENU  # stay in menu

# -------- flow handlers --------
async def choose_currency_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    session = get_session(chat_id)
    session["currency"] = query.data  # "SGD" or "MYR"

    msg = await query.message.reply_text(
        f"💰 Currency set to {session['currency']}.\n"
        f"Enter *total bill amount* (before GST/Service):", parse_mode="Markdown"
    )
    session["messages"].append(msg.message_id)
    return TOTAL

async def set_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    try:
        session["total"] = float(update.message.text)
        if session["total"] < 0:
            raise ValueError
    except ValueError:
        await send_and_track(update, chat_id, "❌ Please enter a valid non-negative number for the total.")
        return TOTAL

    await send_and_track(update, chat_id, "🧾 Enter *GST%* (e.g. 9 for 9). Type 0 if none:", parse_mode="Markdown")
    return GST

async def set_gst(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    try:
        session["gst"] = float(update.message.text)
        if session["gst"] < 0:
            raise ValueError
    except ValueError:
        await send_and_track(update, chat_id, "❌ Please enter a valid GST percentage (>= 0).")
        return GST

    await send_and_track(update, chat_id, "🍽 Enter *Service Charge%* (e.g. 10). Type 0 if none:", parse_mode="Markdown")
    return SERVICE

async def set_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    try:
        session["service"] = float(update.message.text)
        if session["service"] < 0:
            raise ValueError
    except ValueError:
        await send_and_track(update, chat_id, "❌ Please enter a valid Service Charge percentage (>= 0).")
        return SERVICE

    await send_and_track(update, chat_id, "👥 How many people are splitting? (for equal split if no custom amounts are added)")
    return NUM_PEOPLE

async def set_num_people(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    try:
        n = int(update.message.text)
        if n <= 0:
            raise ValueError
        session["num_people"] = n
    except ValueError:
        await send_and_track(update, chat_id, "❌ Please enter a valid positive integer for number of people.")
        return NUM_PEOPLE

    await send_and_track(
        update, chat_id,
        "✅ Setup complete.\n\n"
        "Now add custom subtotals (before GST/Service) with:\n"
        "`/addamount <name> <amount>`\n"
        "Examples:\n"
        "• `/addamount Alice 18.5`\n"
        "• `/addamount Bob 22`\n\n"
        "Commands:\n"
        "• `/editamount <name> <amount>` to change\n"
        "• `/remove <name>` to remove\n"
        "• `/list` to view entries\n"
        "• `/settotal <amount>` to change bill total\n"
        "• `/calculate` to finalize and show breakdown\n"
        "• `/reset` to start over\n"
        "• `/stop` to stop and clear everything",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ----- command utilities (work anytime after /start) -----
async def addamount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await update.message.reply_text("❌ No active bill. Use /start first.")
        return

    if len(context.args) < 2:
        await send_and_track(update, chat_id, "❌ Usage: `/addamount <name> <amount>`", parse_mode="Markdown")
        return

    name = context.args[0]
    try:
        amount = float(context.args[1])
        if amount < 0:
            raise ValueError
    except ValueError:
        await send_and_track(update, chat_id, "❌ Amount must be a non-negative number.")
        return

    # Add or increment existing
    prev = session["people"].get(name, 0.0)
    session["people"][name] = prev + amount
    await send_and_track(update, chat_id, f"✅ Added {name}: {fmt_money(session['currency'], amount)} (total for {name}: {fmt_money(session['currency'], session['people'][name])})")

async def editamount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await update.message.reply_text("❌ No active bill. Use /start first.")
        return
    if len(context.args) < 2:
        await send_and_track(update, chat_id, "❌ Usage: `/editamount <name> <amount>`", parse_mode="Markdown")
        return

    name = context.args[0]
    try:
        amount = float(context.args[1])
        if amount < 0:
            raise ValueError
    except ValueError:
        await send_and_track(update, chat_id, "❌ Amount must be a non-negative number.")
        return

    if name not in session["people"]:
        await send_and_track(update, chat_id, f"❌ {name} is not in the list. Use `/addamount {name} {amount}`.", parse_mode="Markdown")
        return

    session["people"][name] = amount
    await send_and_track(update, chat_id, f"✏️ Updated {name} to {fmt_money(session['currency'], amount)}")

async def remove_person(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await update.message.reply_text("❌ No active bill. Use /start first.")
        return
    if len(context.args) < 1:
        await send_and_track(update, chat_id, "❌ Usage: `/remove <name>`", parse_mode="Markdown")
        return

    name = context.args[0]
    if name in session["people"]            :
        session["people"].pop(name)
        await send_and_track(update, chat_id, f"🗑 Removed {name}.")
    else:
        await send_and_track(update, chat_id, f"❌ {name} not found.")

async def list_people(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await update.message.reply_text("❌ No active bill. Use /start first.")
        return
    if not session["people"]:
        await send_and_track(update, chat_id, "📝 No custom amounts yet. Add with `/addamount <name> <amount>`.", parse_mode="Markdown")
        return

    lines = [f"📋 Current entries ({session['currency']}):"]
    for n, a in session["people"].items():
        lines.append(f"• {n}: {a:.2f}")
    lines.append(f"Target total (before GST/Service): {session['total']:.2f}")
    await send_and_track(update, chat_id, "\n".join(lines))

async def settotal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await update.message.reply_text("❌ No active bill. Use /start first.")
        return
    if len(context.args) < 1:
        await send_and_track(update, chat_id, "❌ Usage: `/settotal <amount>`", parse_mode="Markdown")
        return
    try:
        amt = float(context.args[0])
        if amt < 0:
            raise ValueError
        session["total"] = amt
        await send_and_track(update, chat_id, f"🔁 Bill total updated to {fmt_money(session['currency'], amt)} (before GST/Service).")
    except ValueError:
        await send_and_track(update, chat_id, "❌ Amount must be a non-negative number.")

# ----- improved /reset -----
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Clean up any previous setup/breakdown messages if we were mid-flow
    session = SESSIONS.get(chat_id)
    if session:
        try:
            await delete_setup_messages(context, chat_id, keep_ids=[])
        except Exception as e:
            logger.debug(f"/reset cleanup failed: {e}")
        # delete final breakdown if present
        fid = session.get("finalized_msg_id")
        if fid:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=fid)
            except Exception as e:
                logger.debug(f"/reset final delete fail (msg {fid}): {e}")

    # Fresh session and immediately show the start menu (instructions)
    SESSIONS.pop(chat_id, None)
    # Optional acknowledgement
    await update.message.reply_text("♻️ Reset done. Starting over…")
    return await start(update, context)

# ----- final calculation -----
async def calculate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await update.message.reply_text("❌ No active bill. Use /start first.")
        return

    currency = session["currency"]
    total_before = float(session["total"])
    gst_pct = float(session["gst"])
    svc_pct = float(session["service"])

    # If no custom amounts, equal split by num_people
    if not session["people"]:
        if session["num_people"] <= 0:
            await send_and_track(update, chat_id, "❌ No people yet. Set a valid number with /start again.")
            return
        gst_amt = total_before * (gst_pct / 100.0)
        svc_amt = total_before * (svc_pct / 100.0)
        grand = total_before + gst_amt + svc_amt
        per = grand / session["num_people"]
        # build output
        lines = [
            f"📊 *Bill Breakdown* ({currency})",
            f"💵 Subtotal: {fmt_money(currency, total_before)}",
            f"🧾 GST ({gst_pct}%): {fmt_money(currency, gst_amt)}",
            f"🍽 Service Charge ({svc_pct}%): {fmt_money(currency, svc_amt)}",
            f"💰 *Grand Total*: {fmt_money(currency, grand)}",
            f"👥 *Per Person* ({session['num_people']}): {fmt_money(currency, per)}",
        ]
        msg = await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        session["finalized_msg_id"] = msg.message_id
        # delete all setup messages, keep only breakdown
        await delete_setup_messages(context, chat_id, keep_ids=[msg.message_id])
        return

    # With custom amounts
    people_items: List[Tuple[str, float]] = list(session["people"].items())
    sum_custom = sum(a for _, a in people_items)

    if not close_enough(sum_custom, total_before):
        # error and guidance
        diff = total_before - sum_custom
        sign = "more" if diff > 0 else "less"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Scale amounts to match total", callback_data="SCALE_FIX")],
            [InlineKeyboardButton("✏️ I will edit amounts", callback_data="EDIT_FIX")],
            [InlineKeyboardButton("🧾 Change total to sum of items", callback_data="TOTAL_TO_SUM")],
        ])
        text = (
            "⚠️ *Amounts don’t add up*\n\n"
            f"• Entered total (before GST/Service): {fmt_money(currency, total_before)}\n"
            f"• Sum of custom amounts: {fmt_money(currency, sum_custom)}\n"
            f"• Difference: {fmt_money(currency, diff)} ({sign})\n\n"
            "Choose an option below, or use `/editamount`, `/addamount`, `/remove`, or `/settotal`."
        )
        await send_and_track(update, chat_id, text, parse_mode="Markdown", reply_markup=kb)
        return

    # Compute final shares proportionally
    gst_amt = total_before * (gst_pct / 100.0)
    svc_amt = total_before * (svc_pct / 100.0)
    grand = total_before + gst_amt + svc_amt

    # raw shares = subtotal + proportional tax/service
    raw = []
    for _, sub in people_items:
        tax_part = (sub / total_before) * (gst_amt + svc_amt) if total_before > 0 else 0.0
        raw.append(sub + tax_part)

    final_shares = allocate_cents(raw, grand)

    # output
    lines = [
        f"📊 *Bill Breakdown (Custom)* ({currency})",
        f"💵 Subtotal: {fmt_money(currency, total_before)}",
        f"🧾 GST ({gst_pct}%): {fmt_money(currency, gst_amt)}",
        f"🍽 Service Charge ({svc_pct}%): {fmt_money(currency, svc_amt)}",
        f"💰 *Grand Total*: {fmt_money(currency, grand)}",
        "—",
    ]
    for (name, _), share in zip(people_items, final_shares):
        lines.append(f"👤 {name}: {fmt_money(currency, share)}")
    msg = await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    session["finalized_msg_id"] = msg.message_id

    # auto-cleanup: delete setup/prompt messages, keep only breakdown
    await delete_setup_messages(context, chat_id, keep_ids=[msg.message_id])

# ----- mismatch-fix callbacks -----
async def mismatch_fix_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    session = get_session(chat_id)

    people_items = list(session["people"].items())
    sum_custom = sum(a for _, a in people_items)
    total_before = session["total"]

    if query.data == "SCALE_FIX":
        if sum_custom <= 0:
            await query.message.reply_text("❌ Cannot scale because sum of amounts is 0. Edit amounts first.")
            return
        factor = total_before / sum_custom
        for n, a in people_items:
            session["people"][n] = a * factor
        await query.message.reply_text("✅ Scaled all custom amounts proportionally to match the bill total. Run /calculate again.")

    elif query.data == "EDIT_FIX":
        await query.message.reply_text("✏️ OK. Use `/editamount <name> <amount>` or `/addamount <name> <amount>` then /calculate.", parse_mode="Markdown")

    elif query.data == "TOTAL_TO_SUM":
        session["total"] = sum_custom
        await query.message.reply_text(f"✅ Total updated to match sum of items: {fmt_money(session['currency'], session['total'])}. Run /calculate again.")

# ----- manual delete (optional) -----
async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual cleanup if needed; keeps last breakdown if present."""
    chat_id = update.effective_chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        return
    keep = [session["finalized_msg_id"]] if session["finalized_msg_id"] else []
    await delete_setup_messages(context, chat_id, keep_ids=keep)
    await update.message.reply_text("🧹 Cleaned up setup messages. Leaving the final breakdown.")

# ----- new /stop -----
async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop the whole process, clear session, and clean chat where possible."""
    chat_id = update.effective_chat.id
    session = SESSIONS.get(chat_id)

    # Delete tracked setup messages
    if session:
        try:
            await delete_setup_messages(context, chat_id, keep_ids=[])
        except Exception as e:
            logger.debug(f"/stop cleanup failed: {e}")
        # Try delete the last breakdown if we posted one
        fid = session.get("finalized_msg_id")
        if fid:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=fid)
            except Exception as e:
                logger.debug(f"/stop final delete fail (msg {fid}): {e}")

    SESSIONS.pop(chat_id, None)
    await update.message.reply_text("🛑 Stopped. Type /start to begin again.")

# -------- main --------
def main():
    load_dotenv()
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN not found! Please set it in your .env file.")

    app: Application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(main_menu_cb, pattern="^(START_FLOW|HELP_FLOW)$")],
            CURRENCY: [CallbackQueryHandler(choose_currency_cb, pattern="^(SGD|MYR)$")],
            TOTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_total)],
            GST: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_gst)],
            SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_service)],
            NUM_PEOPLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_num_people)],
        },
        fallbacks=[],
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(mismatch_fix_cb, pattern="^(SCALE_FIX|EDIT_FIX|TOTAL_TO_SUM)$"))

    # Always-available commands after /start
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addamount", addamount))
    app.add_handler(CommandHandler("editamount", editamount))
    app.add_handler(CommandHandler("remove", remove_person))
    app.add_handler(CommandHandler("list", list_people))
    app.add_handler(CommandHandler("settotal", settotal))
    app.add_handler(CommandHandler("calculate", calculate))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))  # optional manual cleanup

    app.run_polling()

if __name__ == "__main__":
    main()
