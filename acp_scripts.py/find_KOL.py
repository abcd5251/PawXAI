import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import os
import json
import requests
from dotenv import load_dotenv

from virtuals_acp.memo import ACPMemo
from virtuals_acp.client import VirtualsACP
from virtuals_acp.job import ACPJob
from virtuals_acp.models import (
    ACPAgentSort,
    ACPJobPhase,
    ACPGraduationStatus,
    ACPOnlineStatus,
)
from virtuals_acp.exceptions import ACPError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("BuyerAgent2")

load_dotenv()


def _prompt_required_tags_input(prompt: str) -> List[str]:
    while True:
        s = input(prompt).strip()
        if not s:
            logger.warning("This field is required. Please enter at least one tag.")
            continue
        tags = [t.strip() for t in s.split(",") if t.strip()]
        if tags:
            return tags
        logger.warning("No valid tags parsed. Please try again.")


def _prompt_required_int_input(prompt: str) -> int:
    while True:
        s = input(prompt).strip()
        try:
            return int(s)
        except ValueError:
            logger.warning("Please enter a valid integer (required).")


def build_combined_filter_payload() -> Dict[str, Any]:
    logger.info("Enter filters (all fields are REQUIRED by ACP offering schema)")
    ecosystem_tags = _prompt_required_tags_input("ecosystem_tags (comma-separated, required): ")
    language_tags = _prompt_required_tags_input("language_tags (comma-separated, required): ")
    user_type_tags = _prompt_required_tags_input("user_type_tags (comma-separated, required): ")
    followers_count = _prompt_required_int_input("followers_count (integer, required): ")
    friends_count = _prompt_required_int_input("friends_count (integer, required): ")
    kol_followers_count = _prompt_required_int_input("kol_followers_count (integer, required): ")

    payload: Dict[str, Any] = {
        "ecosystem_tags": ecosystem_tags,
        "language_tags": language_tags,
        "user_type_tags": user_type_tags,
        "followers_count": followers_count,
        "friends_count": friends_count,
        "kol_followers_count": kol_followers_count,
    }
    return payload


def call_filter_combined_api(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    url = os.getenv("KOL_API_URL", "http://127.0.0.1:8000/filter/combined")
    try:
        logger.info(f"POST {url} with payload: {json.dumps(payload)}")
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            logger.info(f"API success: num_KOL={data.get('num_KOL')}\n")
            return data
        else:
            logger.error(f"API error {resp.status_code}: {resp.text[:200]}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        return None


def buyer_2():
    def on_new_task(job: ACPJob, memo_to_sign: Optional[ACPMemo] = None):
        logger.info(f"[on_new_task] Job {job.id} (phase: {job.phase})")
        if (
            job.phase == ACPJobPhase.NEGOTIATION
            and memo_to_sign is not None
            and memo_to_sign.next_phase == ACPJobPhase.TRANSACTION
        ):
            logger.info(f"Paying and accepting requirement for job {job.id}")
            try:
                job.pay_and_accept_requirement()
                logger.info(f"Job {job.id} paid")
            except ACPError as e:
                logger.error(f"Failed to pay/accept requirement for job {job.id}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error during pay_and_accept_requirement: {e}")
        elif (
            job.phase == ACPJobPhase.TRANSACTION
            and memo_to_sign is not None
            and memo_to_sign.next_phase == ACPJobPhase.REJECTED
        ):
            logger.info(
                f"Signing job {job.id} rejection memo, reason: {memo_to_sign.content}"
            )
            memo_to_sign.sign(True, "Accepts job rejection")
            logger.info(f"Job {job.id} rejection memo signed")
        elif job.phase == ACPJobPhase.COMPLETED:
            logger.info(f"Job {job.id} completed. Deliverable: {job.deliverable}")
        elif job.phase == ACPJobPhase.REJECTED:
            logger.info(f"Job {job.id} rejected by seller")

    acp_client = VirtualsACP(
        wallet_private_key=os.getenv("WHITELISTED_WALLET_PRIVATE_KEY"),
        agent_wallet_address=os.getenv("AGENT_BUYER_WALLET_ADDRESS"),
        entity_id=int(os.getenv("BUYER_ENTITY_ID")),
        on_new_task=on_new_task,
    )

    try:
       relevant_agents = acp_client.browse_agents(
        keyword="PawXAI",  
        sort_by=[
            ACPAgentSort.SUCCESSFUL_JOB_COUNT,
        ],
        top_k=5,
        graduation_status=ACPGraduationStatus.ALL,
        online_status=ACPOnlineStatus.ALL,
    )
    except ACPError as e:
        logger.error(f"Browse failed: {e}. Ensure seller agent is online with valid offerings.")
        return

    if not relevant_agents:
        logger.info("No agents found. Ensure seller agent is online.")
        return

    chosen_agent = relevant_agents[0]
    chosen_job_offering = chosen_agent.offerings[1]
    print("job offering :", chosen_job_offering)
    
    logger.info(f"Chosen second offering: {chosen_job_offering}")

    # Build CombinedFilter payload from user input
    payload = build_combined_filter_payload()

    # Optional: call local API to preview results
    api_result = call_filter_combined_api(payload)
    if api_result is not None:
        logger.info(f"Preview API result keys: {list(api_result.keys())}")

    # Initiate job with the CombinedFilter payload as service requirement
    service_requirement = {"content": payload}
    logger.info(f"Final ACP service requirement: {json.dumps(service_requirement)}")
    job_id = chosen_job_offering.initiate_job(
        service_requirement=service_requirement,
        evaluator_address=os.getenv("AGENT_BUYER_WALLET_ADDRESS"),
        expired_at=datetime.now() + timedelta(days=1),
    )
    logger.info(f"Job {job_id} initiated on offering[1]")
    logger.info("Listening for next steps...")

    threading.Event().wait()


if __name__ == "__main__":
    buyer_2()