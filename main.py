import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup as bs
import re
from db import insert_many, delete_or_insert_data as d_id, select_data

# Разовый скрипт: заливает хадисы из khadisy.epub в базу.
# Повторный запуск не создаёт дубликаты - уже существующие хадисы пропускаются.

book = epub.read_epub('khadisy.epub')
items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))

existing = {row[0] for row in select_data("select khadis from khadisy")}
inserted = 0
skipped = 0

for v in items:
    chapter = v.get_content().decode('utf8')
    chapter_arr = chapter.split("<p class=\"center\">ﷺ</p>&#13;")
    for z in chapter_arr:
        soup = bs(z, "html.parser")
        khadis = soup.find_all('p', 'normal')
        created_khadis = ''
        for x in khadis:
            created_khadis = created_khadis + re.sub(r"(?<=[а-яА-Я\]\}\)\'\"\”])\d+(?=[\b\.\s\,\]])", '', x.get_text())
        if created_khadis != '':
            created_khadis = created_khadis + "\nИсточник: Хадисы. Том 1. Автор: Шамиль Аляутдинов"
            if created_khadis in existing:
                skipped += 1
                continue
            d_id("insert into khadisy(khadis) values(?);", (created_khadis,))
            existing.add(created_khadis)
            inserted += 1

print(f"Добавлено: {inserted}, пропущено дубликатов: {skipped}")
