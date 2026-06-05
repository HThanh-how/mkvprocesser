# mkvtools

Tách video **nhiều audio** thành nhiều file (mỗi audio một bản) + rút phụ đề
tương ứng, rồi **tự động upload lên YouTube** kèm caption và gom playlist.
Có **pipeline tự động** (chạy 24/7) và một **GUI web** để làm tay khi cần.

> Viết lại sạch từ `mkvprocesser` cũ. Giữ lại phần lõi tốt (dò ffmpeg, metadata,
> lệnh map giữ attachment/metadata), bỏ GUI 154KB, code chết và ~200MB binary
> commit nhầm vào git. Tổng quát hoá: không còn cứng nhắc chỉ vie/non-vie.

## Hai cách dùng

**1) Tự động (khuyên dùng).** Tha file vào `inbox/` → tự tách + upload:
```bash
pip install .            # hoặc: pip install -r requirements.txt && export PYTHONPATH=src
mkvtools watch           # theo dõi inbox/
mkvtools once phim.mkv   # xử lý 1 file
mkvtools once phim.mkv --no-upload   # chỉ tách, không upload
mkvtools probe phim.mkv  # xem trước track + kế hoạch, không chạy gì
```
Hoặc Docker: `docker compose up -d --build mkvtools`

**2) GUI web (fallback khi pipeline lỗi / muốn làm tay).**
```bash
mkvtools-gui             # mở http://127.0.0.1:8800
```
Chọn file trong inbox → **Phân tích** (xem track) → tick *upload* nếu muốn → **Chạy**,
xem log trực tiếp. Docker: `docker compose up -d gui` rồi mở cổng 8800.

## Cách tách

- `ffprobe` liệt kê audio + subtitle. Mỗi audio → 1 file = **video (copy) + audio đó**
  (`-map 0:v -map 0:a:N -map_metadata 0 -c:v copy`). Audio AAC thì copy, codec khác
  tự chuyển AAC. Container `mkv` còn giữ attachment/font cho sub ASS.
- Phụ đề ghép **cùng ngôn ngữ** với audio (theo language tag, không có thì theo thứ tự);
  sub chữ rút thành `.srt`. Sub ảnh (PGS/VobSub) bỏ qua.
- Đặt tên: `[ĐộPhânGiải]_[Ngôn ngữ]_[Năm]_Tên.mp4` (vd `4K_VIE_2023_Movie.mp4`).

## Upload YouTube — miễn phí

Dùng OAuth (không phải API key trả phí). `videos.insert` ~100 đơn vị/video (từ 12/2025),
quota 10.000/ngày miễn phí. Upload nhanh nhờ `chunksize=-1`.

Lấy quyền 1 lần: tạo project Google Cloud → bật **YouTube Data API v3** →
**OAuth client (Desktop)** → lưu `secrets/client_secret.json`. Lần chạy upload đầu
sẽ mở trình duyệt cấp quyền, tạo `secrets/token.json`.
**Nhớ Publish app (Production)** trong OAuth consent để token không hết hạn sau 7 ngày.

## Cấu hình — `config.yaml`

Copy `config.example.yaml` → `config.yaml`. Khoá chính: `privacy` (private/unlisted/public),
`subtitle_mode` (caption/burn/both), `container` (mp4/mkv), `upload` (true/false),
`make_playlist`, `title_template {base}{lang}{label}`, `playlist_template {base}`.
Có thể override bằng biến môi trường `MKV_<KHOÁ>` (vd `MKV_UPLOAD=false`).

## ffmpeg

Cần `ffmpeg` + `ffprobe`. Linux/Docker: `apt install ffmpeg`. mkvtools tự tìm trong
`./ffmpeg_bin/` rồi đến PATH (binary **không** commit vào git — xem `tools/download_ffmpeg.py`).

## Cấu trúc

```
src/mkvtools/
  ffmpeg_helper.py  # dò ffmpeg/ffprobe (bundle/PATH), probe ẩn cửa sổ CMD  [port từ repo cũ]
  metadata.py       # độ phân giải, năm, mã ngôn ngữ ISO->viết tắt + BCP-47
  splitter.py       # phân tích track, ghép audio↔sub, dựng lệnh ffmpeg (PURE, có test)
  uploader.py       # YouTube Data API: upload nhanh + caption + playlist
  pipeline.py       # lõi: plan -> split -> upload (dùng chung CLI & GUI)
  cli.py            # probe / once / watch
  webui.py          # GUI web fallback (FastAPI)
  config.py
tests/              # test splitter + metadata (5 test, pass)
```

## Tích hợp với ytshare

Để `privacy: private` → video tách ra vẫn private; dùng **ytshare** chia sẻ/cast
cho bạn bè. Dây hoàn chỉnh: tải về → mkvtools (tách + upload private + sub + playlist)
→ ytshare (chia sẻ riêng tư).
