#!/usr/bin/env python3
"""
Batch process to fetch YouTube videos from multiple channels.
Filters out YouTube Shorts and only shows regular long-form videos.
"""

import os
import time
from datetime import datetime, timedelta
from http.cookiejar import MozillaCookieJar
import requests
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, IpBlocked
from prettytable import PrettyTable
from llama_cpp import Llama

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variable
API_KEY = os.getenv('YOUTUBE_API_KEY')

if not API_KEY:
    raise ValueError("YOUTUBE_API_KEY not found in environment variables. Please create a .env file with your API key.")

# Initialize YouTube API client
youtube = build('youtube', 'v3', developerKey=API_KEY)

# Configuration
FETCH_TRANSCRIPTS = True  # Set to True to fetch transcripts (may hit IP limits)
DAYS_FILTER = 10  # Only fetch transcripts for videos newer than this many days
LLAMA_MODEL_PATH = "/Users/vuk/projects/david_fast_api_backup/david_fast_api/llama_models/llama-2-7b-chat-hf-q4_k_m.gguf"

# Initialize Llama model (load once at startup)
print("Loading Llama model...")
llm = Llama(model_path=LLAMA_MODEL_PATH, n_ctx=2048, n_threads=4)
print("Llama model loaded!")

# List of YouTube channel IDs or handles
# Format: @username for handles
CHANNELS = [
    '@MarkMoss',
    '@LiamOttley',
    '@HeresyFinancial',
    '@RaoulPal',
    '@OrionTaraban',
    '@DavidBayer',
    '@ClearValueTax',
    '@DavidSnyderNLP',
    '@DejanBeric',
    '@BenAzadi',
    '@Kaggle',
    '@TomBilyeu',
    '@JessicaOs',
    '@ViktorJeremic',
    '@EFL',
    '@TheDotPot',
    '@TealSwan',
    '@MilitarySummary',
    '@SimplyBitcoin',
    '@XOFruit',
    '@TuckerCarlson',
    '@KatieClarke',
    '@Fireship',
    '@THEGRIM',
    '@EntrepreneursinCars',
    '@DrEricBergDC',
    '@JOSEMORALEJO',
    '@SpotlightTV',
    '@CaneDojcilovic',
    '@PowerfulJRE',
    '@FatherMoses',
    '@JulianGoldieSEO',
    '@BlicTV',
    '@OliviaAlexa',
    '@StarSports',
    '@HelmCast',
    '@Pivokosa',
    '@WeebUnion',
    '@UFDTech',
    '@CaseyZander',
    '@AIEngineer',
    '@DrTraceyMarks',
    '@IvanKosogorPodcast',
    '@CrvenaZvezda',
    '@SlavicaSquire',
    '@HusseinNasser',
    '@motivationaldoc',
    '@RenaMalikMD',
    '@MichaelFranzese',
    '@Familijobe',
    '@ReverseAgingRevolution',
    '@Teachingmensfashion',
    '@TheAIAdvantage',
    '@PeakProsperity',
    '@AIAnytime',
    '@AaronDoughty',
    '@TAGMEDIATV',
    '@SandraSiladjev',
    '@VasicMedia',
    '@HasanAboulHasan',
    '@TheDiaryOfACEO',
    '@DrJamesDiNicolantonio',
    '@ArthurMello',
    '@ScottRitter',
    '@TripodProduction',
    '@RuhiCenetDocumentaries',
    '@TinyTechnicalTutorials',
    '@SystemDesignFightClub',
    '@EmirKusturica',
    '@MilosPistolic',
    '@ShawTalebi',
    '@RobMulla',
    '@AIFoundations',
]


def get_video_transcript(video_id):
    """
    Fetch the transcript for a YouTube video using cookies for authentication.

    Args:
        video_id: YouTube video ID

    Returns:
        Tuple of (transcript_text, error_type) where error_type is None if successful,
        or a string describing the error ('ip_blocked', 'no_transcript', 'disabled', 'error')
    """
    try:
        # Use cookies file for authentication to avoid IP blocks
        cookies_path = os.path.join(os.path.dirname(__file__), 'cookies.txt')

        # Create a session with cookies
        session = requests.Session()
        cookies = MozillaCookieJar(cookies_path)
        cookies.load(ignore_discard=True, ignore_expires=True)
        session.cookies.update(cookies)

        # Create API instance with authenticated session
        api = YouTubeTranscriptApi(http_client=session)
        transcript_result = api.fetch(video_id)

        # Combine all transcript segments into one text
        transcript_text = ' '.join([snippet.text for snippet in transcript_result.snippets])
        return (transcript_text, None)
    except IpBlocked:
        return (None, 'ip_blocked')
    except NoTranscriptFound:
        return (None, 'no_transcript')
    except TranscriptsDisabled:
        return (None, 'disabled')
    except Exception as e:
        return (None, f'error: {str(e)}')


