import json
from typing import Dict, List, Any

def extract_user_and_tweet_data(json_file_path: str) -> Dict[str, Any]:
    """
    Extract user information and tweet details from the API response JSON file.
    
    Args:
        json_file_path (str): Path to the JSON file containing API response
        
    Returns:
        Dict containing extracted user info and tweets
    """
    
    with open(json_file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    
    # Extract basic response info
    result = {
        'status': data.get('status'),
        'username': data.get('username'),
        'user_info': {},
        'tweets': []
    }
    
    # Process each tweet entry
    tweets_data = data.get('data', [])
    
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
    
    return result

def print_extracted_data(data: Dict[str, Any]) -> None:
    """
    Print the extracted data in a readable format.
    """
    print(f"Status: {data['status']}")
    print(f"Username: {data['username']}")
    print("\n=== USER INFORMATION ===")
    user_info = data['user_info']
    print(f"ID: {user_info['id']}")
    print(f"Name: {user_info['name']}")
    print(f"Location: {user_info['location']}")
    print(f"Description: {user_info['description']}")
    print(f"Website: {user_info['website']}")
    print(f"Followers Count: {user_info['followersCount']}")
    print(f"Friends Count: {user_info['friendsCount']}")
    print(f"KOL Followers Count: {user_info['kolFollowersCount']}")
    
    print("\n=== TWEETS ===")
    for i, tweet in enumerate(data['tweets'], 1):
        print(f"\nTweet {i}:")
        print(f"  Type: {tweet['type'].upper()}")
        print(f"  ID: {tweet['id']}")
        print(f"  Created: {tweet['createdAt']}")
        print(f"  Text: {tweet['text']}")
        print(f"  Likes: {tweet['favoriteCount']}")
        print(f"  Retweets: {tweet['retweetCount']}")
        print(f"  Replies: {tweet['replyCount']}")
        print(f"  Quotes: {tweet['quoteCount']}")

def save_extracted_data(data: Dict[str, Any], output_file: str) -> None:
    """
    Save extracted data to a JSON file.
    """
    with open(output_file, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
    print(f"\nExtracted data saved to: {output_file}")

def save_text_format(data: Dict[str, Any], output_file: str) -> None:
    """
    Save extracted data to a text file in the specified format.
    """
    user_info = data['user_info']
    
    with open(output_file, 'w', encoding='utf-8') as file:
        # Write user information
        file.write(f"Name: {user_info['name']}\n")
        file.write(f"Location: {user_info['location']}\n")
        file.write(f"Description: {user_info['description']}\n")
        file.write(f"Website: {user_info['website']}\n") 
        file.write(f"Followers: {user_info['followersCount']}\n")
        file.write(f"Following: {user_info['friendsCount']}\n")
        file.write(f"KOL Follower Counts: {user_info['kolFollowersCount']}\n\n")
        
        # Write tweets
        for i, tweet in enumerate(data['tweets'], 1):
            file.write(f"Tweet {i}:\n\n")
            file.write(f"Type: {tweet['type'].upper()}\n")
            file.write(f"Text: {tweet['text']}\n\n")
    
    print(f"\nText format data saved to: {output_file}")

if __name__ == "__main__":
    # File paths
    input_file = "./data.json"
    output_json_file = "./extracted_data.json"
    output_text_file = "./extracted_data.txt"
    
    try:
        # Extract data
        extracted_data = extract_user_and_tweet_data(input_file)
        
        # Print to console
        print_extracted_data(extracted_data)
        
        # Save to JSON file
        save_extracted_data(extracted_data, output_json_file)
        
        # Save to text file
        save_text_format(extracted_data, output_text_file)
        
        print(f"\nTotal tweets processed: {len(extracted_data['tweets'])}")
        
    except FileNotFoundError:
        print(f"Error: File {input_file} not found.")
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in {input_file}.")
    except Exception as e:
        print(f"Error: {str(e)}")
        

