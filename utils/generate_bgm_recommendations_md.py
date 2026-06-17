from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HERO_MAP_PATH = ROOT / "data" / "hero_music_map.json"
OUTPUT_PATH = ROOT / "docs" / "hero_bgm_recommendations.md"

SONGS = {
    "night_dancer": ("NIGHT DANCER", "imase", "夜色、轻快、卡点感强"),
    "cloudy": ("阴天", "莫文蔚", "压抑、冷调、情绪拉满"),
    "sunny": ("晴天", "周杰伦", "明亮、青春、治愈"),
    "lover": ("恋人", "李荣浩", "浪漫、双人线、轻松律动"),
    "pipa": ("琵琶行", "奇然 / 沈谧仁", "国风、叙事、古韵"),
    "later_us": ("后来的我们", "五月天", "遗憾、失去、宿命感"),
    "stranded": ("搁浅", "周杰伦", "孤独、执念、破碎感"),
    "rain_love": ("雨爱", "杨丞琳", "水汽、雨幕、柔和情绪"),
    "miss": ("我怀念的", "孙燕姿", "回忆、伤感、旧梦"),
    "unique": ("唯一", "G.E.M. 邓紫棋", "高光、爆发、唯一信念"),
    "spring": ("春娇与志明", "街道办GDC / 欧阳耀莹", "都市、松弛、暧昧"),
    "online": ("Always Online", "林俊杰", "科技感、连接感、轻快"),
    "half": ("小半", "陈粒", "孤独、私语、文艺感"),
    "nocturne": ("夜曲", "周杰伦", "暗夜、刺杀、宿命"),
    "inn": ("红尘客栈", "周杰伦", "江湖、剑客、侠气"),
    "actor": ("演员", "薛之谦", "戏剧、伪装、舞台感"),
    "understand": ("开始懂了", "孙燕姿", "成长、时间、释然"),
    "special": ("特别的人", "方大同", "守护、温暖、治愈"),
    "appear_leave": ("出现又离开 (Live)", "梁博", "浪人、落寞、离去"),
    "friend": ("最佳损友", "陈奕迅", "羁绊、背叛、复杂关系"),
    "balalaika": ("巴拉莱卡 (The Rod) (Live)", "张靓颖 / 陈楚生", "史诗、民谣张力、远征"),
    "crazy_love": ("为爱痴狂2026 (想要问问你敢不敢)", "金志文", "热血、执拗、冲锋"),
    "danger": ("迷人的危险", "姚晓棠", "危险、诱惑、暗流"),
    "iconic": ("ICONIC BY MISTAKE", "LE SSERAFIM / ILLIT / KATSEYE", "锋利、时髦、女王感"),
    "ignite": ("淬火 (IGNITE)", "李佳薇 / DNFU地下城与勇士", "战斗、锻造、燃点"),
    "long_road": ("人生路漫漫 (Live)", "孙楠 / 白小白 / 加木", "远行、厚重、史诗旅程"),
    "waiting": ("等你的季节", "赵乃吉", "等待、季节、柔软"),
    "slow": ("迟迟 (Live)", "薛之谦", "迟疑、拉扯、伤感"),
    "just_so": ("就这样", "何浩楠 / 王一珩OneSD", "轻松、日常、少年感"),
    "ballad": ("Баллада", "Xcho / Мот", "异域、阴影、低沉"),
    "dont_cry": ("我不哭", "王栎鑫", "强忍、悲伤、硬撑"),
    "my_way": ("Reno My Way", "宋雨琦 (YUQI)", "酷感、速度、未来"),
    "peach": ("十里桃花 待嫁的年华 (雷鬼R&B)", "贝利伢", "花影、灵动、东方甜感"),
    "next_crossing": ("下个，路口，见 (Live)", "李宇春", "街头、利落、转身"),
    "heart_cloud": ("心云", "半吨兄弟", "云、风、守护、轻柔"),
    "red_blue": ("赤と青", "ROTH BART BARON", "双面、冷暖对照、宿命"),
    "one_got_away": ("The One That Got Away", "Katy Perry", "失去、回忆、悲剧美"),
    "drop_dead": ("Drop Dead", "Olivia Rodrigo", "复仇、重生、极端情绪"),
    "young": ("Young, Dumb & Broke", "Khalid", "少年、伙伴、轻松"),
    "everglades": ("Everglades", "AZIEDOESNTEXIST", "竞速、野性、肾上腺素"),
    "earrings": ("Earrings", "Malcolm Todd", "酷感、生活流、轻盈"),
    "cinderella": ("Cinderella", "TikTok Trend", "梦幻、奇遇、童话感"),
    "sugar": ("Sugar On My Tongue", "TikTok Trend", "甜、俏皮、带一点危险"),
    "not_over": ("It Ain't Over 'Til It's Over", "Lenny Kravitz", "坚韧、续命、反打"),
    "motion": ("Motion Party", "TikTok Trend", "高动能、派对、跳跃"),
    "delilah": ("Hey There Delilah", "Plain White T's", "温柔、陪伴、轻声告白"),
    "space": ("space", "Shakira / Burna Boy", "星空、远方、宇宙感"),
    "drama": ("Drama", "aespa", "戏剧、强势、冷酷"),
    "standing": ("Standing Next to You", "Jung Kook", "并肩、守护、节奏感"),
    "baddie": ("Baddie", "IVE", "张扬、锋利、叛逆"),
    "risk": ("Risk It All", "Bruno Mars", "冒险、华丽、赌上一切"),
    "no_broke": ("No Broke Boys", "Disco Lines / Tinashe", "潇洒、节奏、都市狠劲"),
    "lights_off": ("Turn The Lights Off", "Kato / Jon", "关灯、潜行、电子暗色"),
    "dragostea": ("Dragostea Din Tei", "O-Zone / Remix", "魔性、搞怪、洗脑"),
}

