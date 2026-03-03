import cv2
import numpy as np
import torch
import os
from datetime import datetime

# ---------- Select Input Source ----------
while True:
    print("📷 Select input source:")
    print("  1 - Webcam")
    print("  2 - Video file")
    choice = input("Enter your choice (1 or 2): ").strip()

    if choice == "1":
        video_path = 0
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print("❌ Error: Webcam not found. Please check your camera and try again.")
            continue
        source_info = "webcam"
        break

    elif choice == "2":
        video_path = input("📂 Enter the video path (in quotes, e.g., \"F:\\Crowd Management\\video.mp4\"): ").strip('"')
        if not os.path.exists(video_path):
            print(f"❌ Error: The video path does not exist: {video_path}")
            continue
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"❌ Error: Could not open video: {video_path}")
            continue
        source_info = "video"
        break

    else:
        print("❗ Invalid choice. Please enter 1 for webcam or 2 for video.")

# ---------- Output Directory ----------
output_dir = r'F:\Crowd Management\data_ansh\output'
os.makedirs(output_dir, exist_ok=True)

# ---------- Unique Output File ----------
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_filename = f"heatmap_output_{timestamp}.mp4"
output_path = os.path.join(output_dir, output_filename)

# ---------- Load YOLOv5 Model ----------
print("🧠 Loading YOLOv5 model...")
model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)
model.conf = 0.4
model.classes = [0]  # Person class only

# ---------- Video Properties ----------
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

# ---------- Video Writer ----------
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

# ---------- Background Subtractor ----------
fgbg = cv2.createBackgroundSubtractorMOG2(history=1500, varThreshold=16, detectShadows=False)

# ---------- Heatmap Accumulator ----------
heatmap_acc = np.zeros((height, width), dtype=np.float32)
alpha = 0.6
sigma = 15

frame_index = 0

print("🚀 Processing started. Press 'q' to stop (for webcam)...")

while True:
    ret, frame = cap.read()
    if not ret:
        print("🛑 End of video.")
        break

    frame_index += 1
    print(f"🔄 Processing frame {frame_index}...")

    # ---------- YOLO Detection ----------
    results = model(frame)
    detections = results.xyxy[0].cpu().numpy()

    # ---------- Motion Detection ----------
    fgmask = fgbg.apply(frame)
    motion_mask = cv2.threshold(fgmask, 200, 255, cv2.THRESH_BINARY)[1]
    motion_mask = cv2.medianBlur(motion_mask, 5)

    heatmap_acc *= 0.95
    for *xyxy, conf, cls in detections:
        x1, y1, x2, y2 = map(int, xyxy)
        heatmap_acc[y1:y2, x1:x2] += 1

    heatmap_acc += (motion_mask / 255.0) * 0.5

    # ---------- Generate Heatmap Overlay ----------
    blurred = cv2.GaussianBlur(heatmap_acc, (0, 0), sigma)
    norm = cv2.normalize(blurred, None, 0, 255, cv2.NORM_MINMAX)
    heatmap_color = cv2.applyColorMap(norm.astype(np.uint8), cv2.COLORMAP_JET)
    overlay = cv2.addWeighted(frame, alpha, heatmap_color, 1 - alpha, 0)

    person_count = len(detections)
    cv2.putText(overlay, f'People: {person_count}', (15, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    out.write(overlay)

    # ---------- Show Live Feed (Webcam Only) ----------
    if source_info == "webcam":
        cv2.imshow("Live Feed", overlay)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("🛑 Exit signal received (q pressed).")
            break

cap.release()
out.release()
cv2.destroyAllWindows()
print(f"\n✅ Hybrid heatmap video saved to: {output_path}")
