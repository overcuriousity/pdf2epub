"""Tests for the non-interactive EPUB metadata handling."""

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import metadata as metadata_lib


class TestSubstitute:
    def test_replaces_both_placeholders(self):
        result = metadata_lib.substitute("{stem} / {filename}", "books/dune.pdf")
        assert result == "dune / dune.pdf"

    def test_keeps_braces_without_filename(self):
        assert metadata_lib.substitute("{stem}", None) == "{stem}"

    def test_leaves_other_braces_alone(self):
        # A title may legitimately contain braces; format() would choke here.
        assert metadata_lib.substitute("The {Weird} Book", "a.pdf") == "The {Weird} Book"


class TestSplitAuthors:
    @pytest.mark.parametrize("value,expected", [
        ("Jane Doe", ["Jane Doe"]),
        ("Jane Doe; John Roe", ["Jane Doe", "John Roe"]),
        ("A;B;C", ["A", "B", "C"]),
    ])
    def test_splits(self, value, expected):
        assert metadata_lib.split_authors(value) == expected

    @pytest.mark.parametrize("value", [
        "Procter and Gamble",   # company name, one creator
        "Simon and Schuster",   # publisher, one creator
        "Jane Doe | John Roe",  # "|" is not a documented separator
    ])
    def test_only_semicolon_splits(self, value):
        # Only ";" is documented, and it cannot appear in an ordinary name.
        # Splitting on " and " or "|" silently mangled real names.
        assert metadata_lib.split_authors(value) == [value]

    def test_keeps_commas_within_one_name(self):
        # A comma is part of "Doe, Jane", not a separator between people.
        assert metadata_lib.split_authors("Doe, Jane") == ["Doe, Jane"]

    def test_drops_empty_segments(self):
        assert metadata_lib.split_authors("A;;B;") == ["A", "B"]


class TestNormaliseDate:
    @pytest.mark.parametrize("value", ["2024-01-05", "2024/01/05", "05.01.2024", "2024"])
    def test_accepted_formats(self, value):
        assert metadata_lib.normalise_date(value).count("-") in (0, 2)

    def test_normalises_to_iso(self):
        assert metadata_lib.normalise_date("05.01.2024") == "2024-01-05"

    def test_rejects_garbage(self):
        with pytest.raises(metadata_lib.MetadataError):
            metadata_lib.normalise_date("not-a-date")

    def test_rejects_impossible_date(self):
        with pytest.raises(metadata_lib.MetadataError):
            metadata_lib.normalise_date("2024-13-45")


class TestBuildMetadata:
    def test_maps_flags_to_dublin_core_keys(self):
        result = metadata_lib.build_metadata({
            "title": "Dune",
            "author": "Frank Herbert",
            "publisher": "Ace",
        })
        assert result == {
            "dc:title": "Dune",
            "dc:creator": ["Frank Herbert"],
            "dc:publisher": "Ace",
        }

    def test_omits_flags_that_were_not_given(self):
        # Distinguishes "not supplied" from "supplied but empty".
        assert metadata_lib.build_metadata({}) == {}
        assert metadata_lib.build_metadata({"title": "  "}) == {}

    def test_substitutes_placeholders_per_file(self):
        result = metadata_lib.build_metadata(
            {"title": "{stem}"}, filename="/books/dune.pdf"
        )
        assert result["dc:title"] == "dune"

    def test_ignores_unknown_flags(self):
        assert metadata_lib.build_metadata({"nonsense": "x"}) == {}