HERO_TO_SONG = {
    "annie": "sugar",
    "olaf": "ignite",
    "galio": "standing",
    "twisted_fate": "night_dancer",
    "xin_zhao": "inn",
    "urgot": "lights_off",
    "leblanc": "danger",
    "vladimir": "ballad",
    "fiddlesticks": "lights_off",
    "kayle": "ignite",
    "master_yi": "inn",
    "alistar": "standing",
    "ryze": "online",
    "sion": "not_over",
    "sivir": "everglades",
    "soraka": "special",
    "teemo": "dragostea",
    "tristana": "motion",
    "warwick": "lights_off",
    "nunu": "young",
    "miss_fortune": "baddie",
    "ashe": "red_blue",
    "tryndamere": "crazy_love",
    "jax": "ignite",
    "morgana": "cloudy",
    "zilean": "understand",
    "singed": "motion",
    "evelynn": "danger",
    "twitch": "lights_off",
    "karthus": "nocturne",
    "chogath": "lights_off",
    "amumu": "dont_cry",
    "rammus": "everglades",
    "anivia": "red_blue",
    "shaco": "drama",
    "dr_mundo": "motion",
    "sona": "special",
    "kassadin": "space",
    "irelia": "inn",
    "janna": "sunny",
    "gangplank": "long_road",
    "corki": "everglades",
    "karma": "heart_cloud",
    "taric": "standing",
    "veigar": "drama",
    "trundle": "balalaika",
    "swain": "ballad",
    "caitlyn": "iconic",
    "blitzcrank": "online",
    "malphite": "ignite",
    "katarina": "baddie",
    "nocturne": "nocturne",
    "maokai": "not_over",
    "renekton": "ignite",
    "jarvan_iv": "standing",
    "elise": "danger",
    "orianna": "online",
    "monkey_king": "inn",
    "brand": "ignite",
    "lee_sin": "ignite",
    "vayne": "nocturne",
    "rumble": "my_way",
    "cassiopeia": "danger",
    "skarner": "ignite",
    "heimerdinger": "online",
    "nasus": "long_road",
    "nidalee": "everglades",
    "udyr": "not_over",
    "poppy": "standing",
    "gragas": "motion",
    "pantheon": "ignite",
    "ezreal": "night_dancer",
    "mordekaiser": "ballad",
    "yorick": "later_us",
    "akali": "iconic",
    "kennen": "night_dancer",
    "garen": "standing",
    "leona": "sunny",
    "malzahar": "space",
    "talon": "nocturne",
    "riven": "appear_leave",
    "kog_maw": "motion",
    "shen": "heart_cloud",
    "lux": "sunny",
    "xerath": "space",
    "shyvana": "ignite",
    "ahri": "danger",
    "graves": "no_broke",
    "fizz": "motion",
    "volibear": "ignite",
    "rengar": "everglades",
    "varus": "stranded",
    "nautilus": "ballad",
    "viktor": "online",
    "sejuani": "red_blue",
    "fiora": "iconic",
    "ziggs": "motion",
    "lulu": "sugar",
    "draven": "iconic",
    "hecarim": "everglades",
    "khazix": "lights_off",
    "darius": "ignite",
    "jayce": "my_way",
    "lissandra": "cloudy",
    "diana": "nocturne",
    "quinn": "everglades",
    "syndra": "drama",
    "aurelion_sol": "space",
    "kayn": "red_blue",
    "zoe": "cinderella",
    "zyra": "peach",
    "kaisa": "space",
    "seraphine": "night_dancer",
    "gnar": "young",
    "zac": "motion",
    "yasuo": "appear_leave",
    "velkoz": "space",
    "taliyah": "long_road",
    "camille": "iconic",
    "akshan": "no_broke",
    "belveth": "drama",
    "braum": "standing",
    "jhin": "actor",
    "kindred": "one_got_away",
    "zeri": "my_way",
    "jinx": "baddie",
    "tahm_kench": "danger",
    "briar": "drop_dead",
    "viego": "later_us",
    "senna": "not_over",
    "lucian": "everglades",
    "zed": "lights_off",
    "kled": "motion",
    "ekko": "night_dancer",
    "qiyana": "baddie",
    "vi": "ignite",
    "aatrox": "ignite",
    "nami": "rain_love",
    "azir": "balalaika",
    "yuumi": "delilah",
    "samira": "baddie",
    "thresh": "nocturne",
    "illaoi": "long_road",
    "rek_sai": "lights_off",
    "ivern": "special",
    "kalista": "stranded",
    "bard": "space",
    "rakan": "lover",
    "xayah": "lover",
    "ornn": "ignite",
    "sylas": "crazy_love",
    "neeko": "peach",
    "aphelios": "nocturne",
    "rell": "ignite",
    "pyke": "nocturne",
    "vex": "cloudy",
    "yone": "red_blue",
    "ambessa": "ignite",
    "mel": "risk",
    "yunara": "sunny",
    "sett": "crazy_love",
    "lillia": "cinderella",
    "gwen": "sugar",
    "renata": "danger",
    "aurora": "cinderella",
    "nilah": "motion",
    "ksante": "standing",
    "smolder": "sugar",
    "milio": "sunny",
    "zaahen": "ignite",
    "hwei": "pipa",
    "naafiri": "everglades",
}

