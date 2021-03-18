from enum import Enum

import aiohttp
import asyncio
import re

import pymorphy2 as pymorphy2
from anyio import sleep, create_task_group, run
from bs4 import BeautifulSoup
from pprint import pprint
from async_timeout import timeout

import adapters
from adapters.inosmi_ru import sanitize
from text_tools import split_by_words, calculate_jaundice_rate


TEST_ARTICLES = [
    'https://lenta.ru/news/2021/03/18/ill/',
    'https://inosmi.ru/politic/20210318/249361396.html',
    'https://inosmi.ru/military/20210318/249362816.html',
    'https://inosmi.ru/military/20210318/249361444.html',
    'https://inosmi.ru/economic/20210316/249333199.html'
]

TIMEOUT = 2


class ProcessingStatus(Enum):
    OK = 'OK'
    FETCH_ERROR = 'FETCH_ERROR'
    PARSING_ERROR = 'PARSING_ERROR'
    TIMEOUT = 'TIMEOUT'


def load_charged_dict():
    with open('charged_dict/negative_words.txt', 'r') as negative_words,\
         open('charged_dict/positive_words.txt', 'r') as positive_words:

        negative_words = negative_words.read().split('\n')
        positive_words = positive_words.read().split('\n')

        positive_words.extend(negative_words)

        return positive_words


async def fetch(session, url):
    async with session.get(url, ssl=False) as response:
        response.raise_for_status()
        return await response.text()


async def process_article(session, morph, charged_words, url, analyze_results):
    title = 'URL not exist'
    jaundice_rating = words_amount = None
    status = ProcessingStatus.OK

    try:
        async with timeout(TIMEOUT):
            html = await fetch(session, url)

        article_soup = BeautifulSoup(html, 'html.parser')
        title = article_soup.find('title').string

        article_text = sanitize(html, plaintext=True)

        splited_text = split_by_words(morph, article_text)
        words_amount = len(splited_text)

        jaundice_rating = calculate_jaundice_rate(splited_text, charged_words)

    except aiohttp.ClientError:
        status = ProcessingStatus.FETCH_ERROR

    except adapters.ArticleNotFound:
        domain_pattern = r'(^http[s]:\/\/)?(?P<domain>\w+\.\w+)'
        match = re.match(domain_pattern, url)
        title = f'Статья с сайта {match.group("domain")}'

    except asyncio.TimeoutError:
        status = ProcessingStatus.TIMEOUT

    analyze_results.append({
        'title': title,
        'status': status,
        'rating': jaundice_rating,
        'words_amount': words_amount
    })


async def main(morph, charged_dict):
    async with aiohttp.ClientSession(trust_env=True) as session:

        analyze_results = []

        async with create_task_group() as tg:
            for url in TEST_ARTICLES:
                await tg.spawn(process_article, session, morph, charged_dict, url, analyze_results)

        pprint(analyze_results)


if __name__ == '__main__':
    morph = pymorphy2.MorphAnalyzer()

    charged_dict = load_charged_dict()

    asyncio.run(main(morph, charged_dict))
