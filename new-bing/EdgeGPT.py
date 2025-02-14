"""
Main.py
"""
from __future__ import annotations

import json
import os
import random
import ssl
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Generator, Literal, Optional, Union

import aiohttp
import certifi
import httpx

from BingImageCreator import async_image_gen
from logger import logger

DELIMITER = '\x1e'

BING_PROXY_URL = os.environ.get('BING_PROXY_URL')


# Generate random IP between range 13.104.0.0/14
def get_forwarded_ip():
    return f'13.{random.randint(104, 107)}.{random.randint(0, 255)}.{random.randint(0, 255)}'


FORWARDED_IP = get_forwarded_ip()

HEADERS = {
    'accept': 'application/json',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/json',
    'sec-ch-ua': '"Microsoft Edge";v="113", "Chromium";v="113", "Not-A.Brand";v="24"',
    'sec-ch-ua-arch': '"x86"',
    'sec-ch-ua-bitness': '"64"',
    'sec-ch-ua-full-version': '"113.0.1774.50"',
    'sec-ch-ua-full-version-list': '"Microsoft Edge";v="113.0.1774.50", "Chromium";v="113.0.5672.127", "Not-A.Brand";v="24.0.0.0"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-model': '""',
    'sec-ch-ua-platform': '"macOS"',
    'sec-ch-ua-platform-version': '"10.15.7"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'x-ms-client-request-id': str(uuid.uuid4()),
    'x-ms-useragent': 'azsdk-js-api-client-factory/1.0.0-beta.1 core-rest-pipeline/1.10.0 OS/MacIntel',
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36 Edg/113.0.1774.50',
    'Referer': 'https://www.bing.com/search?q=Bing+AI&showconv=1&FORM=hpcodx',
    'Referrer-Policy': 'origin-when-cross-origin',
    'x-forwarded-for': FORWARDED_IP,
}

HEADERS_INIT_CONVER = {
    'authority': 'www.bing.com',
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'en-US,en;q=0.9',
    'cache-control': 'max-age=0',
    "sec-ch-ua": '"Microsoft Edge";v="113", "Chromium";v="113", "Not-A.Brand";v="24"',
    "sec-ch-ua-arch": '"x86"',
    "sec-ch-ua-bitness": '"64"',
    "sec-ch-ua-full-version": '"113.0.1774.50"',
    "sec-ch-ua-full-version-list": '"Microsoft Edge";v="113.0.1774.50", "Chromium";v="113.0.5672.127", "Not-A.Brand";v="24.0.0.0"',
    'sec-ch-ua-mobile': '?0',
    "sec-ch-ua-model": '""',
    "sec-ch-ua-platform": '"macOS"',
    "sec-ch-ua-platform-version": '"10.15.7"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'none',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'x-edge-shopping-flag': '1',
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36 Edg/113.0.1774.50',
    'x-forwarded-for': FORWARDED_IP,
}

ssl_context = ssl.create_default_context()
ssl_context.load_verify_locations(certifi.where())


class NotAllowedToAccess(Exception):
    pass


class ConversationStyle(Enum):
    creative = [
        'nlu_direct_response_filter',
        'deepleo',
        'disable_emoji_spoken_text',
        'responsible_ai_policy_235',
        'enablemm',
        'h3imaginative',
        'dv3sugg',
        'autosave',
        'clgalileo',
        'gencontentv3',
    ]
    balanced = [
        'nlu_direct_response_filter',
        'deepleo',
        'disable_emoji_spoken_text',
        'responsible_ai_policy_235',
        'enablemm',
        'galileo',
        'dv3sugg',
        'autosave',
        'saharagenconv5',
    ]
    precise = [
        'nlu_direct_response_filter',
        'deepleo',
        'disable_emoji_spoken_text',
        'responsible_ai_policy_235',
        'enablemm',
        'h3precise',
        'dv3sugg',
        'autosave',
        'clgalileo',
        'gencontentv3',
    ]


CONVERSATION_STYLE_TYPE = Optional[Union[ConversationStyle, Literal['creative', 'balanced', 'precise']]]


def _append_identifier(msg: dict) -> str:
    """
    Appends special character to end of message to identify end of message
    """
    # Convert dict to json string
    return json.dumps(msg, ensure_ascii=False) + DELIMITER


def get_ran_hex(length: int = 32) -> str:
    """
    Returns random hex string
    """
    return ''.join(random.choice('0123456789abcdef') for _ in range(length))


def _get_proxy():
    proxy = (
        os.environ.get('all_proxy') or os.environ.get('ALL_PROXY') or os.environ.get('https_proxy')
        or os.environ.get('HTTPS_PROXY') or None
    )
    if proxy is not None and proxy.startswith('socks5h://'):
        proxy = 'socks5://' + proxy[len('socks5h://'):]
    return proxy


