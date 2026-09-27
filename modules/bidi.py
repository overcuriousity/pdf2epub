import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Optional, Tuple, Union


def strip_markdown(text: str) -> str:
    """
    Remove code blocks, inline code, images, links, LaTeX math formulas,
    and HTML tags so direction and language detection operates purely
    on natural language prose.
    """
    # Remove fenced code blocks
    text = re.sub(r"```[\s\S]*?```", " ", text)
    # Remove inline code
    text = re.sub(r"`[^`]+`", " ", text)
    # Remove display math $$...$$
    text = re.sub(r"\$\$[\s\S]*?\$\$", " ", text)
    # Remove inline math $...$
    text = re.sub(r"(?<!\$)\$(?!\$)[\s\S]*?(?<!\$)\$(?!\$)", " ", text)
    # Remove images ![alt](url)
    text = re.sub(r"!\[.*?\]\(.*?\)", " ", text)
    # Replace links [text](url) with just text
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Remove URLs
    text = re.sub(r"https?://\S+", " ", text)
    return text


def detect_direction(text: str) -> str:
    """
    Detect whether the majority of directional characters in the text are RTL or LTR.

    Returns:
        'rtl' if majority of directional characters are Right-to-Left.
        'ltr' if majority are Left-to-Right or if text has no directional characters.
    """
    cleaned = strip_markdown(text)
    rtl_count = 0
    ltr_count = 0

    for ch in cleaned:
        bidi = unicodedata.bidirectional(ch)
        if bidi in ("R", "AL"):
            rtl_count += 1
        elif bidi == "L":
            ltr_count += 1

    if rtl_count > ltr_count:
        return "rtl"
    return "ltr"


# Stop words for Latin-script language detection
_LATIN_STOP_WORDS = {
    "en": {
        "the", "and", "to", "of", "in", "is", "that", "for", "with", "as",
        "was", "on", "at", "by", "this", "from", "be", "are", "or", "an",
        "have", "which", "one", "you", "were", "her", "all", "she", "there",
        "would", "their", "we", "him", "been", "has", "when", "who", "will",
        "more", "no", "if", "out", "so", "said", "what", "its", "about",
        "into", "than", "them", "can", "only", "other", "new", "some", "could",
    },
    "fr": {
        "le", "la", "les", "de", "et", "en", "du", "un", "une", "pour",
        "dans", "des", "est", "qui", "par", "sur", "au", "avec", "ce", "que",
        "son", "sa", "ses", "sont", "pas", "plus", "aux", "ont", "mais",
        "cette", "il", "elle", "ils", "elles", "comme", "nous", "vous", "leur",
    },
    "de": {
        "der", "die", "das", "und", "in", "zu", "den", "mit", "von", "ist",
        "des", "nicht", "ein", "eine", "einer", "einem", "einen", "eines",
        "auf", "für", "dem", "sich", "im", "auch", "es", "an", "werden",
        "aus", "er", "hat", "dass", "sie", "nach", "wird", "bei", "um", "am",
    },
    "es": {
        "de", "la", "el", "en", "y", "a", "los", "que", "del", "las", "por",
        "un", "para", "con", "una", "es", "al", "se", "su", "mas", "más",
        "pero", "sus", "le", "ya", "o", "fue", "este", "ha", "si", "sí",
        "porque", "esta", "son", "entre", "cuando", "muy", "sin", "sobre",
    },
    "it": {
        "di", "il", "la", "e", "ed", "in", "che", "per", "un", "una", "non",
        "si", "da", "le", "del", "della", "dei", "delle", "nel", "nella",
        "con", "al", "alla", "sono", "ha", "ma", "più", "se", "anche",
        "come", "ci", "su", "dal", "dalla", "questo", "questa", "suo", "sua",
    },
    "pt": {
        "de", "a", "o", "que", "e", "do", "da", "em", "um", "para", "com",
        "não", "uma", "os", "no", "se", "na", "por", "mais", "as", "dos",
        "como", "mas", "ao", "ele", "das", "à", "seu", "sua", "ou", "quando",
        "muito", "nos", "já", "eu", "também", "só", "pelo", "pela", "até",
    },
    "nl": {
        "de", "het", "en", "van", "ik", "te", "dat", "die", "in", "een",
        "hij", "op", "voor", "met", "maar", "zijn", "was", "niet", "is",
        "er", "om", "aan", "zo", "door", "over", "ze", "bij", "wij", "al",
    },
}

_PERSIAN_LETTERS = set("پچژگیک")
_URDU_LETTERS = set("ٹڈڑںےھہ")


