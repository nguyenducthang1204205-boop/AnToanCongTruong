# === CELL 1 ===
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

import cv2
from ultralytics import YOLO

PROJECT_DIR = Path.cwd()
DATASET_DIR = PROJECT_DIR / "dataset"
DATA_YAML = DATASET_DIR / "data.yaml"
WEIGHTS_PATH = PROJECT_DIR / "yolo11n.pt"
RUNS_DIR = PROJECT_DIR / "runs" / "detect"
OUTPUT_DIR = PROJECT_DIR / "output_PPE"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DANGER_LABELS = {"no-helmet", "no-vest", "no-boot", "bare-arms", "non-helmet"}

print(f"Project: {PROJECT_DIR}")
print(f"Dataset config: {DATA_YAML}")
print(f"Weights: {WEIGHTS_PATH}")

# === CELL 2 ===
import ultralytics
print(f"Ultralytics: {ultralytics.__version__}")

required_paths = [
    DATA_YAML,
    DATASET_DIR / "train" / "images",
    DATASET_DIR / "train" / "labels",
    DATASET_DIR / "valid" / "images",
    DATASET_DIR / "valid" / "labels",
]
for path in required_paths:
    print(f"{'OK' if path.exists() else 'MISSING'}: {path}")

# === CELL 3 ===
if not WEIGHTS_PATH.exists():
    raise FileNotFoundError(
        f"Chưa tìm thấy {WEIGHTS_PATH}. Hãy đặt yolo11n.pt vào thư mục dự án "
        "hoặc dùng đường dẫn trọng số khác."
    )

model_v11 = YOLO(str(WEIGHTS_PATH))
print("Đã tải mô hình YOLOv11n.")

# === CELL 4 ===
if not DATA_YAML.exists():
    raise FileNotFoundError(f"Chưa tìm thấy file cấu hình: {DATA_YAML}")

train_results = model_v11.train(
    data=str(DATA_YAML),
    task="detect",
    imgsz=640,
    epochs=50,
    project=str(RUNS_DIR),
    name="train",
    exist_ok=True,
    device=0,
)

BEST_WEIGHTS = RUNS_DIR / "train" / "weights" / "best.pt"
LAST_WEIGHTS = RUNS_DIR / "train" / "weights" / "last.pt"
print(f"Best weights: {BEST_WEIGHTS}")
print(f"Last weights: {LAST_WEIGHTS}")

# === CELL 5 ===
# Đặt ảnh cần nhận diện vào thư mục input_PPE trước khi chạy ô này.
IMAGE_DIR = PROJECT_DIR / "input_PPE"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

image_paths = sorted(
    path for path in IMAGE_DIR.iterdir()
    if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
)

if not image_paths:
    print(f"Chưa có ảnh trong {IMAGE_DIR}")
else:
    image_model = YOLO(str(BEST_WEIGHTS if BEST_WEIGHTS.exists() else WEIGHTS_PATH))
    for image_path in image_paths:
        results = image_model.predict(source=str(image_path), conf=0.25, verbose=False)
        annotated = results[0].orig_img.copy()
        for box in results[0].boxes:
            class_id = int(box.cls.item())
            confidence = float(box.conf.item())
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            label = image_model.names[class_id]
            color = (0, 0, 255) if label.lower() in DANGER_LABELS else (0, 180, 0)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
            text = f"{label} {confidence:.2f}"
            cv2.putText(annotated, text, (x1, max(25, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        output_path = OUTPUT_DIR / f"{image_path.stem}_predicted.jpg"
        cv2.imwrite(str(output_path), annotated)
        print(f"Đã lưu: {output_path}")

# === CELL 6 ===
VIDEO_PATH = PROJECT_DIR / "input_PPE" / "input.mp4"
VIDEO_OUTPUT = OUTPUT_DIR / "output_video.mp4"

if not VIDEO_PATH.exists():
    print(f"Chưa có video đầu vào: {VIDEO_PATH}")
else:
    video_model = YOLO(str(BEST_WEIGHTS if BEST_WEIGHTS.exists() else WEIGHTS_PATH))
    capture = cv2.VideoCapture(str(VIDEO_PATH))
    if not capture.isOpened():
        raise RuntimeError(f"Không thể mở video: {VIDEO_PATH}")

    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    writer = cv2.VideoWriter(
        str(VIDEO_OUTPUT),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )

    frame_count = 0
    while True:
        success, frame = capture.read()
        if not success:
            break
        result = video_model.predict(source=frame, conf=0.25, verbose=False)[0]
        annotated = result.orig_img.copy()
        for box in result.boxes:
            class_id = int(box.cls.item())
            confidence = float(box.conf.item())
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            label = video_model.names[class_id]
            color = (0, 0, 255) if label.lower() in DANGER_LABELS else (0, 180, 0)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
            cv2.putText(annotated, f"{label} {confidence:.2f}",
                        (x1, max(25, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, color, 2)
        writer.write(annotated)
        frame_count += 1

    capture.release()
    writer.release()
    print(f"Đã xử lý {frame_count} frame và lưu: {VIDEO_OUTPUT}")

