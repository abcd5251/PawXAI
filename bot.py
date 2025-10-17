# telegram_bot.py
import os
import logging
import re
import json
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv
import httpx
from utils.constants import LANGUAGE_TAGS, ECOSYSTEM_TAGS, USER_TYPE_TAGS

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BUTTONS = [
    ("latest trending", "latest_trending"),
    ("Analyze account", "analyze_account"),
    ("Find KOL", "find_kol"),
    ("Monitor account", "monitor_account"),
    ("News Trading", "news_trading"),
]

RESPONSES = {
    "latest_trending": "1 for latest trending",
    "analyze_account": "2 for Analyze account",
    "find_kol": "3 for Find KOL",
    "monitor_account": "4 for Monitor account",
    "news_trading": "5 for News Trading",
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[InlineKeyboardButton(text, callback_data=data)] for (text, data) in BUTTONS]
    reply_markup = InlineKeyboardMarkup(keyboard)
    addr = os.getenv("AGENT_BUYER_WALLET_ADDRESS")
    if addr:
        greeting = f"Hello! How can I help you\nYour Agent wallet address: {addr}"
    else:
        greeting = "Hello! How can I help you\nYour Agent address not configured."
    await update.message.reply_text(greeting, reply_markup=reply_markup)

async def on_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    # If Analyze account, prompt for username and set conversation flag
    if query.data == "analyze_account":
        context.user_data["awaiting_username"] = True
        await query.message.reply_text(
            "Please enter a Twitter username (e.g., vitalik, elonmusk)."
        )
        return

    # Start Find KOL flow
    if query.data == "find_kol":
        context.user_data["kol_flow_active"] = True
        context.user_data["kol_filter"] = {}
        await query.message.reply_text(
            (
                "Find KOL: Choose filters below. For tags, you can enter comma-separated values.\n"
                f"Available ecosystem tags: {', '.join(ECOSYSTEM_TAGS)}\n"
                f"Available language tags: {', '.join(LANGUAGE_TAGS)}\n"
                f"Available user type tags: {', '.join(USER_TYPE_TAGS)}"
            ),
            reply_markup=_kol_keyboard()
        )
        return

    # Handle KOL flow callbacks
    if query.data in {"kol_set_ecosystem", "kol_set_language", "kol_set_user_type"}:
        field_map = {
            "kol_set_ecosystem": ("ecosystem_tags", ECOSYSTEM_TAGS, "ecosystem"),
            "kol_set_language": ("language_tags", LANGUAGE_TAGS, "language"),
            "kol_set_user_type": ("user_type_tags", USER_TYPE_TAGS, "user type"),
        }
        field, allowed, label = field_map[query.data]
        context.user_data["awaiting_kol_field"] = field
        await query.message.reply_text(
            (
                f"Enter {label} tags as comma-separated values.\n"
                f"Allowed: {', '.join(allowed)}"
            )
        )
        return

    if query.data in {"kol_set_followers", "kol_set_friends", "kol_set_kol_followers"}:
        field_map = {
            "kol_set_followers": ("followers_count", "followers"),
            "kol_set_friends": ("friends_count", "friends"),
            "kol_set_kol_followers": ("kol_followers_count", "KOL followers"),
        }
        field, label = field_map[query.data]
        context.user_data["awaiting_kol_field"] = field
        await query.message.reply_text(
            f"Enter minimum {label} count (integer)."
        )
        return

    if query.data == "kol_view_filters":
        summary = summarize_filters(context.user_data.get("kol_filter", {}))
        await query.message.reply_text(summary, reply_markup=_kol_keyboard())
        return

    if query.data == "kol_search":
        payload = context.user_data.get("kol_filter") or {}
        if not payload:
            await query.message.reply_text("No filters set. Please add filters first.", reply_markup=_kol_keyboard())
            return

        api_url = os.getenv("FILTER_COMBINED_URL", "http://localhost:8000/filter/combined")
        timeout = float(os.getenv("ANALYZE_API_TIMEOUT", "50"))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(api_url, json=payload)
            if resp.status_code == 200:
                body = resp.json()
                num = body.get("num_KOL")
                results = body.get("results", [])

                # Sort by kolFollowersCount descending
                try:
                    sorted_results = sorted(
                        results,
                        key=lambda r: int(r.get("kolFollowersCount", 0) or 0),
                        reverse=True,
                    )
                except Exception:
                    sorted_results = results

                top_items = sorted_results[:3]

                # Build human-readable summary for top 3
                lines = [f"Matched KOLs: {num}", "Top 3:"]
                for i, item in enumerate(top_items, start=1):
                    lines.append(f"{i}. Username: {item.get('username', '')}")
                    lines.append(f"   FollowersCount: {item.get('followersCount', 0)}")
                    lines.append(f"   FollowingCount: {item.get('friendsCount', 0)}")
                    lines.append(f"   KOLFollowersCount: {item.get('kolFollowersCount', 0)}")
                    lines.append(f"   Description: {item.get('description', '')}")
                    lines.append(f"   Location: {item.get('location', '')}")
                    lines.append(f"   Website: {item.get('website', '')}")
                    lines.append(f"   Ecosystem Tags: {item.get('ecosystem_tags', '')}")
                    lines.append(f"   Language Tags: {item.get('language_tags', '')}")
                    lines.append(f"   User Type Tags: {item.get('user_type_tags', '')}")
                    lines.append(f"   MBTI: {item.get('MBTI', '')}")
                    lines.append(f"   Summary: {item.get('summary', '')}")
                    lines.append("")
                summary_text = "\n".join(lines).rstrip()
                await query.message.reply_text(summary_text)

                # Send full results as JSON file
                full_json = json.dumps(sorted_results, indent=2, ensure_ascii=False)
                buf = io.BytesIO(full_json.encode("utf-8"))
                buf.seek(0)
                await query.message.reply_document(document=buf, filename="find_kol_results.json")
                # Auto-return to main menu like analyze flow
                context.user_data.pop("kol_flow_active", None)
                context.user_data.pop("kol_filter", None)
                context.user_data.pop("awaiting_kol_field", None)
                await query.message.reply_text(
                    "Back to menu:", reply_markup=_main_keyboard()
                )
            else:
                try:
                    err = resp.json()
                    err_msg = err.get("message") or err.get("detail") or resp.text
                except Exception:
                    err_msg = resp.text
                await query.message.reply_text(f"API error ({resp.status_code}): {err_msg[:500]}")
        except httpx.HTTPError as e:
            await query.message.reply_text(f"Request failed: {str(e)}")
        return

    if query.data == "kol_back_menu":
        # Reset KOL flow state and show the main menu
        context.user_data.pop("kol_flow_active", None)
        context.user_data.pop("kol_filter", None)
        context.user_data.pop("awaiting_kol_field", None)
        await query.message.reply_text("How can I help you", reply_markup=_main_keyboard())
        return

    if query.data == "kol_cancel":
        context.user_data.pop("kol_flow_active", None)
        context.user_data.pop("kol_filter", None)
        context.user_data.pop("awaiting_kol_field", None)
        await query.message.reply_text("Cancelled. Back to menu:", reply_markup=_main_keyboard())
        return

    if query.data == "show_wallet":
        addr = os.getenv("AGENT_BUYER_WALLET_ADDRESS")
        if addr:
            await query.message.reply_text(f"Buyer wallet address: {addr}")
        else:
            await query.message.reply_text("Buyer wallet address not configured. Set AGENT_BUYER_WALLET_ADDRESS in .env.")
        return

    response_text = RESPONSES.get(query.data, "Unknown selection")
    # Sends a new message to keep the original keyboard visible
    await query.message.reply_text(response_text)

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{1,15}$")

