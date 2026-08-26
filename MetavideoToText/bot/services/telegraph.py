"""Publicar en Telegraph para lectura Instant View en Telegram."""



import json

import logging

from pathlib import Path



import httpx



from bot.config import ROOT, TELEGRAPH_ACCESS_TOKEN



logger = logging.getLogger(__name__)



API = "https://api.telegra.ph"

TOKEN_FILE = ROOT / "telegraph_token.txt"





def _load_cached_token() -> str:

    if TELEGRAPH_ACCESS_TOKEN:

        return TELEGRAPH_ACCESS_TOKEN

    if TOKEN_FILE.exists():

        return TOKEN_FILE.read_text(encoding="utf-8").strip()

    return ""





def _save_token(token: str) -> None:

    try:

        TOKEN_FILE.write_text(token, encoding="utf-8")

    except OSError as e:

        logger.warning("No pude guardar token Telegraph: %s", e)





def _create_account() -> str:

    with httpx.Client(timeout=30.0) as client:

        r = client.post(

            f"{API}/createAccount",

            data={

                "short_name": "MetavideoToText",

                "author_name": "MetavideoToText",

            },

        )

    data = r.json()

    if not data.get("ok"):

        raise RuntimeError(data.get("error", "Telegraph createAccount falló"))

    return str(data["result"]["access_token"])





def get_access_token() -> str:

    token = _load_cached_token()

    if token:

        return token

    token = _create_account()

    _save_token(token)

    return token





def publish_page(

    title: str,

    nodes: list[dict],

    *,

    author_name: str = "MetavideoToText",

) -> str | None:

    """Devuelve URL telegra.ph o None si falla."""

    if not nodes:

        return None

    try:

        token = get_access_token()

    except Exception as e:

        logger.warning("Telegraph sin cuenta: %s", e)

        return None



    payload = {

        "access_token": token,

        "title": title[:256],

        "author_name": author_name,

        "content": json.dumps(nodes, ensure_ascii=False),

        "return_content": "false",

    }

    try:

        with httpx.Client(timeout=45.0) as client:

            r = client.post(f"{API}/createPage", data=payload)

        data = r.json()

        if not data.get("ok"):

            logger.warning("Telegraph createPage: %s", data.get("error"))

            return None

        return str(data["result"]["url"])

    except Exception as e:

        logger.warning("Telegraph error: %s", e)

        return None


