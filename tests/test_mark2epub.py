import tempfile
import unittest
from xml.etree import ElementTree as ET

from modules.mark2epub import (
    get_chapter_XML, get_navigation_entries, get_TOC_XML, get_TOCNCX_XML,
    normalize_markdown_for_epub,
)

NS = {'h': 'http://www.w3.org/1999/xhtml'}


class EpubRepairsTest(unittest.TestCase):
    def chapter(self, source):
        with tempfile.TemporaryDirectory() as folder:
            text, _ = get_chapter_XML(folder, 'book.md', [], content=source)
        return text, ET.fromstring(text)

    def test_numbered_list_has_one_marker_per_item(self):
        _, root = self.chapter('- 1. First\n- 2. Second\n- 3. Third\n')
        items = root.findall('.//h:ol/h:li', NS)
        self.assertEqual([x.text for x in items], ['First', 'Second', 'Third'])
        self.assertEqual(root.findall('.//h:ul', NS), [])

    def test_nested_bullets_belong_to_numbered_parent(self):
        _, root = self.chapter('- 1. Parent\n  - Child A\n  - Child B\n- 2. Next\n')
        items = root.findall('.//h:body/h:ol/h:li', NS)
        self.assertEqual(len(items), 2)
        self.assertEqual(len(items[0].findall('h:ul/h:li', NS)), 2)

    def test_duplicate_and_standalone_bullets(self):
        _, root = self.chapter('•\n\n- •First\n- • Second\n○ Third\n')
        self.assertEqual([x.text for x in root.findall('.//h:li', NS)],
                         ['First', 'Second', 'Third'])

    def test_loose_sublist_does_not_swallow_next_number(self):
        _, root = self.chapter('1. Parent\n\n    - Child\n2. Next\n    - Next child\n')
        items = root.findall('.//h:body/h:ol/h:li', NS)
        self.assertEqual(len(items), 2)
        self.assertEqual([len(item.findall('h:ul/h:li', NS)) for item in items], [1, 1])

    def test_numbering_continues_after_page_break(self):
        _, root = self.chapter('- 4. Fourth\n\n5. Fifth\n')
        ordered = root.find('.//h:ol', NS)
        self.assertEqual(ordered.get('start'), '4')
        self.assertEqual(len(ordered.findall('h:li', NS)), 2)

    def test_links_breaks_and_currency_form_valid_xhtml(self):
        _, root = self.chapter('Visit <www.example.com><br>Costs \\$19 and \\$60.\n')
        self.assertEqual(root.find('.//h:a', NS).get('href'), 'https://www.example.com')
        self.assertIn('$19 and $60', ''.join(root.itertext()))
        self.assertNotIn('math', [x.tag.rsplit('}', 1)[-1] for x in root.iter()])

    def test_real_math_and_currency_inside_math(self):
        _, root = self.chapter('Price \\$19. Formula $x^2$.\n\n$$\\frac{\\$300}{50}$$')
        self.assertEqual(len(root.findall('.//{http://www.w3.org/1998/Math/MathML}math')), 2)

    def test_code_and_reference_year_unchanged(self):
        source = '```md\n- 1. literal\n<www.example.com>\n```\n\n- 2021. Reference\n'
        self.assertEqual(normalize_markdown_for_epub(source), source)

    def test_heading_navigation_supports_selected_lower_levels(self):
        text, root = self.chapter('# Title\n\n### Chapter One\n\n### Chapter Two\n')
        entries = get_navigation_entries(['book.md'], {'book.md': text},
                                         ['Chapter One', 'Chapter Two'])
        self.assertEqual([label for _, label in entries], ['Chapter One', 'Chapter Two'])
        ids = {x.get('id') for x in root.iter()}
        self.assertTrue(all(href.split('#')[1] in ids for href, _ in entries))
        ET.fromstring(get_TOC_XML([], ['book.md'], entries))
        ET.fromstring(get_TOCNCX_XML(['book.md'], entries=entries))
        with self.assertRaises(ValueError):
            get_navigation_entries(['book.md'], {'book.md': text}, ['Missing'])

    def test_printed_contents_titles_and_pages_are_clickable(self):
        source = ('### SPIS TREŚCI\n\n| Tytuł | Strona |\n|---|---|\n'
                  '| Pierwszy<br>rozdział | 12 |\n\n### Pierwszy rozdział\n\nText\n\n### 100\n')
        _, root = self.chapter(source)
        links = root.findall('.//h:td/h:a', NS)
        self.assertEqual(len(links), 2)
        self.assertEqual({el.get('href') for el in links}, {'#pierwszy-rozdzia'})

    def test_contents_supports_chapter_numbers_and_ordinary_tables_stay_plain(self):
        source = ('# Brief Contents\n\n| Chapter | Title | Page |\n|---|---|---|\n'
                  '| Chapter 1 | First Chapter | 1 |\n\n# First Chapter\n\n'
                  '| Title | Page |\n|---|---|\n| First Chapter | 2 |\n')
        _, root = self.chapter(source)
        tables = root.findall('.//h:table', NS)
        self.assertEqual(len(tables[0].findall('.//h:td/h:a', NS)), 2)
        self.assertEqual(tables[1].findall('.//h:a', NS), [])


if __name__ == '__main__':
    unittest.main()
