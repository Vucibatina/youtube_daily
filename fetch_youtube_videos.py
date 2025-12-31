#!/usr/bin/env python3
"""
Batch process to fetch YouTube videos from multiple channels.
Filters out YouTube Shorts and only shows regular long-form videos.
"""

import os
import sys
import time
from datetime import datetime, timedelta
from http.cookiejar import MozillaCookieJar
from io import StringIO
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, IpBlocked
from prettytable import PrettyTable, ALL
from llama_cpp import Llama

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variable
API_KEY = os.getenv('YOUTUBE_API_KEY')

if not API_KEY:
    raise ValueError("YOUTUBE_API_KEY not found in environment variables. Please create a .env file with your API key.")

# Email Configuration
EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', 'False').lower() == 'true'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USERNAME = os.getenv('EMAIL_USERNAME', '')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')
EMAIL_TO = os.getenv('EMAIL_TO', 'vucibatina@hotmail.com')

# Initialize YouTube API client
youtube = build('youtube', 'v3', developerKey=API_KEY)

# Configuration
FETCH_TRANSCRIPTS = True  # Set to True to fetch transcripts (may hit IP limits)
DAYS_FILTER = 3  # Only fetch transcripts for videos newer than this many days
LLAMA_MODEL_PATH = "/Users/vuk/projects/david_fast_api_backup/david_fast_api/llama_models/llama-2-7b-chat-hf-q4_k_m.gguf"

# Initialize Llama model (load once at startup)
print("Loading Llama model...")
llm = Llama(model_path=LLAMA_MODEL_PATH, n_ctx=2048, n_threads=4)
print("Llama model loaded!")

# List of YouTube channel IDs or handles
# Format: @username for handles
CHANNELS_BAK = [
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

# Test subset - top 10 channels
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

        # Get list of available transcripts
        transcript_list = api.list(video_id)

        # Try to get English transcript (manual or auto-generated)
        try:
            transcript = transcript_list.find_transcript(['en'])
        except:
            transcript = transcript_list.find_generated_transcript(['en'])

        transcript_data = transcript.fetch()

        # Combine all transcript segments into one text
        transcript_text = ' '.join([entry['text'] for entry in transcript_data])
        return (transcript_text, None)
    except IpBlocked:
        return (None, 'ip_blocked')
    except NoTranscriptFound:
        return (None, 'no_transcript')
    except TranscriptsDisabled:
        return (None, 'disabled')
    except Exception as e:
        return (None, f'error: {str(e)}')


def summarize_transcript(transcript_text, max_words=None):
    """
    Summarize a video transcript using local Llama model.

    Args:
        transcript_text: Full transcript text
        max_words: Maximum words for summary (if None, calculated based on transcript length: 500-3000 words)

    Returns:
        Summary string or error message
    """
    try:
        # Calculate dynamic summary length based on transcript length (500-3000 words)
        if max_words is None:
            # Estimate: ~150 words per minute of speech, aim for 10-20% summary ratio
            transcript_word_count = len(transcript_text.split())
            max_words = min(3000, max(500, int(transcript_word_count * 0.15)))

        # Truncate transcript if too long (to fit in context window)
        max_transcript_chars = 6000
        if len(transcript_text) > max_transcript_chars:
            transcript_text = transcript_text[:max_transcript_chars] + "..."

        prompt = f"""Summarize the following YouTube video transcript in {max_words} words.

CRITICAL FORMATTING RULES - YOU MUST FOLLOW THESE:

1. ITEMIZATION (MANDATORY): When the speaker mentions numbered points, laws, steps, rules, principles, or any list:
   - Put each item on a NEW LINE
   - Use clear numbering: 1), 2), 3), etc.
   - Add indentation before each numbered item
   - Example format:
     The speaker discusses 5 laws:
       1) First law description here
       2) Second law description here
       3) Third law description here

2. PRACTICALITY (HIGH PRIORITY): Extract and highlight ALL actionable items:
   - Specific stocks, cryptocurrencies, or assets to buy/sell
   - Trading strategies with entry/exit points
   - Foods, supplements, or products to consume/avoid
   - Step-by-step instructions (format as numbered list)
   - Tools, resources, or techniques mentioned
   - Specific recommendations or advice

3. STRUCTURE: Maintain logical flow and include key insights

FORMATTING EXAMPLE:
The video covers 3 main strategies for investing:
  1) Dollar cost averaging into index funds monthly
  2) Keep 20% cash for market corrections
  3) Diversify across 5-7 sectors

Transcript:
{transcript_text}

Summary:"""

        response = llm(
            prompt,
            max_tokens=2048,  # Increased to accommodate longer summaries
            temperature=0.7,
            stop=["Transcript:", "\n\n\n"],
            echo=False
        )

        summary = response['choices'][0]['text'].strip()
        return summary if summary else "[Unable to generate summary]"

    except Exception as e:
        return f"[Error summarizing: {str(e)[:50]}]"


def send_email_report(report_content, days_filter):
    """
    Send the YouTube video summary report via email.

    Args:
        report_content: The full report text to send
        days_filter: Number of days covered in the report

    Returns:
        Boolean indicating success or failure
    """
    if not EMAIL_ENABLED:
        print("Email sending is disabled. Set EMAIL_ENABLED=True in .env to enable.")
        return False

    if not EMAIL_USERNAME or not EMAIL_PASSWORD:
        print("Email credentials not configured. Please set EMAIL_USERNAME and EMAIL_PASSWORD in .env file.")
        return False

    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USERNAME
        msg['To'] = EMAIL_TO
        msg['Subject'] = f"Summarized youtube videos for past {days_filter} days"

        # Add report content as plain text
        msg.attach(MIMEText(report_content, 'plain'))

        # Connect to SMTP server and send email
        print(f"\nSending email report to {EMAIL_TO}...")
        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
        server.starttls()  # Enable TLS encryption
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()

        print(f"✓ Email sent successfully to {EMAIL_TO}")
        return True

    except Exception as e:
        print(f"✗ Failed to send email: {str(e)}")
        return False


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

                # Create table for this channel's videos with line separation between rows
                table = PrettyTable()
                table.field_names = ["Video ID", "Date", "Title", "Summary"]
                table.align["Video ID"] = "l"
                table.align["Date"] = "c"
                table.align["Title"] = "l"
                table.align["Summary"] = "l"
                table.max_width["Title"] = 40
                table.max_width["Summary"] = 70
                table.hrules = ALL  # Add horizontal rules between all rows for clear separation

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
    # Capture output to send via email
    output_capture = StringIO()

    # Redirect stdout to capture all print statements
    original_stdout = sys.stdout
    sys.stdout = output_capture

    try:
        # Run the main function
        main()
    finally:
        # Restore original stdout
        sys.stdout = original_stdout

    # Get the captured output
    report_content = output_capture.getvalue()

    # Print to console
    print(report_content)

    # Send email report
    send_email_report(report_content, DAYS_FILTER)
