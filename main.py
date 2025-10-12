from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime
from typing import Optional, Dict, Any, Union, List
import os
import re
import json
from dotenv import load_dotenv
from models.schema import TwitterUsernameRequest, TwitterAnalysisResponse
from models.model import OpenAIModel
from prompts.analyze import analyze_prompt

load_dotenv()

app = FastAPI(
    title="Twitter KOL Analysis API",
    description="API for analyzing Twitter KOL (Key Opinion Leader) data",
    version="1.0.0"
)


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Custom exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "message": "Validation error",
            "details": exc.errors()
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": exc.detail
        }
    )

# Validation functions
def validate_twitter_username(username: str) -> bool:
    """Validate Twitter username format"""
    # Twitter username rules: 1-15 characters, alphanumeric and underscores only
    pattern = r'^[a-zA-Z0-9_]{1,15}$'
    return bool(re.match(pattern, username))

def validate_datetime_format(date_string: str) -> bool:
    """Validate ISO datetime format"""
    try:
        datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        return True
    except ValueError:
        return False

def extract_and_save_data(data: Dict[str, Any], username: str) -> None:
    """Extract user and tweet data and save to files"""
    # Extract basic response info
    result = {
        'status': 'success',
        'username': username,
        'user_info': {},
        'tweets': []
    }
    
    # Process each tweet entry
    tweets_data = data if isinstance(data, list) else data.get('data', [])
    
    if tweets_data:
        # Get user info from the first tweet (should be consistent across all tweets)
        first_user = tweets_data[0].get('user', {})
        result['user_info'] = {
            'id': first_user.get('id'),
            'name': first_user.get('name'),
            'location': first_user.get('location'),
            'description': first_user.get('description'),
            'website': first_user.get('website'),
            'followersCount': first_user.get('followersCount'),
            'friendsCount': first_user.get('friendsCount'),
            'kolFollowersCount': first_user.get('kolFollowersCount')
        }
        
        # Extract tweet information
        for entry in tweets_data:
            tweet = entry.get('tweet', {})
            
            # Determine tweet type
            tweet_type = 'tweet'  # default
            if tweet.get('retweetedStatusIdStr'):
                tweet_type = 'retweet'
            elif tweet.get('inReplyToStatusIdStr'):
                tweet_type = 'reply'
            elif tweet.get('quotedStatusIdStr'):
                tweet_type = 'quote_tweet'
            
            tweet_info = {
                'id': tweet.get('id'),
                'type': tweet_type,
                'text': tweet.get('text'),
                'createdAt': tweet.get('createdAt'),
                'favoriteCount': tweet.get('favoriteCount'),
                'retweetCount': tweet.get('retweetCount'),
                'replyCount': tweet.get('replyCount'),
                'quoteCount': tweet.get('quoteCount')
            }
            
            result['tweets'].append(tweet_info)
    
    # Save to JSON file
    output_json_file = f"./extracted_data_{username}.json"
    with open(output_json_file, 'w', encoding='utf-8') as file:
        json.dump(result, file, indent=2, ensure_ascii=False)
    
    # Save to text file
    output_text_file = f"./extracted_data_{username}.txt"
    user_info = result['user_info']
    
    total_text = ""
    
    # Build total_text with user information
    total_text += f"Name: {user_info['name']}\n"
    total_text += f"Location: {user_info['location']}\n"
    total_text += f"Description: {user_info['description']}\n"
    total_text += f"Website: {user_info['website']}\n"
    total_text += f"Followers: {user_info['followersCount']}\n"
    total_text += f"Following: {user_info['friendsCount']}\n"
    total_text += f"KOL Follower Counts: {user_info['kolFollowersCount']}\n\n"
    
    # Add tweets to total_text
    for i, tweet in enumerate(result['tweets'], 1):
        total_text += f"Tweet {i}:\n\n"
        total_text += f"Type: {tweet['type'].upper()}\n"
        total_text += f"Text: {tweet['text']}\n\n"
    
    # Write total_text to file
    with open(output_text_file, 'w', encoding='utf-8') as file:
        file.write(total_text)
    
    print(f"Data extracted and saved for user @{username}")
    print(f"JSON file: {output_json_file}")
    print(f"Text file: {output_text_file}")
    
    return total_text

