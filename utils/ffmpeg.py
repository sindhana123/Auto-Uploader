import asyncio
import os
import re
import json

async def run_cmd(cmd):
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return stdout.decode(), stderr.decode(), process.returncode

async def get_video_resolution(file_path):
    cmd = f'ffprobe -v error -select_streams v -show_entries stream=width,height:stream_disposition=attached_pic -of json "{file_path}"'
    stdout, _, rc = await run_cmd(cmd)
    if rc == 0:
        try:
            data = json.loads(stdout)
            streams = data.get('streams', [])
            non_attached = [s for s in streams if s.get('disposition', {}).get('attached_pic', 0) != 1]
            candidate_streams = non_attached if non_attached else streams
            
            if not candidate_streams:
                return "Unknown"
                
            best_stream = max(candidate_streams, key=lambda s: int(s.get('height') or 0))
            height = int(best_stream.get('height') or 0)
            
            if not height:
                return "Unknown"
            
            # Simple logic to determine common resolutions
            if height <= 480:
                return "480p"
            elif height <= 720:
                return "720p"
            elif height <= 1080:
                return "1080p"
            else:
                return f"{height}p"
        except Exception:
            return "Unknown"
    return "Unknown"

async def strip_and_mux_audio(video_path, audio_path, output_path):
    # -map 0:v (video)
    # -map 1:a (audio)
    # -map 0:s? (subtitles optional)
    # -map 0:t? (fonts/attachments optional)
    cmd = f'ffmpeg -y -i "{video_path}" -i "{audio_path}" -map 0:v -map 1:a -map 0:s? -map 0:t? -c copy "{output_path}"'
    stdout, stderr, rc = await run_cmd(cmd)
    if rc != 0:
        print(f"ffmpeg failed with exit status {rc}. Retrying with stream-specific map...")
        cmd_fallback = f'ffmpeg -y -i "{video_path}" -i "{audio_path}" -map 0:v:0 -map 1:a:0 -map 0:s? -map 0:t? -c copy "{output_path}"'
        stdout, stderr, rc = await run_cmd(cmd_fallback)
        if rc != 0:
            print(f"ffmpeg fallback failed. STDOUT: {stdout} | STDERR: {stderr}")
    return rc == 0

async def extract_thumbnail(video_path, output_path):
    # Extract frame at 2 seconds
    cmd = f'ffmpeg -y -ss 00:00:02 -i "{video_path}" -vframes 1 -q:v 2 "{output_path}"'
    _, _, rc = await run_cmd(cmd)
    return rc == 0

async def get_media_info(file_path):
    cmd = f'ffprobe -v quiet -print_format json -show_format -show_streams "{file_path}"'
    stdout, _, rc = await run_cmd(cmd)
    if rc == 0:
        try:
            return json.loads(stdout)
        except Exception:
            pass
    return {}

async def extract_stream(video_path, stream_index, output_path):
    # e.g. stream_index = "0:a:1"
    cmd = f'ffmpeg -y -i "{video_path}" -map 0:{stream_index} -c copy "{output_path}"'
    _, _, rc = await run_cmd(cmd)
    return rc == 0
