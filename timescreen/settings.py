"""Categorie create dall'utente e assegnazione di app e siti.

Si salva tutto in %LOCALAPPDATA%\\TimeScreen\\settings.json. Nessuna app ha
una categoria finché non la sceglie l'utente.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# la palette categorica ha 8 colori distinguibili: oltre non si va
MAX_CATEGORIES = 8
MAX_NAME_LEN = 40
DEFAULT_CATEGORIES = ["Lavoro", "Video", "Social", "Giochi", "Comunicazione"]


def default_path() -> Path:
    override = os.environ.get("TIMESCREEN_SETTINGS")  # utile per prove e sviluppo
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "TimeScreen" / "settings.json"


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or default_path()
        self.categories: list[dict] = []  # {"id", "name", "slot"}
        self.assignments: dict[str, str] = {}  # nome app -> id categoria
        self._next_id = 1
        self._load()

    # ---------- persistenza ----------

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if not data:
            for name in DEFAULT_CATEGORIES:
                self._append(name)
            return
        self.categories = data.get("categories", [])
        self.assignments = data.get("assignments", {})
        self._next_id = data.get("next_id", len(self.categories) + 1)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {"categories": self.categories, "assignments": self.assignments, "next_id": self._next_id},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def to_dict(self) -> dict:
        return {
            "categories": self.categories,
            "assignments": self.assignments,
            "max_categories": MAX_CATEGORIES,
        }

    # ---------- modifiche ----------

    def _clean_name(self, name: str, ignore_id: str | None = None) -> str:
        name = " ".join(str(name).split())
        if not name:
            raise ValueError("Il nome non può essere vuoto.")
        if len(name) > MAX_NAME_LEN:
            raise ValueError(f"Il nome può avere al massimo {MAX_NAME_LEN} caratteri.")
        for c in self.categories:
            if c["id"] != ignore_id and c["name"].casefold() == name.casefold():
                raise ValueError(f"Esiste già una categoria «{c['name']}».")
        return name

    def _append(self, name: str) -> dict:
        used = {c["slot"] for c in self.categories}
        slot = next(s for s in range(1, MAX_CATEGORIES + 1) if s not in used)
        cat = {"id": f"c{self._next_id}", "name": name, "slot": slot}
        self._next_id += 1
        self.categories.append(cat)
        return cat

    def _find(self, cat_id: str) -> dict:
        for c in self.categories:
            if c["id"] == cat_id:
                return c
        raise ValueError("Categoria non trovata.")

    def add_category(self, name: str) -> dict:
        if len(self.categories) >= MAX_CATEGORIES:
            raise ValueError(f"Puoi avere al massimo {MAX_CATEGORIES} categorie.")
        cat = self._append(self._clean_name(name))
        self.save()
        return cat

    def rename_category(self, cat_id: str, name: str) -> None:
        cat = self._find(cat_id)
        cat["name"] = self._clean_name(name, ignore_id=cat_id)
        self.save()

    def delete_category(self, cat_id: str) -> None:
        cat = self._find(cat_id)
        self.categories.remove(cat)
        # le app di questa categoria tornano «da classificare»
        self.assignments = {a: c for a, c in self.assignments.items() if c != cat_id}
        self.save()

    def assign(self, app: str, cat_id: str | None) -> None:
        if cat_id:
            self._find(cat_id)
            self.assignments[app] = cat_id
        else:
            self.assignments.pop(app, None)
        self.save()
