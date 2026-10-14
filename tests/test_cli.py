"""Tests for the CLI layer in main.py.

`main.py` imports torch at module level, which is far too heavy to install just
to test argument handling, so a stub stands in when the real thing is absent.
"""

import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Stub torch before importing main; the real package pulls in CUDA wheels.
try:  # pragma: no cover - depends on the environment
    import torch  # noqa: F401
except ImportError:  # pragma: no cover
    stub = types.ModuleType("torch")
    stub.cuda = types.SimpleNamespace(is_available=lambda: False)
    stub.backends = types.SimpleNamespace(
        mps=types.SimpleNamespace(is_available=lambda: False)
    )
    sys.modules["torch"] = stub

import main as cli
from modules import metadata as metadata_lib


def build_parser():
    import argparse

    parser = argparse.ArgumentParser()
    cli.add_metadata_arguments(parser)
    return parser


class TestMetadataArguments:
    def test_all_documented_flags_are_accepted(self):
        args = build_parser().parse_args([
            "--title", "Dune",
            "--author", "Frank Herbert",
            "--publisher", "Ace",
            "--language", "en",
            "--rights", "Public domain",
            "--identifier", "urn:uuid:1234",
            "--date", "1965-08-01",
        ])
        assert args.title == "Dune"
        assert args.author == "Frank Herbert"
        assert args.publisher == "Ace"
        assert args.language == "en"
        assert args.rights == "Public domain"
        assert args.identifier == "urn:uuid:1234"
        assert args.date == "1965-08-01"

    def test_defaults_are_unset(self):
        # None means "not supplied", which is distinct from an empty string.
        args = build_parser().parse_args([])
        assert args.title is None
        assert args.author is None
        assert args.date is None

    def test_collect_returns_empty_when_none_given(self):
        args = build_parser().parse_args([])
        assert cli.collect_metadata_args(args) == {}

    def test_collect_returns_only_supplied_flags(self):
        args = build_parser().parse_args(["--title", "Dune", "--author", "Frank Herbert"])
        assert cli.collect_metadata_args(args) == {
            "title": "Dune",
            "author": "Frank Herbert",
        }

    def test_collect_keeps_empty_string_as_supplied(self):
        # An explicitly empty value still counts as supplied so that
        # resolve_metadata applies it rather than a stale previous value.
        args = build_parser().parse_args(["--title", ""])
        assert cli.collect_metadata_args(args) == {"title": ""}

    def test_placeholders_pass_through_to_validation(self):
        args = build_parser().parse_args(["--title", "{stem}"])
        result = cli.metadata_from_args(args, Path("/books/dune.pdf"))
        assert result["dc:title"] == "dune"

    def test_bad_date_raises_metadata_error(self):
        args = build_parser().parse_args(["--date", "not-a-date"])
        with pytest.raises(metadata_lib.MetadataError):
            cli.metadata_from_args(args, Path("book.pdf"))


class TestStdinDetection:
    def test_returns_false_for_non_tty(self, monkeypatch):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
        assert cli.stdin_is_interactive() is False

    def test_returns_true_for_tty(self, monkeypatch):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
        assert cli.stdin_is_interactive() is True

    def test_handles_stdin_without_isatty(self, monkeypatch):
        # sys.stdin can be None under some schedulers (pythonw, cron).
        monkeypatch.setattr(cli.sys, "stdin", None)
        assert cli.stdin_is_interactive() is False

    def test_survives_closed_stdin(self, monkeypatch):
        class Closed:
            def isatty(self):
                raise ValueError("I/O operation on closed file")

        monkeypatch.setattr(cli.sys, "stdin", Closed())
        assert cli.stdin_is_interactive() is False
