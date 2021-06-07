from functools import partial

import aiohttp
import pymorphy2
from aiohttp import web
from anyio import create_task_group

from article_process import process_article, load_charged_dict

MAX_ARTICLES_FOR_ANALYSIS = 10


async def handle(morph, charged_dict, request):
    urls = request.query.get('urls').split(',')

    if not urls:
        return web.json_response(data={'error': 'Give us at least 1 article!'}, status=400)
    if len(urls) > MAX_ARTICLES_FOR_ANALYSIS:
        return web.json_response(
            data={'error': f'Too many urls in request, should be {MAX_ARTICLES_FOR_ANALYSIS} or less'},
            status=400
        )

    async with aiohttp.ClientSession(trust_env=True) as session:

        analyze_results = []

        async with create_task_group() as tg:
            for url in urls:
                await tg.spawn(process_article, session, morph, charged_dict, url, analyze_results)

        return web.json_response(analyze_results)


if __name__ == '__main__':
    app = web.Application()
    morph = pymorphy2.MorphAnalyzer()
    charged_dict = load_charged_dict()
    app.add_routes([web.get('/', partial(handle, morph, charged_dict))])
    web.run_app(app)
