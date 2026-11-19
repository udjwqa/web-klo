from pathlib import Path

from settings import BASE_DIR

LISTS_DIR = BASE_DIR / "lists"

DEFINITIONS = {
    "user_agents_block": "Подстроки User-Agent ботов и краулеров",
    "asn_block": "Номера ASN датацентров и облаков",
    "isp_block": "Провайдеры хостинга, мягкий штраф",
    "cities_block": "Города, которые дают мягкий штраф",
    "gpu_block": "Видеокарты эмуляторов и headless",
    "vpn_asn": "Сети коммерческих VPN: Nord, M247, Surfshark, Proton",
}


class Lists:
    def __init__(self) -> None:
        self._data: dict[str, list[str]] = {}

    def load(self) -> None:
        LISTS_DIR.mkdir(parents=True, exist_ok=True)
        for name in DEFINITIONS:
            path = LISTS_DIR / f"{name}.txt"
            if not path.exists():
                path.write_text("", encoding="utf-8")
            self._data[name] = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]

    def get(self, name: str) -> list[str]:
        return self._data.get(name, [])

    def set(self, name: str, items: list[str]) -> None:
        self._data[name] = items
        path = LISTS_DIR / f"{name}.txt"
        path.write_text("\n".join(items) + ("\n" if items else ""), encoding="utf-8")

    def all(self) -> dict:
        return {
            name: {"description": desc, "items": self.get(name)}
            for name, desc in DEFINITIONS.items()
        }


lists = Lists()
