import pandas as pd
import requests
import json
from datetime import datetime, timedelta
import time
import os
import re
from dotenv import load_dotenv
from models.model import OpenAIModel
from prompts.analyze import analyze_prompt

load_dotenv()

# --- Configuration ---
CSV_FILE_PATH = './kol_list.csv'
OUTPUT_JSON_PATH = './analysis_results.json'
API_KEY = os.getenv("X-API-Key", "test")

# --- Validation Functions (from main.py) ---
def validate_twitter_username(username: str) -> bool:
    """Validate Twitter username format"""
    pattern = r'^[a-zA-Z0-9_]{1,15}$'
    return bool(re.match(pattern, username))

def validate_datetime_format(date_string: str) -> bool:
    """Validate ISO datetime format"""
    try:
        datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        return True
    except ValueError:
        return False

# --- Data Processing Functions (from main.py) ---
def extract_and_save_data(data: dict, username: str) -> str:
    """Extract user and tweet data and return as a formatted string."""
    tweets_data = data if isinstance(data, list) else data.get('data', [])
    
    if not tweets_data:
        return ""

    first_user = tweets_data[0].get('user', {})
    user_info = {
        'name': first_user.get('name'),
        'location': first_user.get('location'),
        'description': first_user.get('description'),
        'website': first_user.get('website'),
        'followersCount': first_user.get('followersCount'),
        'friendsCount': first_user.get('friendsCount'),
        'kolFollowersCount': first_user.get('kolFollowersCount')
    }

    total_text = (
        f"Name: {user_info['name']}\n"
        f"Location: {user_info['location']}\n"
        f"Description: {user_info['description']}\n"
        f"Website: {user_info['website']}\n"
        f"Followers: {user_info['followersCount']}\n"
        f"Following: {user_info['friendsCount']}\n"
        f"KOL Follower Counts: {user_info['kolFollowersCount']}\n\n"
    )

    for i, entry in enumerate(tweets_data, 1):
        tweet = entry.get('tweet', {})
        tweet_type = 'tweet'
        if tweet.get('retweetedStatusIdStr'):
            tweet_type = 'retweet'
        elif tweet.get('inReplyToStatusIdStr'):
            tweet_type = 'reply'
        elif tweet.get('quotedStatusIdStr'):
            tweet_type = 'quote_tweet'
        
        total_text += f"Tweet {i}:\n\n"
        total_text += f"Type: {tweet_type.upper()}\n"
        total_text += f"Text: {tweet.get('text', '')}\n\n"
        
    return total_text

def analyze_user_tweets(username: str, created_after: str, created_before: str) -> dict:
    """
    Fetches tweets and performs analysis for a single user.
    """
    if not validate_twitter_username(username):
        return {"error": "Invalid Twitter username format."}

    api_url = "https://foxhole.bot/api/v1/twitterUsers/stored-tweets"
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "Twitter-KOL-Analysis-Script/1.0.0"
    }
    params = {
        "screenName": username,
        "createdAfter": created_after,
        "createdBefore": created_before
    }

    try:
        response = requests.get(api_url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            total_text = extract_and_save_data(data, username)

            if not total_text:
                return {"error": f"No tweet data found for @{username} in the given range."}

            analyze_instance = OpenAIModel(system_prompt=analyze_prompt, temperature=0)
            prompt = f"INPUT:{total_text}\nOUTPUT:"
            analysis_result, _, _ = analyze_instance.generate_text(prompt)
            
            analysis_json = json.loads(analysis_result)

            tweets_data = data if isinstance(data, list) else data.get('data', [])
            if tweets_data:
                first_user = tweets_data[0].get('user', {})
                if isinstance(analysis_json, dict):
                    analysis_json['location'] = first_user.get('location')
                    analysis_json['description'] = first_user.get('description')
                    analysis_json['website'] = first_user.get('website')
                    analysis_json['followersCount'] = first_user.get('followersCount')
                    analysis_json['friendsCount'] = first_user.get('friendsCount')
                    analysis_json['kolFollowersCount'] = first_user.get('kolFollowersCount')
            
            return analysis_json

        elif response.status_code == 429:
            return {"error": "Rate limit exceeded", "retry": True}
        else:
            return {"error": f"API request failed with status {response.status_code}: {response.text[:150]}"}

    except requests.exceptions.RequestException as e:
        return {"error": f"Request error: {e}"}
    except json.JSONDecodeError:
        return {"error": "Failed to decode JSON from analysis."}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {e}"}


# --- Main Script ---
def fetch_and_save_analysis():
    """
    Reads usernames from a CSV, fetches their analysis,
    and saves the results to a JSON file, writing each result as it is processed.
    """
    try:
        df = pd.read_csv(CSV_FILE_PATH)
        usernames = df['Twitter_name'].dropna().unique().tolist()
        print(f"Found {len(usernames)} unique usernames to process.")
    except FileNotFoundError:
        print(f"Error: The file {CSV_FILE_PATH} was not found.")
        return
    except KeyError:
        print(f"Error: 'Twitter_name' column not found in {CSV_FILE_PATH}.")
        return

    before_date = datetime.fromisoformat("2025-10-08T23:59:59Z".replace('Z', '+00:00'))
    after_date = before_date - timedelta(days=60)
    
    created_before_str = before_date.strftime('%Y-%m-%dT%H:%M:%SZ')
    created_after_str = after_date.strftime('%Y-%m-%dT%H:%M:%SZ')

    for i, username in enumerate(usernames):
        if i < 107:
            continue
        print(f"Processing {i+1}/{len(usernames)}: @{username}...")
        
        analysis_data = analyze_user_tweets(username, created_after_str, created_before_str)
        
        if analysis_data.get("retry"):
            print("  -> Rate limit exceeded. Waiting for 60 seconds before retrying...")
            time.sleep(60)
            analysis_data = analyze_user_tweets(username, created_after_str, created_before_str)

        if "error" not in analysis_data:
            analysis_data['username'] = username
            try:
                # Append each result to the file as a new line (JSON Lines format)
                with open(OUTPUT_JSON_PATH, 'a', encoding='utf-8') as f:
                    json.dump(analysis_data, f, ensure_ascii=False)
                    f.write('\n')
                print(f"  -> Success for @{username}")
            except IOError as e:
                print(f"  -> Error writing to output file for @{username}: {e}")
        else:
            print(f"  -> Failed for @{username}: {analysis_data['error']}")

    print(f"\nProcessing complete. Results saved to {OUTPUT_JSON_PATH}")

if __name__ == "__main__":
    print("Starting batch analysis...")
    fetch_and_save_analysis()