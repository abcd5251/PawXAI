import threading
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
import os

from virtuals_acp.memo import ACPMemo
from virtuals_acp.client import VirtualsACP
from virtuals_acp.env import EnvSettings
from virtuals_acp.job import ACPJob
from virtuals_acp.models import (
    ACPAgentSort,
    ACPJobPhase,
    ACPGraduationStatus,
    ACPOnlineStatus,
)

load_dotenv()


def twitter_analysis_buyer():
    env = EnvSettings()

    def on_new_task(job: ACPJob, memo_to_sign: Optional[ACPMemo] = None):
        print(f"[on_new_task] Received job {job.id} (phase: {job.phase})")
        if (
            job.phase == ACPJobPhase.NEGOTIATION
            and memo_to_sign is not None
            and memo_to_sign.next_phase == ACPJobPhase.TRANSACTION
        ):
            print(f"Paying for Twitter analysis job {job.id}")
            job.pay(job.price)
        elif job.phase == ACPJobPhase.COMPLETED:
            print(f"Twitter analysis job {job.id} completed successfully!")
            print("Analysis result received.")
        elif job.phase == ACPJobPhase.REJECTED:
            print(f"Twitter analysis job {job.id} was rejected")

    def on_evaluate(job: ACPJob):
        print(f"Evaluation function called for job {job.id}")
        # Automatically approve the job if analysis was delivered
        job.evaluate(True)

    acp = VirtualsACP(
        wallet_private_key=os.getenv("WHITELISTED_WALLET_PRIVATE_KEY"),
        agent_wallet_address=os.getenv("AGENT_BUYER_WALLET_ADDRESS"),
        on_new_task=on_new_task,
        on_evaluate=on_evaluate,
        entity_id=int(os.getenv("BUYER_ENTITY_ID")),
    )

    # Browse available Twitter analysis agents
    relevant_agents = acp.browse_agents(
        keyword="PawXAI",  
        sort_by=[
            ACPAgentSort.SUCCESSFUL_JOB_COUNT,
        ],
        top_k=5,
        graduation_status=ACPGraduationStatus.ALL,
        online_status=ACPOnlineStatus.ALL,
    )

    if not relevant_agents:
        print("No Twitter analysis agents found. Make sure your seller agent is registered and online.")
        return

    # Pick the first available agent
    chosen_agent = relevant_agents[0]
    print(f"Selected agent: {chosen_agent}")

    # Pick the first service offering
    if not chosen_agent.offerings:
        print("Selected agent has no service offerings available.")
        return
        
    chosen_job_offering = chosen_agent.offerings[0]
    print("job offering :", chosen_job_offering)
    
    # Request Twitter analysis for a specific username
    twitter_username = input("Enter Twitter username to analyze (without @): ").strip()
    if not twitter_username:
        print("No username provided. Exiting.")
        return

    print(f"Requesting Twitter analysis for @{twitter_username}...")
    
    job_id = chosen_job_offering.initiate_job(
        # Service requirement with Twitter username
        service_requirement={
            "username": twitter_username,
        },
        evaluator_address=os.getenv("AGENT_BUYER_WALLET_ADDRESS"),
        expired_at=datetime.now() + timedelta(days=1),
    )

    print(f"Twitter analysis job {job_id} initiated for @{twitter_username}")
    print("Listening for job updates...")
    # Keep the script running to listen for next steps
    threading.Event().wait()


if __name__ == "__main__":
    twitter_analysis_buyer()