class _ChatHubRequest:
    """
    Request object for ChatHub
    """

    def __init__(
        self,
        conversation_signature: str,
        client_id: str,
        conversation_id: str,
        invocation_id: int = 0,
    ) -> None:
        self.struct: dict = {}
        self.client_id: str = client_id
        self.conversation_id: str = conversation_id
        self.conversation_signature: str = conversation_signature
        self.invocation_id: int = invocation_id
        self.forwarded_ip = get_forwarded_ip()

    def update(
        self,
        prompt: str,
        conversation_style: CONVERSATION_STYLE_TYPE,
        options: list | None = None,
    ) -> None:
        """
        Updates request object
        """
        if options is None:
            options = ConversationStyle.creative.value
        if conversation_style:
            if not isinstance(conversation_style, ConversationStyle):
                conversation_style = getattr(ConversationStyle, conversation_style)
            if conversation_style:
                options = conversation_style.value
        self.struct = {
            'arguments': [
                {
                    'source': 'cib',
                    'optionsSets': options,
                    'allowedMessageTypes': [
                        'Chat',
                        'GenerateContentQuery',
                        'InternalLoaderMessage',
                        'InternalSearchQuery',
                        'SearchQuery',
                        "Progress",
                        'Disengaged',
                    ],
                    'sliceIds': [],
                    'traceId': get_ran_hex(32),
                    'isStartOfSession': self.invocation_id == 0,
                    'tone': conversation_style.name.capitalize() if conversation_style else '',
                    'message': {
                        'locale': 'zh-CN',
                        'market': 'zh-CN',
                        'region': 'WW',
                        'locationHints': [
                            {
                                'country': 'Singapore',
                                'state': 'Central Singapore',
                                'city': 'Singapore',
                                'timezoneoffset': 8,
                                'countryConfidence': 8,
                                'Center': {
                                    'Latitude': 1.2894,
                                    'Longitude': 103.85,
                                },
                                'RegionType': 2,
                                'SourceType': 1,
                            },
                        ],
                        'timestamp': datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00'),
                        'author': 'user',
                        'inputMethod': 'Keyboard',
                        'text': prompt,
                        'messageType': 'Chat',
                    },
                    'conversationSignature': self.conversation_signature,
                    'participant': {
                        'id': self.client_id,
                    },
                    "spokenTextMode": "None",
                    'conversationId': self.conversation_id,
                },
            ],
            'invocationId': str(self.invocation_id),
            'target': 'chat',
            'type': 4,
        }
        self.invocation_id += 1


class _Conversation:
    """
    Conversation API
    """

    def __init__(
        self,
        cookies: dict | None = None,
        async_mode: bool = False,
    ) -> None:
        if async_mode:
            return
        self.struct: dict = {
            'conversationId': None,
            'clientId': None,
            'conversationSignature': None,
            'result': {
                'value': 'Success',
                'message': None
            },
        }
        proxy = _get_proxy()
        self.session = httpx.Client(
            proxies=proxy,
            timeout=60,
            headers=HEADERS_INIT_CONVER,
        )
        if cookies:
            for cookie in cookies:
                self.session.cookies.set(cookie['name'], cookie['value'])

        # Send GET request
        url = BING_PROXY_URL or 'https://www.bing.com/turing/conversation/create'
        response = self.session.get(url=url, )
        if response.status_code != 200 and BING_PROXY_URL:
            response = self.session.get('https://www.bing.com/turing/conversation/create')
        if response.status_code != 200:
            response = self.session.get('https://edgeservices.bing.com/edgesvc/turing/conversation/create')
        if response.status_code != 200:
            logger.error('[create], code: %s, response: %s', response.status_code, response.text)
            try:
                resp = response.json()
                raise NotAllowedToAccess(resp['result']['message'])
            except NotAllowedToAccess as e:
                raise e
            except Exception:
                raise Exception('Authentication failed')
        try:
            self.struct = response.json()
        except (json.decoder.JSONDecodeError, NotAllowedToAccess) as exc:
            raise Exception('Authentication failed. You have not been accepted into the beta.', ) from exc
        if self.struct['result']['value'] == 'UnauthorizedRequest':
            raise NotAllowedToAccess(self.struct['result']['message'])

    @staticmethod
    async def create(cookies: dict, ) -> _Conversation:
        self = _Conversation(async_mode=True)
        self.struct = {
            'conversationId': None,
            'clientId': None,
            'conversationSignature': None,
            'result': {
                'value': 'Success',
                'message': None
            },
        }
        proxy = _get_proxy()
        transport = httpx.AsyncHTTPTransport(retries=5)
        async with httpx.AsyncClient(
                proxies=proxy,
                timeout=60,
                headers=HEADERS_INIT_CONVER,
                transport=transport,
        ) as client:
            for cookie in cookies:
                client.cookies.set(cookie['name'], cookie['value'])
            # Send GET request
            url = BING_PROXY_URL or 'https://www.bing.com/turing/conversation/create'
            response = await client.get(url=url)
            if response.status_code != 200 and BING_PROXY_URL:
                response = await client.get('https://www.bing.com/turing/conversation/create')
            if response.status_code != 200:
                response = await client.get('https://edgeservices.bing.com/edgesvc/turing/conversation/create')
        if response.status_code != 200:
            try:
                logger.error('[create], code: %s, response: %s', response.status_code, response.text)
                resp = response.json()
                raise NotAllowedToAccess(resp['result']['message'])
            except NotAllowedToAccess as e:
                raise e
            except Exception:
                raise Exception('Authentication failed')
        try:
            self.struct = response.json()
        except (json.decoder.JSONDecodeError, NotAllowedToAccess) as exc:
            raise Exception('Authentication failed. You have not been accepted into the beta.', ) from exc
        if self.struct['result']['value'] == 'UnauthorizedRequest':
            raise NotAllowedToAccess(self.struct['result']['message'])
        return self


