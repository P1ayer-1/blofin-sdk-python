"""aiohttp transport for the BloFin REST API.

Same signing and the same return/raise contract as `Client`, but `get` and
`post` are coroutines. `TradingAPI(AsyncClient(...))` therefore works
unchanged: each of its methods returns `self._client.post(...)`, which is now
an awaitable.

    client = AsyncClient(apiKey=..., apiSecret=..., passphrase=..., isDemo=True)
    trading = TradingAPI(client)
    await trading.placeOrder(...)
    await client.close()

The session is created on first use, inside the running event loop, and must
be closed with `close()` from that same loop.
"""

import json
from typing import Dict, Optional
from urllib.parse import urlencode

import aiohttp
from yarl import URL

from blofin.client import BaseClient
from blofin.exceptions import BlofinAPIException


class AsyncClient(BaseClient):
    """BloFin API HTTP client on aiohttp."""

    def __init__(
        self,
        apiKey: Optional[str] = None,
        apiSecret: Optional[str] = None,
        passphrase: Optional[str] = None,
        useServerTime: bool = False,
        baseUrl: str = "https://openapi.blofin.com",
        timeout: float = 30.0,
        proxy: Optional[str] = None,
        isDemo: bool = False,
    ):
        if isDemo:
            baseUrl = "https://demo-trading-openapi.blofin.com"
        super().__init__(
            apiKey=apiKey,
            apiSecret=apiSecret,
            passphrase=passphrase,
            useServerTime=useServerTime,
            baseUrl=baseUrl,
            timeout=timeout,
        )
        self.session.close()        # BaseClient's requests session is not used here
        self.session = None
        self.proxy = proxy
        self.is_demo = isDemo

    def _session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(
                limit=0,
                ttl_dns_cache=300,
                keepalive_timeout=60,
            )
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
        return self.session

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        sign: bool = True
    ) -> Dict:
        method = method.upper()
        query = ('?' + urlencode(params)) if params else ''
        # Serialize once and send those exact bytes: the signature covers the
        # body string, so it must not be re-serialized by the transport.
        body = json.dumps(data) if data else None

        headers = {'Content-Type': 'application/json'}
        if sign:
            if not all([self.API_KEY, self.API_SECRET, self.PASSPHRASE]):
                raise BlofinAPIException(
                    message="API key, secret and passphrase are required for authenticated endpoints",
                    status_code=None,
                    response=None
                )
            timestamp = self._get_timestamp()
            nonce = self._get_nonce()
            signature = self._sign_request(timestamp, method, path + query, body, nonce)
            headers.update({
                'ACCESS-KEY': self.API_KEY,
                'ACCESS-SIGN': signature,
                'ACCESS-TIMESTAMP': timestamp,
                'ACCESS-NONCE': nonce,
                'ACCESS-PASSPHRASE': self.PASSPHRASE
            })

        try:
            # encoded=True: the query is already percent-encoded and signed as
            # written; yarl must not requote it.
            async with self._session().request(
                method,
                URL(self.base_url + path + query, encoded=True),
                headers=headers,
                data=body,
                proxy=self.proxy,
            ) as response:
                text = await response.text()
                status = response.status
        except (aiohttp.ClientError, TimeoutError) as e:
            raise BlofinAPIException(
                message=f"Request failed: {e!r}",
                status_code=None,
                response=None
            )
        try:
            response_data = json.loads(text)
        except ValueError as e:
            raise BlofinAPIException(
                message=f"Invalid JSON response: {e}",
                status_code=status,
                response=text
            )
        if status != 200:
            raise BlofinAPIException(
                message=f"API request failed with status code {status}",
                status_code=status,
                response=response_data
            )
        return response_data

    async def get(self, path: str, params: Optional[Dict] = None, sign: bool = True) -> Dict:
        return await self._request('GET', path, params=params, sign=sign)

    async def post(self, path: str, data: Optional[Dict] = None, sign: bool = True) -> Dict:
        return await self._request('POST', path, data=data, sign=sign)

    async def close(self) -> None:
        if self.session is not None and not self.session.closed:
            await self.session.close()
