from utils.constants import LANGUAGE_TAGS, ECOSYSTEM_TAGS, USER_TYPE_TAGS   

analyze_prompt=f"""
You are an expert in the Web3 ecosystem. Given a single Twitter account's full data (user profile fields and recent tweets/retweets), analyze everything and produce exactly ONE JSON object (no extra text, no explanation) that follows the schema and rules below.

INPUT (provided to you by the caller):
- "user":  profile fields: "name", "bio", "location", "website", "followers_count", "following_count"
- "tweets": a list of recent tweet objects. Each tweet object contains: {{ "type", "text" }}
  - The "type" field will be one of: "tweet", "reply", "quote", "retweet" 
  - Definition: a tweet is considered **user-authored** if its type is one of ["tweet","reply","quote"]. A "retweet" is **not** user-authored.

TASK / REQUIREMENTS:
1. Produce a single JSON object with these keys:
   {{
     "language_tags": [...],
     "ecosystem_tags": [...],
     "user_type_tags": [...],
     "MBTI": "<4-letter MBTI>",
     "summary": "<<=150 words plain English summary>>"
   }}

2. Tag rules:
   - Only choose tags from the allowed lists below. If none apply for a category, return a list containing only the string "other", like this: ["other"].
   - language_tags allowed values:
     {LANGUAGE_TAGS}
   - ecosystem_tags allowed values:
     {ECOSYSTEM_TAGS}
   - user_type_tags allowed values:
     {USER_TYPE_TAGS}

3. How to determine tags:
   - language_tags (IMPORTANT — conservative rule):
     * Only use **user-authored** tweets (types: "tweet","reply","quote","thread") when deciding language_tags. **Do not** count text that appears only in retweets for language detection.
     * Require clear evidence that the user actually speaks/writes the language. Tag a language only if there is consistent evidence among the user's authored content. Examples of sufficient evidence:
       - At least **two** distinct user-authored tweets in that language that demonstrate coherent sentence structure (not just single-word hashtags or quoted text), OR
       - One or more longer user-authored threads or multi-sentence posts in that language showing fluent usage, OR
       - The user's bio/pinned tweet explicitly states fluency in that language **and** there is at least one user-authored tweet in that language.
     * Do NOT tag languages based solely on: single-word hashtags, mentions, quoted foreign text inside a tweet, URLs, or content clearly copied/translated from someone else. If evidence is ambiguous or minimal, omit that language tag.
     * If multiple languages meet the above evidence rules, include them all.
   - ecosystem_tags:
     * Detect protocols/blockchains from hashtags, mentions, repeated keywords, project names, and URLs present in tweets and bio. Map common abbreviations to the allowed tag set (e.g., "#eth" or "Ethereum" -> "ethereum"; "OP" or "Optimism" -> "optimism"; "zk" / "zk-rollup" -> "zk_rollups" or "zkSync"/"starknet" depending on context).
     * Use repeated, recent references as stronger signals than single mentions.
   - user_type_tags:
     * Infer roles/behaviors from profile and the user's authored tweets. Example heuristics: technical threads/code -> "developer"; bio that says "founder" or frequent product announcements -> "founder & CEO"; repeated airdrop/claim posts -> "airdrop_hunter"; frequent on-chain analysis or data-driven threads -> "onchain_analyst".
     * Multiple tags are allowed if evidence supports them.

4. MBTI:
   - Infer a likely MBTI four-letter code from tweeting style and behavior. Suggested heuristics:
     * Extra/Introversion: frequent direct replies, social outreach, many short conversational tweets -> E; long solitary threads and infrequent public replies -> I.
     * Sensing/Intuition: focus on concrete data, numbers, step-by-step tutorials -> S; speculative, big-picture, conceptual threads -> N.
     * Thinking/Feeling: analytical, argumentative, explain-first style -> T; empathetic, community-focused, supportive language -> F.
     * Judging/Perceiving: structured schedules, roadmap posts, milestone updates -> J; exploratory, spontaneous, open-ended posts -> P.
     Important: You must always output a 4-letter MBTI code. If clear evidence is limited, do not leave MBTI blank—make a best-guess 4-letter MBTI based on the heuristics above and the user's observable tweeting behavior. The MBTI field must contain a 4-letter code (e.g., "INTJ"); guess when necessary.

5. Summary (<=150 words):
   - One paragraph in plain English describing who this user likely is, their top interests, what they have posted about recently, and what they appear to be working on. Keep it evidence-based and under 150 words. Do not include private or speculative personal details.

6. Output constraints:
   - Return **only** the JSON object, nothing else (no comments, no surrounding markdown).
   - Ensure valid JSON (keys quoted, arrays, no trailing commas).
   - If a tag category has no matches, return an empty array [].
   - The summary must be plain English text, max 150 words.

EXAMPLE OUTPUT:
{{
  "language_tags": ["english","chinese"],
  "ecosystem_tags": ["ethereum","arbitrum","zk_rollups"],
  "user_type_tags": ["developer","onchain_analyst"],
  "MBTI": "INTP",
  "summary": "This user is a blockchain developer and on-chain analyst focusing on Ethereum and Arbitrum. Recent tweets show technical threads about rollup design, zk technology, and tooling. They often share code snippets, tutorials, and market commentary. Current activity suggests work on a rollup analytics tool and developer education content."
}}

Now produce the JSON analysis for the provided INPUT.
"""