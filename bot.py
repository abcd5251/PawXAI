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
from models.model import OpenAIModel
from prompts.qa import qa_prompt
from prompts.trend import trend_prompt

load_dotenv()

TWEETS_OUTPUT_FILE = "./data/tweets_output.txt"
try:
    with open(TWEETS_OUTPUT_FILE, "r", encoding="utf-8") as f:
        content = f.read()
except Exception:
    content = ""

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BUTTONS = [
    ("latest trending", "latest_trending"),
    ("Analyze account", "analyze_account"),
    ("Find KOL", "find_kol"),
    ("Monitor account", "monitor_account"),
    ("Trending Coins", "trending_coins"),
    ("Analyze Address", "analyze_address"),
]

RESPONSES = {
    "latest_trending": "1 for latest trending",
    "analyze_account": "2 for Analyze account",
    "find_kol": "3 for Find KOL",
    "monitor_account": "4 for Monitor account",
    "trending_coins": "5 for Trending Coins",
    "analyze_address": "6 for Analyze Address",
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

    # Analyze Address flow: prompt for address then chain ID
    if query.data == "analyze_address":
        # Reset state for a clean flow
        context.user_data["awaiting_address"] = True
        context.user_data["awaiting_chain_id"] = False
        context.user_data.pop("address_to_analyze", None)
        await query.message.reply_text("Please enter the address (e.g., 0x...).")
        return

    # Monitor account flow: ask for keyword/slug
    if query.data == "monitor_account":
        context.user_data["awaiting_monitor_keyword"] = True
        await query.message.reply_text(
            "Please input a keyword to find users who mentioned it."
        )
        return

    # Start Find KOL flow
    if query.data == "find_kol":
        context.user_data["kol_flow_active"] = True
        context.user_data["kol_filter"] = {}
        await query.message.reply_text(
            (
                "Find KOL: Choose filters below. For tags, you can enter comma-separated values.\n"
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

        api_url = os.getenv("FILTER_COMBINED_URL", "http://localhost:8010/filter/combined")
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
                    lines.append(f"   MBTI: {item.get('MBTI', '')}")
                    lines.append(f"   Summary: {item.get('summary', '')}")
                    lines.append("")
                summary_text = "\n".join(lines).rstrip()
                await query.message.reply_text(summary_text)

                # Prepare JSON text
                full_json = json.dumps(sorted_results, indent=2, ensure_ascii=False)
                # Try to upload JSON and share a link for smoother viewing
                upload_link = await _upload_json_and_get_link(full_json, "find_kol_results.json")
                if upload_link:
                    link_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Open JSON", url=upload_link)]])
                    await query.message.reply_text(
                        f"Shareable JSON link:\n{upload_link}", reply_markup=link_keyboard
                    )
                # Also send the JSON file as a document
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

    if query.data == "trending_coins":
        # Run trending analysis immediately without extra input
        try:
            trending_instance = OpenAIModel(system_prompt=trend_prompt, temperature=0)
            prompt = f"trending_tweets:{content}OUTPUT:"
            result, _, _ = trending_instance.generate_string_text(prompt)
        except Exception as e:
            result = f"Model invocation error: {str(e)}"
        # Use safe chunked sender to avoid Telegram 4096-char limit
        await _send_long_text(update, str(result))
        uniswap_url = "https://app.uniswap.org/swap?chain=base&inputCurrency=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913&outputCurrency=0x1111111111166b7fe7bd91427724b487980afc69&lng=en-US"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Open Uniswap (Base) Swap", url=uniswap_url)]])
        await query.message.reply_text("Directly Trading link：", reply_markup=kb)
        await query.message.reply_text("Back to menu:", reply_markup=_main_keyboard())
        return

    if query.data == "latest_trending":
        file_path = os.getenv("LATEST_NEWS_FILE", "./data/latest_news.txt")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                news = f.read().strip()
            if not news:
                await query.message.reply_text("(latest news file is empty)")
            else:
                max_len = 4000
                for i in range(0, len(news), max_len):
                    await query.message.reply_text(news[i:i+max_len])
            await query.message.reply_text("Back to menu:", reply_markup=_main_keyboard())
        except FileNotFoundError:
            await query.message.reply_text("File not found: ./data/latest_news.txt")
            await query.message.reply_text("Back to menu:", reply_markup=_main_keyboard())
        except Exception as e:
            await query.message.reply_text(f"Failed to read latest news: {str(e)}")
            await query.message.reply_text("Back to menu:", reply_markup=_main_keyboard())
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

# Upload JSON to a paste service and return a shareable link
# Tries multiple services for robustness: 0x0.st, paste.rs
async def _upload_json_and_get_link(json_text: str, filename: str) -> str | None:
    # Configure candidates via env: UPLOAD_JSON_URLS="https://0x0.st,https://paste.rs"
    urls_env = os.getenv("UPLOAD_JSON_URLS")
    candidates = [u.strip() for u in urls_env.split(",") if u.strip()] if urls_env else []
    primary = os.getenv("UPLOAD_JSON_URL", "https://0x0.st")
    if primary and primary not in candidates:
        candidates.insert(0, primary)
    # Ensure common fallbacks
    if "https://0x0.st" not in candidates:
        candidates.append("https://0x0.st")
    if "https://paste.rs" not in candidates:
        candidates.append("https://paste.rs")

    timeout = float(os.getenv("UPLOAD_JSON_TIMEOUT", os.getenv("ANALYZE_API_TIMEOUT", "50")))
    for url in candidates:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if "0x0.st" in url:
                    # 0x0.st expects multipart form with key 'file'
                    resp = await client.post(url, files={
                        "file": (filename, json_text, "application/json")
                    })
                    if resp.status_code == 200:
                        link = resp.text.strip()
                        if link.startswith("http"):
                            return link
                elif "paste.rs" in url:
                    # paste.rs accepts plain text body
                    resp = await client.post(url, content=json_text.encode("utf-8"), headers={
                        "Content-Type": "text/plain; charset=utf-8"
                    })
                    if resp.status_code in (200, 201):
                        link = resp.text.strip()
                        if link.startswith("http"):
                            return link
                else:
                    # Generic: attempt multipart upload
                    resp = await client.post(url, files={
                        "file": (filename, json_text, "application/json")
                    })
                    if resp.status_code in (200, 201):
                        link = resp.text.strip()
                        if link.startswith("http"):
                            return link
        except httpx.HTTPError:
            # Try next candidate
            continue
    return None

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
    # Build a readable summary of current KOL filters
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

    # Analyze Address: capture address first, then chain ID, then call /tokens
    if context.user_data.get("awaiting_address"):
        address = text.strip()
        # Basic address format check; continue even if invalid to let API decide
        if not re.match(r"^0x[a-fA-F0-9]{40}$", address):
            await update.message.reply_text("Address format looks invalid; continuing anyway.")
        context.user_data["address_to_analyze"] = address
        context.user_data["awaiting_address"] = False
        context.user_data["awaiting_chain_id"] = True
        await update.message.reply_text("Please enter the chain ID (e.g., 8453 for Base).")
        return

    if context.user_data.get("awaiting_chain_id"):
        chain_id = text.strip()
        address = context.user_data.get("address_to_analyze")
        context.user_data["awaiting_chain_id"] = False
        # Call the FastAPI /tokens endpoint in balance_api.py
        # Configure URL via env BALANCE_API_TOKENS_URL, default http://127.0.0.1:8001/tokens
        api_url = os.getenv("BALANCE_API_TOKENS_URL", "http://127.0.0.1:5050/tokens")
        timeout = float(os.getenv("ANALYZE_API_TIMEOUT", "50"))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(api_url, json={"chain_id": chain_id, "address": address})
            if resp.status_code == 200:
                # /tokens returns PlainTextResponse; stream text result back
                await _send_long_text(update, resp.text)
            else:
                # Try to show structured error if present
                try:
                    err = resp.json()
                    err_msg = err.get("detail") or err.get("message") or resp.text
                except Exception:
                    err_msg = resp.text
                await update.message.reply_text(f"API error ({resp.status_code}): {err_msg[:500]}")
        except httpx.HTTPError as e:
            await update.message.reply_text(f"Request failed: {str(e)}")
        finally:
            # Reset flow state and return to main menu
            context.user_data.pop("address_to_analyze", None)
            context.user_data["awaiting_address"] = False
            context.user_data["awaiting_chain_id"] = False
            await update.message.reply_text("Back to menu:", reply_markup=_main_keyboard())
        return

    # News Trading coin input
    if context.user_data.get("awaiting_news_coin"):
        risk_or_coin = text.strip()

        if risk_or_coin.lower() == "high risk":
            file_path = os.getenv("TWEETS_OUTPUT_FILE", "./data/tweets_output.txt")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    tweets_content = f.read().strip()
            except FileNotFoundError:
                await update.message.reply_text(f"File not found: {file_path}")
                context.user_data["awaiting_news_coin"] = False
                await update.message.reply_text("Back to menu:", reply_markup=_main_keyboard())
                return
            except Exception as e:
                await update.message.reply_text(f"Failed to read tweets_output.txt: {str(e)}")
                context.user_data["awaiting_news_coin"] = False
                await update.message.reply_text("Back to menu:", reply_markup=_main_keyboard())
                return

            trending_instance = OpenAIModel(system_prompt=trend_prompt, temperature=0)
            prompt = f"trending_tweets:{tweets_content}OUTPUT:"
            try:
                result, _, _ = trending_instance.generate_string_text(prompt)
            except Exception as e:
                result = f"Model invocation error: {str(e)}"

            await _send_long_text(update, str(result))
            context.user_data["awaiting_news_coin"] = False
            await update.message.reply_text("Back to menu:", reply_markup=_main_keyboard())
            return

        coin = risk_or_coin.upper()
        mapping = {"BTC": "1", "ETH": "2", "VIRTUALS": "3"}
        if coin in mapping:
            await update.message.reply_text(mapping[coin])
        else:
            await update.message.reply_text("Unsupported input. Enter 'high risk', or BTC/ETH/Virtuals.")
        context.user_data["awaiting_news_coin"] = False
        await update.message.reply_text("Back to menu:", reply_markup=_main_keyboard())
        return

    # Monitor keyword handling
    if context.user_data.get("awaiting_monitor_keyword"):
        slug = text.strip()
        api_url_tpl = os.getenv(
            "MONITOR_USERS_API_URL",
            "http://localhost:8010/keywordMonitors/{slug}/users",
        )
        api_url = api_url_tpl.replace("{slug}", slug)
        timeout = float(os.getenv("ANALYZE_API_TIMEOUT", "50"))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(api_url)
            if resp.status_code == 200:
                body = resp.json()
                # Extract raw list and compute total count
                raw_list = None
                if isinstance(body, list):
                    raw_list = body
                elif isinstance(body, dict):
                    for key in ("users", "data", "results"):
                        v = body.get(key)
                        if isinstance(v, list):
                            raw_list = v
                            break
                total_count = len(raw_list) if isinstance(raw_list, list) else 0
                # Build concise summary
                lines = [f"Total: {total_count} — Number of KOL talk about this keyword recently"]
                if isinstance(raw_list, list) and raw_list:
                    top_lines = []
                    for u in raw_list[:10]:
                        uname = (
                            (u.get("screenName") if isinstance(u, dict) else None)
                            or (u.get("username") if isinstance(u, dict) else None)
                            or (u.get("name") if isinstance(u, dict) else None)
                            or str(u)
                        )
                        top_lines.append(f"- {uname}")
                    if top_lines:
                        lines.append("Top matched users:")
                        lines.extend(top_lines)
                await update.message.reply_text("\n".join(lines))
                # Prepare JSON text (count based on raw list)
                json_to_send = {
                    "keyword": slug,
                    "total": total_count,
                    "raw": raw_list if isinstance(raw_list, list) else [],
                }
                text_preview = json.dumps(json_to_send, indent=2, ensure_ascii=False)

                # Try to upload JSON and share a link for smoother viewing
                file_name = f"monitor_users_{slug}.json"
                upload_link = await _upload_json_and_get_link(text_preview, file_name)
                if upload_link:
                    link_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Open JSON", url=upload_link)]])
                    await update.message.reply_text(
                        f"Shareable JSON link:\n{upload_link}", reply_markup=link_keyboard
                    )

                # Also send the JSON file as a document
                buf = io.BytesIO(text_preview.encode("utf-8"))
                buf.seek(0)
                await update.message.reply_document(document=buf, filename=file_name)
            else:
                try:
                    err = resp.json()
                    err_msg = err.get("message") or err.get("detail") or resp.text
                except Exception:
                    err_msg = resp.text
                await update.message.reply_text(f"API error ({resp.status_code}): {err_msg[:500]}")
        except httpx.HTTPError as e:
            await update.message.reply_text(f"Request failed: {str(e)}")
        finally:
            context.user_data["awaiting_monitor_keyword"] = False
            await update.message.reply_text("Back to menu:", reply_markup=_main_keyboard())
        return

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

        api_url = os.getenv("ANALYZE_API_URL", "http://localhost:8010/analyze-twitter-user")
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
                    # Send shareable link first, then file, then truncated preview
                    text_preview = json.dumps(data, indent=2, ensure_ascii=False)
                    file_name = f"analysis_{username}.json"
                    upload_link = await _upload_json_and_get_link(text_preview, file_name)
                    if upload_link:
                        link_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Open JSON", url=upload_link)]])
                        await update.message.reply_text(
                            f"Shareable JSON link:\n{upload_link}", reply_markup=link_keyboard
                        )
                    # Send the JSON file as a document
                    buf = io.BytesIO(text_preview.encode("utf-8"))
                    buf.seek(0)
                    await update.message.reply_document(document=buf, filename=file_name)
                    # Finally show truncated preview
                    max_len = 4000
                    preview = text_preview if len(text_preview) <= max_len else text_preview[:max_len] + "\n... (truncated)"
                    await update.message.reply_text(
                        f"Analysis JSON for @{username}:\n{preview}"
                    )
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
        return

    # Free-text QA fallback (no buttons pressed / not in a flow)
    try:
        qa_instance = OpenAIModel(system_prompt=qa_prompt, temperature=0)
        total_text = text
        prompt = f"trending_tweets:{content}\nquestion:{total_text}\nOUTPUT:"
        analysis_result, input_tokens_length, output_tokens_length = qa_instance.generate_string_text(prompt)
        # Use chunked sender to avoid hitting 4096-char limit
        await _send_long_text(update, str(analysis_result))
        await update.message.reply_text("Back to menu:", reply_markup=_back_keyboard())
    except Exception as e:
        await update.message.reply_text(f"LLM error: {str(e)}", reply_markup=_back_keyboard())

async def _send_long_text(update: Update, text: str, parse_mode=None, reply_markup=None):
    MAX_LEN = 4096
    if not text:
        return
    # Prefer splitting by newline to preserve formatting
    chunks = []
    buf = ""
    for line in text.split("\n"):
        piece = line + "\n"
        if len(buf) + len(piece) <= MAX_LEN:
            buf += piece
        else:
            if buf:
                chunks.append(buf)
                buf = ""
            # Hard split very long lines
            while len(piece) > MAX_LEN:
                chunks.append(piece[:MAX_LEN])
                piece = piece[MAX_LEN:]
            buf = piece
    if buf:
        chunks.append(buf)
    # Determine correct message context; support both message and callback_query
    target_msg = getattr(update, "message", None)
    if target_msg is None and getattr(update, "callback_query", None):
        target_msg = update.callback_query.message
    if target_msg is None:
        return
    for i, c in enumerate(chunks):
        if reply_markup and i == 0:
            # Attach markup on the first chunk only
            await target_msg.reply_text(c, parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            await target_msg.reply_text(c, parse_mode=parse_mode)

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
    
    
    
    
