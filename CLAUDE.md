# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

University ML group project: "Xây dựng hệ thống giám sát an toàn công trường sử dụng mô hình YOLO". It fine-tunes Ultralytics YOLOv11n (`yolo11n.pt`) on a Roboflow PPE dataset. It then checks **each worker** for the 4 required items (helmet, gloves, vest, boots) and raises alerts on images, video files and live cameras. User-facing strings, comments and function names are in Vietnamese; keep that convention.

No test suite, linter, or build step exists.

## Environment

- Windows, local venv at `.venv` (Python 3.11, `torch 2.7.1+cu118`, `ultralytics 8.4.x`, `opencv-python`, `customtkinter` for the GUI). Always use `.venv\Scripts\python.exe` (or `.venv/Scripts/python.exe` from Bash), not the system Python, which lacks these packages.
- Training and evaluation use `device="0"` (RTX 3050 6GB).
- Since 2026-10-09, Windows **Smart App Control** has been enforcing (`HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy` `VerifiedAndReputablePolicyState` = 1). It blocks DLLs in `.venv` ("An Application Control policy has blocked this file", WinError 4551), so `torch`, `ultralytics` and `pandas` fail to import and `.venv\Scripts\*.exe` launchers give "Permission denied". Nothing local that needs torch runs until the user turns Smart App Control off. That is the user's security decision; never change it yourself.
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

### GUI (`giao_dien.py`)

A CustomTkinter desktop app: `.venv\Scripts\python.exe giao_dien.py`. It needs `customtkinter` (installed in `.venv`; on another machine run `pip install customtkinter`). It does **not** duplicate the compliance logic. At startup it execs cells 1 and 5 of `notebook_code.py` into a module namespace (`nap_logic_notebook`), so edits to those cells take effect in the GUI. Renumbering or removing those cells breaks it.
- Layout:
  - Left column: a mode selector (Ảnh / Video / Camera). Each mode has its own panel. Below it are the detection settings: conf and alert-cycle sliders, plus sound and draw-box switches.
  - Center: the annotated display, a progress bar and context controls. Image mode shows prev/next and stop. Video/camera mode shows pause/resume, end and replay.
  - Right column: the status banner, 4 counters, the per-worker ✔/✘ table and the latest-alert thumbnail.
  - Bottom: the alert log, preloaded from the CSV. Double-click a row to open its snapshot.
  - Header: a light/dark theme switch.
- Look matches the web version: slate + safety orange, Be Vietnam Pro loaded privately from `assets/fonts/` (`nap_font`, falls back to Segoe UI; must run before the first font is created), appearance follows Windows by default. Icons are glyphs of the Windows icon font (Segoe Fluent Icons / MDL2, codepoints in `IC`) rendered to `CTkImage` by `icon()`; the logo is drawn by `ve_mu_bao_ho`. No emoji in UI text.
- The right column has a **fixed width** (`grid_propagate(False)`) and the canvas only redraws on a real size change (`_doi_co_canvas`). Otherwise per-frame text changes (FPS, frame counts) resize the columns and force a full relayout plus a second canvas redraw on every frame, which halved the displayed frame rate. Frames are scaled with `cv2.resize` (PIL resize cost ~40 ms per 1080p frame on the UI thread).
- Colors live in `MAU` as `(light, dark)` tuples. CTk widgets switch automatically. The ttk Treeviews and the display `tk.Canvas` do not, so `_ap_dung_mau_ttk` restyles them via `_c()` when the theme changes. ttk/Canvas sizes are multiplied by `self.s` (CTk widget scaling); CTk widget sizes, `wraplength` and `CTkImage` sizes must not be.
- Vertical space is tight at 1920×1080 with 125% scaling. Check screenshots after adding widgets to the side columns. A `CTkScrollbar` needs an explicit small `height`, because its 200 px default stretches the tables.
- Threading:
  - One worker thread runs inference. It hands the newest frame to the UI through a locked slot (frames can be dropped) and sends alerts/done/errors through a `queue.Queue` (never dropped).
  - The worker reads plain attributes (`self.conf`, `self.chu_ky`, `self.ve_trang_bi`, `self.dung_toc_do`), never Tk variables.
  - Pause is `pause_event`: the loop idles (camera keeps calling `grab()` to drain stale frames). End is `stop_event`.