class _ChatHub:
    """
    Chat API
    """

    def __init__(self, conversation: _Conversation = None, request: _ChatHubRequest = None) -> None:
        self.session: aiohttp.ClientSession | None = None
        self.wss: aiohttp.ClientWebSocketResponse | None = None
        self.request: _ChatHubRequest
        self.wss = None
        self.session = None
        if request and not hasattr(request, 'forwarded_ip'):
            setattr(request, 'forwarded_ip', get_forwarded_ip())
        self.request = _ChatHubRequest(
            conversation_signature=conversation.struct['conversationSignature'],
            client_id=conversation.struct['clientId'],
            conversation_id=conversation.struct['conversationId'],
        ) if not request else request

    async def ask_stream(
        self,
        prompt: str,
        wss_link: str,
        conversation_style: CONVERSATION_STYLE_TYPE = None,
        raw: bool = False,
        options: dict = None,
        cookie_path: str = '',
        another_try: bool = False,
    ) -> Generator[str, None, None]:
        """
        Ask a question to the bot
        """
        timeout = aiohttp.ClientTimeout(total=3600)
        self.session = aiohttp.ClientSession(timeout=timeout)
        headers = HEADERS
        headers['x-forwarded-for'] = self.request.forwarded_ip
        self.wss = await self.session.ws_connect(
            wss_link,
            headers=HEADERS,
            ssl=ssl_context,
            autoclose=True,
            timeout=3600,
            proxy=_get_proxy(),
        )
        await self._initial_handshake()
        logger.info(
            '[Session] create session, %s.',
            self.wss,
        )
        if not another_try:
            self.request.update(
                prompt=prompt,
                conversation_style=conversation_style,
                options=options,
            )
        else:
            self.request.struct['arguments'][0]['message']['text'] = prompt
        await self.wss.send_str(_append_identifier(self.request.struct))
        logger.info('[Request] send data: %s', _append_identifier(self.request.struct))
        final = False
        draw = False
        resp_txt = ''
        resp_txt_no_link = ''
        retry_count = 5
        last_t = 0
        while not final:
            msg = await self.wss.receive(timeout=600)
            if msg.data is None:
                retry_count -= 1
                if retry_count == 0:
                    logger.error('[Response] message data is None, %s, %s, %s', msg, msg.type, msg.data)
                    raise Exception('Unexpected message type: %s' % msg.type)
                continue
            if type(msg.data) is int:
                logger.error('[Response] receive int response, %s, %s, %s', msg, msg.type, msg.data)
                raise Exception('Unexpected message type: %s' % msg.type)
            objects = msg.data.split(DELIMITER)
            for obj in objects:
                t = int(time.time())
                if t % 5 == 0 and t > last_t:
                    try:
                        last_t = t
                        await self.wss.send_str(_append_identifier({'type': 6}))
                        logger.info('Send message type 6 to keep alive.')
                    except:
                        pass
                if not obj:
                    continue
                response = json.loads(obj)
                if response.get('type') != 2 and raw:
                    yield False, response
                elif response.get('type') == 1 and response['arguments'][0].get('messages', ):
                    if not draw:
                        if (response['arguments'][0]['messages'][0].get('messageType') == 'GenerateContentQuery'):
                            images = await async_image_gen(
                                response['arguments'][0]['messages'][0]['text'],
                                cookie_path=cookie_path,
                                forwarded_ip=self.request.forwarded_ip,
                            )
                            for i, image in enumerate(images):
                                resp_txt += f'\n![image{i}]({image})'
                            draw = True
                        if (response['arguments'][0]['messages'][0]['contentOrigin'] != 'Apology') and not draw:
                            resp_txt = response['arguments'][0]['messages'][0]['adaptiveCards'][0]['body'][0].get(
                                'text', ''
                            )
                            resp_txt_no_link = resp_txt + response['arguments'][0]['messages'][0].get('text', '')
                            if response['arguments'][0]['messages'][0].get('messageType', ''):
                                resp_txt = response['arguments'][0]['messages'][0]['adaptiveCards'][0]['body'][0][
                                    'inlines'][0].get('text')
                        yield False, resp_txt

                elif response.get('type') == 2:
                    try:
                        logger.info('[Response] %s', response)
                        if draw:
                            for i in range(1, len(response['item']['messages'])):
                                try:
                                    if 'text' not in response['item']['messages'][i]['adaptiveCards'][0]['body'][0]:
                                        continue
                                    response['item']['messages'][i]['adaptiveCards'][0]['body'][0]['text'] = resp_txt
                                except:
                                    pass
                        if (response['item']['messages'][-1]['contentOrigin'] == 'Apology' and resp_txt):
                            response['item']['messages'][-1]['text'] = resp_txt_no_link
                            response['item']['messages'][-1]['adaptiveCards'][0]['body'][0]['text'] = resp_txt
                    except KeyError:
                        pass
                    final = True
                    try:
                        await self.close()
                    except:
                        pass
                    yield True, response
                elif response.get('type') == 6:
                    try:
                        logger.info('[Response], receive %s', response)
                        await self.wss.send_str(_append_identifier({'type': 6}))
                    except Exception:
                        logger.error('[Response], send response to bing error occor', exc_info=True)
                elif response.get('type') == 3:
                    try:
                        logger.info('[Response], receive %s', response)
                        await self.close()
                    except Exception:
                        pass
                else:
                    logger.info('[Response], receive %s', response)

    async def _initial_handshake(self) -> None:
        if not self.wss:
            return
        await self.wss.send_str(_append_identifier({
            'protocol': 'json',
            'version': 1
        }))
        await self.wss.receive(timeout=60)
        await self.wss.send_str(_append_identifier({
            'type': 6,
        }))

    async def close(self) -> None:
        """
        Close the connection
        """
        if self.wss and not self.wss.closed:
            await self.wss.close()
        if self.session and not self.session.closed:
            await self.session.close()


