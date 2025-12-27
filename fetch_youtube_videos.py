#!/usr/bin/env python3
"""
Batch process to fetch YouTube videos from multiple channels.
Filters out YouTube Shorts and only shows regular long-form videos.
"""

import os
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variable
API_KEY = os.getenv('YOUTUBE_API_KEY')

if not API_KEY:
    raise ValueError("YOUTUBE_API_KEY not found in environment variables. Please create a .env file with your API key.")

# Initialize YouTube API client
youtube = build('youtube', 'v3', developerKey=API_KEY)

# List of YouTube channel IDs or handles
# You can find channel IDs by going to a channel page and looking at the URL
# Format: UC... for channel IDs, or @username for handles
CHANNELS = [
    '@DavidSnyderNLP',  # David Snyder NLP
]


def get_channel_id(channel_identifier):
    """
    Convert a channel handle (@username) or return channel ID if already provided.

    Args:
        channel_identifier: Channel ID (UC...) or handle (@username)

    Returns:
        Channel ID string
    """
    if channel_identifier.startswith('@'):
        try:
            # Search for channel by handle
            request = youtube.search().list(
                part='snippet',
                q=channel_identifier,
                type='channel',
                maxResults=1
            )
            response = request.execute()

            if response['items']:
                return response['items'][0]['snippet']['channelId']
            else:
                return None
        except HttpError as e:
            return None
    else:
        return channel_identifier


def get_channel_videos(channel_id, max_results=50):
    """
    Fetch videos from a YouTube channel, filtering out Shorts.

    Args:
        channel_id: YouTube channel ID
        max_results: Maximum number of videos to fetch (default 50)

    Returns:
        List of video dictionaries with title and publish date
    """
    videos = []

    try:
        # Get the channel's uploads playlist ID
        channel_response = youtube.channels().list(
            part='contentDetails,snippet',
            id=channel_id
        ).execute()

        if not channel_response['items']:
            return videos

        channel_title = channel_response['items'][0]['snippet']['title']
        uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

        # Fetch videos from the uploads playlist
        next_page_token = None

        while len(videos) < max_results:
            playlist_response = youtube.playlistItems().list(
                part='contentDetails',
                playlistId=uploads_playlist_id,
                maxResults=min(50, max_results - len(videos)),
                pageToken=next_page_token
            ).execute()

            video_ids = [item['contentDetails']['videoId'] for item in playlist_response['items']]

            # Get video details to filter out Shorts
            videos_response = youtube.videos().list(
                part='snippet,contentDetails',
                id=','.join(video_ids)
            ).execute()

            for video in videos_response['items']:
                # Parse duration to filter out Shorts (typically under 60 seconds)
                duration = video['contentDetails']['duration']

                # Convert ISO 8601 duration to seconds
                # Simple check: Shorts are usually very short (< 61 seconds)
                # We'll filter by checking if duration contains 'M' (minutes) or has 'H' (hours)
                # or has more than 61 seconds
                is_long_video = 'H' in duration or 'M' in duration or (
                    'S' in duration and int(duration.split('PT')[1].split('S')[0]) > 61
                )

                if is_long_video:
                    title = video['snippet']['title']
                    published_at = video['snippet']['publishedAt']

                    # Parse and format the date
                    date_obj = datetime.strptime(published_at, '%Y-%m-%dT%H:%M:%SZ')
                    formatted_date = date_obj.strftime('%Y-%m-%d %H:%M:%S')

                    videos.append({
                        'title': title,
                        'published_at': formatted_date,
                        'video_id': video['id']
                    })

                    print(f"{video['id']}, {title}, {formatted_date}")

            next_page_token = playlist_response.get('nextPageToken')

            if not next_page_token:
                break

    except HttpError as e:
        pass

    return videos


def main():
    """Main function to process all channels."""
    all_videos = {}

    for channel_identifier in CHANNELS:
        channel_id = get_channel_id(channel_identifier)

        if channel_id:
            videos = get_channel_videos(channel_id)
            all_videos[channel_identifier] = videos


if __name__ == '__main__':
    main()