DEFAULT_BY_TAG = {
    "assassin": "nocturne",
    "fighter": "ignite",
    "tank": "standing",
    "mage": "space",
    "marksman": "everglades",
    "support": "special",
}


def main() -> None:
    heroes = json.loads(HERO_MAP_PATH.read_text(encoding="utf-8"))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# 英雄联盟全英雄抖音热歌风格 BGM 推荐",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "- 用途：给 Rift BGM 做选曲参考；这里只列歌名/歌手，不下载音频。",
        "- 说明：这是基于热歌榜/短视频趋势 + 英雄气质的主观适配表，不代表平台官方“该英雄使用最多”的统计。",
        "- 英雄数据源：Riot Data Dragon `16.12.1`，本地文件 `data/hero_music_map.json`。",
        "",
        "## 参考热歌源",
        "",
        "- QQ音乐：抖音热歌榜（06.05-06.11）",
        "- QQ音乐：流行指数榜（2026-06-16）",
        "- Buffer：TikTok Trending Songs and Sounds（Updated June 2026）",
        "- Tokchart：Top Trending Audios on TikTok Today（Last updated June 16, 2026）",
        "",
        "## 推荐清单",
        "",
        "| # | 英雄 | English | 推荐曲 | 歌手 | 适配理由 |",
        "|---:|---|---|---|---|---|",
    ]

    missing = []
    for index, (hero_key, hero) in enumerate(heroes.items(), start=1):
        song_key = HERO_TO_SONG.get(hero_key) or choose_default(hero.get("tags", []))
        if hero_key not in HERO_TO_SONG:
            missing.append(hero_key)
        title, artist, vibe = SONGS[song_key]
        tags = " / ".join(hero.get("tags", [])[:2])
        reason = f"{vibe}；贴合 {hero['display_name']} 的 {tags or '英雄'} 气质。"
        lines.append(
            "| {index} | {hero} | {english} | {song} | {artist} | {reason} |".format(
                index=index,
                hero=escape_md(hero["display_name"]),
                english=escape_md(hero["english_name"]),
                song=escape_md(title),
                artist=escape_md(artist),
                reason=escape_md(reason),
            )
        )

    lines.extend(
        [
            "",
            "## 版权提醒",
            "",
            "这份表只用于选曲规划。实际接入 Rift BGM 时，请使用你自己购买、授权、原创或平台允许离线使用的音频文件。",
            "",
            "## 生成备注",
            "",
            f"- 覆盖英雄数：{len(heroes)}",
            f"- 未显式配置而走默认规则的英雄数：{len(missing)}",
        ]
    )
    if missing:
        lines.append(f"- 默认规则英雄：{', '.join(missing)}")

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    print(f"Heroes: {len(heroes)}, fallback: {len(missing)}")


def choose_default(tags: list[str]) -> str:
    for tag in tags:
        if tag in DEFAULT_BY_TAG:
            return DEFAULT_BY_TAG[tag]
    return "night_dancer"


def escape_md(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    main()
