"""
Module for downloading YouTube videos using yt-dlp.
"""
from pathlib import Path
from yt_dlp import YoutubeDL

def download_video(url: str, quality: str = "medium", output_path: str = "downloads/video.mp4") -> str:
    """
    Downloads a YouTube video and saves it to the specified path.
    
    Args:
        url (str): YouTube video URL
        quality (str): Video quality ('low', 'medium', or 'high')
        output_path (str): Path where the video will be saved
        
    Returns:
        str: Path to the downloaded video file
    """
    # Ensure the output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Define format based on quality parameter
    if quality == "low":
        format_option = "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best"
    elif quality == "medium":
        format_option = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best"
    else:  # high quality (default)
        format_option = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    
    ydl_opts = {
        'format': format_option,
        'outtmpl': output_path,
        'quiet': False,  # Show progress
        'no_warnings': True,
        'extract_flat': False,
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return output_path
    except Exception as e:
        raise Exception(f"Failed to download video: {str(e)}")
