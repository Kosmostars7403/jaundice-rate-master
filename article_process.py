import logging
from contextlib import contextmanager
from enum import Enum
import time

import aiohttp
import asyncio
import re

import pymorphy2 as pymorphy2
import pytest
from bs4 import BeautifulSoup
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


@contextmanager
def runtime_measurement(*args, **kwds):
    start_time = time.monotonic()
    try:
        yield
    finally:
        end_time = time.monotonic()
        logging.info(f'Анализ закончен за {end_time - start_time} сек')


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


async def process_article(session, morph, charged_words, url, analyze_results, fetch_timeout=TIMEOUT):
    title = 'URL not exist'
    jaundice_rating = words_amount = None
    status = ProcessingStatus.OK

    try:
        async with timeout(fetch_timeout):
            html = await fetch(session, url)

        article_soup = BeautifulSoup(html, 'html.parser')
        title = article_soup.find('title').string

        article_text = sanitize(html, plaintext=True)
        with runtime_measurement():
            splited_text = await split_by_words(morph, article_text)
        words_amount = len(splited_text)

        jaundice_rating = calculate_jaundice_rate(splited_text, charged_words)

    except aiohttp.ClientError:
        status = ProcessingStatus.FETCH_ERROR

    except adapters.ArticleNotFound:
        domain_pattern = r'(^http[s]:\/\/)?(?P<domain>\w+\.\w+)'
        match = re.match(domain_pattern, url)
        title = f'Статья с сайта {match.group("domain")}'
        status = ProcessingStatus.PARSING_ERROR

    except asyncio.TimeoutError:
        status = ProcessingStatus.TIMEOUT

    analyze_result = {
        'title': title,
        'status': status.value,
        'rating': jaundice_rating,
        'words_amount': words_amount
    }

    analyze_results.append(analyze_result)

    return analyze_result


@pytest.mark.asyncio
async def test_process_article():
    morph = pymorphy2.MorphAnalyzer()
    charged_words = load_charged_dict()

    async with aiohttp.ClientSession() as session:
        processing_results = await process_article(
            session=session,
            charged_words=charged_words,
            morph=morph,
            url='https://inosmi.ru/politic/20200125/246700442.html',
            analyze_results=[]
        )
        assert processing_results['status'] == ProcessingStatus.OK.value

        processing_results = await process_article(
            session=session,
            charged_words=charged_words,
            morph=morph,
            url='https://inosmi.ru/politic/20200125/2467002.html',
            analyze_results=[]
        )
        assert processing_results['status'] == ProcessingStatus.FETCH_ERROR.value

        processing_results = await process_article(
            session=session,
            charged_words=charged_words,
            morph=morph,
            url='https://youtube.com',
            analyze_results=[]
        )
        assert processing_results['status'] == ProcessingStatus.PARSING_ERROR.value

        processing_results = await process_article(
            session=session,
            charged_words=charged_words,
            morph=morph,
            url='https://inosmi.ru/politic/20200125/246700442.html',
            analyze_results=[],
            fetch_timeout=0.1
        )
        assert processing_results['status'] == ProcessingStatus.TIMEOUT.value

        processing_results = await process_article(
            session=session,
            charged_words=charged_words,
            morph=morph,
            url='https://inosmi.ru/politic/20200125/246700442.html',
            analyze_results=[],
            fetch_timeout=0.1
        )
        assert processing_results['status'] == ProcessingStatus.TIMEOUT.value


