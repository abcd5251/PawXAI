# Twitter Analysis with Virtuals ACP

A comprehensive system for Twitter KOL (Key Opinion Leader) analysis using Virtuals ACP (Agent Communication Protocol). This project includes both seller agents that provide Twitter analysis services and buyer agents that can request analysis.

## Components

### 1. Twitter Analysis API Server
Provides the core Twitter analysis functionality via REST API.

### 2. ACP Seller Agent (`acp_agent_with_twitter_api_updated.py`)
A Virtuals ACP seller agent that:
- Listens for Twitter analysis job requests
- Extracts Twitter usernames from job requirements
- Calls the analysis API
- Delivers results back to buyers

### 3. ACP Buyer Agent (`twitter_analysis_buyer.py`)
A Virtuals ACP buyer agent that:
- Browses available Twitter analysis agents
- Initiates analysis jobs for specific Twitter users
- Handles payment and evaluation

## Setup

### 1. Environment Configuration
Copy the example environment file and configure your credentials:
```bash
cp .env.example .env
```

Edit `.env` with your actual values:
```bash
# Required for ACP
WHITELISTED_WALLET_PRIVATE_KEY=your_whitelisted_wallet_private_key
SELLER_ENTITY_ID=1
SELLER_AGENT_WALLET_ADDRESS=your_seller_wallet_address
BUYER_ENTITY_ID=2
BUYER_AGENT_WALLET_ADDRESS=your_buyer_wallet_address

# API Configuration
OPENAI_MODEL=""
OPENAI_API_KEY=""
SERPER_API=""
QDRANT_DB_URL=""
QDRANT_APIKEY=""
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Start the Analysis API Server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Usage

### Running the Seller Agent
Start the Twitter analysis service provider:
```bash
python acp_agent_with_twitter_api_updated.py
```

The seller agent will:
1. Wait for incoming job requests
2. Accept valid Twitter analysis requests
3. Process usernames and call the analysis API
4. Deliver results to buyers

### Running the Buyer Agent
Request Twitter analysis for a specific user:
```bash
python twitter_analysis_buyer.py
```

The buyer agent will:
1. Browse available Twitter analysis agents
2. Prompt you for a Twitter username
3. Initiate a job request
4. Handle payment and receive results

## Job Flow

1. **REQUEST**: Buyer initiates job with Twitter username
2. **NEGOTIATION**: Seller accepts the job
3. **TRANSACTION**: Buyer pays, seller delivers analysis
4. **EVALUATION**: Buyer evaluates and approves the work
5. **COMPLETED**: Job finished successfully

## Service Requirements

When requesting analysis, provide the Twitter username in the service requirements:
```json
{
  "username": "elonmusk",
  "account": "elonmusk",
  "request_type": "twitter_analysis"
}
```

## Error Handling

The system handles various error scenarios:
- Invalid or missing Twitter usernames
- API failures
- Network timeouts
- Job rejections

## Legacy Files

- `buyer.py` - Original ACP buyer example
- `seller.py` - Original ACP seller example
- `sample_acp_client.py` - ACP client samples

These files serve as reference implementations for the ACP protocol.
