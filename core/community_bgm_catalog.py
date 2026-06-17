from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.music_manager import HeroMusic


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


class CommunityBgmCatalog:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.payload = self._load()

    def keywords_for(self, hero: HeroMusic) -> list[str]:
        context = self._context(hero)
        values: list[str] = [
            f"{context['primary_alias']}の小曲",
        ]

        override = self.overrides.get(hero.key.lower())
        if isinstance(override, dict):
            values.extend(self._expand_many(override.get("queries"), context))

        values.extend(self._expand_many(self.default_query_templates, context))

        english = context["english_name"]
        compact = context["english_compact"]
        if compact and compact != english:
            compact_context = {**context, "english_name": compact}
            values.extend(self._expand_many(self.default_query_templates, compact_context))

        return self._unique(values)

    def add_comment_text(self, hero: HeroMusic, text: str, source_label: str = "manual import") -> list[str]:
        queries = self.extract_queries_from_text(hero, text)
        return self.add_queries(hero, queries, source_label=source_label)

    def add_queries(self, hero: HeroMusic, queries: list[str], source_label: str = "manual import") -> list[str]:
        cleaned = self._unique([query for query in queries if query.strip()])
        if not cleaned:
            return []

        overrides = self.payload.setdefault("overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}
            self.payload["overrides"] = overrides

        key = hero.key.lower()
        override = overrides.get(key)
        if not isinstance(override, dict):
            override = {"confidence": "manual", "queries": []}
            overrides[key] = override

        existing = [str(query) for query in override.get("queries", []) if str(query).strip()]
        existing_norm = {query.lower() for query in existing}
        added = [query for query in cleaned if query.lower() not in existing_norm]
        if not added:
            return []

        override["confidence"] = override.get("confidence") or "manual"
        override["queries"] = self._unique([*existing, *added])
        note = str(override.get("notes") or "").strip()
        if "手动导入" not in note:
            override["notes"] = (note + "；" if note else "") + "支持从小红书/社区评论手动导入。"

        source_notes = self.payload.setdefault("source_notes", [])
        if isinstance(source_notes, list):
            label = f"Manual community import: {hero.english_name}"
            if not any(isinstance(item, dict) and item.get("label") == label for item in source_notes):
                source_notes.append(
                    {
                        "label": label,
                        "note": source_label,
                    }
                )

        self.save()
        return added

    def extract_queries_from_text(self, hero: HeroMusic, text: str) -> list[str]:
        primary = self._primary_alias(hero)
        terms: list[str] = []

        for match in re.finditer(r"[《\"“]([^》\"”]{2,48})[》\"”]", text):
            terms.append(match.group(1))
        for match in re.finditer(r"#([0-9a-zA-Z\u4e00-\u9fff _-]{2,48})", text):
            terms.append(match.group(1))

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lower = line.lower()
            if not any(marker in lower for marker in ("bgm", "小曲", "专属", "推荐", "歌", "music", "song")):
                continue
            terms.append(line)

        queries: list[str] = []
        hero_terms = [self._normalize(alias) for alias in (*hero.aliases, hero.display_name, hero.english_name)]
        for term in self._unique(terms):
            clean = self._clean_import_term(term, hero_terms)
            if not clean:
                continue
            normalized = self._normalize(clean)
            mentions_hero = any(hero_term and hero_term in normalized for hero_term in hero_terms)
            if mentions_hero or "bgm" in clean.lower() or "小曲" in clean:
                queries.append(clean)
            else:
                queries.append(f"{primary} {clean} BGM")
                queries.append(f"{clean} {primary}")

        return self._unique(queries)[:18]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def default_query_templates(self) -> list[str]:
        templates = self.payload.get("default_query_templates")
        if isinstance(templates, list) and templates:
            return [str(template) for template in templates if str(template).strip()]
        return [
            "{primary_alias}の小曲",
            "{primary_alias} 小曲",
            "{primary_alias} 专属BGM 英雄联盟",
            "LOL {english_name} 专属BGM",
            "{english_name} montage BGM League of Legends",
        ]

    @property
    def overrides(self) -> dict[str, Any]:
        overrides = self.payload.get("overrides")
        if not isinstance(overrides, dict):
            return {}
        return {str(key).lower(): value for key, value in overrides.items()}

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _context(self, hero: HeroMusic) -> dict[str, str]:
        english = hero.english_name.strip() or hero.key.replace("_", " ")
        primary_alias = self._primary_alias(hero)
        return {
            "hero_key": hero.key,
            "display_name": hero.display_name.strip(),
            "primary_alias": primary_alias,
            "english_name": english,
            "english_compact": english.replace("'", "").replace(".", ""),
        }

    def _primary_alias(self, hero: HeroMusic) -> str:
        cjk_aliases: list[str] = []
        for value in (*hero.aliases, hero.display_name):
            text = str(value).strip()
            if text and _CJK_RE.search(text):
                cjk_aliases.append(text)

        short_aliases = [alias for alias in cjk_aliases if " " not in alias and 2 <= len(alias) <= 4]
        if short_aliases:
            return min(short_aliases, key=len)

        compact_aliases = [alias for alias in cjk_aliases if " " not in alias]
        if compact_aliases:
            return min(compact_aliases, key=len)

        if cjk_aliases:
            return cjk_aliases[0]
        return hero.english_name.strip() or hero.key.replace("_", " ")

    def _expand_many(self, values: Any, context: dict[str, str]) -> list[str]:
        if not isinstance(values, list):
            return []
        expanded: list[str] = []
        for value in values:
            template = str(value).strip()
            if not template:
                continue
            try:
                expanded.append(template.format_map(context))
            except KeyError:
                expanded.append(template)
        return expanded

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = re.sub(r"\s+", " ", value).strip()
            normalized = text.lower()
            if text and normalized not in seen:
                unique.append(text)
                seen.add(normalized)
        return unique

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", value).lower()

    @staticmethod
    def _clean_import_term(value: str, hero_terms: list[str]) -> str:
        text = re.sub(r"https?://\S+", " ", value)
        text = re.sub(r"[@#【】\[\]（）()：:，,。；;！!？?]+", " ", text)
        text = re.sub(
            r"\b(lol|league of legends|music|song)\b|英雄联盟|专属|推荐|评论区|歌名|歌曲|音乐|这首|适合|很搭|绝了|就是|叫什么",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        for hero_term in hero_terms:
            if len(hero_term) >= 2:
                text = re.sub(re.escape(hero_term), " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip(" -_·/\\")
        if len(text) < 2 or len(text) > 48:
            return ""
        if text.lower() in {"bgm", "小曲", "专属bgm"}:
            return ""
        return text
