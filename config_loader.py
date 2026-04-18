from __future__ import annotations
import yaml
from pathlib import Path

_BASE = Path(__file__).parent / 'config'


def load_style() -> dict:
    with open(_BASE / 'style.yaml') as f:
        return yaml.safe_load(f)['theme']


def load_gauges() -> dict:
    with open(_BASE / 'gauges.yaml') as f:
        return yaml.safe_load(f)