- `_luong_video` mirrors the notebook's `giam_sat_video` (same throttle, snapshot and log format), plus pause and optional real-time pacing. Keep the two in step. Camera recordings are saved as `output_PPE/camera_<timestamp>_giam_sat.mp4`.

### Web version for Streamlit Community Cloud (`streamlit_app/`), the deployed one

A self-contained, CPU-only Streamlit app. It is deployed from its **own GitHub repo**, https://github.com/nguyenducthang1204205-boop/AnToanCongTruong-web (main file `streamlit_app.py`, Python 3.12). To update it, copy the contents of `streamlit_app/` into a clone of that repo, then commit and push; Community Cloud redeploys on push. The repo root is the contents of `streamlit_app/` because Community Cloud requires `packages.txt` at the repo root, and the main repo carries a ~935 MB dataset. Like the desktop GUI, it execs cells 1 and 5 of its own `notebook_code.py` copy.
- Look: industrial slate + safety orange, font Be Vietnam Pro, light and dark palettes in `.streamlit/config.toml` (`[theme.light]`/`[theme.dark]`; config is read only at server start). Icons are Material (`:material/…:`) or inline Lucide SVG, not emoji. `st.context.theme` can be wrong on first load, so custom HTML (header, status banner `the_trang_thai`, sidebar legend, table tints) must read correctly on both backgrounds: solid fills with white text or translucent rgba tints. KPI rows use `st.container(horizontal=True)` so they stay in one row on phones.
- Two pages via `st.navigation(position="top")`: `trang_giam_sat` (image/video/camera tabs, sidebar settings) and `trang_mo_hinh` (model analytics). Both open with `hero()`, a dark banner that is identical in both themes.
- Charts are Altair, built in `streamlit_app/bieu_do.py`. Series colors come from `chartCategoricalColors` in the theme config (validated with the dataviz palette checker on both surfaces), so charts pass only a `domain` order, never hex. Vega expressions must use `datum['…']` because field names are Vietnamese. Numbers use a decimal comma (`PHAN_TRAM_VN`, `SO_VN`). Video results also store `dien_bien` (time, workers, violators per model run; charted per second, max) and `dem_thieu` (missing-item counts). The video section "Mô hình trên video này" (`mo_hinh_tren_video`) uses `phan_tich_ghi_lai`, which wraps the model in `GhiPhatHien` to keep raw (class, confidence) pairs and inference ms per run without changing the notebook; results also store `phat_hien`, `thoi_gian_suy_luan`, `thieu_theo_lan`, `ty_le_tuan_thu` and `ban_do_nhiet` (a JPEG: violators' foot positions blurred over the frame with the most violators). Uploaded videos have no ground truth, so this section shows **confidence, never accuracy**, and says so on the page; real P/R/mAP live on the model page. Altair charts in Streamlit use autosize "fit", so a chart's `height` includes its axes and bottom legend: add room for them or the plot collapses.
- Model data on that page is real: `DANH_GIA` (per-class P/R/mAP from the notebook's val/test output), `PHAN_BO` (label counts from `dataset/*/labels`), and `assets/mo_hinh/` (copies of `runs/detect/train/results.csv`, `results.png` and the eval_val/eval_test plots). Update them all after retraining.
- `streamlit_app/notebook_code.py` and `streamlit_app/runs/detect/train/weights/best.pt` are **copies**. Re-copy both after changing the notebook logic or retraining.
- On a push, Community Cloud reruns the new `streamlit_app.py` but keeps already-imported local modules in memory, so `streamlit_app.py` calls `importlib.reload(bd)` on every run. Without it, an update that touches `bieu_do.py` shows stale numbers or raises `AttributeError` until the app is rebooted. To check the live app headlessly, open `https://<app>.streamlit.app/~/+/<page>` (the bare URL wraps the app in an iframe).
- `requirements.txt` pulls CPU-only torch via `--extra-index-url https://download.pytorch.org/whl/cpu`. Free apps get as little as 690 MB RAM.
- The model is loaded once per server (`st.cache_resource`) and shared by all sessions behind a `threading.Lock`. Image results are cached by `(bytes, conf)` with `st.cache_data`. Video results live in `st.session_state`.
- Video: the whole video is analyzed and every frame is written at the source fps, so the output is exactly as long as the input (the 30 s cap was removed at the user's request; the caption estimates CPU time, roughly 2–6× the video length at 4 analyses/s). The temp dir is deleted afterwards. Frames are downscaled to at most 960 px. The model runs `khung_moi_giay` times per second, and in-between frames redraw the last report so playback stays smooth. The output is transcoded to H.264 with the ffmpeg bundled in `imageio-ffmpeg`.
- Video tab: the original upload is shown next to the result. The two `st.video` sit in `st.container(key="video_goc"/"video_ket_qua")`, and an invisible components-v2 component (`DONG_BO_VIDEO_JS`, it runs in the page, not an iframe) finds both `<video>` tags by their `st-key-…` class and mirrors play/pause/seek/rate between them, re-syncing the result to the original when drift exceeds 0.3 s. The result video is `muted` (it has no audio). `ban_xem_truoc` transcodes it to H.264 when the browser can't play it (mp4v, .avi, .mkv, HEVC). It is cached by `file_id`.
- Camera tab has two modes sharing one `GiamSatCamera` state object in `st.session_state` (same alert throttle and log format as the notebook):
  - **A, live:** `streamlit-webrtc` (`webrtc_streamer`). `GiamSatCamera.xu_ly_khung_webrtc` runs on the webrtc worker thread. It runs the model `khung_moi_giay` times per second and redraws the last report in between. The status panel is a `@st.fragment(run_every=1.0)`.
  - On Community Cloud, STUN alone does **not** carry media, so a TURN server is required. If `st.secrets["ice_servers"]` is set, it is passed explicitly. Otherwise `rtc_configuration=None` lets streamlit-webrtc pick TURN itself from the env vars `CLOUDFLARE_TURN_KEY_ID`/`CLOUDFLARE_TURN_KEY_API_TOKEN`, `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN` or `HF_TOKEN` (free HF TURN, 10 GB/month); Community Cloud exposes root-level secrets as env vars. If none is set, it falls back to Google STUN.
  - `nguon_ice()` shows which source is active. If the webrtc callback has received no frames 8 s after Start (`so_khung_webrtc == 0`), the panel shows a warning and a button that switches to mode B.
  - **B, fallback:** an inline `st.components.v2` component (`CAMERA_TU_CHUP_JS`). It grabs a webcam frame every second and sends it as a JPEG data URL trigger value. It lives inside an `@st.fragment`, so each frame reruns only that fragment.
- `AppTest` cannot run the camera tab (webrtc needs a real runtime). Test in a browser instead: headless Edge with `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream --use-file-for-fake-video-capture=<file>.y4m`, driven over the DevTools protocol. Button text in the webrtc iframe is uppercased by CSS, so match it case-insensitively.
- Local test: `.venv\Scripts\streamlit.exe run streamlit_app\streamlit_app.py` (streamlit and streamlit-webrtc are installed in `.venv`). A local run creates `input_PPE/`, `output_PPE/` and `__pycache__/` inside the folder (gitignored).
- To simulate the CPU-only server locally, monkeypatch `torch.cuda.is_available = lambda: False`. Do not set `CUDA_VISIBLE_DEVICES=""`: with the CUDA torch build, Ultralytics then crashes with "Invalid device id".

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

# Desktop GUI (image / video / camera monitoring with live alerts)
.venv\Scripts\python.exe giao_dien.py

# Run the whole pipeline headless via the script copy (skips training when best.pt exists; ~2 min)
$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python.exe notebook_code.py
```

`nbconvert` is not installed in the venv. When running the `.py` as a script on Windows, any Ultralytics call with DataLoader workers > 0 (train/val) re-executes the unguarded script in the spawned workers and hangs. The eval cell therefore passes `workers=0`; the train cell only works this way inside Jupyter.
