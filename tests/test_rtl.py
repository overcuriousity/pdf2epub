import zipfile
from xml.dom import minidom

from modules.bidi import (
    detect_direction,
    detect_language,
    detect_direction_and_language,
    detect_from_markdown_files,
    strip_markdown,
)
import modules.mark2epub as mark2epub


def test_strip_markdown():
    text = """
# Header
This is prose with [a link](https://example.com) and ![image](images/foo.png).
```python
def foo():
    pass
```
Inline `code` and $$E = mc^2$$ math $x = 1$.
<span class="test">HTML</span>
"""
    cleaned = strip_markdown(text)
    assert "https://example.com" not in cleaned
    assert "images/foo.png" not in cleaned
    assert "def foo():" not in cleaned
    assert "mc^2" not in cleaned
    assert "<span" not in cleaned
    assert "This is prose with a link" in cleaned
    assert "HTML" in cleaned


def test_detect_direction_hebrew():
    hebrew_text = "שלום לכולם! זהו ספר כתוב בשפה העברית לבדיקת כיוון הטקסט."
    assert detect_direction(hebrew_text) == "rtl"


def test_detect_direction_arabic():
    arabic_text = "مرحبا بكم في هذا الكتاب الرائع المكتوب باللغة العربية."
    assert detect_direction(arabic_text) == "rtl"


def test_detect_direction_english():
    english_text = "This is a standard English book that should be detected as LTR."
    assert detect_direction(english_text) == "ltr"


def test_detect_direction_empty_and_neutral():
    assert detect_direction("") == "ltr"
    assert detect_direction("12345 !@#$%^&*() \n\t") == "ltr"


def test_detect_direction_mixed():
    # Hebrew majority with a few English words
    hebrew_majority = "שלום עולם! זהו טקסט בעברית עם מילים בודדות באנגלית כמו hello world."
    assert detect_direction(hebrew_majority) == "rtl"

    # English majority with a few Hebrew words
    english_majority = "Hello everyone! This is mostly English text with a single Hebrew word: שלום."
    assert detect_direction(english_majority) == "ltr"


def test_detect_language():
    assert detect_language("שלום עולם, ברוכים הבאים לספר זה") == "he"
    assert detect_language("مرحبا بكم في هذا الكتاب الرائع") == "ar"
    assert detect_language("این یک کتاب بسیار زیبا به زبان فارسی است") == "fa"
    assert detect_language("یہ اردو زبان میں لکھی گئی ایک کتاب ہے") == "ur"
    assert detect_language("This is a book written in the English language.") == "en"
    assert detect_language("Ceci est un livre formidable sur la programmation.") == "fr"
    assert detect_language("Dies ist ein wunderbares Buch über die Wissenschaft.") == "de"
    assert detect_language("Este es un libro excelente para aprender a programar.") == "es"
    assert detect_language("Это прекрасная книга о программировании.") == "ru"
    assert detect_language("这是一本关于计算机科学的书籍。") == "zh"
    assert detect_language("これはコンピュータサイエンスについての本です。") == "ja"


def test_detect_direction_and_language_overrides():
    text = "This is English prose."
    # Auto
    d, lang = detect_direction_and_language(text)
    assert d == "ltr"
    assert lang == "en"

    # Override direction
    d, lang = detect_direction_and_language(text, override_direction="rtl")
    assert d == "rtl"
    assert lang == "en"

    # Override language
    d, lang = detect_direction_and_language(text, override_language="fr")
    assert d == "ltr"
    assert lang == "fr"

    # Override both
    d, lang = detect_direction_and_language(text, override_direction="rtl", override_language="he")
    assert d == "rtl"
    assert lang == "he"


def test_detect_from_markdown_files(tmp_path):
    md_file = tmp_path / "chapter1.md"
    md_file.write_text("שלום עולם! זהו הפרק הראשון בספר.", encoding="utf-8")

    d, lang = detect_from_markdown_files(tmp_path)
    assert d == "rtl"
    assert lang == "he"


def test_get_packageOPF_XML_rtl():
    description_data = {
        "metadata": {
            "dc:title": "ספר בדיקה",
            "dc:creator": "מחבר",
            "dc:identifier": "id-12345",
            "dc:language": "he",
        },
        "default_css": ["style.css"],
        "chapters": [{"markdown": "ch1.md", "css": ""}],
        "cover_image": None,
        "direction": "rtl",
    }

    xml_str = mark2epub.get_packageOPF_XML(
        md_filenames=["ch1.md"],
        image_filenames=[],
        css_filenames=["style.css"],
        description_data=description_data,
        direction="rtl",
        lang="he",
    )

    doc = minidom.parseString(xml_str)
    package = doc.getElementsByTagName("package")[0]
    assert package.getAttribute("dir") == "rtl"
    assert package.getAttribute("xml:lang") == "he"

    spine = doc.getElementsByTagName("spine")[0]
    assert spine.getAttribute("page-progression-direction") == "rtl"

    languages = doc.getElementsByTagName("dc:language")
    assert len(languages) > 0
    assert languages[0].firstChild.nodeValue == "he"


