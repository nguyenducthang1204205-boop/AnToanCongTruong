"""Giao diện chương trình giám sát an toàn công trường (YOLOv11 + CustomTkinter).

Chạy từ thư mục dự án:
    .venv\\Scripts\\python.exe giao_dien.py

Ba chế độ: giám sát ẢNH, VIDEO (tạm dừng / tiếp tục / phát lại) và CAMERA (webcam hoặc RTSP/HTTP).
Logic nhận diện và kiểm tra 4 trang bị bảo hộ được nạp trực tiếp từ notebook_code.py
(cell 1: cấu hình, cell 5: logic tuân thủ), nên giao diện luôn dùng đúng quy tắc của notebook.
"""
import csv
import os
import queue
import sys
import threading
import time
import types
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import tkinter.font as tkfont

import customtkinter as ctk
import cv2
from PIL import Image, ImageDraw, ImageFont, ImageTk

for stream in (sys.stdout, sys.stderr):  # console Windows mặc định cp1252, không in được tiếng Việt
    if stream is not None and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

APP_DIR = Path(__file__).resolve().parent
os.chdir(APP_DIR)  # notebook dùng PROJECT_DIR = Path.cwd()

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv")

# Mỗi màu là (giao diện sáng, giao diện tối). Cùng bảng màu với bản web (streamlit_app/.streamlit/config.toml):
# xám công nghiệp + cam an toàn. Màu nền đặc của băng trạng thái giống nhau ở hai giao diện để chữ trắng luôn đọc rõ.
MAU = {
    "nen": ("#f8fafc", "#0b1220"), "the": ("#ffffff", "#111a2b"), "the2": ("#eef2f6", "#172235"),
    "vien": ("#d5dce5", "#2a3a52"), "chu": ("#0f172a", "#e2e8f0"), "phu": ("#475569", "#94a3b8"),
    "man_hinh": ("#e2e8f0", "#060b14"),
    "cam": ("#c2410c", "#ea580c"), "cam_dam": ("#9a3412", "#c2410c"), "cam_chu": ("#c2410c", "#fb923c"),
    "xanh": ("#15803d", "#15803d"), "xanh_dam": ("#166534", "#166534"), "xanh_chu": ("#15803d", "#4ade80"),
    "do": ("#b91c1c", "#b91c1c"), "do_dam": ("#7f1d1d", "#7f1d1d"), "do_chu": ("#dc2626", "#f87171"),
    "vang": ("#b45309", "#b45309"), "xam": ("#475569", "#475569"),
    "phu_nut": ("#e2e8f0", "#1f2c42"), "phu_nut_hover": ("#cbd5e1", "#2a3a52"),
    "chon": ("#fed7aa", "#c2410c"), "chon_hover": ("#fdba74", "#9a3412"),  # mục đang chọn của nút chọn chế độ
    # nền nhạt của dòng trong bảng công nhân (Treeview không có màu trong suốt nên trộn sẵn với màu "the2")
    "nen_dat": ("#dcf1e3", "#15301f"), "nen_loi": ("#fbe0e0", "#3b1a22"),
}
CHE_DO = ("Ảnh", "Video", "Camera")
LOAI_CHE_DO = ("anh", "video", "camera")
FONT_DIR = APP_DIR / "assets" / "fonts"

# Biểu tượng lấy từ font Segoe Fluent Icons (Windows 11) / Segoe MDL2 Assets (Windows 10), thay cho emoji.
FILE_ICON = next((p for p in (Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / ten
                              for ten in ("SegoeIcons.ttf", "segmdl2.ttf")) if p.exists()), None)
IC = {"anh": "\uE91B", "video": "\uE714", "camera": "\uE722", "thu_muc": "\uE8B7", "tai_lieu": "\uE8A5",
      "canh_bao": "\uE7BA", "play": "\uE768", "pause": "\uE769", "stop": "\uE71A", "phat_lai": "\uE72C",
      "truoc": "\uE76B", "sau": "\uE76C", "dat": "\uE930", "nguoi": "\uE77B", "cho": "\uE916"}


def nap_font():
    """Nạp Be Vietnam Pro (giống bản web) từ assets/fonts cho riêng tiến trình này; thiếu file thì dùng Segoe UI."""
    try:
        if all(ctk.FontManager.load_font(str(FONT_DIR / f"BeVietnamPro-{kieu}.ttf")) for kieu in ("Regular", "Bold")):
            return "Be Vietnam Pro"
    except Exception:
        pass
    return "Segoe UI"


def ve_icon(ky_tu, mau, co):
    """Vẽ một biểu tượng của font icon Windows thành ảnh RGBA (vẽ to gấp 4 rồi để CTkImage thu nhỏ cho nét)."""
    s = co * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((s / 2, s / 2), ky_tu, font=ImageFont.truetype(str(FILE_ICON), round(s * 0.78)),
                             fill=mau, anchor="mm")
    return img


def ve_mu_bao_ho(mau, co):
    """Logo mũ bảo hộ (theo biểu tượng hard-hat của Lucide, lưới 24×24, nét 2)."""
    s = co * 4
    k, net = s / 24, round(s / 12)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2 * k, 15 * k, 22 * k, 19.5 * k], radius=k, outline=mau, width=net)   # vành mũ
    d.arc([4 * k, 6 * k, 20 * k, 24 * k], 180, 360, fill=mau, width=net)                      # vòm mũ
    d.rounded_rectangle([10 * k, 4 * k, 14 * k, 11 * k], radius=k, outline=mau, width=net)    # gờ giữa
    return img


def icon(ky_tu, mau, co=18):
    """CTkImage của biểu tượng; `mau` là (sáng, tối) hoặc một màu. Không có font icon thì trả về None."""
    if FILE_ICON is None:
        return None
    sang, toi = mau if isinstance(mau, tuple) else (mau, mau)
    return ctk.CTkImage(light_image=ve_icon(ky_tu, sang, co), dark_image=ve_icon(ky_tu, toi, co), size=(co, co))


def nap_logic_notebook():
    """Chạy cell 1 (cấu hình) và cell 5 (mô hình + logic tuân thủ) của notebook_code.py."""
    code = (APP_DIR / "notebook_code.py").read_text(encoding="utf-8")
    cells = {}
    for part in code.split("# === CELL ")[1:]:
        so, _, body = part.partition(" ===\n")
        cells[int(so)] = body
    core = types.ModuleType("giam_sat_core")
    core.__file__ = str(APP_DIR / "notebook_code.py")
    for so in (1, 5):
        exec(compile(cells[so], f"notebook_code.py (cell {so})", "exec"), core.__dict__)
    # Chạy thử một khung hình để nạp CUDA trước, lần nhận diện đầu tiên không bị khựng.
    import numpy as np
    core.phan_tich_khung_hinh(core.detector, np.zeros((640, 640, 3), dtype=np.uint8))
    return core


