# PawXAI
Your best Web3 information assistant on Telegram

## Project Demo
- YouTube: https://youtu.be/KQkwbn4xXBg

## Features
A compact toolkit that combines a Telegram bot with a local API to analyze crypto Twitter activity. It supports:
- Latest news browsing
- Twitter account analysis
- KOL discovery with filters
- Keyword monitoring for mentions
- Trending Coins analysis with a one-click Uniswap Base Swap link

**Setup**
- Create `.env` (use `.env.example` as reference):
```
AGENT_BUYER_WALLET_ADDRESS=0xYourWallet
WHITELISTED_WALLET_PRIVATE_KEY=0xPrivateKey
AGENT_SELLER_WALLET_ADDRESS=0xYourWallet
AGENT_BUYER_WALLET_ADDRESS=0xYourWallet
ANALYZE_API_TIMEOUT=50
UPLOAD_JSON_URL=https://0x0.st
# Optional: UPLOAD_JSON_URLS=https://0x0.st,https://paste.rs
OPENAI_API_KEY=your_openai_key
```
- Install dependencies: `pip install -r requirements.txt`

**How to Run**
- Run API: `python main.py`
- Run Bot: `python bot.py`

**Bot Usage**
- The main menu includes: `latest trending`, `Analyze account`, `Find KOL`, `Monitor account`, `Trending Coins`.
- Trending Coins:
  - Runs analysis on latest tweets and replies with results.
  - Adds a clickable Uniswap Base Swap link for quick trading.
- Find KOL:
  - Set filters step-by-step, execute the search, get a Top 3 summary and full JSON (shareable link + downloadable file).
- Monitor account:
  - Input a keyword (slug) to query recent mentions.
- Analyze account:
  - Enter a Twitter username and receive an analysis reply (or run the script directly).


**Project Layout**
- `bot.py`: Telegram bot entry point and handlers.
- `main.py`: local API entry point (`python main.py`).
- `utils/`: constants and helpers.
