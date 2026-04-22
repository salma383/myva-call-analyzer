import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".call_analyzer"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "openai_api_key": "",
    "theme": "dark",
    "caller_name": "",
}


def load() -> dict:
    CONFIG_DIR.mkdir(exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            # fill missing keys with defaults
            for k, v in DEFAULTS.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return dict(DEFAULTS)


def save(config: dict) -> None:
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get(key: str):
    return load().get(key, DEFAULTS.get(key))


def set_value(key: str, value) -> None:
    config = load()
    config[key] = value
    save(config)