class Chatbot:
    """
    Combines everything to make it seamless
    """

    def __init__(
        self,
        cookie_path: str = '',
        request: _ChatHubRequest = None,
    ) -> None:
        self.cookie_path = cookie_path
        self.load_cookie()
        if not request:
            self.chat_hub: _ChatHub = _ChatHub(_Conversation(self.cookies))
        else:
            self.chat_hub: _ChatHub = _ChatHub(request=request)

    @staticmethod
    async def create():
        self = Chatbot.__new__(Chatbot)
        self.load_cookie()
        self.chat_hub = _ChatHub(await _Conversation.create(self.cookies))
        return self

    async def ask(
        self,
        prompt: str,
        wss_link: str = 'wss://sydney.bing.com/sydney/ChatHub',
        conversation_style: CONVERSATION_STYLE_TYPE = None,
        options: dict = None,
    ) -> dict:
        """
        Ask a question to the bot
        """
        try:
            async for final, response in self.chat_hub.ask_stream(
                    prompt=prompt,
                    conversation_style=conversation_style,
                    wss_link=wss_link,
                    options=options,
                    cookie_path=self.cookie_path,
            ):
                if final:
                    return response
            return {}
        except Exception as e:
            await self.close()
            raise e

    async def ask_stream(
        self,
        prompt: str,
        wss_link: str = 'wss://sydney.bing.com/sydney/ChatHub',
        conversation_style: CONVERSATION_STYLE_TYPE = None,
        raw: bool = False,
        options: dict = None,
        another_try: bool = False,
    ) -> Generator[str, None, None]:
        """
        Ask a question to the bot
        """
        try:
            async for response in self.chat_hub.ask_stream(
                    prompt=prompt,
                    conversation_style=conversation_style,
                    wss_link=wss_link,
                    raw=raw,
                    options=options,
                    cookie_path=self.cookie_path,
                    another_try=another_try,
            ):
                yield response
        except Exception as e:
            await self.close()
            raise e

    async def close(self) -> None:
        """
        Close the connection
        """
        await self.chat_hub.close()

    async def reset(self) -> None:
        """
        Reset the conversation
        """
        await self.close()
        self.load_cookie()
        self.chat_hub = _ChatHub(await _Conversation.create(self.cookies))

    def load_cookie(self):
        try:
            with open(self.cookie_path) as f:
                self.cookies = json.load(f)
        except FileNotFoundError as exc:
            raise FileNotFoundError('Cookie file not found') from exc