def dong_nhat_ky(nguon, thoi_diem, report, ten_anh):
    """Các dòng nhật ký giống hệt những gì ghi_nhat_ky ghi vào CSV."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = [(now, nguon, thoi_diem, f"#{w['id']}", ", ".join(name for name, _ in w["thieu"]), ten_anh)
            for w in report["workers"] if not w["dat_chuan"]]
    rows += [(now, nguon, thoi_diem, "không xác định", d["label"], ten_anh)
             for d in report["orphan_violations"]]
    return rows


def dinh_dang_tg(giay):
    phut, giay = divmod(int(giay), 60)
    return f"{phut:02d}:{giay:02d}"


def anh_thu_nho(bgr, rong=360):
    h, w = bgr.shape[:2]
    nho = cv2.resize(bgr, (rong, max(1, int(h * rong / w))), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(nho, cv2.COLOR_BGR2RGB)


class UngDungGiamSat(ctk.CTk):
    def __init__(self):
        self.ho_font = nap_font()  # phải nạp trước khi tạo font đầu tiên
        ctk.set_appearance_mode("system")  # giống bản web: mặc định theo Windows, đổi bằng công tắc ở góc phải
        super().__init__(fg_color=MAU["nen"])
        self.title("Hệ thống giám sát an toàn công trường – YOLOv11")
        self.minsize(1280, 760)
        self.after(0, lambda: self.state("zoomed"))
        self.s = ctk.ScalingTracker.get_widget_scaling(self)

        self.core = None
        self.q = queue.Queue()              # thông điệp từ luồng xử lý -> giao diện (không bỏ sót)
        self.khoa = threading.Lock()
        self.khung_moi = None               # khung hình mới nhất (chỉ giữ cái mới nhất để hiển thị)
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.luong, self.loai_luong = None, None   # loai_luong: "anh" | "video" | "camera"
        self.che_do = "anh"
        self.anh_rgb, self._tk_img, self._anh_canh_bao, self._tk_logo = None, None, None, None
        self.ket_qua_anh, self.chi_so_anh = [], 0
        self.video_cuoi = None
        self.dang_canh_bao, self._nhay = False, False
        self.so_canh_bao, self.thong_ke = 0, [0, 0]   # số lần cảnh báo; [khung hình, khung hình vi phạm]
        self.duong_dan_canh_bao = None
        # Luồng xử lý chỉ đọc các thuộc tính Python này, không chạm vào biến Tk.
        self.conf, self.chu_ky, self.ve_trang_bi, self.dung_toc_do = 0.3, 3, True, True

        self._tao_font()
        self._tao_giao_dien()
        self._ap_dung_mau_ttk()
        self._nap_lich_su_nhat_ky()
        self.seg.set(CHE_DO[0])
        self._chon_che_do(CHE_DO[0])
        self._dat_chip("Đang nạp mô hình…", MAU["xam"])

        self.protocol("WM_DELETE_WINDOW", self._dong)
        self.bind("<space>", lambda e: self._phim(e, self.tam_dung))
        self.bind("<Escape>", lambda e: self.ket_thuc())
        self.bind("<Left>", lambda e: self._phim(e, lambda: self._xem_anh(self.chi_so_anh - 1)))
        self.bind("<Right>", lambda e: self._phim(e, lambda: self._xem_anh(self.chi_so_anh + 1)))
        self.after(15, self._cap_nhat)
        self.after(450, self._nhap_nhay)
        threading.Thread(target=self._luong_nap_mo_hinh, daemon=True).start()

    # ------------------------------------------------------------------ dựng giao diện
    def _tao_font(self):
        ho = self.ho_font
        f = lambda size, weight="normal": ctk.CTkFont(family=ho, size=size, weight=weight)
        self.f_tieu_de, self.f_muc, self.f_chu, self.f_nho = f(19, "bold"), f(11, "bold"), f(13), f(11)
        self.f_nut, self.f_banner, self.f_so, self.f_dam = f(13, "bold"), f(19, "bold"), f(22, "bold"), f(13, "bold")
        self.f_chip = f(11)
        px = lambda n: -max(8, round(n * self.s))  # cỡ âm = pixel, dùng cho ttk/Canvas (CTk tự nhân scaling)
        self.f_bang = tkfont.Font(family=ho, size=px(13))
        self.f_bang_dam = tkfont.Font(family=ho, size=px(13), weight="bold")
        self.f_canvas = (ho, px(15))
        self.f_canvas_dam = (ho, px(22), "bold")
        self.f_canvas_icon = ("Segoe Fluent Icons" if FILE_ICON and FILE_ICON.name == "SegoeIcons.ttf"
                              else "Segoe MDL2 Assets", px(44))

    def _the(self, parent, tieu_de=None, **grid):
        the = ctk.CTkFrame(parent, fg_color=MAU["the"], corner_radius=12, border_width=1, border_color=MAU["vien"])
        the.grid(**grid)
        if tieu_de:
            ctk.CTkLabel(the, text=tieu_de, font=self.f_muc, text_color=MAU["phu"], anchor="w",
                         height=20).pack(fill="x", padx=16, pady=(10, 4))
        return the

    def _nut(self, parent, text, lenh, kieu="chinh", ky_tu=None, **kw):
        mau = {"chinh": (MAU["cam"], MAU["cam_dam"], "white"),
               "phu": (MAU["phu_nut"], MAU["phu_nut_hover"], MAU["chu"]),
               "do": (MAU["do"], MAU["do_dam"], "white"),
               "xanh": (MAU["xanh"], MAU["xanh_dam"], "white")}[kieu]
        kw.setdefault("height", 38)
        if ky_tu:  # biểu tượng cùng màu chữ của nút
            kw["image"], kw["compound"] = icon(IC[ky_tu], mau[2], 16), "left"
        return ctk.CTkButton(parent, text=text, command=lenh, fg_color=mau[0], hover_color=mau[1],
                             text_color=mau[2], text_color_disabled=MAU["phu"], corner_radius=10,
                             font=self.f_nut, **kw)

    def _cong_tac(self, parent, text, var):
        ctk.CTkSwitch(parent, text=text, variable=var, onvalue=True, offvalue=False, font=self.f_chu,
                      text_color=MAU["chu"], progress_color=MAU["cam"], command=self._doc_cai_dat
                      ).pack(fill="x", padx=16, pady=3)

    def _mo_ta(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=self.f_nho, text_color=MAU["phu"], justify="left", anchor="w",
                     wraplength=250).pack(fill="x", padx=16, pady=(0, 8))

    def _tao_giao_dien(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        # --- Thanh tiêu đề
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=3, sticky="ew", padx=18, pady=(14, 10))
        anh_logo = ve_mu_bao_ho("white", 26)
        ctk.CTkLabel(header, text="", width=48, height=48, corner_radius=12, fg_color="#ea580c",
                     image=ctk.CTkImage(light_image=anh_logo, dark_image=anh_logo, size=(26, 26))).pack(side="left")
        chu = ctk.CTkFrame(header, fg_color="transparent")
        chu.pack(side="left", padx=12)
        dong = ctk.CTkFrame(chu, fg_color="transparent")
        dong.pack(anchor="w")
        ctk.CTkLabel(dong, text="Giám sát an toàn công trường", font=self.f_tieu_de,
                     text_color=MAU["chu"], height=28, anchor="w").pack(side="left")
        self.khung_ppe = ctk.CTkFrame(dong, fg_color="transparent")  # nhãn 4 trang bị, điền khi nạp xong mô hình
        self.khung_ppe.pack(side="left", padx=(14, 0))
        ctk.CTkLabel(chu, text="Mô hình YOLOv11n kiểm tra từng công nhân có đủ 4 trang bị bảo hộ bắt buộc "
                               "và cảnh báo khi thiếu.",
                     font=self.f_nho, text_color=MAU["phu"], height=18, anchor="w").pack(anchor="w")
        self.var_toi = tk.BooleanVar(value=ctk.get_appearance_mode() == "Dark")
        ctk.CTkSwitch(header, text="Giao diện tối", variable=self.var_toi, onvalue=True, offvalue=False,
                      font=self.f_chu, text_color=MAU["chu"], progress_color=MAU["cam"],
                      command=self._doi_giao_dien).pack(side="right", padx=(16, 0))
        self.chip = ctk.CTkLabel(header, text="", height=32, corner_radius=16, font=self.f_dam,
                                 text_color="white", padx=14)
        self.chip.pack(side="right")

        # --- Cột trái: chế độ và cài đặt
        trai = ctk.CTkFrame(self, fg_color="transparent")
        trai.grid(row=1, column=0, sticky="nsw", padx=(18, 8))
        the = self._the(trai, "①  CHỌN CHẾ ĐỘ GIÁM SÁT", row=0, column=0, sticky="ew")
        self.seg = ctk.CTkSegmentedButton(the, values=list(CHE_DO), command=self._chon_che_do, height=36,
                                          font=self.f_dam, selected_color=MAU["chon"],
                                          selected_hover_color=MAU["chon_hover"], unselected_color=MAU["the2"],
                                          unselected_hover_color=MAU["phu_nut"], fg_color=MAU["the2"],
                                          text_color=MAU["chu"], corner_radius=10)
        self.seg.pack(fill="x", padx=14, pady=(0, 12))

        self.var_luu_video = tk.BooleanVar(value=True)
        self.var_toc_do = tk.BooleanVar(value=True)
        self.var_nguon_cam = tk.StringVar(value="0")
        self.khung_che_do = {}

        k = self.khung_che_do["anh"] = ctk.CTkFrame(the, fg_color="transparent")
        self._mo_ta(k, "Phân tích một hoặc nhiều ảnh. Kết quả lưu vào thư mục output_PPE.")
        self.nut_chon_anh = self._nut(k, "Chọn ảnh…", self.chon_anh, ky_tu="anh")
        self.nut_chon_anh.pack(fill="x", padx=16, pady=(0, 6))
        self.nut_chon_thu_muc = self._nut(k, "Chọn cả thư mục ảnh…", self.chon_thu_muc, "phu", ky_tu="thu_muc")
        self.nut_chon_thu_muc.pack(fill="x", padx=16, pady=(0, 12))

        k = self.khung_che_do["video"] = ctk.CTkFrame(the, fg_color="transparent")
        self._mo_ta(k, "Phân tích từng khung hình. Có thể tạm dừng, tiếp tục và phát lại.")
        self.nut_chon_video = self._nut(k, "Chọn video…", self.chon_video, ky_tu="video")
        self.nut_chon_video.pack(fill="x", padx=16, pady=(0, 8))
        self._cong_tac(k, "Phát đúng tốc độ gốc", self.var_toc_do)
        self._cong_tac(k, "Lưu video kết quả", self.var_luu_video)
        ctk.CTkFrame(k, fg_color="transparent", height=4).pack()

        k = self.khung_che_do["camera"] = ctk.CTkFrame(the, fg_color="transparent")
        self._mo_ta(k, "Nhập 0, 1… cho webcam hoặc địa chỉ rtsp://… cho camera IP.")
        ctk.CTkEntry(k, textvariable=self.var_nguon_cam, height=34, corner_radius=10, font=self.f_chu,
                     fg_color=MAU["the2"], border_color=MAU["vien"], text_color=MAU["chu"]
                     ).pack(fill="x", padx=16, pady=(0, 8))
        self.nut_bat_cam = self._nut(k, "Bật camera", self.mo_camera, ky_tu="camera")
        self.nut_bat_cam.pack(fill="x", padx=16, pady=(0, 8))
        self._cong_tac(k, "Ghi lại video", self.var_luu_video)
        ctk.CTkFrame(k, fg_color="transparent", height=4).pack()

        the = self._the(trai, "②  CÀI ĐẶT NHẬN DIỆN", row=1, column=0, sticky="ew", pady=(12, 0))
        self.var_conf = tk.DoubleVar(value=0.3)
        self.var_chu_ky = tk.DoubleVar(value=3)
        self.lbl_gia_tri = {}
        for khoa, nhan, var, tu, den, buoc, goi_y in (
                ("conf", "Ngưỡng tin cậy", self.var_conf, 0.1, 0.9, 16, "Thấp: phát hiện nhiều hơn nhưng dễ nhầm"),
                ("chu_ky", "Chu kỳ cảnh báo", self.var_chu_ky, 1, 10, 9, "Khoảng cách giữa hai lần lưu cảnh báo")):
            hang = ctk.CTkFrame(the, fg_color="transparent")
            hang.pack(fill="x", padx=16)
            ctk.CTkLabel(hang, text=nhan, font=self.f_chu, text_color=MAU["chu"], height=22).pack(side="left")
            self.lbl_gia_tri[khoa] = ctk.CTkLabel(hang, text="", font=self.f_dam, text_color=MAU["cam_chu"], height=22)
            self.lbl_gia_tri[khoa].pack(side="right")
            ctk.CTkSlider(the, from_=tu, to=den, number_of_steps=buoc, variable=var, height=18,
                          progress_color=MAU["cam"], button_color=MAU["cam"], button_hover_color=MAU["cam_dam"],
                          fg_color=MAU["the2"], command=lambda v: self._doc_cai_dat()).pack(fill="x", padx=10, pady=(4, 0))
            ctk.CTkLabel(the, text=goi_y, font=self.f_nho, text_color=MAU["phu"], anchor="w",
                         height=16).pack(fill="x", padx=16, pady=(0, 4))
        self.var_am_thanh = tk.BooleanVar(value=True)
        self.var_ve_trang_bi = tk.BooleanVar(value=True)
        self._cong_tac(the, "Âm thanh cảnh báo", self.var_am_thanh)
        self._cong_tac(the, "Vẽ khung trang bị", self.var_ve_trang_bi)
        ctk.CTkFrame(the, fg_color="transparent", height=4).pack()

        # --- Cột giữa: màn hình giám sát
        giua = self._the(self, None, row=1, column=1, sticky="nsew", padx=8)
        thanh = ctk.CTkFrame(giua, fg_color="transparent")
        thanh.pack(fill="x", padx=16, pady=(12, 8))
        ctk.CTkLabel(thanh, text="MÀN HÌNH GIÁM SÁT", font=self.f_muc, text_color=MAU["phu"], height=20).pack(side="left")
        self.lbl_nguon = ctk.CTkLabel(thanh, text="", font=self.f_dam, text_color=MAU["chu"], height=20,
                                      compound="left")
        self.lbl_nguon.pack(side="right")
        self.icon_nguon = {loai: icon(IC[loai], MAU["phu"], 16) for loai in ("anh", "video", "camera")}
        self.canvas = tk.Canvas(giua, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True, padx=16)
        self._co_canvas = None
        self.canvas.bind("<Configure>", self._doi_co_canvas)

        dieu_khien = ctk.CTkFrame(giua, fg_color="transparent")
        dieu_khien.pack(fill="x", padx=16, pady=(10, 12))
        hang = ctk.CTkFrame(dieu_khien, fg_color="transparent")
        hang.pack(fill="x")
        self.lbl_tg = ctk.CTkLabel(hang, text="", font=self.f_nho, text_color=MAU["phu"], width=100, anchor="w")
        self.lbl_tg.pack(side="left")
        self.tien_do = ctk.CTkProgressBar(hang, height=8, corner_radius=4, progress_color=MAU["cam"],
                                          fg_color=MAU["the2"])
        self.tien_do.set(0)
        self.tien_do.pack(side="left", fill="x", expand=True, padx=8)

        hang_nut = ctk.CTkFrame(dieu_khien, fg_color="transparent")
        hang_nut.pack(pady=(8, 0))
        self.icon_tam_dung = icon(IC["pause"], MAU["chu"], 16)
        self.icon_tiep_tuc = icon(IC["play"], "white", 16)
        self.dk_video = ctk.CTkFrame(hang_nut, fg_color="transparent")
        self.nut_tam_dung = self._nut(self.dk_video, "Tạm dừng", self.tam_dung, "phu", ky_tu="pause", width=150)
        self.nut_ket_thuc = self._nut(self.dk_video, "Kết thúc", self.ket_thuc, "do", ky_tu="stop", width=140)
        self.nut_phat_lai = self._nut(self.dk_video, "Phát lại", self.phat_lai, "phu", ky_tu="phat_lai", width=140)
        for nut in (self.nut_tam_dung, self.nut_ket_thuc, self.nut_phat_lai):
            nut.pack(side="left", padx=5)
        self.dk_anh = ctk.CTkFrame(hang_nut, fg_color="transparent")
        self.nut_truoc = self._nut(self.dk_anh, "Ảnh trước", lambda: self._xem_anh(self.chi_so_anh - 1), "phu",
                                   ky_tu="truoc", width=140)
        self.lbl_so_anh = ctk.CTkLabel(self.dk_anh, text="", font=self.f_dam, text_color=MAU["chu"], width=80)
        self.nut_sau = self._nut(self.dk_anh, "Ảnh sau", lambda: self._xem_anh(self.chi_so_anh + 1), "phu",
                                 ky_tu="sau", width=140)
        self.nut_sau.configure(compound="right")
        self.nut_dung_anh = self._nut(self.dk_anh, "Dừng", self.ket_thuc, "do", ky_tu="stop", width=110)
        for w in (self.nut_truoc, self.lbl_so_anh, self.nut_sau, self.nut_dung_anh):
            w.pack(side="left", padx=5)
        self.lbl_phim_tat = ctk.CTkLabel(dieu_khien, text="", font=self.f_nho, text_color=MAU["phu"], height=18)
        self.lbl_phim_tat.pack(pady=(6, 0))

        # --- Cột phải: kết quả cảnh báo
        # Bề rộng cố định: nếu cột này co giãn theo chữ (FPS, số khung hình… đổi mỗi khung) thì cả cửa sổ phải tính
        # lại bố cục và vẽ lại màn hình giám sát ở mỗi khung hình, làm video/camera bị giật.
        phai = ctk.CTkFrame(self, fg_color="transparent", width=384)
        phai.grid(row=1, column=2, sticky="nse", padx=(8, 18))
        phai.grid_propagate(False)
        phai.columnconfigure(0, weight=1)
        phai.rowconfigure(2, weight=1)

        # Băng trạng thái giống bản web: biểu tượng bên trái, tiêu đề + mô tả căn trái, nền đặc chữ trắng
        self.icon_banner = {khoa: icon(IC[ky_tu], "white", 30)
                            for khoa, ky_tu in (("do", "canh_bao"), ("xanh", "dat"), ("xam", "nguoi"), ("cho", "cho"))}
        self.banner = ctk.CTkFrame(phai, fg_color=MAU["xam"], corner_radius=12)
        self.banner.grid(row=0, column=0, sticky="ew")
        self.lbl_banner_icon = ctk.CTkLabel(self.banner, text="", image=self.icon_banner["cho"], width=34)
        self.lbl_banner_icon.pack(side="left", padx=(16, 4), pady=8)
        chu = ctk.CTkFrame(self.banner, fg_color="transparent")
        chu.pack(side="left", fill="x", expand=True, padx=(8, 16), pady=8)
        self.lbl_banner = ctk.CTkLabel(chu, text="CHƯA GIÁM SÁT", font=self.f_banner, text_color="white",
                                       height=28, anchor="w")
        self.lbl_banner.pack(fill="x")
        self.lbl_banner_phu = ctk.CTkLabel(chu, text="Đang chuẩn bị mô hình nhận diện…", font=self.f_chu,
                                           text_color="white", height=20, anchor="w", justify="left",
                                           wraplength=280)
        self.lbl_banner_phu.pack(fill="x")

        o = ctk.CTkFrame(phai, fg_color="transparent")
        o.grid(row=1, column=0, sticky="ew", pady=10)
        self.so_lieu = {}
        for i, (khoa, nhan) in enumerate((("cn", "Công nhân"), ("vp", "Vi phạm"), ("fps", "FPS"), ("cb", "Cảnh báo"))):
            the = ctk.CTkFrame(o, fg_color=MAU["the"], corner_radius=10, border_width=1, border_color=MAU["vien"])
            the.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0 if i == 3 else 4))
            o.columnconfigure(i, weight=1, uniform="the")
            ctk.CTkLabel(the, text=nhan, font=self.f_nho, text_color=MAU["phu"], height=16,
                         anchor="w").pack(fill="x", padx=12, pady=(6, 0))
            self.so_lieu[khoa] = ctk.CTkLabel(the, text="–", font=self.f_so, text_color=MAU["chu"], height=32, anchor="w")
            self.so_lieu[khoa].pack(fill="x", padx=12, pady=(0, 4))
        self.lbl_thong_ke = ctk.CTkLabel(o, text="", font=self.f_nho, text_color=MAU["phu"], height=18)
        self.lbl_thong_ke.grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))

        the = self._the(phai, "CHI TIẾT TỪNG CÔNG NHÂN", row=2, column=0, sticky="nsew")
        self.lbl_ghi_chu_cn = ctk.CTkLabel(the, text="", font=self.f_nho, text_color=MAU["phu"], justify="left",
                                           anchor="w", wraplength=340)
        self.lbl_ghi_chu_cn.pack(side="bottom", fill="x", padx=16, pady=(2, 8))
        bang = ctk.CTkFrame(the, fg_color="transparent")
        bang.pack(fill="both", expand=True, padx=14)
        cot = ("cn", "mu", "gang", "ao", "giay", "tay", "kl")
        self.bang_cn = ttk.Treeview(bang, columns=cot, show="headings", height=3, selectmode="none")
        for c, nhan, rong in zip(cot, ("CN", "Mũ", "Găng", "Áo", "Giày", "Tay", "Kết luận"),
                                 (40, 40, 52, 38, 46, 40, 80)):
            self.bang_cn.heading(c, text=nhan)
            self.bang_cn.column(c, width=round(rong * self.s), anchor="center", stretch=c == "kl")
        cuon = ctk.CTkScrollbar(bang, command=self.bang_cn.yview, width=12, height=40)
        self.bang_cn.configure(yscrollcommand=cuon.set)
        self.bang_cn.pack(side="left", fill="both", expand=True)
        cuon.pack(side="right", fill="y")

        the = self._the(phai, "CẢNH BÁO GẦN NHẤT  ·  nhấp vào ảnh để mở", row=3, column=0, sticky="ew",
                        pady=(10, 0))
        hang = ctk.CTkFrame(the, fg_color="transparent")
        hang.pack(fill="x", padx=14, pady=(0, 12))
        self.lbl_anh_cb = ctk.CTkLabel(hang, text="", width=0, height=0, cursor="hand2")
        self.lbl_anh_cb.pack(side="left")
        self.lbl_anh_cb.bind("<Button-1>", lambda e: self._mo(self.duong_dan_canh_bao))
        self.lbl_mo_ta_cb = ctk.CTkLabel(hang, text="Chưa có cảnh báo trong phiên này", font=self.f_nho,
                                         text_color=MAU["phu"], justify="left", anchor="nw", wraplength=170)
        self.lbl_mo_ta_cb.pack(side="left", fill="both", expand=True, padx=(10, 0))

        # --- Hàng dưới: nhật ký cảnh báo
        nhat_ky = self._the(self, None, row=2, column=0, columnspan=3, sticky="ew", padx=18, pady=(12, 0))
        thanh = ctk.CTkFrame(nhat_ky, fg_color="transparent")
        thanh.pack(fill="x", padx=16, pady=(10, 6))
        ctk.CTkLabel(thanh, text="NHẬT KÝ CẢNH BÁO", font=self.f_muc, text_color=MAU["phu"], height=20).pack(side="left")
        ctk.CTkLabel(thanh, text="     Nhấp đúp một dòng để mở ảnh cảnh báo  ·  dòng chữ đỏ = cảnh báo của phiên này",
                     font=self.f_nho, text_color=MAU["phu"], height=20).pack(side="left")
        for text, ky_tu, lenh in (("Nhật ký CSV", "tai_lieu", lambda: self._mo(self.core and self.core.LOG_PATH)),
                                  ("Ảnh cảnh báo", "canh_bao", lambda: self._mo(self.core and self.core.ALERT_DIR)),
                                  ("Thư mục kết quả", "thu_muc", lambda: self._mo(self.core and self.core.OUTPUT_DIR))):
            nut = self._nut(thanh, text, lenh, "phu", ky_tu=ky_tu, height=30, width=150)
            nut.configure(font=self.f_chu)
            nut.pack(side="right", padx=(8, 0))
        bang = ctk.CTkFrame(nhat_ky, fg_color="transparent")
        bang.pack(fill="x", padx=14, pady=(0, 12))
        cot = ("tg", "nguon", "td", "cn", "vp", "anh")
        self.bang_nk = ttk.Treeview(bang, columns=cot, show="headings", height=3)
        for c, nhan, rong in zip(cot, ("Thời gian", "Nguồn", "Thời điểm (s)", "Công nhân", "Vi phạm", "Ảnh cảnh báo"),
                                 (150, 260, 100, 110, 320, 320)):
            self.bang_nk.heading(c, text=nhan)
            self.bang_nk.column(c, width=round(rong * self.s), anchor="center" if c in ("td", "cn") else "w")
        cuon = ctk.CTkScrollbar(bang, command=self.bang_nk.yview, width=12, height=40)
        self.bang_nk.configure(yscrollcommand=cuon.set)
        self.bang_nk.pack(side="left", fill="both", expand=True)
        cuon.pack(side="right", fill="y")
        self.bang_nk.bind("<Double-1>", self._mo_anh_nhat_ky)

        self.lbl_trang_thai = ctk.CTkLabel(self, text="", font=self.f_nho, text_color=MAU["phu"], anchor="w", height=22)
        self.lbl_trang_thai.grid(row=3, column=0, columnspan=3, sticky="ew", padx=22, pady=(4, 8))

        self._doc_cai_dat()
        self._hien_thi_bao_cao(None)
        self._cap_nhat_thong_ke()

    # ------------------------------------------------------------------ màu sắc
    def _c(self, khoa):
        """Màu hiện tại (dạng chuỗi) cho các widget Tk/ttk không tự đổi theo giao diện sáng/tối."""
        return MAU[khoa][0 if ctk.get_appearance_mode() == "Light" else 1]

    def _ap_dung_mau_ttk(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Treeview", background=self._c("the2"), fieldbackground=self._c("the2"),
                    foreground=self._c("chu"), rowheight=round(self.f_bang.metrics("linespace") * 1.6),
                    borderwidth=0, font=self.f_bang)
        s.configure("Treeview.Heading", background=self._c("vien"), foreground=self._c("chu"), relief="flat",
                    borderwidth=0, font=self.f_bang_dam, padding=(4, round(5 * self.s)))
        s.map("Treeview.Heading", background=[("active", self._c("vien"))])
        s.map("Treeview", background=[("selected", self._c("cam"))], foreground=[("selected", "white")])
        s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        # Cả dòng tô nền nhạt (Treeview không tô được từng ô), chữ giữ màu thường để ✔/✘ luôn đọc rõ
        self.bang_cn.tag_configure("dat", background=self._c("nen_dat"), foreground=self._c("chu"))
        self.bang_cn.tag_configure("loi", background=self._c("nen_loi"), foreground=self._c("chu"))
        self.bang_nk.tag_configure("moi", foreground=self._c("do_chu"))
        self.canvas.configure(bg=self._c("man_hinh"))
        self._ve_canvas()

    def _doi_giao_dien(self):
        ctk.set_appearance_mode("dark" if self.var_toi.get() else "light")
        self._ap_dung_mau_ttk()

    # ------------------------------------------------------------------ tiện ích giao diện
    def _dat_chip(self, text, mau):
        self.chip.configure(text=text, fg_color=mau)

    def _bao(self, text):
        self.lbl_trang_thai.configure(text=f"{datetime.now():%H:%M:%S}   {text}")

    def _phim(self, event, lenh):
        if not isinstance(event.widget, tk.Entry):  # đang gõ trong ô nhập thì không bắt phím tắt
            lenh()

    def _dang_chay(self):
        return self.luong is not None and self.luong.is_alive()

    def _chon_che_do(self, gia_tri):
        if self._dang_chay():  # không đổi chế độ khi đang xử lý
            self.seg.set(CHE_DO[LOAI_CHE_DO.index(self.che_do)])
            return
        self.che_do = LOAI_CHE_DO[CHE_DO.index(gia_tri)]
        for khung in self.khung_che_do.values():
            khung.pack_forget()
        self.khung_che_do[self.che_do].pack(fill="x")
        self.dk_anh.pack_forget()
        self.dk_video.pack_forget()
        if self.che_do == "anh":
            self.dk_anh.pack()
            self.lbl_phim_tat.configure(text="Phím tắt:  ← / →  chuyển ảnh   ·   Esc  dừng xử lý")
        else:
            self.dk_video.pack()
            self.lbl_phim_tat.configure(text="Phím tắt:  Space  tạm dừng / tiếp tục   ·   Esc  kết thúc")
        if self.che_do == "camera":
            self.nut_phat_lai.pack_forget()
        elif not self.nut_phat_lai.winfo_manager():
            self.nut_phat_lai.pack(side="left", padx=5)
        self._cap_nhat_nut()

    def _cap_nhat_nut(self):
        dang_chay = self._dang_chay()
        san_sang = self.core is not None and not dang_chay
        trang_thai = lambda bat: "normal" if bat else "disabled"
        for nut in (self.nut_chon_anh, self.nut_chon_thu_muc, self.nut_chon_video, self.nut_bat_cam):
            nut.configure(state=trang_thai(san_sang))
        self.seg.configure(state=trang_thai(san_sang))

        phat = dang_chay and self.loai_luong in ("video", "camera")
        if self.pause_event.is_set():
            self.nut_tam_dung.configure(text="Tiếp tục", image=self.icon_tiep_tuc, fg_color=MAU["xanh"],
                                        hover_color=MAU["xanh_dam"], text_color="white")
        else:
            self.nut_tam_dung.configure(text="Tạm dừng", image=self.icon_tam_dung, fg_color=MAU["phu_nut"],
                                        hover_color=MAU["phu_nut_hover"], text_color=MAU["chu"])
        self.nut_tam_dung.configure(state=trang_thai(phat))
        self.nut_ket_thuc.configure(state=trang_thai(phat))
        self.nut_phat_lai.configure(state=trang_thai(san_sang and self.video_cuoi is not None))
        self.nut_dung_anh.configure(state=trang_thai(dang_chay and self.loai_luong == "anh"))

        n = len(self.ket_qua_anh)
        self.nut_truoc.configure(state=trang_thai(not dang_chay and n and self.chi_so_anh > 0))
        self.nut_sau.configure(state=trang_thai(not dang_chay and n and self.chi_so_anh < n - 1))
        self.lbl_so_anh.configure(text=f"{self.chi_so_anh + 1} / {n}" if n else "– / –")

    def _doc_cai_dat(self):
        self.conf = round(self.var_conf.get(), 2)
        self.chu_ky = round(self.var_chu_ky.get())
        self.lbl_gia_tri["conf"].configure(text=f"{self.conf:.2f}")
        self.lbl_gia_tri["chu_ky"].configure(text=f"{self.chu_ky} giây")
        self.ve_trang_bi = self.var_ve_trang_bi.get()
        self.dung_toc_do = self.var_toc_do.get()

    def _mo(self, path):
        if not path:
            return
        if Path(path).exists():
            os.startfile(path)
        else:
            messagebox.showinfo("Chưa có dữ liệu", f"Chưa tồn tại:\n{path}")

    def _doi_co_canvas(self, event):
        if (event.width, event.height) != self._co_canvas:  # chỉ vẽ lại khi kích thước thật sự thay đổi
            self._co_canvas = (event.width, event.height)
            self._ve_canvas()

    def _ve_canvas(self):
        c = self.canvas
        c.delete("all")
        cw, ch = c.winfo_width(), c.winfo_height()
        if cw < 10 or ch < 10:
            return
        if self.anh_rgb is None:
            cx, cy = cw // 2, ch // 2
            if self.core is None:
                if FILE_ICON:
                    c.create_text(cx, cy - round(30 * self.s), text=IC["cho"], fill=self._c("phu"),
                                  font=self.f_canvas_icon)
                c.create_text(cx, cy + round(40 * self.s), text="Đang nạp mô hình YOLOv11…", fill=self._c("chu"),
                              font=self.f_canvas_dam)
                return
            buoc = ("①  Chọn chế độ Ảnh, Video hoặc Camera ở bảng bên trái",
                    "②  Chọn tệp cần kiểm tra hoặc bật camera",
                    "③  Theo dõi cảnh báo ở cột bên phải và nhật ký bên dưới")
            top = cy - round(90 * self.s)
            co = round(64 * self.s)
            self._tk_logo = ImageTk.PhotoImage(ve_mu_bao_ho(self._c("phu"), co).resize((co, co), Image.LANCZOS))
            c.create_image(cx, top, image=self._tk_logo)
            c.create_text(cx, top + round(70 * self.s), text="Bắt đầu giám sát", fill=self._c("chu"),
                          font=self.f_canvas_dam)
            for i, text in enumerate(buoc):
                c.create_text(cx, top + round((115 + 30 * i) * self.s), text=text, fill=self._c("phu"),
                              font=self.f_canvas)
            return
        h, w = self.anh_rgb.shape[:2]
        ti_le = min(cw / w, ch / h)
        # cv2.resize nhanh hơn PIL khoảng 4–10 lần (khung 1080p: ~5 ms so với ~40 ms). Bước này chạy trên luồng
        # giao diện ở mỗi khung hình nên quyết định video/camera hiển thị có mượt hay không.
        anh = cv2.resize(self.anh_rgb, (max(1, int(w * ti_le)), max(1, int(h * ti_le))),
                         interpolation=cv2.INTER_AREA if ti_le < 1 else cv2.INTER_LINEAR)
        self._tk_img = ImageTk.PhotoImage(Image.fromarray(anh))
        c.create_image(cw // 2, ch // 2, image=self._tk_img)
        if self.pause_event.is_set() and self._dang_chay():
            item = c.create_text(cw // 2, ch - round(34 * self.s), fill="white", font=self.f_canvas,
                                 text="ĐANG TẠM DỪNG  ·  nhấn Space hoặc nút Tiếp tục để phát tiếp")
            x1, y1, x2, y2 = c.bbox(item)
            pad = round(12 * self.s)
            c.create_rectangle(x1 - pad, y1 - pad // 2, x2 + pad, y2 + pad // 2, fill=self._c("vang"), outline="")
            c.tag_raise(item)

    # ------------------------------------------------------------------ hiển thị kết quả
    def _hien_thi(self, rgb, report, info):
        self.anh_rgb = rgb
        self._ve_canvas()
        nguon = info["nguon"]
        if len(nguon) > 60:  # đường dẫn hoặc địa chỉ rtsp:// dài: giữ phần đầu và tên ở cuối
            nguon = nguon[:22] + "…" + nguon[-35:]
        self.lbl_nguon.configure(text=f"  {nguon}", image=self.icon_nguon.get(info.get("loai")))
        if info.get("tien_do") is not None:
            self.tien_do.set(min(1.0, info["tien_do"]))
        if "thoi_gian" in info:
            hien_tai, tong = info["thoi_gian"]
            self.lbl_tg.configure(text=dinh_dang_tg(hien_tai) + (f" / {dinh_dang_tg(tong)}" if tong else ""))
        self.so_lieu["fps"].configure(text=f"{info['fps']:.0f}" if info.get("fps") else "–")
        if "frames" in info:
            self.thong_ke = [info["frames"], info["vp_frames"]]
            self._cap_nhat_thong_ke()
        self._hien_thi_bao_cao(report)

    def _hien_thi_bao_cao(self, report):
        if report is None:
            self.banner.configure(fg_color=MAU["xam"])
            self.lbl_banner_icon.configure(image=self.icon_banner["cho"])
            for khoa in ("cn", "vp"):
                self.so_lieu[khoa].configure(text="–", text_color=MAU["chu"])
            self.lbl_ghi_chu_cn.configure(text="✔ có trang bị   ✘ thiếu / vi phạm   (Tay ✘ = để tay trần)")
            return
        n, k = report["so_cong_nhan"], report["so_nguoi_vi_pham"]
        self.dang_canh_bao = report["canh_bao"]
        if report["canh_bao"]:
            khoa, chinh = "do", "CẢNH BÁO"
            phu = f"{k}/{n} công nhân thiếu đồ bảo hộ" if k else "Phát hiện vi phạm bảo hộ"
        elif n:
            khoa, chinh, phu = "xanh", "AN TOÀN", f"{n}/{n} công nhân đủ đồ bảo hộ"
        else:
            khoa, chinh, phu = "xam", "KHÔNG CÓ CÔNG NHÂN", "Không phát hiện người trong khung hình"
        self.banner.configure(fg_color=MAU[khoa])
        self.lbl_banner_icon.configure(image=self.icon_banner[khoa])
        self.lbl_banner.configure(text=chinh)
        self.lbl_banner_phu.configure(text=phu)
        self.so_lieu["cn"].configure(text=str(n))
        self.so_lieu["vp"].configure(text=str(k), text_color=MAU["do_chu"] if k else MAU["chu"])

        self.bang_cn.delete(*self.bang_cn.get_children())
        for w in report["workers"]:
            thieu = {name for name, _ in w["thieu"]}
            dau = ["✘" if name in thieu else "✔" for name, _, _, _ in self.core.PPE_RULES]
            dau.append("✘" if any(name in thieu for name, _ in self.core.EXTRA_VIOLATIONS.values()) else "✔")
            self.bang_cn.insert("", "end", values=(f"#{w['id']}", *dau, "Đạt" if w["dat_chuan"] else "Vi phạm"),
                                tags=("dat" if w["dat_chuan"] else "loi",))
        ghi_chu = "✔ có trang bị   ✘ thiếu / vi phạm   (Tay ✘ = để tay trần)"
        if report["orphan_violations"]:
            ghi_chu += "\nVi phạm chưa gắn được công nhân: " + ", ".join(
                f"{d['label']} ({d['conf']:.2f})" for d in report["orphan_violations"])
        self.lbl_ghi_chu_cn.configure(text=ghi_chu)

    def _cap_nhat_thong_ke(self):
        frames, vp_frames = self.thong_ke
        self.so_lieu["cb"].configure(text=str(self.so_canh_bao),
                                     text_color=MAU["do_chu"] if self.so_canh_bao else MAU["chu"])
        if frames:
            self.lbl_thong_ke.configure(text=f"Đã xử lý {frames} khung hình / ảnh  ·  {vp_frames} có vi phạm "
                                             f"({vp_frames / frames:.0%})")
        else:
            self.lbl_thong_ke.configure(text="Chưa xử lý khung hình nào trong phiên này")

    def _nhap_nhay(self):
        if self.dang_canh_bao and self._dang_chay() and not self.pause_event.is_set():
            self._nhay = not self._nhay
            self.banner.configure(fg_color=MAU["do_dam"] if self._nhay else MAU["do"])
        self.after(450, self._nhap_nhay)

    def _them_canh_bao(self, rows, thu_nho, duong_dan):
        self.so_canh_bao += 1
        self._cap_nhat_thong_ke()
        for row in rows:
            self.bang_nk.insert("", 0, values=row, tags=("moi",))
        anh = Image.fromarray(thu_nho)
        ti_le = min(150 / anh.width, 84 / anh.height)  # khung tối đa 150x84, CTkImage tự nhân scaling
        kich_thuoc = (round(anh.width * ti_le), round(anh.height * ti_le))
        self._anh_canh_bao = ctk.CTkImage(light_image=anh, dark_image=anh, size=kich_thuoc)
        self.lbl_anh_cb.configure(image=self._anh_canh_bao)
        self.duong_dan_canh_bao = duong_dan
        if rows:
            r = rows[0]
            nguon = r[1] if len(r[1]) <= 24 else r[1][:21] + "…"
            luc = f" · {r[2]}s" if r[2] else ""
            dong = [f"{x[3]}: {x[4]}" for x in rows[:2]]
            if len(rows) > 2:
                dong.append(f"+ {len(rows) - 2} vi phạm khác")
            self.lbl_mo_ta_cb.configure(text=f"{r[0][11:]}  ·  {nguon}{luc}\n" + "\n".join(dong),
                                        text_color=MAU["chu"])
            self._bao(f"CẢNH BÁO [{r[1]}] " + "; ".join(f"{x[3]} thiếu {x[4]}" for x in rows))
        if self.var_am_thanh.get():
            try:
                import winsound
                winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
            except Exception:
                self.bell()

    def _nap_lich_su_nhat_ky(self):
        log_path = APP_DIR / "output_PPE" / "nhat_ky_vi_pham.csv"
        if not log_path.exists():
            return
        with open(log_path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))[1:]
        for row in rows[-300:]:
            if len(row) == 6:
                self.bang_nk.insert("", 0, values=row)

    def _mo_anh_nhat_ky(self, event):
        item = self.bang_nk.identify_row(event.y)
        if not item:
            return
        ten = self.bang_nk.item(item, "values")[5]
        for folder in (APP_DIR / "output_PPE" / "canh_bao", APP_DIR / "output_PPE"):
            if ten and (folder / ten).exists():
                os.startfile(folder / ten)
                return
        messagebox.showinfo("Không tìm thấy", f"Không tìm thấy ảnh cảnh báo: {ten}")

    def _xem_anh(self, i):
        if not self.ket_qua_anh or not 0 <= i < len(self.ket_qua_anh) or self._dang_chay():
            return
        self.chi_so_anh = i
        ten, rgb, report = self.ket_qua_anh[i]
        self._hien_thi(rgb, report, {"nguon": f"Ảnh: {ten}", "loai": "anh"})
        self._cap_nhat_nut()

    # ------------------------------------------------------------------ vòng lặp giao diện
    def _cap_nhat(self):
        with self.khoa:
            moi, self.khung_moi = self.khung_moi, None
        if moi is not None:
            self._hien_thi(*moi)
        try:
            while True:
                loai, data = self.q.get_nowait()
                if loai == "san_sang":
                    self.core = data
                    self.var_conf.set(self.core.CONF_THRESHOLD)
                    self._doc_cai_dat()
                    self._dat_chip("●  Sẵn sàng", MAU["xanh"])
                    self._cap_nhat_nut()
                    self._ve_canvas()
                    self.lbl_banner_phu.configure(text="Chọn chế độ ở bảng bên trái để bắt đầu")
                    for ten, _, _, _ in self.core.PPE_RULES:  # 4 nhãn trang bị cạnh tiêu đề, như bản web
                        ctk.CTkLabel(self.khung_ppe, text=ten, font=self.f_chip, text_color=MAU["chu"], height=22,
                                     corner_radius=11, fg_color=MAU["the2"], padx=10).pack(side="left", padx=(0, 6))
                    weights = self.core.BEST_WEIGHTS if self.core.BEST_WEIGHTS.exists() else self.core.WEIGHTS_PATH
                    self._bao(f"Đã nạp mô hình: {weights}")
                elif loai == "canh_bao":
                    self._them_canh_bao(*data)
                elif loai == "anh_xong":
                    with self.khoa:
                        self.khung_moi = None  # tránh ảnh cuối ghi đè lên ảnh đầu đang xem
                    self.ket_qua_anh, self.chi_so_anh = data, 0
                    self.thong_ke = [len(data), sum(r["canh_bao"] for _, _, r in data)]
                    self._ket_thuc(f"Đã xử lý {len(data)} ảnh. Ảnh kết quả lưu trong {self.core.OUTPUT_DIR}")
                    if data:
                        self._xem_anh(0)
                elif loai == "xong":
                    self._ket_thuc(data)
                elif loai == "loi":
                    self._ket_thuc(f"Lỗi: {data}")
                    messagebox.showerror("Lỗi", data)
                elif loai == "loi_nap":
                    self._dat_chip("Lỗi nạp mô hình", MAU["do"])
                    messagebox.showerror("Không nạp được mô hình", data)
        except queue.Empty:
            pass
        self.after(15, self._cap_nhat)

    def _bat_dau(self, loai, target, *args):
        self._doc_cai_dat()
        self.stop_event.clear()
        self.pause_event.clear()
        self.loai_luong = loai
        self.ket_qua_anh, self.chi_so_anh = [], 0
        self.so_canh_bao, self.thong_ke = 0, [0, 0]
        self.tien_do.set(0)
        self.lbl_tg.configure(text="")
        self._cap_nhat_thong_ke()
        self._dat_chip_dang_chay()
        self._bao({"anh": "Bắt đầu phân tích ảnh", "video": "Bắt đầu phát video",
                   "camera": "Đang mở camera…"}[loai])
        self.luong = threading.Thread(target=self._chay_an_toan, args=(target, *args), daemon=True)
        self.luong.start()
        self._cap_nhat_nut()

    def _dat_chip_dang_chay(self):
        text = {"anh": "●  Đang phân tích ảnh", "video": "●  Đang phát video", "camera": "●  Camera trực tiếp"}
        self._dat_chip(text[self.loai_luong], MAU["do"] if self.loai_luong == "camera" else MAU["cam"])

    def _ket_thuc(self, thong_bao):
        self.luong = None
        self.pause_event.clear()
        if self.dang_canh_bao:  # ngừng nhấp nháy, giữ banner đỏ của khung hình cuối
            self.banner.configure(fg_color=MAU["do"])
        self._dat_chip("●  Sẵn sàng", MAU["xanh"])
        self._cap_nhat_thong_ke()
        self._cap_nhat_nut()
        self._ve_canvas()
        self._bao(thong_bao)

    def _chay_an_toan(self, target, *args):
        try:
            target(*args)
        except Exception as e:  # báo lỗi lên giao diện thay vì làm chết luồng âm thầm
            self.q.put(("loi", str(e)))

    def _dat_khung(self, annotated_bgr, report, info):
        rgb = cv2.cvtColor(annotated_bgr, cv2.COLOR_BGR2RGB)
        with self.khoa:
            self.khung_moi = (rgb, report, info)
        return rgb

    # ------------------------------------------------------------------ 3 chế độ và điều khiển
    def chon_anh(self):
        paths = filedialog.askopenfilenames(title="Chọn ảnh công trường", initialdir=self.core.INPUT_DIR,
                                            filetypes=[("Ảnh", " ".join("*" + e for e in IMAGE_EXTS)),
                                                       ("Tất cả", "*.*")])
        if paths:
            self._bat_dau("anh", self._luong_anh, [Path(p) for p in paths])

    def chon_thu_muc(self):
        folder = filedialog.askdirectory(title="Chọn thư mục ảnh", initialdir=self.core.INPUT_DIR)
        if not folder:
            return
        paths = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in IMAGE_EXTS)
        if paths:
            self._bat_dau("anh", self._luong_anh, paths)
        else:
            messagebox.showinfo("Không có ảnh", f"Thư mục không chứa ảnh ({', '.join(IMAGE_EXTS)}).")

    def chon_video(self):
        path = filedialog.askopenfilename(title="Chọn video công trường", initialdir=self.core.INPUT_DIR,
                                          filetypes=[("Video", " ".join("*" + e for e in VIDEO_EXTS)),
                                                     ("Tất cả", "*.*")])
        if path:
            self.video_cuoi = Path(path)
            self.phat_lai()

    def phat_lai(self):
        if self.video_cuoi is None or self._dang_chay():
            return
        out = self.core.OUTPUT_DIR / f"{self.video_cuoi.stem}_giam_sat.mp4" if self.var_luu_video.get() else None
        self._bat_dau("video", self._luong_video, str(self.video_cuoi), False, out)

    def mo_camera(self):
        nguon = self.var_nguon_cam.get().strip() or "0"
        source = int(nguon) if nguon.isdigit() else nguon
        out = (self.core.OUTPUT_DIR / f"camera_{datetime.now():%Y%m%d_%H%M%S}_giam_sat.mp4"
               if self.var_luu_video.get() else None)
        self._bat_dau("camera", self._luong_video, source, True, out)

    def tam_dung(self):
        """Tạm dừng / tiếp tục video hoặc camera (luồng xử lý vẫn giữ nguyên vị trí đang phát)."""
        if not self._dang_chay() or self.loai_luong not in ("video", "camera"):
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
            self._dat_chip_dang_chay()
            self._bao("Tiếp tục giám sát")
        else:
            self.pause_event.set()
            self._dat_chip("Tạm dừng", MAU["vang"])
            if self.dang_canh_bao:
                self.banner.configure(fg_color=MAU["do"])
            self._bao("Đã tạm dừng. Nhấn Space hoặc nút Tiếp tục để phát tiếp")
        self._cap_nhat_nut()
        self._ve_canvas()

    def ket_thuc(self):
        if self._dang_chay():
            self.stop_event.set()
            self.pause_event.clear()
            self._bao("Đang kết thúc…")

    # ------------------------------------------------------------------ luồng xử lý
    def _luong_anh(self, paths):
        core = self.core
        ket_qua, vp = [], 0
        for i, p in enumerate(paths, 1):
            if self.stop_event.is_set():
                break
            frame = cv2.imread(str(p))
            if frame is None:
                continue
            report = core.phan_tich_khung_hinh(core.detector, frame, conf=self.conf)
            annotated = core.ve_ket_qua(frame, report, ve_trang_bi=self.ve_trang_bi)
            out = core.OUTPUT_DIR / f"{p.stem}_giam_sat.jpg"
            cv2.imwrite(str(out), annotated)
            if report["canh_bao"]:
                vp += 1
                core.ghi_nhat_ky(p.name, "", report, out.name)
                self.q.put(("canh_bao", (dong_nhat_ky(p.name, "", report, out.name), anh_thu_nho(annotated), out)))
            rgb = self._dat_khung(annotated, report, {"nguon": f"Ảnh: {p.name}", "loai": "anh", "tien_do": i / len(paths),
                                                      "frames": i, "vp_frames": vp})
            ket_qua.append((p.name, rgb, report))
        self.q.put(("anh_xong", ket_qua))

    def _luong_video(self, source, is_camera, output_path):
        """Giống giam_sat_video của notebook, thêm tạm dừng/tiếp tục và gửi từng khung hình lên giao diện."""
        core = self.core
        if is_camera:
            ten_nguon, ten_file = f"camera {source}", "camera"
        else:
            ten_nguon, ten_file = Path(source).name, Path(source).stem

        capture = None
        if isinstance(source, int) and os.name == "nt":
            capture = cv2.VideoCapture(source, cv2.CAP_DSHOW)  # DirectShow mở webcam nhanh hơn MSMF
        if capture is None or not capture.isOpened():
            capture = cv2.VideoCapture(source)
        if not capture.isOpened():
            raise RuntimeError(f"Không thể mở nguồn video: {source}")
        src_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        if src_fps > 120:
            src_fps = 30.0
        tong = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) if not is_camera else 0

        writer = None
        frames, vp_frames, fps = 0, 0, 0.0
        last_alert = float("-inf")
        nhip = None  # (thời điểm, số khung) làm mốc để phát đúng tốc độ gốc
        start = time.perf_counter()
        try:
            while not self.stop_event.is_set():
                if self.pause_event.is_set():
                    if is_camera:
                        capture.grab()  # bỏ khung cũ để khi tiếp tục là hình mới nhất
                    else:
                        time.sleep(0.03)
                    nhip = None
                    continue
                ok, frame = capture.read()
                if not ok:
                    break
                t0 = time.perf_counter()
                report = core.phan_tich_khung_hinh(core.detector, frame, conf=self.conf)
                dt = max(time.perf_counter() - t0, 1e-6)
                fps = 1 / dt if fps == 0 else 0.9 * fps + 0.1 / dt
                annotated = core.ve_ket_qua(frame, report, fps=fps, ve_trang_bi=self.ve_trang_bi)

                thoi_diem = time.perf_counter() - start if is_camera else frames / src_fps
                if report["canh_bao"]:
                    vp_frames += 1
                    if thoi_diem - last_alert >= self.chu_ky:
                        last_alert = thoi_diem
                        stamp = datetime.now().strftime("%Y%m%d_%H%M%S") if is_camera else f"{thoi_diem:06.1f}s"
                        alert_path = core.ALERT_DIR / f"{ten_file}_{stamp}.jpg"
                        cv2.imwrite(str(alert_path), annotated)
                        core.ghi_nhat_ky(ten_nguon, f"{thoi_diem:.1f}", report, alert_path.name)
                        rows = dong_nhat_ky(ten_nguon, f"{thoi_diem:.1f}", report, alert_path.name)
                        self.q.put(("canh_bao", (rows, anh_thu_nho(annotated), alert_path)))

                if output_path is not None:
                    if writer is None:
                        h, w = annotated.shape[:2]
                        writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), src_fps, (w, h))
                    writer.write(annotated)
                frames += 1
                self._dat_khung(annotated, report, {
                    "nguon": f"{'Camera' if is_camera else 'Video'}: {ten_nguon}",
                    "loai": "camera" if is_camera else "video",
                    "fps": fps, "frames": frames, "vp_frames": vp_frames,
                    "thoi_gian": (thoi_diem, tong / src_fps if tong else None),
                    "tien_do": frames / tong if tong else None})

                if not is_camera and self.dung_toc_do:
                    now = time.perf_counter()
                    if nhip is None or now - (nhip[0] + (frames - nhip[1]) / src_fps) > 0.5:
                        nhip = (now, frames)  # bắt đầu, vừa tiếp tục, hoặc xử lý bị chậm: đặt lại mốc
                    cho = nhip[0] + (frames - nhip[1]) / src_fps - now
                    if cho > 0:
                        time.sleep(cho)
        finally:
            capture.release()
            if writer is not None:
                writer.release()

        tom_tat = (f"{'Đã kết thúc' if self.stop_event.is_set() else 'Đã xử lý xong'} {ten_nguon}: "
                   f"{frames} khung hình, {vp_frames} có vi phạm ({vp_frames / frames if frames else 0:.0%}).")
        if output_path is not None and frames:
            tom_tat += f" Video kết quả: {Path(output_path).name}"
        if not is_camera:
            tom_tat += "   ·   Nhấn Phát lại để xem lại"
        self.q.put(("xong", tom_tat))

    # ------------------------------------------------------------------ nạp mô hình / thoát
    def _luong_nap_mo_hinh(self):
        try:
            self.q.put(("san_sang", nap_logic_notebook()))
        except Exception as e:
            self.q.put(("loi_nap", str(e)))

    def _dong(self):
        self.stop_event.set()
        self.pause_event.clear()
        if self.luong is not None:
            self.luong.join(timeout=3)
        self.destroy()


if __name__ == "__main__":
    UngDungGiamSat().mainloop()
