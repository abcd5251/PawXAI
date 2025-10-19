import threading
import json
import re
import requests
import os
from typing import Optional

from dotenv import load_dotenv

from virtuals_acp.memo import ACPMemo
from virtuals_acp.client import VirtualsACP
from virtuals_acp.env import EnvSettings
from virtuals_acp.job import ACPJob
from virtuals_acp.models import ACPJobPhase, IDeliverable

load_dotenv(override=True)

# Twitter Analysis API configuration
# Use localhost by default; override via env ANALYZE_API

def _sanitize_local_url(url: str) -> str:
    return (url or "").replace("://0.0.0.0", "://127.0.0.1").replace("://0.0.0.1", "://127.0.0.1").replace("://localhost", "://127.0.0.1")

ANALYZE_API = _sanitize_local_url(os.getenv("ANALYZE_API", "http://127.0.0.1:8000/analyze-twitter-user"))
ANALYZE_API_TIMEOUT = int(os.getenv("ANALYZE_API_TIMEOUT", "30"))  # seconds

# Keyword monitor users API (for keyword jobs)
MONITOR_USERS_API_URL = _sanitize_local_url(os.getenv("MONITOR_USERS_API_URL", "http://127.0.0.1:8000/keywordMonitors/{slug}/users"))

def to_slug(s: str) -> str:
    return str(s).lower().replace(" ", "-")

def call_keyword_monitor_users(keyword: str) -> dict | None:
    slug = to_slug(keyword)
    url = MONITOR_USERS_API_URL.replace("{slug}", slug)
    try:
        resp = requests.get(url, timeout=ANALYZE_API_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e), "url": url}

def extract_username_from_job(job: ACPJob) -> str | None:
    """
    Attempts to extract username from ACPJob object, with error tolerance for multiple common field/format patterns:
      - job.service_requirement (if dict, extract its username)
      - service_requirement as text using regex to extract username
      - fallback: find first token that looks like twitter username (with/without @)
    """
    # Get service_requirement from ACPJob
    sr = getattr(job, 'service_requirement', None) or getattr(job, 'requirement', None) or ""
    
    if isinstance(sr, dict):
        # Direct fields (prioritize 'account' for ACP Virtuals schema)
        for k in ("account", "username", "user", "twitter_username"):
            if k in sr and sr[k]:
                return str(sr[k]).lstrip("@")
        sr_text = json.dumps(sr)
    else:
        sr_text = str(sr)

    # regex: account/username: value or plain @handle or bare handle (1-15 chars, letters/numbers/underscore)
    m = re.search(r'(?:account|username)\s*[:=]\s*["\']?@?([A-Za-z0-9_]{1,15})["\']?', sr_text, re.IGNORECASE)
    if m:
        return m.group(1)
    m2 = re.search(r'@([A-Za-z0-9_]{1,15})', sr_text)
    if m2:
        return m2.group(1)
    # fallback: first token that looks like handle
    m3 = re.search(r'\b([A-Za-z0-9_]{3,15})\b', sr_text)
    if m3:
        return m3.group(1)
    return None

def call_analyze_api(username: str) -> dict:
    """
    Call the Twitter analysis API, POST JSON {"username": "<username>"}
    Returns parsed JSON (if API returns non-JSON, it will be placed in content.raw_text)
    """
    payload = {"username": username}
    headers = {"Content-Type": "application/json"}
    resp = requests.post(ANALYZE_API, json=payload, headers=headers, timeout=ANALYZE_API_TIMEOUT)
    resp.raise_for_status()
    print("response :", resp.json)
    try:
        return resp.json()
    except ValueError:
        return {"raw_text": resp.text}


def seller():

    def on_new_task(job: ACPJob, memo_to_sign: Optional[ACPMemo] = None):
        print(f"[on_new_task] Received job {job.id} (phase: {job.phase})")
        if (
            job.phase == ACPJobPhase.REQUEST
            and memo_to_sign is not None
            and memo_to_sign.next_phase == ACPJobPhase.NEGOTIATION
        ):
            print(f"Accepting job request {job.id}")
            job.respond(True)
        elif (
            job.phase == ACPJobPhase.TRANSACTION
            and memo_to_sign is not None
            and memo_to_sign.next_phase == ACPJobPhase.EVALUATION
        ):
            print(f"Delivering job payload for {job.id}")
            sr = getattr(job, 'service_requirement', None) or getattr(job, 'requirement', None) or {}
            if isinstance(sr, dict) and ('keyword' in sr) and not any(k in sr for k in ("username","account","user","twitter_username")):
                keyword = sr.get('keyword')
                print(f"Detected keyword job, keyword='{keyword}'")
                try:
                    api_result = call_keyword_monitor_users(keyword)
                    analysis_text = f"Keyword Monitor for '{keyword}':\n\n{json.dumps(api_result, indent=2, ensure_ascii=False)}"
                    deliverable = IDeliverable(type="text", value=analysis_text)
                    job.deliver(deliverable)
                    print(f"Delivered keyword monitor result for '{keyword}'")
                except Exception as e:
                    print(f"Error monitoring keyword '{keyword}': {e}")
                    error_deliverable = IDeliverable(type="text", value=f"Error monitoring keyword '{keyword}': {str(e)}")
                    job.deliver(error_deliverable)
            else:
                username = extract_username_from_job(job)
                if not username:
                    print("Cannot find username in job payload")
                    error_deliverable = IDeliverable(
                        type="text", 
                        value="Error: Cannot find Twitter username in job requirements"
                    )
                    job.deliver(error_deliverable)
                    return
                print(f"Extracted username: {username}")
                try:
                    api_result = call_analyze_api(username)
                    analysis_text = f"Twitter Analysis for @{username}:\n\n{json.dumps(api_result, indent=2, ensure_ascii=False)}"
                    deliverable = IDeliverable(type="text", value=analysis_text)
                    job.deliver(deliverable)
                    print(f"Delivered Twitter analysis result for @{username}")
                except Exception as e:
                    print(f"Error analyzing Twitter user {username}: {e}")
                    error_deliverable = IDeliverable(
                        type="text", 
                        value=f"Error analyzing Twitter user @{username}: {str(e)}"
                    )
                    job.deliver(error_deliverable)
                
        elif job.phase == ACPJobPhase.COMPLETED:
            print(f"Job {job.id} completed successfully")
        elif job.phase == ACPJobPhase.REJECTED:
            print(f"Job {job.id} was rejected")

    if os.getenv("WHITELISTED_WALLET_PRIVATE_KEY") is None:
        raise Exception("WHITELISTED_WALLET_PRIVATE_KEY is not set")
    if os.getenv("BUYER_ENTITY_ID") is None:
        raise Exception("SELLER_ENTITY_ID is not set")
    if os.getenv("AGENT_SELLER_WALLET_ADDRESS") is None:
        raise Exception("SELLER_AGENT_WALLET_ADDRESS is not set")

    # Initialize the ACP client
    acp_client = VirtualsACP(
        wallet_private_key=os.getenv("WHITELISTED_WALLET_PRIVATE_KEY"),
        agent_wallet_address=os.getenv("AGENT_SELLER_WALLET_ADDRESS"),
        on_new_task=on_new_task,
        entity_id=int(os.getenv("SELLER_ENTITY_ID")),
    )

    print("Twitter Analysis Seller Agent started and waiting for jobs...")
    # Keep the script running to listen for new tasks
    threading.Event().wait()


if __name__ == "__main__":
    seller()