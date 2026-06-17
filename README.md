# LOLMusic / Rift BGM

Rift BGM 是一个基于 Python/PySide6 的英雄联盟选英雄阶段 BGM 播放器。

它会优先监听本机 League Client 的 LCU 状态，识别当前选择或锁定的英雄，然后到 Bilibili 搜索对应英雄的热门民间 BGM 视频，并通过本地播放器解析在线音频流播放。B 站音频只在线播放，不会下载或永久缓存。

## 下载

Windows 绿色版可以在 GitHub Release 下载：

[Rift BGM v1.0.0](https://github.com/Colvin0315/LOLMusic/releases/tag/v1.0.0)

下载 `RiftBGM-v1.0.0-windows-x64.zip` 后解压，双击 `RiftBGM.exe` 即可运行。

## 本地运行

```powershell
python -m pip install -r requirements.txt
python main.py
```

可选 OCR 兜底依赖：

```powershell
python -m pip install -r requirements-ocr.txt
```

当前便携版默认不内置 OCR 大依赖，主要使用 LCU 识别选英雄。

## 打包 Windows 便携版

```powershell
python -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File scripts/build_windows_portable.ps1
```

打包产物会生成到：

```text
release/RiftBGM-v1.0.0-windows-x64.zip
```

发布包不会包含你的 Bilibili 登录态、本机设置、日志、缓存、OCR 依赖或英雄图片缓存。

## 功能

- 自动监听英雄联盟客户端选英雄状态。
- 根据识别到的英雄搜索 B 站热门民间 BGM。
- 支持 Bilibili 扫码登录，提高播放兼容性。
- 通过本地流代理解析 B 站在线音频，交给 PySide `QMediaPlayer` 播放。
- 支持收藏、历史记录、自动播放、音量和界面尺寸设置。
- 英雄头像和背景图首次使用时联网缓存。
- B 站搜索或播放失败时，会回落到本地兜底音频。

## 本地数据

运行时用户数据默认保存在：

```text
%LOCALAPPDATA%\RiftBGM
```

常见文件：

- `app_state.json`：收藏、音量、自动播放和界面尺寸设置。
- `bilibili_cookies.txt`：Bilibili 登录 cookies。
- `bilibili_profile.json`：Bilibili 用户信息缓存。
- `bilibili_avatar.jpg`：Bilibili 头像缓存。
- `data/community_bgm_catalog.json`：可编辑的社区 BGM 搜索词库。
- `champions/`：英雄头像和背景图缓存。

这些运行时文件不会提交到仓库，也不会打进发布包。

## 项目结构

- `main.py`：应用入口。
- `ui/`：PySide 界面。
- `core/`：LCU 识别、Bilibili、播放器、路径和资源管理逻辑。
- `data/`：英雄映射和社区 BGM 搜索词库种子。
- `assets/music/`：本地兜底音频。
- `packaging/RiftBGM.spec`：PyInstaller 打包配置。
- `scripts/build_windows_portable.ps1`：Windows 便携包构建脚本。