class TestResolveMetadata:
    def test_fills_every_default(self):
        result = metadata_lib.resolve_metadata({}, fallback_title="book")
        assert set(result) == {key for _, key in metadata_lib.METADATA_FIELDS}
        assert result["dc:title"] == "book"
        assert result["dc:language"] == "en"

    def test_falls_back_to_file_stem_before_generic_default(self):
        result = metadata_lib.resolve_metadata({}, fallback_title="dune")
        assert result["dc:title"] == "dune"

    def test_overrides_win(self):
        overrides = metadata_lib.build_metadata({"title": "Dune", "author": "Frank Herbert"})
        result = metadata_lib.resolve_metadata(overrides, fallback_title="ignored")
        assert result["dc:title"] == "Dune"
        assert result["dc:creator"] == ["Frank Herbert"]

    def test_existing_metadata_preserved_when_not_overridden(self):
        existing = {"dc:title": "Old Title", "dc:publisher": "Old Press"}
        result = metadata_lib.resolve_metadata({}, existing=existing)
        assert result["dc:title"] == "Old Title"
        assert result["dc:publisher"] == "Old Press"

    def test_override_beats_existing(self):
        existing = {"dc:title": "Old Title"}
        overrides = metadata_lib.build_metadata({"title": "New Title"})
        assert metadata_lib.resolve_metadata(overrides, existing=existing)["dc:title"] == "New Title"

    def test_identifier_unique_per_document(self):
        # The old timestamp default collided across a batch; a title+name seed
        # must not, otherwise several EPUBs share a dc:identifier.
        first = metadata_lib.resolve_metadata({}, fallback_title="a", filename="a.pdf")
        second = metadata_lib.resolve_metadata({}, fallback_title="b", filename="b.pdf")
        assert first["dc:identifier"] != second["dc:identifier"]

    def test_identifier_unique_per_document_with_shared_title(self):
        # A batch run passing one constant --title must still yield one
        # identifier per file; only the file name distinguishes them.
        ids = set()
        for stem in ("dune", "ubik", "snowcrash"):
            overrides = metadata_lib.build_metadata({"title": "Report"}, filename=f"{stem}.pdf")
            resolved = metadata_lib.resolve_metadata(
                overrides, fallback_title=stem, filename=f"/work/{stem}"
            )
            assert resolved["dc:title"] == "Report"
            ids.add(resolved["dc:identifier"])
        assert len(ids) == 3

    def test_identifier_uses_override_title(self):
        # The identifier is seeded from the title that is actually written to
        # the EPUB, not from the file-name fallback.
        overrides = metadata_lib.build_metadata({"title": "Dune"}, filename="scan1.pdf")
        resolved = metadata_lib.resolve_metadata(overrides, fallback_title="scan1", filename="scan1.pdf")
        expected = metadata_lib.default_identifier("Dune", "scan1.pdf")
        assert resolved["dc:identifier"] == expected

    def test_prompt_defaults_leaves_identifier_unset(self):
        # resolve_metadata derives it; deriving it here would ignore --title.
        defaults = metadata_lib.prompt_defaults({}, fallback_title="scan1")
        assert defaults["dc:identifier"] == ""

    def test_existing_identifier_is_preserved(self):
        existing = {"dc:identifier": "urn:isbn:old"}
        resolved = metadata_lib.resolve_metadata({}, existing=existing, fallback_title="scan1")
        assert resolved["dc:identifier"] == "urn:isbn:old"

    def test_explicit_identifier_wins(self):
        overrides = metadata_lib.build_metadata({"identifier": "urn:isbn:12345"}, filename="a.pdf")
        resolved = metadata_lib.resolve_metadata(overrides, fallback_title="a", filename="a.pdf")
        assert resolved["dc:identifier"] == "urn:isbn:12345"

    def test_identifier_stable_across_runs(self):
        first = metadata_lib.resolve_metadata({}, fallback_title="a", filename="a.pdf")
        second = metadata_lib.resolve_metadata({}, fallback_title="a", filename="a.pdf")
        assert first["dc:identifier"] == second["dc:identifier"]

    def test_identifier_is_valid_uuid_urn(self):
        result = metadata_lib.resolve_metadata({}, fallback_title="a", filename="a.pdf")
        assert result["dc:identifier"].startswith("urn:uuid:")

    def test_existing_list_author_is_flattened(self):
        # description.json may hold a list from an earlier run; prompts and the
        # cover page need a plain string.
        existing = {"dc:creator": ["Frank Herbert", "Brian Herbert"]}
        result = metadata_lib.resolve_metadata({}, existing=existing)
        assert isinstance(result["dc:creator"], str)
        assert result["dc:creator"] == "Frank Herbert, Brian Herbert"

    def test_date_defaults_to_today(self):
        result = metadata_lib.resolve_metadata({}, fallback_title="book")
        assert result["dc:date"] == datetime.now().strftime("%Y-%m-%d")
