"""静态前端 + /api 与 WebSocket 反向代理（公网隧道 / 单端口联机）。"""



from __future__ import annotations



import argparse

import asyncio

import logging

import os

from pathlib import Path



import httpx

import uvicorn

import websockets

from starlette.applications import Starlette

from starlette.exceptions import HTTPException

from starlette.requests import Request

from starlette.responses import FileResponse, Response

from starlette.routing import Mount, Route, WebSocketRoute

from starlette.staticfiles import StaticFiles

from starlette.websockets import WebSocket, WebSocketDisconnect



logger = logging.getLogger(__name__)



BACKEND_BASE = os.environ.get("DEBATE_BACKEND_URL", "http://127.0.0.1:9000").rstrip("/")

_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=120.0, pool=10.0)

_HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length"}





def _backend_ws_base() -> str:

    if BACKEND_BASE.startswith("https://"):

        return "wss://" + BACKEND_BASE[len("https://") :]

    if BACKEND_BASE.startswith("http://"):

        return "ws://" + BACKEND_BASE[len("http://") :]

    return f"ws://{BACKEND_BASE}"





async def proxy_http(request: Request) -> Response:

    path = request.url.path

    query = request.url.query

    url = f"{BACKEND_BASE}{path}"

    if query:

        url = f"{url}?{query}"

    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP}

    body = await request.body()

    try:

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=False, trust_env=False) as client:

            upstream = await client.request(request.method, url, headers=headers, content=body or None)

    except httpx.RequestError as exc:

        logger.warning("http proxy failed %s %s: %s", request.method, url, exc)

        return Response(content=f"upstream unavailable: {exc}", status_code=502)

    out_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in _HOP_BY_HOP}

    return Response(content=upstream.content, status_code=upstream.status_code, headers=out_headers)





async def proxy_websocket(client_ws: WebSocket) -> None:

    await client_ws.accept()

    path = client_ws.url.path

    query_value = client_ws.url.query
    query = query_value.decode() if isinstance(query_value, bytes) else (query_value or "")

    target = f"{_backend_ws_base()}{path}"

    if query:

        target = f"{target}?{query}"

    debate_id = path.rsplit("/", 1)[-1] if "/ws/" in path else ""

    try:

        async with websockets.connect(

            target,

            open_timeout=20,

            close_timeout=5,

            max_size=16 * 1024 * 1024,

            ping_interval=20,

            ping_timeout=20,

        ) as backend_ws:



            async def client_to_backend() -> None:

                try:

                    while True:

                        message = await client_ws.receive()

                        if message["type"] == "websocket.disconnect":

                            break

                        if message.get("text") is not None:

                            await backend_ws.send(message["text"])

                        elif message.get("bytes") is not None:

                            await backend_ws.send(message["bytes"])

                except WebSocketDisconnect:

                    pass

                except Exception as exc:

                    logger.warning("ws client->backend closed debate=%s: %s", debate_id, exc)



            async def backend_to_client() -> None:

                try:

                    async for payload in backend_ws:

                        if isinstance(payload, str):

                            await client_ws.send_text(payload)

                        else:

                            await client_ws.send_bytes(payload)

                except Exception as exc:

                    logger.warning("ws backend->client closed debate=%s: %s", debate_id, exc)



            done, pending = await asyncio.wait(

                [asyncio.create_task(client_to_backend()), asyncio.create_task(backend_to_client())],

                return_when=asyncio.FIRST_COMPLETED,

            )

            for task in pending:

                task.cancel()

            await asyncio.gather(*done, *pending, return_exceptions=True)

    except Exception as exc:

        logger.warning("websocket proxy closed debate=%s target=%s: %s", debate_id, target, exc)

        await client_ws.close()





class SPAStaticFiles(StaticFiles):

    """静态资源 + SPA 回退：/join/session/... 等前端路由返回 index.html。"""



    async def get_response(self, path: str, scope):

        try:

            return await super().get_response(path, scope)

        except HTTPException as exc:

            if exc.status_code != 404:

                raise

            index = Path(self.directory) / "index.html"

            if index.is_file():

                return FileResponse(index)

            raise





def make_app(root: Path) -> Starlette:

    static_root = str(root.resolve())

    routes = [

        WebSocketRoute("/api/debates/ws/{debate_id}", proxy_websocket),

        Route("/api/{rest:path}", proxy_http, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]),

        Route("/health", proxy_http, methods=["GET", "HEAD"]),

        Mount("/", SPAStaticFiles(directory=static_root, html=True), name="static"),

    ]

    return Starlette(routes=routes)





def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument("--port", type=int, default=5173)

    parser.add_argument("--host", type=str, default="0.0.0.0")

    parser.add_argument(

        "--root",

        type=Path,

        default=Path(__file__).resolve().parents[1] / "assets" / "frontend-dist",

    )

    args = parser.parse_args()

    root = args.root.resolve()

    if not (root / "index.html").is_file():

        raise SystemExit(f"缺少 {root / 'index.html'}，请先运行「准备程序.bat」。")



    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = make_app(root)

    print(f"Unified server: http://{args.host}:{args.port}/  -> API {BACKEND_BASE}")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")





if __name__ == "__main__":

    main()