@app.get("/")
async def root():
    return {"message": "Twitter KOL Analysis API is running"}

@app.post("/analyze-twitter-user", response_model=TwitterAnalysisResponse)
async def analyze_twitter_user(request: TwitterUsernameRequest):
    """
    Analyze a Twitter user by fetching their stored tweets from the external API
    
    Args:
        request: TwitterUsernameRequest containing username and optional date range
    
    Returns:
        TwitterAnalysisResponse with the analysis results
    
    Raises:
        HTTPException: For various error conditions
    """
    try:
        # Validate username format
        if not validate_twitter_username(request.username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Twitter username format. Username must be 1-15 characters, alphanumeric and underscores only."
            )
        
        # Validate date formats
        if not validate_datetime_format(request.created_after):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid created_after date format. Use ISO format like '2025-09-01T12:00:00Z'"
            )
        
        if not validate_datetime_format(request.created_before):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid created_before date format. Use ISO format like '2025-10-06T23:59:59Z'"
            )
        
        # Validate date range logic
        after_date = datetime.fromisoformat(request.created_after.replace('Z', '+00:00'))
        before_date = datetime.fromisoformat(request.created_before.replace('Z', '+00:00'))
        
        if after_date >= before_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="created_after must be earlier than created_before"
            )
        
        # Construct the API URL
        api_url = "https://foxhole.bot/api/v1/twitterUsers/stored-tweets"
        
        # Set up headers
        headers = {
            "X-API-Key": "test",
            "Content-Type": "application/json",
            "User-Agent": "Twitter-KOL-Analysis-API/1.0.0"
        }
        
        # Set up query parameters
        params = {
            "screenName": request.username,
            "createdAfter": request.created_after,
            "createdBefore": request.created_before
        }
        
        # Make the API call with improved error handling
        response = requests.get(
            api_url,
            headers=headers,
            params=params,
            timeout=30
        )
        
        
        # Check if the request was successful
        if response.status_code == 200:
            try:
                data = response.json()
                
                # Extract and save data to files
                total_text = extract_and_save_data(data, request.username)
                analyze_instance = OpenAIModel(system_prompt=analyze_prompt, temperature=0)
                prompt = f"INPUT:{total_text}\nOUTPUT:"
                analysis_result, input_tokens_length, output_tokens_length = analyze_instance.generate_text(prompt)
                
                # Parse the JSON response
                try:
                    analysis_json = json.loads(analysis_result)
                except json.JSONDecodeError as json_error:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Invalid JSON response from OpenAI: {str(json_error)}"
                    )
                
                
                # Handle both list and dictionary responses
                if isinstance(data, list):
                    tweet_count = len(data)
                    message = f"Successfully retrieved {tweet_count} tweets for user @{request.username}. Data saved to files."
                elif isinstance(data, dict):
                    # If it's a dict, try to get tweet count from common fields
                    tweet_count = len(data.get('tweets', [])) if 'tweets' in data else 'unknown number of'
                    message = f"Successfully retrieved {tweet_count} tweets for user @{request.username}. Data saved to files."
                else:
                    message = f"Successfully retrieved data for user @{request.username}. Data saved to files."
                
                return TwitterAnalysisResponse(
                    status="success",
                    username=request.username,
                    #data=data,
                    data=analysis_json,
                    message=message
                )
            except ValueError as json_error:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Invalid JSON response from external API: {str(json_error)}"
                )
        elif response.status_code == 404:
            return TwitterAnalysisResponse(
                status="error",
                username=request.username,
                message=f"User @{request.username} not found or has no tweets in the specified date range"
            )
        elif response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key for external service"
            )
        elif response.status_code == 429:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded for external API. Please try again later."
            )
        else:
            # Handle other API errors
            error_message = f"External API returned status code {response.status_code}"
            if response.text:
                error_message += f": {response.text[:200]}"  # Limit error message length
            
            return TwitterAnalysisResponse(
                status="error",
                username=request.username,
                message=error_message
            )
            
    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="Request timeout - the external API took too long to respond (>30 seconds)"
        )
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Connection error - unable to reach the external API. Please check your internet connection."
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Request error: {str(e)}"
        )
    except HTTPException:
        # Re-raise HTTPExceptions to preserve status codes
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "Twitter KOL Analysis API"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)