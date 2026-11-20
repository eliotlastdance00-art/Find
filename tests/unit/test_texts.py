"""Translations must stay complete: every language has exactly the same keys."""

from __future__ import annotations

import re
from pathlib import Path

import dfd
from dfd.domain import errors
from dfd.infrastructure.report.texts import DEFAULT_LANGUAGE, LANGUAGES, TEXTS, text

I18N = Path(dfd.__file__).parent / "presentation" / "static" / "js" / "i18n.js"
STATIC = I18N.parent


def _ui_dictionaries() -> dict[str, dict[str, str]]:
    source = I18N.read_text(encoding="utf-8")
    blocks = re.split(r"^  (tk|ru|en): \{$", source, flags=re.M)[1:]
    return {
        code: dict(re.findall(r'^\s+"([\w.]+)":\s*"((?:[^"\\]|\\.)*)",?$', body, flags=re.M))
        for code, body in zip(blocks[::2], blocks[1::2], strict=True)
    }


def test_report_texts_cover_all_languages() -> None:
    assert LANGUAGES == ("tk", "ru", "en") and DEFAULT_LANGUAGE == "tk"
    for key, entry in TEXTS.items():
        assert set(entry) == set(LANGUAGES), key
        assert all(value.strip() for value in entry.values()), key
    assert text("fake", "ru") == "ПОДДЕЛКА"
    assert text("fake", "xx") == "GALP"  # unknown language falls back to Turkmen


def test_ui_dictionaries_have_identical_keys_and_placeholders() -> None:
    dictionaries = _ui_dictionaries()
    assert set(dictionaries) == {"tk", "ru", "en"}
    reference = dictionaries["en"]
    assert len(reference) > 150
    for code, entries in dictionaries.items():
        assert set(entries) == set(reference), code
        for key, value in entries.items():
            assert value.strip(), (code, key)
            assert set(re.findall(r"\{(\w+)\}", value)) == set(
                re.findall(r"\{(\w+)\}", reference[key])
            ), (code, key)


def test_every_error_code_is_translated() -> None:
    codes = {
        cls.code
        for cls in vars(errors).values()
        if isinstance(cls, type) and issubclass(cls, errors.DomainError)
    }
    entries = _ui_dictionaries()["tk"]
    assert not {code for code in codes if f"err.{code}" not in entries}


def test_ui_only_uses_defined_keys() -> None:
    entries = _ui_dictionaries()["en"]
    used: set[str] = set()
    for name in ("app.js", "views.js", "ui.js"):
        used |= set(re.findall(r'\bt\(\s*"([\w.]+)"', (STATIC / name).read_text(encoding="utf-8")))
    assert used and not {key for key in used if key not in entries}


def test_turkmen_verdict_words_match_the_assignment() -> None:
    entries = _ui_dictionaries()["tk"]
    assert [entries[f"verdict.{v}"] for v in ("real", "fake", "suspicious")] == [
        "Hakyky",
        "Galp",
        "Şübheli",
    ]
