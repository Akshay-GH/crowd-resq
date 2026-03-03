import cv2
import numpy as np
import torch
import os
import random
from datetime import datetime
import heapq
from pathlib import Path

# ---------- A* Pathfinding ----------
def astar(cost_map, start, end):
    rows, cols = cost_map.shape
    open_set = [(0, start)]
    came_from = {}
    g_score = {start: 0}

    def heuristic(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    while open_set:
        _, current = heapq.heappop(open_set)
        if current == end:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            return path[::-1]

        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            neighbor = (current[0] + dx, current[1] + dy)
            if 0 <= neighbor[0] < rows and 0 <= neighbor[1] < cols:
                tentative_g = g_score[current] + cost_map[neighbor]
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + heuristic(neighbor, end)
                    heapq.heappush(open_set, (f_score, neighbor))
                    came_from[neighbor] = current
    return []

# ---------- Mouse Click for Ground Points ----------
def get_four_points_from_image(image):
    points = []
    def mouse_handler(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
            points.append((x, y))
            print(f"📌 Point {len(points)}: ({x}, {y})")

    clone = image.copy()
    cv2.namedWindow("Select 4 ground points")
    cv2.setMouseCallback("Select 4 ground points", mouse_handler)
    print("💁️ Click 4 points in this order: Top-left, Top-right, Bottom-right, Bottom-left")
    print("🔔 Press any key after selecting 4 points.")
    while True:
        temp = clone.copy()
        for p in points:
            cv2.circle(temp, p, 5, (0, 255, 0), -1)
        cv2.imshow("Select 4 ground points", temp)
        if cv2.waitKey(1) & 0xFF != 255 and len(points) == 4:
            break
    cv2.destroyWindow("Select 4 ground points")
    return points

# ---------- Output Directories ----------
BASE_OUT = Path(r"F:/Crowd Management/data_ansh/output")
OUT_IMG = BASE_OUT / "out_img"
OUT_VID = BASE_OUT / "out_vid"
OUT_CAM = BASE_OUT / "out_cam"
OUT_IMG.mkdir(parents=True, exist_ok=True)
OUT_VID.mkdir(parents=True, exist_ok=True)
OUT_CAM.mkdir(parents=True, exist_ok=True)

# ---------- Input Source ----------
print("📷 Choose input:")
print("  1 - Webcam")
print("  2 - Single Image")
print("  3 - Single Video")
print("  4 - Folder of Images")
print("  5 - Folder of Videos")
choice = input("Enter choice: ").strip()

input_type = None
input_paths = []
output_folder = None

if choice == "1":
    input_type = "webcam"
    input_paths = [0]
    output_folder = OUT_CAM
elif choice == "2":
    path = input("Enter image path: ").strip('"')
    if os.path.isfile(path):
        input_type = "image"
        input_paths = [path]
        output_folder = OUT_IMG
elif choice == "3":
    path = input("Enter video path: ").strip('"')
    if os.path.isfile(path):
        input_type = "video"
        input_paths = [path]
        output_folder = OUT_VID
elif choice == "4":
    folder = input("Enter folder path with images: ").strip('"')
    if os.path.isdir(folder):
        input_type = "image_folder"
        input_paths = sorted(list(Path(folder).glob("*.jpg")) + list(Path(folder).glob("*.png")))
        output_folder = OUT_IMG / f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_folder.mkdir(parents=True, exist_ok=True)
elif choice == "5":
    folder = input("Enter folder path with videos: ").strip('"')
    if os.path.isdir(folder):
        input_type = "video_folder"
        input_paths = sorted(list(Path(folder).glob("*.mp4")) + list(Path(folder).glob("*.avi")))
        output_folder = OUT_VID / f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_folder.mkdir(parents=True, exist_ok=True)
else:
    print("❌ Invalid choice.")
    exit()

# ---------- Load YOLOv5 ----------
print("🧠 Loading YOLOv5...")
model = torch.hub.load('ultralytics/yolov5', 'custom', path='yolov5s.pt', force_reload=False)
model.conf = 0.4
model.classes = [0]

# ---------- Background Subtraction ----------
fgbg = cv2.createBackgroundSubtractorMOG2(history=1500, varThreshold=16, detectShadows=False)

# ---------- Processing Frame ----------
def process_frame(frame, heatmap_acc, H, H_inv, grid_size=20, alpha=0.6, sigma=15):
    results = model(frame)
    detections = results.xyxy[0].cpu().numpy()

    fgmask = fgbg.apply(frame)
    motion_mask = cv2.threshold(fgmask, 200, 255, cv2.THRESH_BINARY)[1]
    motion_mask = cv2.medianBlur(motion_mask, 5)

    heatmap_acc *= 0.95
    for *xyxy, conf, cls in detections:
        x1, y1, x2, y2 = map(int, xyxy)
        heatmap_acc[y1:y2, x1:x2] += 1

    motion_mask_resized = cv2.resize(motion_mask, (heatmap_acc.shape[1], heatmap_acc.shape[0]))
    heatmap_acc += (motion_mask_resized / 255.0) * 0.5

    blurred = cv2.GaussianBlur(heatmap_acc, (0, 0), sigma)
    norm = cv2.normalize(blurred, None, 0, 255, cv2.NORM_MINMAX)
    heatmap_color = cv2.applyColorMap(norm.astype(np.uint8), cv2.COLORMAP_JET)
    overlay = cv2.addWeighted(frame, alpha, heatmap_color, 1 - alpha, 0)

    warp_width, warp_height = 640, 480
    warped_heatmap = cv2.warpPerspective(norm, H, (warp_width, warp_height))
    resized_cost = cv2.resize(warped_heatmap, (grid_size, grid_size))
    cost_map = resized_cost.astype(np.float32) + 1

    start, end = (grid_size - 1, 0), (0, 0)
    path = astar(cost_map, start, end)

    for i in range(len(path) - 1):
        y1, x1 = path[i]
        y2, x2 = path[i + 1]
        wx1 = int((x1 + 0.5) * warp_width / grid_size)
        wy1 = int((y1 + 0.5) * warp_height / grid_size)
        wx2 = int((x2 + 0.5) * warp_width / grid_size)
        wy2 = int((y2 + 0.5) * warp_height / grid_size)
        pt1 = cv2.perspectiveTransform(np.array([[[wx1, wy1]]], dtype=np.float32), H_inv)[0][0].astype(int)
        pt2 = cv2.perspectiveTransform(np.array([[[wx2, wy2]]], dtype=np.float32), H_inv)[0][0].astype(int)
        cv2.circle(overlay, tuple(pt1), 2, (0,255,0), -1)
        if i % 5 == 0:
            cv2.arrowedLine(overlay, tuple(pt1), tuple(pt2), (0,255,0), 2, tipLength=0.4)
    return overlay, heatmap_acc

# ---------- Get Ground Points ----------
if input_type in ["video", "video_folder", "webcam"]:
    cap = cv2.VideoCapture(str(input_paths[0]))
    while True:
        ret, preview_frame = cap.read()
        if not ret:
            print("❌ Failed to read frame.")
            exit()
        cv2.imshow("Preview", preview_frame)
        print("Press 's' to select points")
        if cv2.waitKey(0) == ord('s'):
            break
    cv2.destroyWindow("Preview")
else:
    preview_frame = cv2.imread(str(input_paths[0]))

ground_points = get_four_points_from_image(preview_frame)
src_pts = np.array(ground_points, dtype=np.float32)
dst_pts = np.array([[0,0],[639,0],[639,479],[0,479]], dtype=np.float32)
H = cv2.getPerspectiveTransform(src_pts, dst_pts)
H_inv = np.linalg.inv(H)

# ---------- Main Processing ----------
for path in input_paths:
    # heatmap_acc = np.zeros((720, 1280), dtype=np.float32)
    frame = cv2.imread(str(path))
    h, w = frame.shape[:2]
    heatmap_acc = np.zeros((h, w), dtype=np.float32)
    rand = random.randint(1000, 9999)

    if input_type in ["image", "image_folder"]:
        frame = cv2.imread(str(path))
        overlay, _ = process_frame(frame, heatmap_acc, H, H_inv)
        outname = output_folder / f"hm_img_{rand}.jpg"
        cv2.imwrite(str(outname), overlay)
        print(f"✅ Saved: {outname}")

    elif input_type in ["video", "video_folder"]:
        cap = cv2.VideoCapture(str(path))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        outname = output_folder / f"hm_vid_{rand}.mp4"
        out = cv2.VideoWriter(str(outname), cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            overlay, heatmap_acc = process_frame(frame, heatmap_acc, H, H_inv)
            out.write(overlay)
        cap.release()
        out.release()
        print(f"✅ Saved: {outname}")

    elif input_type == "webcam":
        cap = cv2.VideoCapture(0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = 25
        outname = output_folder / f"gm_cam_{rand}.mp4"
        out = cv2.VideoWriter(str(outname), cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            overlay, heatmap_acc = process_frame(frame, heatmap_acc, H, H_inv)
            out.write(overlay)
            cv2.imshow("Live", overlay)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        cap.release()
        out.release()
        print(f"✅ Saved: {outname}")

cv2.destroyAllWindows()
print("🎉 All done!")