def summarize_transcript(transcript_text, max_words=700):
    """
    Summarize a video transcript using local Llama model.

    Args:
        transcript_text: Full transcript text
        max_words: Maximum words for summary (default 700)

    Returns:
        Summary string or error message
    """
    try:
        # Truncate transcript if too long (to fit in context window)
        max_transcript_chars = 6000
        if len(transcript_text) > max_transcript_chars:
            transcript_text = transcript_text[:max_transcript_chars] + "..."

        prompt = f"""Summarize the following YouTube video transcript in maximum {max_words} words. Focus on the main points, key insights, and actionable takeaways.

Transcript:
{transcript_text}

Summary:"""

        response = llm(
            prompt,
            max_tokens=1024,
            temperature=0.7,
            stop=["Transcript:", "\n\n\n"],
            echo=False
        )

        summary = response['choices'][0]['text'].strip()
        return summary if summary else "[Unable to generate summary]"

    except Exception as e:
        return f"[Error summarizing: {str(e)[:50]}]"


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


def get_channel_videos(channel_id, max_results=50, days_filter=10):
    """
    Fetch videos from a YouTube channel, filtering out Shorts and old videos.

    Args:
        channel_id: YouTube channel ID
        max_results: Maximum number of videos to fetch (default 50)
        days_filter: Only include videos from the past N days (default 10)

    Returns:
        Tuple of (channel_title, list of recent video dictionaries)
    """
    videos = []
    channel_title = None
    cutoff_date = datetime.now() - timedelta(days=days_filter)

    try:
        # Get the channel's uploads playlist ID
        channel_response = youtube.channels().list(
            part='contentDetails,snippet',
            id=channel_id
        ).execute()

        if not channel_response['items']:
            return (None, [])

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
                is_long_video = 'H' in duration or 'M' in duration or (
                    'S' in duration and int(duration.split('PT')[1].split('S')[0]) > 61
                )

                if is_long_video:
                    title = video['snippet']['title']
                    published_at = video['snippet']['publishedAt']

                    # Parse and format the date
                    date_obj = datetime.strptime(published_at, '%Y-%m-%dT%H:%M:%SZ')

                    # Only include videos from the past N days
                    if date_obj >= cutoff_date:
                        formatted_date = date_obj.strftime('%Y-%b-%d')

                        videos.append({
                            'title': title,
                            'published_at': formatted_date,
                            'video_id': video['id'],
                            'date_obj': date_obj
                        })

            next_page_token = playlist_response.get('nextPageToken')

            if not next_page_token:
                break

    except HttpError as e:
        pass

    return (channel_title, videos)


def main():
    """Main function to process all channels and display videos from past 10 days."""

    print(f"Fetching videos from the past {DAYS_FILTER} days...\n")

    channels_with_videos = 0
    total_videos = 0

    for channel_identifier in CHANNELS:
        channel_id = get_channel_id(channel_identifier)

        if channel_id:
            channel_title, videos = get_channel_videos(channel_id, days_filter=DAYS_FILTER)

            # Only display channels that have videos in the past N days
            if videos and channel_title:
                channels_with_videos += 1
                total_videos += len(videos)

                # Print channel name as header
                print("=" * 120)
                print(f"  {channel_title}")
                print("=" * 120)

                # Sort videos by date (most recent first)
                sorted_videos = sorted(videos, key=lambda x: x['date_obj'], reverse=True)

                # Fetch transcripts and summaries for each video
                if FETCH_TRANSCRIPTS:
                    print(f"Fetching transcripts and generating summaries for {len(sorted_videos)} videos...")
                    for video in sorted_videos:
                        transcript, error = get_video_transcript(video['video_id'])
                        if transcript:
                            print(f"  Summarizing: {video['title'][:60]}...")
                            video['summary'] = summarize_transcript(transcript)
                        else:
                            video['summary'] = f"[No transcript: {error}]"
                        time.sleep(1.5)  # Rate limiting
                    print()

                # Create table for this channel's videos
                table = PrettyTable()
                table.field_names = ["Video ID", "Date", "Title", "Summary"]
                table.align["Video ID"] = "l"
                table.align["Date"] = "c"
                table.align["Title"] = "l"
                table.align["Summary"] = "l"
                table.max_width["Title"] = 40
                table.max_width["Summary"] = 70

                # Add rows to table
                for video in sorted_videos:
                    table.add_row([
                        video['video_id'],
                        video['published_at'],
                        video['title'],
                        video.get('summary', '[Transcripts disabled]')
                    ])

                print(table)
                print()  # Empty line between channels

    # Summary
    print("=" * 80)
    print(f"Summary: Found {total_videos} videos from {channels_with_videos} channels in the past {DAYS_FILTER} days")
    print("=" * 80)


if __name__ == '__main__':
    main()
