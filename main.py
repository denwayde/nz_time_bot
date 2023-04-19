import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup as bs
import re
from db import insert_many, delete_or_insert_data as d_id, select_data


book = epub.read_epub('khadisy.epub')
items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))

for v in items:
    chapter = v.get_content().decode('utf8')
    chapter_arr = chapter.split("<p class=\"center\">ﷺ</p>&#13;")
    for z in chapter_arr:
        soup = bs(z, "html.parser")
        khadis = soup.find_all('p','normal')
        created_khadis = ''
        for x in khadis:
            created_khadis = created_khadis + re.sub(r"(?<=[а-яА-Я\]\}\)\'\"\”])\d+(?=[\b\.\s\,\]])",'',x.get_text())   
        if created_khadis != '':
            created_khadis = created_khadis + "\nИсточник: Хадисы. Том 1. Автор: Шамиль Аляутдинов"
            d_id("insert into khadisy(khadis) values(?);",(created_khadis, ))

