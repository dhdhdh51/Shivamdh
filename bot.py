"""Telegram interface for the bounded game-server UDP load simulator."""

from __future__ import annotations

import asyncio
import html
import logging
import os
from dataclasses import dataclass
from typing import Final

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from load_engine import MAX_DURATION_SECONDS, MAX_PPS, LoadSnapshot, UdpLoadTest
from target_verification import (
    DEFAULT_VERIFIER_PORT,
    load_verified_targets,
    save_verified_target,
    verify_target,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
LOGGER = logging.getLogger(__name__)

TARGET, PORT, PPS, DURATION, ADD_TARGET = range(5)
ACTIVE_TEST_KEY: Final = "active_test"
ACTIVE_TASK_KEY: Final = "active_task"
OWNER_KEY: Final = "test_owner"


@dataclass
class DraftTest:
    target: str = ""
    port: int = 0
    pps: int = 0
    duration: int = 0


def parse_csv_env(name: str) -> set[str]:
    return {item.strip() for item in os.getenv(name, "").split(",") if item.strip()}


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("▶️ Start UDP test", callback_data="new_udp")],
            [
                InlineKeyboardButton("➕ Add server", callback_data="add_target"),
                InlineKeyboardButton("📋 Servers", callback_data="list_targets"),
            ],
            [
                InlineKeyboardButton("📊 Status", callback_data="status"),
                InlineKeyboardButton("⏹ Stop", callback_data="stop"),
            ],
        ]
    )


def confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ Run test", callback_data="confirm_run"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_draft"),
        ]]
    )


def authorized(update: Update) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    allowed = parse_csv_env("ALLOWED_CHAT_IDS")
    return bool(allowed and ((user and str(user.id) in allowed) or (chat and str(chat.id) in allowed)))