def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, callback_data=data)] for (text, data) in BUTTONS])

def _kol_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Set Ecosystem Tags", callback_data="kol_set_ecosystem")],
        [InlineKeyboardButton("Set Language Tags", callback_data="kol_set_language")],
        [InlineKeyboardButton("Set User Type Tags", callback_data="kol_set_user_type")],
        [InlineKeyboardButton("Set Followers >", callback_data="kol_set_followers")],
        [InlineKeyboardButton("Set Friends >", callback_data="kol_set_friends")],
        [InlineKeyboardButton("Set KOL Followers >", callback_data="kol_set_kol_followers")],
        [InlineKeyboardButton("View Current Filters", callback_data="kol_view_filters")],
        [InlineKeyboardButton("Search", callback_data="kol_search")],
        [InlineKeyboardButton("Cancel", callback_data="kol_cancel")],
    ])

def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Back to menu", callback_data="kol_back_menu")]
    ])

def canonicalize_tags(input_text: str, allowed: list[str]):
    allowed_map = {t.lower(): t for t in allowed}
    inputs = [t.strip() for t in input_text.split(",") if t.strip()]
    canonical = []
    invalid = []
    for t in inputs:
        key = t.lower()
        if key in allowed_map:
            canonical.append(allowed_map[key])
        else:
            invalid.append(t)
    return canonical, invalid

