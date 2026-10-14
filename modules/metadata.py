"""
Non-interactive EPUB metadata handling.

The interactive prompts in :mod:`modules.mark2epub` are the main obstacle to
batch converting PDFs. This module holds the metadata defaults plus the logic
that lets the CLI supply those values directly:

* :func:`build_metadata` turns validated CLI values into a metadata mapping.
* :func:`resolve_metadata` fills a complete metadata mapping with no prompts.
* :func:`prompt_defaults` computes the defaults shown for each interactive
  prompt.

Values may be given per file: the placeholders ``{filename}`` (with extension)
and ``{stem}`` (without) are replaced with the name of the PDF currently being
processed, so one command line can serve a whole directory.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import NAMESPACE_URL, uuid5

# Defaults mirroring the ones the interactive prompts have always offered.
DEFAULT_TITLE = "Untitled Document"
DEFAULT_AUTHOR = "Unknown Author"
DEFAULT_LANGUAGE = "en"
DEFAULT_RIGHTS = "All rights reserved"
DEFAULT_PUBLISHER = "PDF2EPUB"

# CLI flag name -> EPUB metadata key, in the order the prompts ask for them.
METADATA_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("title", "dc:title"),
    ("author", "dc:creator"),
    ("identifier", "dc:identifier"),
    ("language", "dc:language"),
    ("rights", "dc:rights"),
    ("publisher", "dc:publisher"),
    ("date", "dc:date"),
)

# Accepted date inputs, normalised to the YYYY-MM-DD that EPUB expects.
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y")

# Separators that turn one --author argument into several dc:creator elements.
# Only ";" is used: it is the documented separator and is not part of any
# ordinary name. Splitting on " and " or "|" would mangle names such as
# "Procter and Gamble" or a surname containing a pipe.
AUTHOR_SEPARATORS = (";",)


class MetadataError(ValueError):
    """Raised when a metadata value cannot be used for an EPUB."""


def substitute(value: str, filename: Optional[str] = None) -> str:
    """Replace the ``{filename}``/``{stem}`` placeholders in a CLI value.

    Plain string replacement is used rather than :meth:`str.format` so that
    titles legitimately containing braces are left alone.
    """
    if not filename:
        return value

    path = Path(filename)
    return value.replace("{filename}", path.name).replace("{stem}", path.stem)


def split_authors(value: str) -> List[str]:
    """Split an author argument into individual names.

    Commas are kept because they are common inside names ("Doe, John"); the
    documented ";" separator is the only one that splits two people apart.
    """
    authors = [value]
    for separator in AUTHOR_SEPARATORS:
        authors = [part for author in authors for part in author.split(separator)]

    return [author.strip() for author in authors if author.strip()]


def normalise_date(value: str) -> str:
    """Normalise a publication date to ``YYYY-MM-DD``.

    Raises:
        MetadataError: if the value is not a recognised date.
    """
    candidate = value.strip()
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(candidate, date_format).strftime("%Y-%m-%d")
        except ValueError:
            continue

    raise MetadataError(
        f"Unrecognised date {value!r}. Use YYYY-MM-DD, or one of "
        f"{', '.join(DATE_FORMATS)}."
    )


def normalise_language(value: str) -> str:
    """Normalise a language tag to lower case, e.g. ``EN-us`` -> ``en-us``."""
    return value.strip().lower().replace("_", "-")


def build_metadata(cli_metadata: Dict[str, str], filename: Optional[str] = None) -> Dict:
    """Validate CLI metadata and return a mapping of EPUB metadata keys.

    Only the keys that were actually supplied are present in the result, so the
    caller can tell "not given" apart from "given but empty".

    Args:
        cli_metadata: Flag name (as in :data:`METADATA_FIELDS`) to raw value.
        filename: PDF being processed, used for placeholder substitution.

    Raises:
        MetadataError: on an unusable date.
    """
    metadata = {}

    for flag, key in METADATA_FIELDS:
        if flag not in cli_metadata:
            continue

        raw = cli_metadata[flag]
        if raw is None:
            continue

        value = substitute(raw.strip(), filename)
        if not value:
            continue

        if key == "dc:date":
            value = normalise_date(value)
        elif key == "dc:language":
            value = normalise_language(value)
        elif key == "dc:creator":
            metadata[key] = split_authors(value)
            continue

        metadata[key] = value

    return metadata


def default_identifier(title: str, filename: Optional[str] = None) -> str:
    """Build a stable, unique ``dc:identifier``.

    The interactive default embedded the current timestamp, which collides
    across a batch: every PDF converted within the same second got the same
    identifier. A UUID5 derived from the title and file name is unique per
    document and stable across re-runs.
    """
    name = Path(filename).name if filename else ""
    seed = f"pdf2epub:{title}:{name}"
    return f"urn:uuid:{uuid5(NAMESPACE_URL, seed)}"


def prompt_defaults(existing: Optional[Dict] = None, fallback_title: Optional[str] = None) -> Dict:
    """Return the default value for each prompt.

    Existing values from a previously written ``description.json`` win, so
    re-running a conversion still offers what was used last time.
    """
    existing = existing or {}

    defaults = {
        "dc:title": existing.get("dc:title") or fallback_title or DEFAULT_TITLE,
        "dc:creator": existing.get("dc:creator") or DEFAULT_AUTHOR,
        # Left empty when unknown: resolve_metadata derives it from the final
        # title and file name. Filling it in here would bake in the fallback
        # title and ignore an --title override.
        "dc:identifier": existing.get("dc:identifier") or "",
        "dc:language": existing.get("dc:language") or DEFAULT_LANGUAGE,
        "dc:rights": existing.get("dc:rights") or DEFAULT_RIGHTS,
        "dc:publisher": existing.get("dc:publisher") or DEFAULT_PUBLISHER,
        "dc:date": existing.get("dc:date") or datetime.now().strftime("%Y-%m-%d"),
    }

    # A value carried over from description.json may be a list (several
    # authors, written by an unattended run). Both callers need a string, so
    # flatten here rather than in each of them.
    return {
        key: ", ".join(value) if isinstance(value, list) else value
        for key, value in defaults.items()
    }


def resolve_metadata(
    overrides: Optional[Dict] = None,
    existing: Optional[Dict] = None,
    fallback_title: Optional[str] = None,
    filename: Optional[str] = None,
) -> Dict:
    """Build a complete metadata mapping without asking anything.

    Precedence is CLI value, then existing ``description.json`` value, then the
    default. ``fallback_title`` (the PDF's stem) is used as the title when
    neither of the first two supplies one, which keeps unnamed batch
    conversions from being labelled "Untitled Document".

    Args:
        overrides: Metadata mapping from :func:`build_metadata`.
        existing: Metadata mapping from a previous run.
        fallback_title: Title to use when nothing else provides one.
        filename: PDF being processed, used for the derived identifier.
    """
    defaults = prompt_defaults(existing, fallback_title)
    metadata = dict(defaults)

    if overrides:
        for key, value in overrides.items():
            if key == "dc:identifier" and not value:
                continue
            metadata[key] = value

    if not metadata.get("dc:identifier"):
        metadata["dc:identifier"] = default_identifier(
            metadata.get("dc:title") or fallback_title or DEFAULT_TITLE, filename
        )

    return metadata