async def reject_unauthorized(update: Update) -> None:
    message = update.effective_message
    if message:
        await message.reply_text("⛔ This bot is private. Your Telegram ID is not authorized.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await reject_unauthorized(update)
        return
    await update.effective_message.reply_text(
        "🎮 <b>Game Server Load Bot</b>\n\n"
        "Runs a bounded UDP simulation against a server verified by your private agent.",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


async def begin_udp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not authorized(update):
        await reject_unauthorized(update)
        return -1
    if context.application.bot_data.get(ACTIVE_TEST_KEY):
        await query.edit_message_text("A test is already running. Stop it first.", reply_markup=main_keyboard())
        return -1
    context.user_data["draft"] = DraftTest()
    context.user_data["step"] = TARGET
    await query.edit_message_text("Send your allowlisted game-server IP or hostname.")
    return TARGET


async def receive_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    target = update.effective_message.text.strip().lower()
    allowlist = {item.lower() for item in parse_csv_env("TARGET_ALLOWLIST")}
    allowlist.update(load_verified_targets())
    if target not in allowlist:
        await update.effective_message.reply_text(
            "Server is not authorized. Tap Add server first and complete proof-of-control verification."
        )
        return TARGET
    context.user_data["draft"].target = target
    context.user_data["step"] = PORT
    await update.effective_message.reply_text("Send the UDP port (1-65535).")
    return PORT


async def receive_port(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        value = int(update.effective_message.text)
        if not 1 <= value <= 65535:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text("Enter a whole-number port from 1 to 65535.")
        return PORT
    context.user_data["draft"].port = value
    context.user_data["step"] = PPS
    await update.effective_message.reply_text(f"Send packets/second (1-{MAX_PPS}).")
    return PPS


async def receive_pps(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        value = int(update.effective_message.text)
        if not 1 <= value <= MAX_PPS:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text(f"Enter a whole number from 1 to {MAX_PPS}.")
        return PPS
    context.user_data["draft"].pps = value
    context.user_data["step"] = DURATION
    await update.effective_message.reply_text(
        f"Send duration in seconds (1-{MAX_DURATION_SECONDS})."
    )
    return DURATION


async def receive_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        value = int(update.effective_message.text)
        if not 1 <= value <= MAX_DURATION_SECONDS:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text(
            f"Enter a whole number from 1 to {MAX_DURATION_SECONDS}."
        )
        return DURATION

    draft: DraftTest = context.user_data["draft"]
    draft.duration = value
    context.user_data.pop("step", None)
    await update.effective_message.reply_text(
        "<b>Review test</b>\n"
        f"Target: <code>{html.escape(draft.target)}</code>\n"
        f"Port: <code>{draft.port}</code>\n"
        f"Rate: <code>{draft.pps} PPS</code>\n"
        f"Duration: <code>{draft.duration}s</code>",
        parse_mode="HTML",
        reply_markup=confirmation_keyboard(),
    )
    return -1


async def confirm_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not authorized(update):
        await reject_unauthorized(update)
        return -1
    if context.application.bot_data.get(ACTIVE_TEST_KEY):
        await query.edit_message_text("A test is already running.", reply_markup=main_keyboard())
        return -1

    draft: DraftTest = context.user_data.pop("draft")
    test = UdpLoadTest(draft.target, draft.port, draft.pps, draft.duration)
    context.application.bot_data[ACTIVE_TEST_KEY] = test
    context.application.bot_data[OWNER_KEY] = update.effective_chat.id
    task = asyncio.create_task(run_test(context.application, test, update.effective_chat.id))
    context.application.bot_data[ACTIVE_TASK_KEY] = task
    await query.edit_message_text("✅ Test started.", reply_markup=main_keyboard())
    return -1


async def run_test(application: Application, test: UdpLoadTest, chat_id: int) -> None:
    try:
        result = await asyncio.to_thread(test.run)
        label = "stopped" if result.remaining_seconds > 0 else "completed"
        await application.bot.send_message(
            chat_id,
            format_snapshot(result, f"Test {label}"),
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )
    except Exception as exc:  # Resolution/socket failures must reach the operator.
        LOGGER.exception("Load test failed")
        await application.bot.send_message(
            chat_id, f"❌ Test failed: <code>{html.escape(str(exc))}</code>", parse_mode="HTML"
        )
    finally:
        application.bot_data.pop(ACTIVE_TEST_KEY, None)
        application.bot_data.pop(ACTIVE_TASK_KEY, None)
        application.bot_data.pop(OWNER_KEY, None)


def format_snapshot(snapshot: LoadSnapshot, heading: str = "Current status") -> str:
    duration = snapshot.elapsed_seconds + snapshot.remaining_seconds
    progress = min(100, int((snapshot.elapsed_seconds / duration) * 100)) if duration else 0
    filled = progress // 10
    bar = "█" * filled + "░" * (10 - filled)
    state = "Running" if snapshot.running else "Finished"
    return (
        f"📊 <b>{heading}</b>\n"
        f"State: {state}\n"
        f"Progress: <code>{bar}</code> {progress}%\n"
        f"Elapsed: {snapshot.elapsed_seconds:.1f}s\n"
        f"Remaining: {snapshot.remaining_seconds:.1f}s\n"
        f"Packets sent: {snapshot.packets_sent}\n"
        f"Actual rate: {snapshot.actual_pps:.1f} PPS\n"
        f"Send errors: {snapshot.send_errors}"
    )


async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await reject_unauthorized(update)
        return
    test = context.application.bot_data.get(ACTIVE_TEST_KEY)
    text = format_snapshot(test.snapshot()) if test else "No test is running."
    message = update.effective_message
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=main_keyboard())
    else:
        await message.reply_text(text, parse_mode="HTML", reply_markup=main_keyboard())


async def stop_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await reject_unauthorized(update)
        return
    if update.callback_query:
        await update.callback_query.answer()
    test = context.application.bot_data.get(ACTIVE_TEST_KEY)
    text = "No test is running."
    if test:
        test.stop()
        text = "⏹ Stop requested. The final result will arrive shortly."
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=main_keyboard())
    else:
        await update.effective_message.reply_text(text, reply_markup=main_keyboard())


async def cancel_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not authorized(update):
        await reject_unauthorized(update)
        return -1
    context.user_data.pop("draft", None)
    context.user_data.pop("step", None)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Cancelled.", reply_markup=main_keyboard())
    else:
        await update.effective_message.reply_text("Cancelled.", reply_markup=main_keyboard())
    return -1


async def begin_add_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not authorized(update):
        await reject_unauthorized(update)
        return -1
    context.user_data.pop("draft", None)
    context.user_data["step"] = ADD_TARGET
    await query.edit_message_text(
        "Send the IP or hostname of a server running verifier_agent.py. "
        "The bot will authorize it only after proof-of-control succeeds."
    )
    return ADD_TARGET


async def receive_add_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    target = update.effective_message.text.strip().lower()
    if not target or len(target) > 253:
        await update.effective_message.reply_text("Enter a valid IP address or hostname.")
        return ADD_TARGET

    await update.effective_message.reply_text("🔐 Checking proof of control…")
    secret = os.environ["VERIFICATION_SECRET"]
    port = int(os.getenv("VERIFIER_PORT", str(DEFAULT_VERIFIER_PORT)))
    try:
        verified = await asyncio.to_thread(verify_target, target, secret, port)
    except (OSError, ValueError):
        verified = False

    if not verified:
        await update.effective_message.reply_text(
            "❌ Verification failed. Start verifier_agent.py on that server and allow "
            f"UDP {port} only from this bot server's public IP.",
            reply_markup=main_keyboard(),
        )
        return ADD_TARGET

    save_verified_target(target)
    context.user_data.pop("step", None)
    await update.effective_message.reply_text(
        f"✅ <code>{html.escape(target)}</code> is now authorized.",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )
    return -1


async def list_targets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await reject_unauthorized(update)
        return
    if update.callback_query:
        await update.callback_query.answer()
    targets = {item.lower() for item in parse_csv_env("TARGET_ALLOWLIST")}
    targets.update(load_verified_targets())
    text = "<b>Authorized servers</b>\n" + (
        "\n".join(f"• <code>{html.escape(item)}</code>" for item in sorted(targets))
        if targets
        else "None yet. Tap Add server."
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=main_keyboard()
        )
    else:
        await update.effective_message.reply_text(
            text, parse_mode="HTML", reply_markup=main_keyboard()
        )


async def route_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route form replies using per-user state without blocking other chats."""
    if not authorized(update):
        await reject_unauthorized(update)
        return
    handlers = {
        TARGET: receive_target,
        PORT: receive_port,
        PPS: receive_pps,
        DURATION: receive_duration,
        ADD_TARGET: receive_add_target,
    }
    handler = handlers.get(context.user_data.get("step"))
    if handler:
        await handler(update, context)
    else:
        await update.effective_message.reply_text(
            "Tap Start UDP test to begin.", reply_markup=main_keyboard()
        )


def build_application(token: str) -> Application:
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", show_status))
    application.add_handler(CommandHandler("stop", stop_test))
    application.add_handler(CommandHandler("targets", list_targets))
    application.add_handler(CommandHandler("cancel", cancel_draft))
    application.add_handler(CallbackQueryHandler(begin_udp, pattern="^new_udp$"))
    application.add_handler(CallbackQueryHandler(begin_add_target, pattern="^add_target$"))
    application.add_handler(CallbackQueryHandler(list_targets, pattern="^list_targets$"))
    application.add_handler(CallbackQueryHandler(confirm_run, pattern="^confirm_run$"))
    application.add_handler(CallbackQueryHandler(cancel_draft, pattern="^cancel_draft$"))
    application.add_handler(CallbackQueryHandler(show_status, pattern="^status$"))
    application.add_handler(CallbackQueryHandler(stop_test, pattern="^stop$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_text))
    return application


def main() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    allowed_ids = parse_csv_env("ALLOWED_CHAT_IDS")
    verification_secret = os.getenv("VERIFICATION_SECRET", "").strip()
    verifier_port = os.getenv("VERIFIER_PORT", str(DEFAULT_VERIFIER_PORT))
    if not token or token == "replace-me":
        raise SystemExit("TELEGRAM_BOT_TOKEN is missing. Run setup.sh and edit .env.")
    if not allowed_ids or not all(item.lstrip("-").isdigit() for item in allowed_ids):
        raise SystemExit("ALLOWED_CHAT_IDS must contain numeric Telegram IDs.")
    if len(verification_secret) < 32 or verification_secret == "replace-with-a-long-random-secret":
        raise SystemExit("VERIFICATION_SECRET must be a random value of at least 32 characters.")
    try:
        if not 1 <= int(verifier_port) <= 65535:
            raise ValueError
    except ValueError:
        raise SystemExit("VERIFIER_PORT must be between 1 and 65535.") from None
    LOGGER.info("Starting private Telegram bot")
    build_application(token).run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
