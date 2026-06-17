from __future__ import annotations

import base64
import json
import re
import ssl
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.paths import user_data_path


class LcuClientError(RuntimeError):
    pass


class LcuUnavailableError(LcuClientError):
    pass


class LcuNotInChampSelectError(LcuClientError):
    pass


@dataclass(frozen=True)
class LcuAuth:
    port: int
    auth_token: str
    pid: int | None = None
    region: str = ""
    source: str = ""


@dataclass(frozen=True)
class LcuSelection:
    champion_id: int
    is_locked: bool
    source: str
    champion_name: str = ""


class LcuClient:
    PORT_RE = re.compile(r"--app-port=([0-9]+)")
    TOKEN_RE = re.compile(r"--remoting-auth-token=([\w_-]+)")
    PID_RE = re.compile(r"--app-pid=([0-9]+)")
    REGION_RE = re.compile(r"--region=([\w_-]+)")
    BASIC_URL_RE = re.compile(r"https://riot:([^@\s\"']+)@127\.0\.0\.1:([0-9]+)", re.IGNORECASE)

    def __init__(self, timeout_seconds: float = 1.6, config_path: Path | str | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self._auth: LcuAuth | None = None
        self._ssl_context = ssl._create_unverified_context()
        self.config_path = Path(config_path) if config_path is not None else user_data_path("lcu_config.json")

    @property
    def auth(self) -> LcuAuth | None:
        return self._auth

    def get_current_selection(self) -> LcuSelection | None:
        auth = self._ensure_auth()

        try:
            session = self._get_json(auth, "/lol-champ-select/v1/session")
        except LcuNotInChampSelectError:
            return None
        except LcuUnavailableError:
            self._auth = None
            raise

        selection = self._selection_from_session(session)
        if selection is not None:
            return selection

        try:
            champion_id = int(self._get_json(auth, "/lol-champ-select/v1/current-champion") or 0)
        except LcuNotInChampSelectError:
            champion_id = 0

        if champion_id > 0:
            return LcuSelection(champion_id=champion_id, is_locked=True, source="current-champion")

        selection = self._selection_from_gameflow_session(auth)
        if selection is not None:
            return selection

        return self._selection_from_live_client()

    def get_gameflow_phase(self) -> str | None:
        auth = self._ensure_auth()
        try:
            value = self._get_json(auth, "/lol-gameflow/v1/gameflow-phase")
        except LcuNotInChampSelectError:
            return None
        return str(value) if value is not None else None

    def _ensure_auth(self) -> LcuAuth:
        if self._auth is not None:
            return self._auth

        auths = self._discover_auths()
        if not auths:
            if self._league_process_running():
                raise LcuUnavailableError("已发现客户端，但没有找到 LCU token；请等待几秒或重启客户端")
            raise LcuUnavailableError("未发现 LeagueClientUx.exe")

        for auth in auths:
            try:
                self._get_json(auth, "/riotclient/auth-token")
            except LcuClientError:
                continue
            self._auth = auth
            return auth

        raise LcuUnavailableError("发现 LCU token，但本地接口验证失败；可能是客户端刚重启")

    def _get_json(self, auth: LcuAuth, path: str) -> Any:
        url = f"https://127.0.0.1:{auth.port}{path}"
        token = base64.b64encode(f"riot:{auth.auth_token}".encode("utf-8")).decode("ascii")
        request = Request(url, headers={"Authorization": f"Basic {token}"})

        try:
            with urlopen(request, context=self._ssl_context, timeout=self.timeout_seconds) as response:
                payload = response.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise LcuNotInChampSelectError(path) from exc
            raise LcuUnavailableError(f"LCU HTTP {exc.code}: {path}") from exc
        except (OSError, URLError) as exc:
            raise LcuUnavailableError(str(exc)) from exc

        if not payload:
            return None
        return json.loads(payload.decode("utf-8"))

    def _get_live_json(self, path: str) -> Any:
        url = f"https://127.0.0.1:2999{path}"
        request = Request(url)

        try:
            with urlopen(request, context=self._ssl_context, timeout=0.9) as response:
                payload = response.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise LcuNotInChampSelectError(path) from exc
            raise LcuUnavailableError(f"Live Client HTTP {exc.code}: {path}") from exc
        except (OSError, URLError) as exc:
            raise LcuUnavailableError(str(exc)) from exc

        if not payload:
            return None
        return json.loads(payload.decode("utf-8"))

    def _discover_auths(self) -> list[LcuAuth]:
        auths: list[LcuAuth] = []

        auths.extend(self._discover_auths_from_config())
        auths.extend(self._discover_auths_from_logs())
        auths.extend(self._discover_auths_from_lockfiles())

        command_lines = self._query_command_lines_with_powershell()
        if not command_lines:
            command_lines = self._query_command_lines_with_wmic()
        auths.extend(
            auth for line in command_lines if (auth := self._parse_command_line(line, source="process")) is not None
        )

        return self._dedupe_auths(auths)

    def _discover_auths_from_config(self) -> list[LcuAuth]:
        config_path = self.config_path
        if not config_path.exists():
            return []

        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        auths: list[LcuAuth] = []
        manual_port = payload.get("port")
        manual_token = payload.get("auth_token") or payload.get("token") or payload.get("remoting_auth_token")
        if manual_port and manual_token:
            auths.append(LcuAuth(port=int(manual_port), auth_token=str(manual_token), source="config"))

        for raw_path in payload.get("lockfiles", ()) or ():
            auth = self._parse_lockfile(Path(str(raw_path)))
            if auth is not None:
                auths.append(auth)

        for raw_path in payload.get("log_files", ()) or ():
            auths.extend(self._extract_auths_from_file(Path(str(raw_path)), source="config-log"))

        return auths

    def _discover_auths_from_logs(self) -> list[LcuAuth]:
        auths: list[LcuAuth] = []
        for directory in self._possible_league_client_dirs():
            try:
                files = sorted(
                    directory.glob("*_LeagueClientUx.log"),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
            except OSError:
                continue

            for log_file in files[:8]:
                auths.extend(self._extract_auths_from_file(log_file, source=f"log:{log_file.name}"))

        return auths

    def _discover_auths_from_lockfiles(self) -> list[LcuAuth]:
        auths: list[LcuAuth] = []
        for path in self._possible_lockfiles():
            auth = self._parse_lockfile(path)
            if auth is not None:
                auths.append(auth)
        return auths

    def _extract_auths_from_file(self, path: Path, source: str) -> list[LcuAuth]:
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as file:
                text = file.read(128_000)
        except OSError:
            return []
        return self._extract_auths_from_text(text, source)

    def _extract_auths_from_text(self, text: str, source: str) -> list[LcuAuth]:
        auths: list[LcuAuth] = []

        command_auth = self._parse_command_line(text, source=source)
        if command_auth is not None:
            auths.append(command_auth)

        for token, port in self.BASIC_URL_RE.findall(text):
            auths.append(LcuAuth(port=int(port), auth_token=token, source=source))

        return auths

    def _possible_league_client_dirs(self) -> list[Path]:
        directories: list[Path] = []

        config_path = self.config_path
        if config_path.exists():
            try:
                payload = json.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            for raw_path in payload.get("league_client_dirs", ()) or ():
                directories.append(Path(str(raw_path)))

        for root in self._possible_install_roots():
            try:
                children = list(root.iterdir())
            except OSError:
                continue

            league_client = root / "LeagueClient"
            if league_client.exists():
                directories.append(league_client)

            for child in children:
                candidate = child / "LeagueClient"
                if candidate.exists():
                    directories.append(candidate)

        return self._dedupe_paths(directories)

    def _possible_lockfiles(self) -> list[Path]:
        paths: list[Path] = []
        for directory in self._possible_league_client_dirs():
            paths.append(directory / "lockfile")
            paths.append(directory.parent / "lockfile")
            paths.append(directory.parent / "Riot Client Data" / "User Data" / "Config" / "lockfile")

        for root in self._possible_install_roots():
            try:
                paths.extend(path for path in root.rglob("lockfile") if path.is_file())
            except OSError:
                continue

        return self._dedupe_paths(paths)

    def _possible_install_roots(self) -> list[Path]:
        candidates = [
            Path("C:/Game/WeGame/WeGameApps"),
            Path("D:/Game/WeGame/WeGameApps"),
            Path("C:/WeGameApps"),
            Path("D:/WeGameApps"),
            Path("C:/Riot Games"),
            Path("D:/Riot Games"),
            Path("C:/ProgramData/Riot Games"),
        ]
        return [path for path in candidates if path.exists()]

    def _parse_lockfile(self, path: Path) -> LcuAuth | None:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            return None

        parts = text.split(":")
        if len(parts) != 5 or not parts[2].isdigit() or not parts[3]:
            return None

        return LcuAuth(
            port=int(parts[2]),
            auth_token=parts[3],
            pid=int(parts[1]) if parts[1].isdigit() else None,
            source=f"lockfile:{path.name}",
        )

    def _query_command_lines_with_powershell(self) -> list[str]:
        script = (
            "Get-CimInstance Win32_Process -Filter \"Name = 'LeagueClientUx.exe'\" "
            "| ForEach-Object { $_.CommandLine }"
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            return []

        if completed.returncode != 0:
            return []
        return [line.strip() for line in completed.stdout.splitlines() if line.strip()]

    def _query_command_lines_with_wmic(self) -> list[str]:
        try:
            completed = subprocess.run(
                ["wmic", "process", "where", "name='LeagueClientUx.exe'", "get", "CommandLine"],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            return []

        if completed.returncode != 0:
            return []
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        return [line for line in lines if line.upper() != "COMMANDLINE"]

    def _parse_command_line(self, line: str, source: str = "process") -> LcuAuth | None:
        port_match = self.PORT_RE.search(line)
        token_match = self.TOKEN_RE.search(line)
        if port_match is None or token_match is None:
            return None

        pid_match = self.PID_RE.search(line)
        region_match = self.REGION_RE.search(line)
        return LcuAuth(
            port=int(port_match.group(1)),
            auth_token=token_match.group(1),
            pid=int(pid_match.group(1)) if pid_match else None,
            region=region_match.group(1) if region_match else "",
            source=source,
        )

    def _league_process_running(self) -> bool:
        script = (
            "Get-Process -Name LeagueClient,LeagueClientUx,LeagueClientUxRender "
            "-ErrorAction SilentlyContinue | Select-Object -First 1 | ForEach-Object { $_.Id }"
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=2,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return bool(completed.stdout.strip())

    @staticmethod
    def _dedupe_auths(auths: list[LcuAuth]) -> list[LcuAuth]:
        unique: list[LcuAuth] = []
        seen: set[tuple[int, str]] = set()
        for auth in auths:
            key = (auth.port, auth.auth_token)
            if key in seen:
                continue
            seen.add(key)
            unique.append(auth)
        return unique

    @staticmethod
    def _dedupe_paths(paths: list[Path]) -> list[Path]:
        unique: list[Path] = []
        seen: set[str] = set()
        for path in paths:
            normalized = str(path).casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append(path)
        return unique

    @staticmethod
    def _selection_from_session(session: dict[str, Any]) -> LcuSelection | None:
        local_cell_id = session.get("localPlayerCellId")
        my_team = session.get("myTeam") or []

        self_player = next((p for p in my_team if p.get("cellId") == local_cell_id), None)
        if not self_player:
            return None

        champion_id = int(self_player.get("championId") or 0)
        intent_id = int(self_player.get("championPickIntent") or 0)

        if champion_id > 0:
            return LcuSelection(champion_id=champion_id, is_locked=True, source="session.championId")
        if intent_id > 0:
            return LcuSelection(champion_id=intent_id, is_locked=False, source="session.championPickIntent")

        for action_group in session.get("actions") or []:
            for action in action_group or []:
                if action.get("actorCellId") != local_cell_id or action.get("type") != "pick":
                    continue
                action_champion_id = int(action.get("championId") or 0)
                if action_champion_id > 0:
                    return LcuSelection(
                        champion_id=action_champion_id,
                        is_locked=bool(action.get("completed")),
                        source="session.actions.pick",
                    )
        return None

    def _selection_from_gameflow_session(self, auth: LcuAuth) -> LcuSelection | None:
        try:
            gameflow = self._get_json(auth, "/lol-gameflow/v1/session")
            summoner = self._get_json(auth, "/lol-summoner/v1/current-summoner")
        except LcuClientError:
            return None

        selections = ((gameflow or {}).get("gameData") or {}).get("playerChampionSelections") or []
        if not selections:
            return None

        summoner_id = int((summoner or {}).get("summonerId") or 0)
        if summoner_id:
            for selection in selections:
                if int(selection.get("summonerId") or 0) != summoner_id:
                    continue
                champion_id = int(selection.get("championId") or 0)
                if champion_id > 0:
                    return LcuSelection(champion_id=champion_id, is_locked=True, source="gameflow.session")

        non_empty = [selection for selection in selections if int(selection.get("championId") or 0) > 0]
        if len(non_empty) == 1:
            return LcuSelection(
                champion_id=int(non_empty[0].get("championId") or 0),
                is_locked=True,
                source="gameflow.session.single",
            )
        return None

    def _selection_from_live_client(self) -> LcuSelection | None:
        try:
            active_name = str(self._get_live_json("/liveclientdata/activeplayername") or "")
            players = self._get_live_json("/liveclientdata/playerlist") or []
        except LcuClientError:
            return None

        for player in players:
            if str(player.get("summonerName") or "") != active_name and str(player.get("riotId") or "") != active_name:
                continue
            champion_name = str(player.get("championName") or "")
            if champion_name:
                return LcuSelection(
                    champion_id=0,
                    is_locked=True,
                    source="live-client.playerlist",
                    champion_name=champion_name,
                )
        return None
