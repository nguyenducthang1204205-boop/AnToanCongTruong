# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

University ML group project: "Xây dựng hệ thống giám sát an toàn công trường sử dụng mô hình YOLO". It fine-tunes Ultralytics YOLOv11n (`yolo11n.pt`) on a Roboflow PPE dataset. It then checks **each worker** for the 4 required items (helmet, gloves, vest, boots) and raises alerts on images, video files and live cameras. User-facing strings, comments and function names are in Vietnamese; keep that convention.

No git repo, test suite, linter, or build step exists. The original pre-refactor notebook and script are kept in `backup_goc/`.

## Environment

- Windows, local venv at `.venv` (Python 3.11, `torch 2.7.1+cu118`, `ultralytics 8.4.x`, `opencv-python`). Always use `.venv\Scripts\python.exe` (or `.venv/Scripts/python.exe` from Bash), not the system Python, which lacks these packages.
- Training and evaluation use `device="0"` (RTX 3050 6GB).
- The console defaults to cp1252. Set `PYTHONIOENCODING=utf-8` when running code that prints Vietnamese.
- The project path contains non-ASCII characters (`Học Máy`). This works because importing `ultralytics` patches `cv2.imread`/`imwrite` for unicode paths, and `cv2.VideoCapture`/`VideoWriter` also work here. `cv2.putText` cannot draw Vietnamese diacritics, so on-image text is unaccented (the rules carry a separate unaccented short name).

## Code layout

`File code chương trình nhận diện.ipynb` is the primary artifact (kernel `.venv`; run it from the project root, since `PROJECT_DIR = Path.cwd()`). [notebook_code.py](notebook_code.py) is a generated copy of its code cells with `# === CELL n ===` markers. Keep the two in sync when editing.

Notebook sections:
0. **Config:** paths, `CONF_THRESHOLD`, and the compliance rules `PPE_RULES`, `EXTRA_VIOLATIONS` and `DANGER_LABELS`.
1. **Train:** skipped when `best.pt` exists unless `RETRAIN = True`. A retrain takes about 1 hour and overwrites `runs/detect/train`.
2. **Evaluate:** `val` on the val and test splits. Results go to `runs/detect/eval_val` and `runs/detect/eval_test`.
3. **Compliance logic:** the core of the system.
   - `phan_tich_khung_hinh` runs detection and assigns each PPE/violation box to the `Person` box that contains its center. Person boxes are expanded 10%; ties go to the nearest horizontal center (`tim_cong_nhan`).
   - A worker is compliant only if all 4 "have" classes are assigned and no "lack" class is. Missing = not detected, which is a conservative rule. `bare-arms` is an extra violation.
   - `ve_ket_qua` draws the results, `ghi_nhat_ky` appends to the CSV log, and `giam_sat_video` handles file/camera streaming with a throttled alert (snapshot plus log at most once every `chu_ky_canh_bao` seconds).
4. **Images:** reads `input_PPE/*` and writes `output_PPE/<stem>_giam_sat.jpg`.
5. **Video:** reads any video in `input_PPE/` and writes `output_PPE/<stem>_giam_sat.mp4`.
6. **Camera:** guarded by `RUN_CAMERA = False`. It opens a `cv2.imshow` window; press Q or Esc to quit.

Alerts go to `output_PPE/canh_bao/*.jpg` and `output_PPE/nhat_ky_vi_pham.csv` (utf-8-sig, so it opens in Excel).

## Dataset and classes

`dataset/data.yaml` (Roboflow export, YOLO format, CC BY 4.0) has train/valid/test splits (about 5.7k/1.6k/0.9k images). It has 9 classes:
`Gloves, Helmet, Person, Safety Boot, Safety Vest, bare-arms, no-boot, no-helmet, no-vest`.

There is **no `no-gloves` class**; missing gloves is inferred from the absence of `Gloves`. Gloves and Safety Boot are the weakest classes (valid mAP50 about 0.74), and `no-boot` has few samples.

## Common commands

```powershell
# Evaluate trained weights on a split
.venv\Scripts\yolo.exe detect val model=runs/detect/train/weights/best.pt data=dataset/data.yaml split=test

# Raw Ultralytics prediction (no per-worker compliance logic)
.venv\Scripts\yolo.exe detect predict model=runs/detect/train/weights/best.pt source=input_PPE conf=0.3

# Run the whole pipeline headless via the script copy (skips training when best.pt exists; ~2 min)
$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python.exe notebook_code.py
```

`nbconvert` is not installed in the venv. When running the `.py` as a script on Windows, any Ultralytics call with DataLoader workers > 0 (train/val) re-executes the unguarded script in the spawned workers and hangs. The eval cell therefore passes `workers=0`; the train cell only works this way inside Jupyter.
