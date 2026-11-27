"""One-off script: loads hadiths into the `khadisy` table of the SQLite database.

Which source file it reads (whichever is present in the project root):
  - khadisy.txt  - plain text: one hadith per paragraph, paragraphs separated
                   by a blank line. Lines starting with '#' are ignored.
                   This is the recommended source for an English hadith collection.
  - khadisy.epub - the legacy Russian book "Hadiths. Volume 1" by Shamil Alyautdinov.

Re-running the script does not create duplicates - already existing hadiths are skipped.
"""
import os
import re
import sys

from db import insert_many, delete_or_insert_data as d_id, select_data

TXT_FILE = "khadisy.txt"
EPUB_FILE = "khadisy.epub"


def load_from_txt(path):
    """Reads a plain-text file: paragraphs separated by a blank line."""
    with open(path, encoding="utf-8") as f:
        content = f.read()

    hadiths = []
    for paragraph in re.split(r"\n\s*\n", content):
        paragraph = paragraph.strip()
        # skip comments and empty blocks
        lines = [ln for ln in paragraph.splitlines() if not ln.strip().startswith("#")]
        paragraph = "\n".join(lines).strip()
        if paragraph:
            hadiths.append(paragraph)
    return hadiths


def load_from_epub(path):
    """Reads the legacy Russian epub book (structure-specific parsing)."""
    # lazy imports: they are only needed for the epub source
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup as bs

    book = epub.read_epub(path)
    items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))

    hadiths = []
    for v in items:
        chapter = v.get_content().decode("utf8")
        chapter_arr = chapter.split("<p class=\"center\">ﷺ</p>&#13;")
        for z in chapter_arr:
            soup = bs(z, "html.parser")
            khadis = soup.find_all('p', 'normal')
            created_khadis = ''
            for x in khadis:
                created_khadis = created_khadis + re.sub(
                    r"(?<=[а-яА-Яa-zA-Z\]\}\)\'\"\”])\d+(?=[\b\.\s\,\]])", '', x.get_text())
            if created_khadis != '':
                created_khadis = created_khadis + "\nSource: Hadiths. Volume 1. Author: Shamil Alyautdinov"
                hadiths.append(created_khadis)
    return hadiths


if os.path.exists(TXT_FILE):
    source = TXT_FILE
    hadiths = load_from_txt(TXT_FILE)
elif os.path.exists(EPUB_FILE):
    source = EPUB_FILE
    hadiths = load_from_epub(EPUB_FILE)
else:
    print(f"No source file found. Put '{TXT_FILE}' (recommended) or '{EPUB_FILE}' "
          f"into the project root and run this script again.")
    sys.exit(1)

existing = {row[0] for row in select_data("select khadis from khadisy")}
inserted = 0
skipped = 0

for hadis_text in hadiths:
    if hadis_text in existing:
        skipped += 1
        continue
    d_id("insert into khadisy(khadis) values(?);", (hadis_text,))
    existing.add(hadis_text)
    inserted += 1

print(f"Source file: {source}")
print(f"Added: {inserted}, duplicates skipped: {skipped}")