def summarize_filters(f: dict) -> str:
    lines = ["Current filters:"]
    if not f:
        lines.append("(none)")
    else:
        if f.get("ecosystem_tags"):
            lines.append(f"- ecosystem_tags: {', '.join(f['ecosystem_tags'])}")
        if f.get("language_tags"):
            lines.append(f"- language_tags: {', '.join(f['language_tags'])}")
        if f.get("user_type_tags"):
            lines.append(f"- user_type_tags: {', '.join(f['user_type_tags'])}")
        for k in ("followers_count", "friends_count", "kol_followers_count"):
            if f.get(k) is not None:
                lines.append(f"- {k}: {f[k]}")
    return "\n".join(lines)

async def handle_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()

    # KOL filter input handling
    awaiting_field = context.user_data.get("awaiting_kol_field")
    if awaiting_field:
        kol_filter = context.user_data.setdefault("kol_filter", {})
        if awaiting_field in {"ecosystem_tags", "language_tags", "user_type_tags"}:
            allowed_map = {
                "ecosystem_tags": ECOSYSTEM_TAGS,
                "language_tags": LANGUAGE_TAGS,
                "user_type_tags": USER_TYPE_TAGS,
            }
            canonical, invalid = canonicalize_tags(text, allowed_map[awaiting_field])
            if invalid:
                await update.message.reply_text(
                    "Unrecognized tags: " + ", ".join(invalid)
                )
                await update.message.reply_text(
                    "Please try again with allowed tags.", reply_markup=_kol_keyboard()
                )
            else:
                kol_filter[awaiting_field] = canonical
                await update.message.reply_text(
                    summarize_filters(kol_filter), reply_markup=_kol_keyboard()
                )
        else:
            # numeric fields
            try:
                value = int(text)
                if value < 0:
                    raise ValueError("must be non-negative")
                kol_filter[awaiting_field] = value
                await update.message.reply_text(
                    summarize_filters(kol_filter), reply_markup=_kol_keyboard()
                )
            except ValueError:
                await update.message.reply_text(
                    "Please enter a valid non-negative integer.", reply_markup=_kol_keyboard()
                )
        context.user_data["awaiting_kol_field"] = None
        return

    # Analyze account username handling
    if context.user_data.get("awaiting_username"):
        raw = text
        username = raw.lstrip("@")

        if not USERNAME_PATTERN.match(username):
            await update.message.reply_text(
                "Invalid username. Please enter 1–15 letters, numbers, or underscore."
            )
            return

        api_url = os.getenv("ANALYZE_API_URL", "http://localhost:8000/analyze-twitter-user")
        timeout = float(os.getenv("ANALYZE_API_TIMEOUT", "50"))

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                payload = {"username": username}
                resp = await client.post(api_url, json=payload)

            if resp.status_code == 200:
                body = resp.json()
                data = body.get("data")
                message = body.get("message")
                if data is None:
                    await update.message.reply_text(
                        f"No analysis data returned for @{username}."
                    )
                else:
                    # Send analysis_json as formatted text (truncated) and as a file
                    text_preview = json.dumps(data, indent=2, ensure_ascii=False)
                    max_len = 4000
                    preview = text_preview if len(text_preview) <= max_len else text_preview[:max_len] + "\n... (truncated)"
                    await update.message.reply_text(
                        f"Analysis JSON for @{username}:\n{preview}"
                    )

                    buf = io.BytesIO(text_preview.encode("utf-8"))
                    buf.seek(0)
                    await update.message.reply_document(document=buf, filename=f"analysis_{username}.json")
            else:
                try:
                    err = resp.json()
                    err_msg = err.get("message") or err.get("detail") or resp.text
                except Exception:
                    err_msg = resp.text
                await update.message.reply_text(
                    f"API error ({resp.status_code}): {err_msg[:500]}"
                )
        except httpx.HTTPError as e:
            await update.message.reply_text(f"Request failed: {str(e)}")
        finally:
            # Reset conversation flag and show main keyboard again
            context.user_data["awaiting_username"] = False
            await update.message.reply_text("Back to menu:", reply_markup=_main_keyboard())

def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Please set TELEGRAM_BOT_TOKEN environment variable to your bot token.")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_button_click))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username))
    app.run_polling()

if __name__ == "__main__":
    main()