def test_get_packageOPF_XML_ltr():
    description_data = {
        "metadata": {
            "dc:title": "Test Book",
            "dc:creator": "Author",
            "dc:identifier": "id-12345",
            "dc:language": "en",
        },
        "default_css": ["style.css"],
        "chapters": [{"markdown": "ch1.md", "css": ""}],
        "cover_image": None,
        "direction": "ltr",
    }

    xml_str = mark2epub.get_packageOPF_XML(
        md_filenames=["ch1.md"],
        image_filenames=[],
        css_filenames=["style.css"],
        description_data=description_data,
        direction="ltr",
        lang="en",
    )

    doc = minidom.parseString(xml_str)
    package = doc.getElementsByTagName("package")[0]
    assert package.getAttribute("dir") == "ltr"
    assert package.getAttribute("xml:lang") == "en"

    spine = doc.getElementsByTagName("spine")[0]
    assert spine.getAttribute("page-progression-direction") == "ltr"


def test_get_coverpage_XML():
    cover = mark2epub.get_coverpage_XML("ספר", "מחבר", direction="rtl", lang="he")
    assert 'dir="rtl"' in cover
    assert 'xml:lang="he"' in cover
    assert 'lang="he"' in cover
    assert "direction: rtl" in cover


def test_get_TOC_XML():
    toc = mark2epub.get_TOC_XML(["style.css"], ["ch1.md"], direction="rtl", lang="he")
    assert 'dir="rtl"' in toc
    assert 'xml:lang="he"' in toc
    assert 'lang="he"' in toc


def test_get_TOCNCX_XML():
    ncx = mark2epub.get_TOCNCX_XML(["ch1.md"], uid="id-1", title="כותרת", lang="he")
    assert 'xml:lang="he"' in ncx


def test_get_chapter_XML(tmp_path):
    md_file = tmp_path / "ch1.md"
    md_file.write_text("# כותרת\n\nטקסט עברי.", encoding="utf-8")

    xhtml, images = mark2epub.get_chapter_XML(
        str(tmp_path),
        "ch1.md",
        ["style.css"],
        direction="rtl",
        lang="he",
    )
    assert 'dir="rtl"' in xhtml
    assert 'xml:lang="he"' in xhtml
    assert 'lang="he"' in xhtml
    assert "<h1>כותרת</h1>" in xhtml


def test_end_to_end_epub_generation_rtl(tmp_path):
    work_dir = tmp_path / "book"
    work_dir.mkdir()
    (work_dir / "01_intro.md").write_text("# מבוא\n\nזהו ספר ניסיוני בעברית.", encoding="utf-8")
    (work_dir / "02_body.md").write_text("# תוכן\n\nפרק שני על בינה מלאכותית.", encoding="utf-8")

    epub_path = tmp_path / "book.epub"

    # Run conversion with auto-detection (input is in non-interactive mode)
    mark2epub.convert_markdown_to_epub(work_dir, epub_path)

    assert epub_path.exists()
    with zipfile.ZipFile(epub_path, "r") as z:
        # Check mimetype
        assert z.namelist()[0] == "mimetype"
        assert z.read("mimetype").decode("utf-8") == "application/epub+zip"

        # Check OPF
        opf = z.read("OPS/package.opf").decode("utf-8")
        assert 'dir="rtl"' in opf
        assert 'xml:lang="he"' in opf
        assert 'page-progression-direction="rtl"' in opf
        assert "<dc:language>he</dc:language>" in opf

        # Check titlepage
        titlepage = z.read("OPS/titlepage.xhtml").decode("utf-8")
        assert 'dir="rtl"' in titlepage
        assert 'lang="he"' in titlepage

        # Check TOC
        toc = z.read("OPS/TOC.xhtml").decode("utf-8")
        assert 'dir="rtl"' in toc
        assert 'lang="he"' in toc

        # Check chapter xhtml
        ch1 = z.read("OPS/s00000-01_intro.xhtml").decode("utf-8")
        assert 'dir="rtl"' in ch1
        assert 'lang="he"' in ch1

        # Check CSS includes RTL rule
        css = z.read("OPS/css/style.css").decode("utf-8")
        assert 'dir="rtl"' in css


def test_end_to_end_epub_override_ltr_to_rtl(tmp_path):
    work_dir = tmp_path / "book_en"
    work_dir.mkdir()
    (work_dir / "01_intro.md").write_text("# Chapter 1\n\nThis is English text.", encoding="utf-8")

    epub_path = tmp_path / "book_en.epub"

    # User overrides direction to RTL and language to ar
    mark2epub.convert_markdown_to_epub(
        work_dir,
        epub_path,
        direction="rtl",
        language="ar",
    )

    assert epub_path.exists()
    with zipfile.ZipFile(epub_path, "r") as z:
        opf = z.read("OPS/package.opf").decode("utf-8")
        assert 'dir="rtl"' in opf
        assert 'xml:lang="ar"' in opf
        assert 'page-progression-direction="rtl"' in opf

        ch1 = z.read("OPS/s00000-01_intro.xhtml").decode("utf-8")
        assert 'dir="rtl"' in ch1
        assert 'lang="ar"' in ch1


def test_main_cli_arguments():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument('input_path', nargs='?')
    p.add_argument('output_path', nargs='?')
    p.add_argument('--direction', '--dir', dest='direction', choices=['rtl', 'ltr', 'auto'], default='auto')
    p.add_argument('--rtl', action='store_true')
    p.add_argument('--ltr', action='store_true')
    p.add_argument('--lang', '--language', dest='language', default=None)

    args = p.parse_args(["--direction", "rtl", "--lang", "he"])
    assert args.direction == "rtl"
    assert args.language == "he"

    args2 = p.parse_args(["--rtl"])
    assert args2.rtl is True

    args3 = p.parse_args(["--dir", "ltr"])
    assert args3.direction == "ltr"
