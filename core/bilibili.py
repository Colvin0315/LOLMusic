from __future__ import annotations

import html
import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from http.cookiejar import Cookie, LoadError, MozillaCookieJar
from pathlib import Path
from typing import Any

from core.community_bgm_catalog import CommunityBgmCatalog
from core.music_manager import HeroMusic


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

WBI_MIXIN_KEY_ENC_TAB = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
]


class BilibiliError(RuntimeError):
    pass


@dataclass(frozen=True)
class BilibiliProfile:
    mid: int
    uname: str
    face_url: str = ""
    img_key: str = ""
    sub_key: str = ""


@dataclass(frozen=True)
class BilibiliQrLogin:
    url: str
    qrcode_key: str


@dataclass(frozen=True)
class BilibiliLoginPoll:
    code: int
    message: str
    profile: BilibiliProfile | None = None
    expired: bool = False
    confirmed: bool = False


@dataclass(frozen=True)
class BilibiliVideo:
    title: str
    bvid: str
    author: str
    duration: str
    play_count: int | None
    page_url: str
    player_url: str
    keyword: str


@dataclass(frozen=True)
class BilibiliAudioStream:
    stream_url: str
    backup_urls: list[str]
    headers: dict[str, str]
    cid: int
    duration_seconds: int | None
    bandwidth: int
    quality_id: int | None
    quality_label: str | None


@dataclass(frozen=True)
class BilibiliResolvedAudio:
    video: BilibiliVideo
    stream: BilibiliAudioStream


