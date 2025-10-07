from pydantic import BaseModel
from typing import Optional, Dict, Any, Union, List

### Twitter KOL Analysis Models
class TwitterUsernameRequest(BaseModel):
    username: str
    created_after: Optional[str] = "2025-09-01T12:00:00Z"
    created_before: Optional[str] = "2025-10-06T23:59:59Z"

class TwitterAnalysisResponse(BaseModel):
    status: str
    username: str
    data: Optional[Union[Dict[Any, Any], List[Any]]] = None
    message: Optional[str] = None

class TwitterTweet(BaseModel):
    id: str
    conversation_id: Optional[str] = None
    text: str
    created_at: Optional[str] = None
    author_id: Optional[str] = None
    public_metrics: Optional[Dict[str, Any]] = None
    entities: Optional[Dict[str, Any]] = None

class TwitterUserAnalysis(BaseModel):
    username: str
    total_tweets: int
    date_range: Dict[str, str]
    tweets: Optional[list[TwitterTweet]] = None
    analysis_summary: Optional[str] = None