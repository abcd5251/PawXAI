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
logger = logging.getLogger("BuyerKeywordKOL")

load_dotenv()


def _prompt_required_keyword(prompt: str) -> str:
    while True:
        s = input(prompt).strip()
        if not s:
            logger.warning("This field is required. Please enter a keyword.")
            continue
        return s

def to_slug(s: str) -> str:
    # Simple slugify: lowercase and spaces -> '-'
    return s.lower().replace(" ", "-")


def _extract_raw_list(body: Any) -> List[Any]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        # Prefer 'raw' if present, else common keys
        for key in ("raw", "users", "data", "results"):
            v = body.get(key)
            if isinstance(v, list):
                return v
    return []

# Added: robust output URL extractor for different deliverable formats
def _extract_output_url(deliverable: Any) -> Optional[str]:
    import re
    # Direct dict with output field
    if isinstance(deliverable, dict):
        v = deliverable.get("output")
        if isinstance(v, str) and v.startswith("http"):
            return v
        # IDeliverable-like structure: {"type": "text", "value": "..."}
        val = deliverable.get("value")
        if isinstance(val, str):
            m = re.search(r"https?://\S+", val)
            if m:
                return m.group(0)
        if isinstance(val, dict):
            v2 = val.get("output")
            if isinstance(v2, str) and v2.startswith("http"):
                return v2
    # Plain string deliverable
    elif isinstance(deliverable, str):
        m = re.search(r"https?://\S+", deliverable)
        if m:
            return m.group(0)
    return None

# Normalize any local host like 0.0.0.0/0.0.0.1/localhost to 127.0.0.1
def _sanitize_local_url(url: str) -> str:
    return (url or "").replace("://0.0.0.0", "://127.0.0.1").replace("://0.0.0.1", "://127.0.0.1").replace("://localhost", "://127.0.0.1")


