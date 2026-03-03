import cv2
import numpy as np
import torch
from pytube import YouTube
import os

# ---------- Function to Download YouTube Video ----------
def download_video(youtube_url, download_path):
    try:
        yt = YouTube(youtube_url)
        print(f"Available streams for {yt.title}:")
        
        # List all available streams (with details)
        streams = yt.streams.filter(file_extension='mp4')
        for stream in streams:
            print(f"Stream details: {stream} | Resolution: {stream.resolution} | Codec: {stream.video_codec} | Type: {stream.mime_type}")
        
        # Select the highest resolution stream
        stream = yt.streams.filter(progressive=True, file_extension='mp4').get_highest_resolution()

        if not stream:
            print("No progressive streams available, trying to select separately.")
            # If no progressive stream available, try to select video-only and audio-only streams
            video_stream = yt.streams.filter(file_extension='mp4', only_video=True).get_highest_resolution()
            audio_stream = yt.streams.filter(file_extension='mp4', only_audio=True).first()
            if video_stream and audio_stream:
                print(f"Downloading video-only stream: {video_stream} and audio-only stream: {audio_stream}")
                video_file = video_stream.download(download_path)
                audio_file = audio_stream.download(download_path)
                return video_file, audio_file
            else:
                raise ValueError("No suitable video or audio streams found.")

        print(f"Downloading {yt.title}...")
        stream.download(download_path)
        return os.path.join(download_path, stream.default_filename)

    except Exception as e:
        print(f"Error downloading video: {str(e)}")
        return None
# def download_video(youtube_url, download_path):
#     try:
#         yt = YouTube(youtube_url)
#         # Get the highest resolution stream available
#         stream = yt.streams.filter(progressive=True, file_extension='mp4').first()
#         if stream is None:
#             raise ValueError("No suitable video stream found.")
#         print(f"Downloading {yt.title}...")
#         stream.download(download_path)
#         return os.path.join(download_path, stream.default_filename)
#     except Exception as e:
#         print(f"Error downloading video: {str(e)}")
#         return None
    
# ---------- YouTube Video URL and Download Path ----------
youtube_url = 'https://www.youtube.com/watch?v=P0wNIsAjht8'  # Replace with your video URL
download_path = r'F:\Crowd Management\heat_map\heat_map\download_v'  # Change to where you want to save the video

# Download the video
video_path = download_video(youtube_url, download_path)
print(f"Downloaded video: {video_path}")

# ---------- Load YOLOv5 Model ----------
model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)
model.conf = 0.4
model.classes = [0]  # person class only

# ---------- Video Input/Output ----------
cap = cv2.VideoCapture(video_path)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS)

fourcc = cv2.VideoWriter_fourcc(*'mp4v')
output_path = r'F:\Crowd Management\heat_map\heat_map\output\heatmap_hybrid_output.mp4'
out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

# ---------- Background Subtractor ----------
fgbg = cv2.createBackgroundSubtractorMOG2(history=1500, varThreshold=16, detectShadows=False)

# ---------- Heatmap Accumulator ----------
heatmap_acc = np.zeros((height, width), dtype=np.float32)
alpha = 0.6  # overlay transparency
sigma = 15   # for blur

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # ---------- YOLO Detection ----------
    results = model(frame)
    detections = results.xyxy[0].cpu().numpy()

    # ---------- Motion Detection ----------
    fgmask = fgbg.apply(frame)
    motion_mask = cv2.threshold(fgmask, 200, 255, cv2.THRESH_BINARY)[1]
    motion_mask = cv2.medianBlur(motion_mask, 5)

    decay_rate = 0.95  # Lower = faster fade, try 0.90 for even quicker
    heatmap_acc *= decay_rate
    # ---------- Update Heatmap from YOLO ----------
    for *xyxy, conf, cls in detections:
        x1, y1, x2, y2 = map(int, xyxy)
        heatmap_acc[y1:y2, x1:x2] += 1

    # ---------- Update Heatmap from Motion ----------
    heatmap_acc += (motion_mask / 255.0) * 0.5

    # ---------- Generate Heatmap Overlay ----------
    blurred = cv2.GaussianBlur(heatmap_acc, (0, 0), sigma)
    norm = cv2.normalize(blurred, None, 0, 255, cv2.NORM_MINMAX)
    heatmap_color = cv2.applyColorMap(norm.astype(np.uint8), cv2.COLORMAP_JET)
    overlay = cv2.addWeighted(frame, alpha, heatmap_color, 1 - alpha, 0)

    # ---------- Show Count ----------
    person_count = len(detections)
    cv2.putText(overlay, f'People: {person_count}', (15, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    out.write(overlay)

cap.release()
out.release()
cv2.destroyAllWindows()
print(f"✅ Hybrid heatmap video saved to: {output_path}")
