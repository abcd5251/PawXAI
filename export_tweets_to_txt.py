import os
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import List

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("FOXHOLE_API_KEY", "test")
API_URL = "https://foxhole.bot/api/v1/twitterUsers/stored-tweets"
OUTPUT_TXT_PATH = "./tweets_output.txt"
SMART_KOL_JSON_PATH = "./smart_kol.json"


def validate_twitter_username(username: str) -> bool:
    import re
    pattern = r'^[a-zA-Z0-9_]{1,15}$'
    return bool(re.match(pattern, username))


def load_kol_list(path: str) -> List[str]:
    p = Path(path)
    if not p.exists():
        print(f"Warning: {path} not found.")
        return []
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    # Extract values only (per user's snippet)
    values = list(data.values())
    kol_list: List[str] = []
    for v in values:
        if isinstance(v, list):
            kol_list.extend([str(x).strip() for x in v])
        else:
            kol_list.append(str(v).strip())
    # Deduplicate while preserving order
    seen = set()
    unique: List[str] = []
    for name in kol_list:
        if name and name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


def fetch_user_tweets(username: str, created_after: str, created_before: str):
    if not validate_twitter_username(username):
        return {"error": f"Invalid Twitter username: {username}"}

    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "Twitter-KOL-Export/1.0.0",
    }
    params = {
        "screenName": username,
        "createdAfter": created_after,
        "createdBefore": created_before,
    }

    try:
        resp = requests.get(API_URL, headers=headers, params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            tweets_data = data if isinstance(data, list) else data.get('data', [])
            return {"data": tweets_data}
        elif resp.status_code == 429:
            return {"error": "Rate limit", "retry": True}
        else:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except requests.exceptions.RequestException as e:
        return {"error": f"Request error: {e}"}


def format_entry(entry: dict, fallback_screen_name: str):
    user = entry.get('user', {}) or {}
    tweet = entry.get('tweet', {}) or {}

    screen_name = (
        user.get('screenName') or
        user.get('screen_name') or
        fallback_screen_name
    )
    display_name = user.get('name') or screen_name or "Unknown"

    tweet_id = (
        tweet.get('idStr') or
        tweet.get('id') or
        tweet.get('statusIdStr') or
        tweet.get('tweetId')
    )
    url = f"https://twitter.com/{screen_name}/status/{tweet_id}" if (screen_name and tweet_id) else ""

    text = tweet.get('text', '') or ''
    text_one_line = " ".join(text.split())

    return display_name, text_one_line, url


def export_tweets_to_txt(usernames: List[str], created_after: str, created_before: str, output_path: str):
    total_written = 0
    # Clear output file at start
    with open(output_path, 'w', encoding='utf-8'):
        pass

    for i, username in enumerate(usernames, 1):
        print(f"Processing {i}/{len(usernames)}: @{username}...")
        res = fetch_user_tweets(username, created_after, created_before)
        if res.get("retry"):
            print("  -> Rate limit. Sleeping 60s then retrying...")
            time.sleep(60)
            res = fetch_user_tweets(username, created_after, created_before)

        if "error" in res:
            print(f"  -> Failed for @{username}: {res['error']}")
            continue

        tweets_data = res.get("data", [])
        if not tweets_data:
            print(f"  -> No tweets found for @{username}.")
            continue

        for idx, entry in enumerate(tweets_data, 1):
            poster, text, url = format_entry(entry, username)
            with open(output_path, 'a', encoding='utf-8') as f:
                f.write(f"===== @{username} =====\n")
                f.write(f"Poster: {poster}\n")
                f.write(f"Text: {text}\n")
                f.write(f"URL: {url}\n")
                f.write("\n")
            total_written += 1

        print(f"  -> Wrote {len(tweets_data)} tweets for @{username}.")

    print(f"\nDone. Wrote {total_written} tweets to {output_path}")


def main():
    
    # Data Range 1 hour, For example
    now_utc = datetime.utcnow()
    after_date = now_utc - timedelta(days=2)
    before_date = now_utc - timedelta(days=1)
    created_after_str = after_date.strftime('%Y-%m-%dT%H:%M:%SZ')
    created_before_str = before_date.strftime('%Y-%m-%dT%H:%M:%SZ')

    usernames = load_kol_list(SMART_KOL_JSON_PATH)
    if not usernames:
        print("No usernames loaded from smart_kol.json.")
        return

    print(f"Found {len(usernames)} usernames to process.")
    export_tweets_to_txt(usernames, created_after_str, created_before_str, OUTPUT_TXT_PATH)


if __name__ == "__main__":
    print("Starting export...")
    main()