def call_monitor_users_api(slug: str) -> Optional[Any]:
    """
    Call local proxy API to list users matched by monitor.
    Default: http://127.0.0.1:8000/keywordMonitors/{slug}/users
    """
    url_tpl = os.getenv(
        "MONITOR_USERS_API_URL",
        "http://127.0.0.1:8000/keywordMonitors/{slug}/users",
    )
    url_tpl = _sanitize_local_url(url_tpl)
    url = url_tpl.replace("{slug}", slug)
    try:
        logger.info(f"GET {url}")
        resp = requests.get(url, timeout=float(os.getenv("ANALYZE_API_TIMEOUT", "50")))
        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError:
                logger.error("Invalid JSON response from local proxy API")
                return None
        else:
            logger.error(f"API error {resp.status_code}: {resp.text[:200]}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        return None


def buyer_keyword_kol():
    def on_new_task(job: ACPJob, memo_to_sign: Optional[ACPMemo] = None):
        logger.info(f"[on_new_task] Job {job.id} (phase: {job.phase})")
        if (
            job.phase == ACPJobPhase.NEGOTIATION
            and memo_to_sign is not None
            and memo_to_sign.next_phase == ACPJobPhase.TRANSACTION
        ):
            logger.info(f"Paying for job {job.id}")
            try:
                job.pay(job.price)
                logger.info(f"Job {job.id} paid")
            except ACPError as e:
                logger.error(f"Failed to pay for job {job.id}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error during pay: {e}")
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
            deliverable = job.deliverable
            output_url = None
            try:
                output_url = _extract_output_url(deliverable)
            except Exception:
                output_url = None
            if output_url:
                logger.info(f"Job {job.id} completed. Output URL: {output_url}")
            else:
                logger.info(f"Job {job.id} completed. Deliverable: {deliverable}")
        elif job.phase == ACPJobPhase.REJECTED:
            logger.info(f"Job {job.id} rejected by seller")

    def on_evaluate(job: ACPJob):
        logger.info(f"Evaluation function called for job {job.id}")
        try:
            job.evaluate(True)
            logger.info(f"Job {job.id} evaluated and approved")
        except ACPError as e:
            logger.error(f"Evaluate failed for job {job.id}: {e}")

    acp_client = VirtualsACP(
        wallet_private_key=os.getenv("WHITELISTED_WALLET_PRIVATE_KEY"),
        agent_wallet_address=os.getenv("AGENT_BUYER_WALLET_ADDRESS"),
        entity_id=int(os.getenv("BUYER_ENTITY_ID")),
        on_new_task=on_new_task,
        on_evaluate=on_evaluate,
    )

    # Browse agents by keyword (configurable)
    browse_keyword = os.getenv("ACP_BROWSE_KEYWORD", "PawXAI")
    try:
        relevant_agents = acp_client.browse_agents(
            keyword=browse_keyword,
            sort_by=[ACPAgentSort.SUCCESSFUL_JOB_COUNT],
            top_k=int(os.getenv("ACP_TOP_K", "5")),
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

    def _select_keyword_offering(agent) -> Optional[tuple[int, Any]]:
        try:
            for idx, off in enumerate(getattr(agent, "offerings", []) or []):
                schema = getattr(off, "requirement_schema", None)
                if isinstance(schema, dict):
                    req = schema.get("required") or []
                    props = schema.get("properties") or {}
                    # Prefer offerings that explicitly require a string 'keyword'
                    kw = props.get("keyword")
                    if "keyword" in req and isinstance(kw, dict):
                        t = kw.get("type")
                        if t in (None, "string"):
                            return idx, off
        except Exception:
            pass
        # Safe fallback to env index or 0
        offs = getattr(agent, "offerings", []) or []
        fallback_idx = int(os.getenv("ACP_OFFERING_INDEX", "0"))
        if 0 <= fallback_idx < len(offs):
            return fallback_idx, offs[fallback_idx]
        return None

    selected = _select_keyword_offering(chosen_agent)
    if not selected:
        logger.error("No offering requiring 'keyword' found. Set ACP_OFFERING_INDEX or ensure seller offers keyword service.")
        return
    offering_index, chosen_job_offering = selected
    print("job offering :", chosen_job_offering)
    logger.info(f"Chosen offering[{offering_index}]: {chosen_job_offering}")

    # Prompt for keyword (plain string for seller requirement)
    keyword = _prompt_required_keyword("Enter keyword: ")
    slug = to_slug(keyword)

    # Optional: call local API to preview results
    api_result = call_monitor_users_api(slug)
    raw_list = _extract_raw_list(api_result) if api_result is not None else []
    total_count = len(raw_list)
    logger.info(f"Preview: total matched users = {total_count}")

    # Prepare concise preview for log
    top_unames: List[str] = []
    for u in raw_list[:10]:
        if isinstance(u, dict):
            uname = u.get("screenName") or u.get("username") or u.get("name")
        else:
            uname = str(u)
        if uname:
            top_unames.append(uname)
    if top_unames:
        logger.info("Top matched users: " + ", ".join(top_unames))

    # Initiate job with service requirement (only keyword per schema)
    service_requirement: Dict[str, Any] = {
        "keyword": keyword
    }

    logger.info(f"Chosen offering requirement schema: {json.dumps(getattr(chosen_job_offering, 'requirement_schema', {}))[:1000]}")
    logger.info(f"Final ACP service requirement: {json.dumps(service_requirement)[:1000]}")
    try:
        job_id = chosen_job_offering.initiate_job(
            service_requirement=service_requirement,
            evaluator_address=os.getenv("AGENT_BUYER_WALLET_ADDRESS"),
            expired_at=datetime.now() + timedelta(days=1),
        )
    except Exception as e:
        logger.error(f"Failed to initiate job: {e}")
        return
    logger.info(f"Job {job_id} initiated on offering[{offering_index}]")
    logger.info("Listening for next steps...")

    threading.Event().wait()


if __name__ == "__main__":
    buyer_keyword_kol()