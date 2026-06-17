# LOLMusic

LOLMusic is a Python/PySide desktop app for League of Legends champion-select BGM.
It watches the local League Client LCU state, identifies the selected champion, searches
Bilibili for related popular BGM videos, and plays the resolved audio stream through the
local PySide media player.

## Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Optional OCR fallback dependencies:

```powershell
python -m pip install -r requirements-ocr.txt
```

## Build portable Windows package

```powershell
python -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File scripts/build_windows_portable.ps1
```

The portable archive is written to `release/RiftBGM-v1.0.0-windows-x64.zip`.
It excludes local Bilibili login state, app settings, logs, OCR dependencies, and champion
image cache. Runtime user data is stored under `%LOCALAPPDATA%\RiftBGM`.

## Behavior

- Uses LCU first to detect the selected champion, with OCR fallback when configured.
- Supports Bilibili QR-code login.
- Searches Bilibili for champion-related BGM videos, prioritizing the local community
  BGM catalog in `data/community_bgm_catalog.json`.
- Resolves the selected Bilibili result to an online audio stream and forwards it through a
  local in-memory proxy so `QMediaPlayer` can play it with the required request headers.
- Includes a real music library page, hero search, persistent favorites, and settings for
  auto-scan / Bilibili-priority playback.
- Does not download or permanently cache Bilibili audio.
- Falls back to bundled local demo audio if Bilibili lookup or playback resolution fails.

## Local Data

- `data/community_bgm_catalog.json`: editable community search terms such as Akali + 梨花香,
  Yasuo + 面对疾风吧, Pantheon + Rise And Fall, and Sett + Repeat/够格小曲.
- `data/app_state.json`: local user state for favorites and settings. This file is ignored.
- `data/bilibili_cookies.txt` and `data/bilibili_profile.json`: local Bilibili login state.
  These files are ignored.