def detect_language(text: str, direction: Optional[str] = None) -> str:
    """
    Detect language code from text. If direction is not specified, it is detected first.

    Returns ISO 639-1 / 639-2 language code (e.g. 'he', 'ar', 'fa', 'ur', 'en', 'fr', etc.).
    """
    if direction is None:
        direction = detect_direction(text)

    cleaned = strip_markdown(text)

    if direction == "rtl":
        hebrew_count = 0
        arabic_count = 0
        persian_specific = 0
        urdu_specific = 0
        syriac_count = 0
        thaana_count = 0

        for ch in cleaned:
            code = ord(ch)
            if (0x0590 <= code <= 0x05FF) or (0xFB1D <= code <= 0xFB4F):
                hebrew_count += 1
            elif (
                (0x0600 <= code <= 0x06FF)
                or (0x0750 <= code <= 0x077F)
                or (0x08A0 <= code <= 0x08FF)
                or (0xFB50 <= code <= 0xFDFF)
                or (0xFE70 <= code <= 0xFEFF)
            ):
                arabic_count += 1
                if ch in _PERSIAN_LETTERS:
                    persian_specific += 1
                if ch in _URDU_LETTERS:
                    urdu_specific += 1
            elif 0x0700 <= code <= 0x074F:
                syriac_count += 1
            elif 0x0780 <= code <= 0x07BF:
                thaana_count += 1

        total_rtl_chars = hebrew_count + arabic_count + syriac_count + thaana_count
        if hebrew_count > arabic_count and hebrew_count > 0:
            return "he"
        if arabic_count > 0:
            if urdu_specific > 0:
                return "ur"
            if persian_specific > 0:
                return "fa"
            return "ar"
        if syriac_count > 0:
            return "syr"
        if thaana_count > 0:
            return "dv"
        if total_rtl_chars == 0:
            return _detect_ltr_language(cleaned)
        return "he" if hebrew_count > 0 else "ar"

    return _detect_ltr_language(cleaned)


def _detect_ltr_language(cleaned: str) -> str:
    """Detect language code for LTR or non-RTL text."""
    greek_count = 0
    cyrillic_count = 0
    cjk_count = 0
    kana_count = 0
    hangul_count = 0
    devanagari_count = 0
    bengali_count = 0
    thai_count = 0
    ukrainian_specific = 0
    belarusian_specific = 0

    ukr_letters = set("іїєґІЇЄҐ")
    bel_letters = set("ўЎ")

    for ch in cleaned:
        code = ord(ch)
        if 0x0370 <= code <= 0x03FF:
            greek_count += 1
        elif 0x0400 <= code <= 0x04FF:
            cyrillic_count += 1
            if ch in ukr_letters:
                ukrainian_specific += 1
            elif ch in bel_letters:
                belarusian_specific += 1
        elif 0x3040 <= code <= 0x30FF:
            kana_count += 1
        elif (0xAC00 <= code <= 0xD7AF) or (0x1100 <= code <= 0x11FF):
            hangul_count += 1
        elif 0x4E00 <= code <= 0x9FFF:
            cjk_count += 1
        elif 0x0900 <= code <= 0x097F:
            devanagari_count += 1
        elif 0x0980 <= code <= 0x09FF:
            bengali_count += 1
        elif 0x0E00 <= code <= 0x0E7F:
            thai_count += 1

    words = re.findall(r"\b[a-zà-ÿ]+\b", cleaned.lower())
    latin_word_count = len(words)

    if kana_count > 0:
        return "ja"
    if hangul_count > 0:
        return "ko"
    if cjk_count > 0 and cjk_count >= latin_word_count:
        return "zh"
    if greek_count > 0 and greek_count >= latin_word_count:
        return "el"
    if cyrillic_count > 0 and cyrillic_count >= latin_word_count:
        if ukrainian_specific > 0:
            return "uk"
        if belarusian_specific > 0:
            return "be"
        return "ru"
    if devanagari_count > 0 and devanagari_count >= latin_word_count:
        return "hi"
    if bengali_count > 0 and bengali_count >= latin_word_count:
        return "bn"
    if thai_count > 0 and thai_count >= latin_word_count:
        return "th"

    # Latin-script language detection using stop words
    if not words:
        return "en"

    word_counts = Counter(words)
    scores = {}
    for lang, stop_words in _LATIN_STOP_WORDS.items():
        score = sum(word_counts[w] for w in stop_words if w in word_counts)
        scores[lang] = score

    best_lang, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score > 0:
        return best_lang

    return "en"


def detect_direction_and_language(
    text: str,
    override_direction: Optional[str] = None,
    override_language: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Determine (direction, language) with optional overrides.

    Direction: 'rtl' or 'ltr'
    Language: ISO code, e.g. 'he', 'ar', 'en'
    """
    norm_dir = (
        override_direction.strip().lower()
        if override_direction and override_direction.strip().lower() != "auto"
        else None
    )

    direction = norm_dir if norm_dir in ("rtl", "ltr") else detect_direction(text)

    if override_language and override_language.strip():
        language = override_language.strip().lower()
    else:
        language = detect_language(text, direction=direction)

    return direction, language


def detect_from_markdown_files(
    markdown_path: Union[str, Path],
    override_direction: Optional[str] = None,
    override_language: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Detect direction and language by reading markdown files from a directory or single file.
    """
    path = Path(markdown_path)
    combined_text = []

    if path.is_file() and path.suffix.lower() == ".md":
        try:
            combined_text.append(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    elif path.is_dir():
        for md_file in sorted(path.glob("*.md")):
            try:
                combined_text.append(md_file.read_text(encoding="utf-8"))
            except Exception:
                pass

    all_text = "\n".join(combined_text)
    return detect_direction_and_language(
        all_text,
        override_direction=override_direction,
        override_language=override_language,
    )