class BilibiliClient:
    def __init__(self, data_dir: Path | str, community_catalog_path: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.cookie_file = self.data_dir / "bilibili_cookies.txt"
        self.profile_file = self.data_dir / "bilibili_profile.json"
        catalog_path = Path(community_catalog_path) if community_catalog_path is not None else self.data_dir / "community_bgm_catalog.json"
        self.community_bgm_catalog = CommunityBgmCatalog(catalog_path)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.cookies = MozillaCookieJar(str(self.cookie_file))
        self._load_cookies()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))

    def start_qr_login(self) -> BilibiliQrLogin:
        payload = self._request_json(
            "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
            referer="https://passport.bilibili.com/login",
        )
        data = payload.get("data") or {}
        url = str(data.get("url") or "")
        qrcode_key = str(data.get("qrcode_key") or "")
        if not url or not qrcode_key:
            raise BilibiliError("B站没有返回可用的扫码登录二维码")
        return BilibiliQrLogin(url=url, qrcode_key=qrcode_key)

    def poll_qr_login(self, qrcode_key: str) -> BilibiliLoginPoll:
        payload = self._request_json(
            "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
            params={"qrcode_key": qrcode_key},
            referer="https://passport.bilibili.com/login",
        )
        data = payload.get("data") or {}
        code = int(data.get("code", -1))
        message = {
            0: "登录成功",
            86038: "二维码已过期",
            86090: "已扫码，请在手机上确认",
            86101: "等待扫码",
        }.get(code, str(data.get("message") or payload.get("message") or "等待扫码"))

        if code == 0:
            self._save_cookies()
            profile = self.fetch_profile()
            if profile is not None:
                self._save_profile(profile)
            return BilibiliLoginPoll(code=code, message=message, profile=profile, confirmed=True)

        return BilibiliLoginPoll(code=code, message=message, expired=code == 86038, confirmed=code == 86090)

    def fetch_profile(self) -> BilibiliProfile | None:
        payload = self._request_json("https://api.bilibili.com/x/web-interface/nav")
        data = payload.get("data") or {}
        if not data.get("isLogin"):
            return None
        img_key, sub_key = self._extract_wbi_keys(data)
        profile = BilibiliProfile(
            mid=int(data.get("mid") or 0),
            uname=str(data.get("uname") or "B站用户"),
            face_url=str(data.get("face") or ""),
            img_key=img_key,
            sub_key=sub_key,
        )
        self._save_profile(profile)
        return profile

    def cached_profile(self) -> BilibiliProfile | None:
        if not self.profile_file.exists():
            return None
        try:
            payload = json.loads(self.profile_file.read_text(encoding="utf-8"))
            return BilibiliProfile(
                mid=int(payload.get("mid") or 0),
                uname=str(payload.get("uname") or "B站用户"),
                face_url=str(payload.get("face_url") or payload.get("face") or ""),
                img_key=str(payload.get("img_key") or ""),
                sub_key=str(payload.get("sub_key") or ""),
            )
        except (OSError, ValueError, TypeError):
            return None

    def has_saved_session(self) -> bool:
        return self.cookie_file.exists()

    def clear_session(self) -> None:
        self.cookies.clear()
        for path in (self.cookie_file, self.profile_file):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        try:
            self.profile_avatar_file.unlink()
        except FileNotFoundError:
            pass

    @property
    def profile_avatar_file(self) -> Path:
        return self.data_dir / "bilibili_avatar.jpg"

    def cached_profile_avatar(self, profile: BilibiliProfile | None = None) -> Path | None:
        profile = profile or self.cached_profile()
        if (profile is None or not profile.face_url) and self.has_saved_session():
            try:
                profile = self.fetch_profile()
            except BilibiliError:
                profile = profile
        if profile is None or not profile.face_url:
            return self.profile_avatar_file if self.profile_avatar_file.exists() else None
        if self.profile_avatar_file.exists() and self.profile_avatar_file.stat().st_size > 0:
            return self.profile_avatar_file

        request = urllib.request.Request(profile.face_url, headers={"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com/"})
        temp_path = self.profile_avatar_file.with_suffix(".tmp")
        try:
            with self._opener.open(request, timeout=5) as response:
                data = response.read()
            if data:
                temp_path.write_bytes(data)
                temp_path.replace(self.profile_avatar_file)
        except (OSError, urllib.error.URLError):
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

        return self.profile_avatar_file if self.profile_avatar_file.exists() else None

    def cookie_payloads(self) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for cookie in self.cookies:
            if "bilibili.com" not in cookie.domain:
                continue
            payloads.append(
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path or "/",
                    "secure": bool(cookie.secure),
                    "expires": cookie.expires,
                }
            )
        return payloads

    def search_hero_bgm(self, hero: HeroMusic, limit: int = 5) -> list[BilibiliVideo]:
        videos: list[BilibiliVideo] = []
        seen: set[str] = set()
        search_limit = max(limit * 2, 8)

        for index, keyword in enumerate(self._hero_keywords(hero)):
            for video in self.search_videos(keyword, limit=search_limit):
                if video.bvid in seen:
                    continue
                seen.add(video.bvid)
                videos.append(video)

            ranked = self._rank_hero_videos(hero, videos)
            if len(ranked) >= limit and index >= 1:
                return ranked[:limit]
            if index >= 3:
                return ranked[:limit]

        return self._rank_hero_videos(hero, videos)[:limit]

    def search_videos(self, keyword: str, limit: int = 5) -> list[BilibiliVideo]:
        self._ensure_buvid_cookies()
        payload = self._request_json(
            "https://api.bilibili.com/x/web-interface/search/type",
            params={
                "search_type": "video",
                "keyword": keyword,
                "order": "click",
                "duration": "0",
                "page": "1",
            },
            referer=f"https://search.bilibili.com/all?keyword={urllib.parse.quote(keyword)}",
            timeout=5,
        )
        data = payload.get("data") or {}
        results = data.get("result") or []

        videos: list[BilibiliVideo] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            bvid = str(item.get("bvid") or "").strip()
            if not bvid:
                continue
            title = self._clean_title(str(item.get("title") or bvid))
            author = str(item.get("author") or "Bilibili")
            duration = str(item.get("duration") or "")
            page_url = f"https://www.bilibili.com/video/{urllib.parse.quote(bvid)}"
            player_url = (
                "https://player.bilibili.com/player.html?"
                f"bvid={urllib.parse.quote(bvid)}&page=1&autoplay=1&high_quality=1&as_wide=1&danmaku=0"
            )
            videos.append(
                BilibiliVideo(
                    title=title,
                    bvid=bvid,
                    author=author,
                    duration=duration,
                    play_count=self._coerce_int(item.get("play")),
                    page_url=page_url,
                    player_url=player_url,
                    keyword=keyword,
                )
            )
            if len(videos) >= limit:
                break
        return videos

    def resolve_audio_stream(self, video: BilibiliVideo) -> BilibiliResolvedAudio:
        view = self._fetch_video_view(video.bvid)
        cid = int(view.get("cid") or 0)
        if cid <= 0:
            raise BilibiliError("B站视频缺少可播放的 cid")

        signed_params = self._sign_wbi_params(
            {
                "bvid": video.bvid,
                "cid": str(cid),
                "fnval": "4048",
                "fnver": "0",
                "qn": "80",
                "fourk": "1",
            }
        )
        payload = self._request_json(
            "https://api.bilibili.com/x/player/wbi/playurl",
            params=signed_params,
            referer=video.page_url,
            timeout=8,
            extra_headers={"Cookie": self.cookie_header()},
        )
        data = payload.get("data") or {}
        dash = data.get("dash") or {}
        candidates = self._audio_candidates(dash)
        if not candidates:
            raise BilibiliError("B站没有返回可播放的音频流")

        candidates.sort(key=lambda item: int(item.get("bandwidth") or 0), reverse=True)
        selected = candidates[0]
        stream_url = str(selected.get("baseUrl") or selected.get("base_url") or "")
        if not stream_url:
            raise BilibiliError("B站音频流地址为空")

        resolved_video = BilibiliVideo(
            title=str(view.get("title") or video.title),
            bvid=video.bvid,
            author=str(view.get("author") or video.author),
            duration=video.duration,
            play_count=video.play_count,
            page_url=video.page_url,
            player_url=video.player_url,
            keyword=video.keyword,
        )
        duration_ms = self._coerce_int(data.get("timelength"))
        quality_id = self._coerce_int(selected.get("id"))
        bandwidth = self._coerce_int(selected.get("bandwidth")) or 0
        stream = BilibiliAudioStream(
            stream_url=stream_url,
            backup_urls=[*self._string_list(selected.get("backupUrl")), *self._string_list(selected.get("backup_url"))],
            headers=self._playback_headers(video.page_url),
            cid=cid,
            duration_seconds=(duration_ms // 1000) if duration_ms else None,
            bandwidth=bandwidth,
            quality_id=quality_id,
            quality_label=self._quality_label(quality_id, bandwidth),
        )
        return BilibiliResolvedAudio(video=resolved_video, stream=stream)

    def resolve_first_playable_audio(self, videos: list[BilibiliVideo]) -> BilibiliResolvedAudio:
        last_error: Exception | None = None
        for video in videos:
            try:
                return self.resolve_audio_stream(video)
            except BilibiliError as exc:
                last_error = exc
        if last_error is not None:
            raise BilibiliError(str(last_error)) from last_error
        raise BilibiliError("没有可解析的 B 站视频")

    def _request_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        referer: str = "https://www.bilibili.com/",
        timeout: int = 10,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Content-Type": "application/json",
            "Connection": "keep-alive",
            "Origin": "https://www.bilibili.com",
            "Referer": referer,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }
        if extra_headers:
            headers.update({key: value for key, value in extra_headers.items() if value})

        request = urllib.request.Request(url, headers=headers)

        try:
            with self._opener.open(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise BilibiliError(f"B站请求失败：{reason}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BilibiliError("B站返回了无法解析的数据") from exc

        code = payload.get("code")
        if code not in (None, 0):
            message = payload.get("message") or payload.get("msg") or f"错误码 {code}"
            raise BilibiliError(f"B站接口返回错误：{message}")

        self._save_cookies()
        return payload

    def _load_cookies(self) -> None:
        if not self.cookie_file.exists():
            return
        try:
            self.cookies.load(ignore_discard=True, ignore_expires=True)
        except (LoadError, OSError):
            self.cookies.clear()

    def _save_cookies(self) -> None:
        self.cookies.save(ignore_discard=True, ignore_expires=True)

    def _save_profile(self, profile: BilibiliProfile) -> None:
        self.profile_file.write_text(json.dumps(asdict(profile), ensure_ascii=False, indent=2), encoding="utf-8")

    def _ensure_buvid_cookies(self) -> None:
        if self._has_cookie("buvid3") and self._has_cookie("buvid4"):
            return

        payload = self._request_json("https://api.bilibili.com/x/frontend/finger/spi", timeout=5)
        data = payload.get("data") or {}
        expires = int(time.time()) + 365 * 24 * 60 * 60
        b3 = str(data.get("b_3") or "")
        b4 = str(data.get("b_4") or "")
        if b3:
            self._set_cookie("buvid3", b3, expires=expires)
        if b4:
            self._set_cookie("buvid4", b4, expires=expires)
        self._set_cookie("b_nut", str(int(time.time())), expires=expires)
        self._save_cookies()

    def _has_cookie(self, name: str) -> bool:
        return any(cookie.name == name and "bilibili.com" in cookie.domain for cookie in self.cookies)

    def _set_cookie(self, name: str, value: str, expires: int | None = None) -> None:
        cookie = Cookie(
            version=0,
            name=name,
            value=value,
            port=None,
            port_specified=False,
            domain=".bilibili.com",
            domain_specified=True,
            domain_initial_dot=True,
            path="/",
            path_specified=True,
            secure=False,
            expires=expires,
            discard=expires is None,
            comment=None,
            comment_url=None,
            rest={},
            rfc2109=False,
        )
        self.cookies.set_cookie(cookie)

    def _fetch_video_view(self, bvid: str) -> dict[str, Any]:
        payload = self._request_json(
            "https://api.bilibili.com/x/web-interface/view",
            params={"bvid": bvid},
            referer=f"https://www.bilibili.com/video/{urllib.parse.quote(bvid)}",
            timeout=6,
        )
        data = payload.get("data") or {}
        pages = data.get("pages") or []
        if not pages:
            raise BilibiliError("B站视频没有可播放分P")
        first_page = pages[0] if isinstance(pages[0], dict) else {}
        owner = data.get("owner") if isinstance(data.get("owner"), dict) else {}
        return {
            "cid": first_page.get("cid"),
            "title": data.get("title"),
            "author": owner.get("name"),
        }

    def _sign_wbi_params(self, params: dict[str, Any]) -> dict[str, Any]:
        img_key, sub_key = self._current_wbi_keys()
        if not img_key or not sub_key:
            raise BilibiliError("当前 B 站登录态缺少 WBI key，请重新扫码登录")

        mixin_key = self._mixin_key(img_key + sub_key)
        wts = int(time.time())
        normalized = {key: self._normalize_wbi_value(value) for key, value in params.items()}
        normalized["wts"] = str(wts)
        query = "&".join(
            f"{urllib.parse.quote(key, safe='')}={urllib.parse.quote(normalized[key], safe='')}"
            for key in sorted(normalized)
        )
        w_rid = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
        return {**params, "wts": wts, "w_rid": w_rid}

    def _current_wbi_keys(self) -> tuple[str, str]:
        profile = self.cached_profile()
        if profile is not None and profile.img_key and profile.sub_key:
            return profile.img_key, profile.sub_key

        payload = self._request_json(
            "https://api.bilibili.com/x/web-interface/nav",
            timeout=6,
            extra_headers={"Cookie": self.cookie_header()},
        )
        data = payload.get("data") or {}
        if not data.get("isLogin"):
            raise BilibiliError("B站登录态已失效，请重新扫码登录")
        img_key, sub_key = self._extract_wbi_keys(data)
        profile = BilibiliProfile(
            mid=int(data.get("mid") or 0),
            uname=str(data.get("uname") or "B站用户"),
            face_url=str(data.get("face") or ""),
            img_key=img_key,
            sub_key=sub_key,
        )
        self._save_profile(profile)
        return img_key, sub_key

    def _extract_wbi_keys(self, nav_data: dict[str, Any]) -> tuple[str, str]:
        wbi_img = nav_data.get("wbi_img") if isinstance(nav_data.get("wbi_img"), dict) else {}
        return self._extract_key_from_url(str(wbi_img.get("img_url") or "")), self._extract_key_from_url(
            str(wbi_img.get("sub_url") or "")
        )

    @staticmethod
    def _extract_key_from_url(url: str) -> str:
        if not url:
            return ""
        path = urllib.parse.urlparse(url).path
        name = path.rsplit("/", 1)[-1]
        return name.rsplit(".", 1)[0] if "." in name else name

    @staticmethod
    def _mixin_key(raw: str) -> str:
        return "".join(raw[index] for index in WBI_MIXIN_KEY_ENC_TAB if index < len(raw))[:32]

    @staticmethod
    def _normalize_wbi_value(value: Any) -> str:
        return re.sub(r"[!'()*]", "", str(value if value is not None else ""))

    def _audio_candidates(self, dash: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = [item for item in dash.get("audio") or [] if isinstance(item, dict)]
        flac = dash.get("flac") if isinstance(dash.get("flac"), dict) else {}
        flac_audio = flac.get("audio") if isinstance(flac.get("audio"), dict) else None
        if flac_audio:
            candidates.append(flac_audio)
        return candidates

    def _playback_headers(self, page_url: str) -> dict[str, str]:
        cookie = self.cookie_header()
        return {
            "User-Agent": USER_AGENT,
            "Referer": page_url,
            "Origin": "https://www.bilibili.com",
            **({"Cookie": cookie} if cookie else {}),
        }

    def cookie_header(self) -> str:
        pairs = []
        for cookie in self.cookies:
            if "bilibili.com" not in cookie.domain:
                continue
            pairs.append(f"{cookie.name}={cookie.value}")
        return "; ".join(pairs)

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if isinstance(item, str) and item]

    @staticmethod
    def _quality_label(quality_id: int | None, bandwidth: int) -> str | None:
        labels = {
            30251: "Hi-Res",
            30280: "192K",
            30232: "132K",
            30216: "64K",
            30250: "Dolby",
        }
        if quality_id in labels:
            return labels[quality_id]
        if bandwidth > 0:
            return f"{round(bandwidth / 1000)} kbps"
        return None

    def _hero_keywords(self, hero: HeroMusic) -> list[str]:
        catalog_keywords = self.community_bgm_catalog.keywords_for(hero)
        if catalog_keywords:
            return catalog_keywords

        english = hero.english_name.strip() or hero.key.replace("_", " ")
        compact = english.replace("'", "")
        values = [
            f"LOL {english} 专属BGM",
            f"{english} 小曲 英雄联盟",
            f"{english} montage BGM League of Legends",
        ]
        if compact != english:
            values.append(f"LOL {compact} 专属BGM")

        unique: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = value.lower()
            if normalized not in seen:
                unique.append(value)
                seen.add(normalized)
        return unique

    def _rank_hero_videos(self, hero: HeroMusic, videos: list[BilibiliVideo]) -> list[BilibiliVideo]:
        scored = [(self._score_hero_video(hero, video), -index, video) for index, video in enumerate(videos)]
        scored.sort(reverse=True)
        return [video for _, _, video in scored]

    def _score_hero_video(self, hero: HeroMusic, video: BilibiliVideo) -> float:
        title = video.title.lower()
        normalized_title = self._normalize_search_text(video.title)
        score = 0.0

        if "の小曲" in video.keyword:
            score += 12.0
            if "の小曲" in video.title:
                score += 8.0
        elif "小曲" in video.keyword:
            score += 5.0

        if video.play_count:
            score += min(math.log10(video.play_count + 1), 6) * 0.15

        indicator_matches = 0
        for indicator in ("bgm", "小曲", "专属", "背景音乐", "配乐", "循环歌单", "单曲循环", "music", "song"):
            if indicator in title:
                indicator_matches += 1
        score += indicator_matches * 3.0

        hero_term_matched = False
        for term in self._hero_search_terms(hero):
            if term and term in normalized_title:
                hero_term_matched = True
                score += 2.5

        important_matches = 0
        for term in self._meaningful_keyword_terms(video.keyword):
            if term and term in normalized_title:
                important_matches += 1
                score += 6.0

        if not hero_term_matched and important_matches == 0:
            score -= 4.0
        if indicator_matches == 0:
            score -= 2.0

        return score

    @staticmethod
    def _hero_search_terms(hero: HeroMusic) -> list[str]:
        values = [hero.key.replace("_", ""), hero.english_name, hero.english_name.replace("'", "").replace(".", "")]
        values.extend(hero.aliases)
        unique: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = BilibiliClient._normalize_search_text(str(value))
            if normalized and normalized not in seen:
                unique.append(normalized)
                seen.add(normalized)
        return unique

    @staticmethod
    def _meaningful_keyword_terms(keyword: str) -> list[str]:
        generic = {
            "lol",
            "league",
            "of",
            "legends",
            "英雄联盟",
            "bgm",
            "专属",
            "小曲",
            "高燃",
            "montage",
            "music",
            "song",
            "background",
            "remix",
        }
        raw_terms = re.findall(r"[a-zA-Z0-9']+|[\u4e00-\u9fff]+", keyword.lower())
        terms: list[str] = []
        seen: set[str] = set()
        for raw in raw_terms:
            term = BilibiliClient._normalize_search_text(raw)
            if len(term) <= 1 or term in generic or term in seen:
                continue
            terms.append(term)
            seen.add(term)
        return terms

    @staticmethod
    def _normalize_search_text(value: str) -> str:
        return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", value).lower()

    @staticmethod
    def _clean_title(value: str) -> str:
        text = re.sub(r"<[^>]+>", "", value)
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            cleaned = value.replace(",", "").strip()
            if cleaned.isdigit():
                return int(cleaned)
        return None
