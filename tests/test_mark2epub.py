"""Tests for the interactive metadata prompt in mark2epub.

These cover the defaults shown at the prompt, which are what a user accepts by
pressing Enter.
"""

import builtins
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from modules import mark2epub, metadata as metadata_lib


def answer(monkeypatch, *responses):
    """Feed *responses* to the metadata prompts, then answer the review prompt."""
    answers = list(responses)

    def fake_input(prompt=""):
        return answers.pop(0) if answers else ""

    monkeypatch.setattr(builtins, "input", fake_input)


# title, author, identifier, language, rights, publisher, date, review
DEFAULTS_ONLY = ("My Title", "Jane Doe", "", "", "", "", "", "n")


class TestInteractiveIdentifier:
    def test_derived_from_entered_title_and_file(
        self, monkeypatch, capsys
    ):
        answer(monkeypatch, *DEFAULTS_ONLY)
        result = mark2epub.get_metadata_from_user(
            {}, fallback_title="book", filename="/work/book"
        )
        assert result["metadata"]["dc:identifier"] == metadata_lib.default_identifier(
            "My Title", "/work/book"
        )

    def test_same_title_different_files_give_different_identifiers(
        self, monkeypatch, capsys
    ):
        # The interactive prompt must key on the file as well as the title, or
        # two books sharing a title collide on dc:identifier.
        seen = set()
        for directory in ("bookA", "bookB"):
            answer(monkeypatch, *DEFAULTS_ONLY)
            result = mark2epub.get_metadata_from_user(
                {}, fallback_title=directory, filename=f"/work/{directory}"
            )
            seen.add(result["metadata"]["dc:identifier"])

        assert len(seen) == 2

    def test_matches_unattended_path_for_same_inputs(self, monkeypatch):
        # Both paths must agree, or switching modes would change the id.
        answer(monkeypatch, *DEFAULTS_ONLY)
        interactive = mark2epub.get_metadata_from_user(
            {}, fallback_title="scan", filename="/work/scan"
        )["metadata"]

        overrides = metadata_lib.build_metadata(
            {"title": "My Title", "author": "Jane Doe"}, filename="scan"
        )
        unattended = metadata_lib.resolve_metadata(
            overrides, fallback_title="scan", filename="/work/scan"
        )

        assert interactive["dc:identifier"] == unattended["dc:identifier"]
        assert interactive["dc:title"] == unattended["dc:title"]

    def test_existing_identifier_is_offered_and_kept(self, monkeypatch):
        existing = {"metadata": {"dc:identifier": "urn:isbn:old", "dc:title": "Kept Title"}}
        answer(monkeypatch, "", "", "", "", "", "", "", "n")
        result = mark2epub.get_metadata_from_user(existing, filename="/work/book")
        assert result["metadata"]["dc:identifier"] == "urn:isbn:old"

    def test_user_supplied_identifier_wins(self, monkeypatch):
        answer(monkeypatch, "T", "A", "urn:isbn:mine", "", "", "", "", "n")
        result = mark2epub.get_metadata_from_user({}, filename="/work/book")
        assert result["metadata"]["dc:identifier"] == "urn:isbn:mine"


class TestInteractiveDefaults:
    def test_falls_back_to_file_name_for_title(self, monkeypatch):
        answer(monkeypatch, "", "", "", "", "", "", "", "n")
        result = mark2epub.get_metadata_from_user({}, fallback_title="dune")
        assert result["metadata"]["dc:title"] == "dune"

    def test_existing_title_is_offered_as_default(self, monkeypatch):
        existing = {"metadata": {"dc:title": "Old Title"}}
        answer(monkeypatch, "", "", "", "", "", "", "", "n")
        result = mark2epub.get_metadata_from_user(existing, fallback_title="new")
        assert result["metadata"]["dc:title"] == "Old Title"

    def test_list_author_from_previous_run_is_flattened(self, monkeypatch):
        # description.json may hold several authors from an unattended run.
        existing = {"metadata": {"dc:creator": ["Frank Herbert", "Brian Herbert"]}}
        answer(monkeypatch, "", "", "", "", "", "", "", "n")
        result = mark2epub.get_metadata_from_user(existing)
        assert result["metadata"]["dc:creator"] == "Frank Herbert, Brian Herbert"

    def test_bad_date_falls_back_to_default(self, monkeypatch, capsys):
        answer(monkeypatch, "T", "A", "", "", "", "", "not-a-date", "n")
        result = mark2epub.get_metadata_from_user({}, filename="/work/book")
        # The unusable value is discarded rather than written into the EPUB.
        assert result["metadata"]["dc:date"] != "not-a-date"
        assert "not-a-date" in capsys.readouterr().out


class TestInteractiveFlags:
    def test_signature_accepts_filename_keyword(self):
        # Guard against the parameter being dropped again; it is what keeps
        # same-titled documents from colliding.
        import inspect

        params = inspect.signature(mark2epub.get_metadata_from_user).parameters
        assert "filename" in params
