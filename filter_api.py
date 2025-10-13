import json
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

def load_data(file_path):
    data = []
    with open(file_path, 'r') as f:
        for line in f:
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError:
                # Handle cases where a line is not valid JSON
                print(f"Skipping invalid JSON line: {line.strip()}")
    return data

# Load data on startup
file_path = './analysis_results.jsonl'
all_data = load_data(file_path)

class FilterTags(BaseModel):
    tags: List[str]

class FilterCount(BaseModel):
    count: int

class CombinedFilter(BaseModel):
    ecosystem_tags: Optional[List[str]] = None
    language_tags: Optional[List[str]] = None
    user_type_tags: Optional[List[str]] = None
    followers_count: Optional[int] = None
    friends_count: Optional[int] = None
    kol_followers_count: Optional[int] = None

@app.post("/filter/ecosystem_tags")
def filter_by_ecosystem_tags(payload: FilterTags):
    """
    Filters data based on a list of ecosystem tags.
    Returns a list of items where at least one of the provided tags is present in the item's 'ecosystem_tags'.
    """
    tags_to_filter = set(payload.tags)
    filtered_results = [
        item for item in all_data
        if 'ecosystem_tags' in item and tags_to_filter.intersection(item.get('ecosystem_tags', []))
    ]
    return {"num_KOL": len(filtered_results), "results": filtered_results}

@app.post("/filter/language_tags")
def filter_by_language_tags(payload: FilterTags):
    """
    Filters data based on a list of language tags.
    Returns a list of items where at least one of the provided tags is present in the item's 'language_tags'.
    """
    tags_to_filter = set(payload.tags)
    filtered_results = [
        item for item in all_data
        if 'language_tags' in item and tags_to_filter.intersection(item.get('language_tags', []))
    ]
    return {"num_KOL": len(filtered_results), "results": filtered_results}

@app.post("/filter/user_type_tags")
def filter_by_user_type_tags(payload: FilterTags):
    """
    Filters data based on a list of user type tags.
    Returns a list of items where at least one of the provided tags is present in the item's 'user_type_tags'.
    """
    tags_to_filter = set(payload.tags)
    filtered_results = [
        item for item in all_data
        if 'user_type_tags' in item and tags_to_filter.intersection(item.get('user_type_tags', []))
    ]
    return {"num_KOL": len(filtered_results), "results": filtered_results}

@app.post("/filter/followers_count")
def filter_by_followers_count(payload: FilterCount):
    """
    Filters data based on followersCount.
    Returns a list of items where 'followersCount' is greater than the provided count.
    """
    count_to_filter = payload.count
    filtered_results = [
        item for item in all_data
        if 'followersCount' in item and item.get('followersCount', 0) > count_to_filter
    ]
    return {"num_KOL": len(filtered_results), "results": filtered_results}

@app.post("/filter/friends_count")
def filter_by_friends_count(payload: FilterCount):
    """
    Filters data based on friendsCount.
    Returns a list of items where 'friendsCount' is greater than the provided count.
    """
    count_to_filter = payload.count
    filtered_results = [
        item for item in all_data
        if 'friendsCount' in item and item.get('friendsCount', 0) > count_to_filter
    ]
    return {"num_KOL": len(filtered_results), "results": filtered_results}

@app.post("/filter/kol_followers_count")
def filter_by_kol_followers_count(payload: FilterCount):
    """
    Filters data based on kolFollowersCount.
    Returns a list of items where 'kolFollowersCount' is greater than the provided count.
    """
    count_to_filter = payload.count
    filtered_results = [
        item for item in all_data
        if 'kolFollowersCount' in item and item.get('kolFollowersCount', 0) > count_to_filter
    ]
    return {"num_KOL": len(filtered_results), "results": filtered_results}

def passes_filters(item, payload: CombinedFilter):
    if payload.ecosystem_tags:
        if not ('ecosystem_tags' in item and set(payload.ecosystem_tags).intersection(item.get('ecosystem_tags', []))):
            return False
    
    if payload.language_tags:
        if not ('language_tags' in item and set(payload.language_tags).intersection(item.get('language_tags', []))):
            return False

    if payload.user_type_tags:
        if not ('user_type_tags' in item and set(payload.user_type_tags).intersection(item.get('user_type_tags', []))):
            return False

    if payload.followers_count is not None:
        if not (item.get('followersCount', 0) > payload.followers_count):
            return False

    if payload.friends_count is not None:
        if not (item.get('friendsCount', 0) > payload.friends_count):
            return False

    if payload.kol_followers_count is not None:
        if not (item.get('kolFollowersCount', 0) > payload.kol_followers_count):
            return False
            
    return True

@app.post("/filter/combined")
def filter_combined(payload: CombinedFilter):
    """
    Filters data based on a combination of criteria in a single pass.
    """
    filtered_results = [item for item in all_data if passes_filters(item, payload)]
    return {"num_KOL": len(filtered_results), "results": filtered_results}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)