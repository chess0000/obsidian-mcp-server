import argparse
import httpx
import os
import sys
import json
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field
from typing import Any, Union
from dotenv import load_dotenv

from loguru import logger

logger.remove()
logger.add(sys.stderr, level=os.getenv('FASTMCP_LOG_LEVEL', 'INFO'))

# Obsidian Local REST API 接続設定
load_dotenv()
API_KEY = os.getenv('OBSIDIAN_API_KEY')
BASE_URL_REST_LOCAL = os.getenv('OBSIDIAN_BASE_URL') # HTTP: 27123, HTTPS: 27124

BASE_URL_OMNI_SEARCH = os.getenv('OBSIDIAN_OMNI_SEARCH_BASE_URL') # HTTP: 51361

# MCP サーバーの初期化
mcp = FastMCP(
    'self.obsidian-mcp-server',
    instructions="""
    # Obsidian MCP Server

    このサーバーは、Obsidian Local REST API と通信するためのツールを提供します。

    ## 利用可能なツール

    - **get_status**: サーバーステータスの取得
    - **get_active_note**: 現在アクティブなノートの取得
    - **update_file**: 指定したファイルの内容を更新（または新規作成）
    """,
    dependencies=[
        'httpx',
        'loguru',
        'pydantic'
    ]
)

@mcp.tool()
async def get_status(ctx: Context) -> dict[str, Any]:
    """
    Obsidian Local REST API の基本情報（サーバーステータス）を取得します。

    GET / エンドポイントを呼び出し、認証情報もヘッダーに含めて接続します。
    """
    url = f"{BASE_URL_REST_LOCAL}"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            error_msg = f"Error: Received status code {response.status_code} from Obsidian API."
            logger.error(error_msg)
            await ctx.error(error_msg)
            return {"error": error_msg}
        return json.dumps(response.json(), ensure_ascii=False, indent=2)
    except Exception as e:
        error_msg = f"Failed to get status: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        return {"error": error_msg}

@mcp.tool()
async def omni_search(
    ctx: Context,
    q: str = Field(description="検索クエリ。`q`: 'query'で指定する。"),
) -> list[dict[str, Any]]:
    """
    Omni Search を使用して、Vault 内の全ファイルに対して指定されたクエリを評価し、一致する結果のみを返します。

    クエリ例:
    - tag指定は '#tag_name' その他の用語は 'term' で検索できる。 ',' で区切ることで複数の用語を指定可能。
    - `inbox`ディレクトリ内の`#lang/react`タグと`#prompts`を持つノートを取得する場合:
        - "#prompts,useEffect"
    """
    # Omni Search のエンドポイントを使用
    url = f"{BASE_URL_OMNI_SEARCH}/search"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params={"q": q}, timeout=10)
            print(response.url)
        if response.status_code != 200:
            error_msg = f"Error: Received status code {response.status_code} from Omni Search."
            logger.error(error_msg)
            await ctx.error(error_msg)
            return [{"error": error_msg}]
        return json.dumps(response.json(), ensure_ascii=False, indent=2)
    except Exception as e:
        error_msg = f"Failed to perform Omni Search: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        return [{"error": error_msg}]


# @mcp.tool()
async def search(
    ctx: Context,
    query: str = Field(description="検索クエリ（Dataview DQL または JsonLogic の形式）"),
    content_type: str = Field(
        default="application/vnd.olrapi.dataview.dql+txt",
        description="クエリの Content-Type ヘッダ（例: application/vnd.olrapi.dataview.dql+txt または application/vnd.olrapi.jsonlogic+json）"
    )
) -> list[dict[str, Any]]:
    """
    Vault内の全ファイルに対して、指定されたクエリを評価し、一致する結果のみを返します。

    サポートされるクエリ形式:
    - Dataview DQL: テキスト形式のクエリ（例: TABLE クエリ）
    - JsonLogic: JSON形式のクエリ（例: フロントマターの値でフィルタリング）

    クエリ例:
    - `inbox`ディレクトリ内の`#lang/react`タグと`#prompts`を持つノートを取得する場合:
        - Dataview DQL: TABLE FROM "inbox" WHERE contains(file.tags, "#lang/react") AND contains(file.tags, "#prompts") SORT rating DESC
    """
    url = f"{BASE_URL_REST_LOCAL}/search"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": content_type,
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, data=query, timeout=10)
        if response.status_code != 200:
            error_msg = f"Error: Received status code {response.status_code} from /search/ endpoint."
            logger.error(error_msg)
            await ctx.error(error_msg)
            return [{"error": error_msg}]
        return json.dumps(response.json(), ensure_ascii=False, indent=2)
    except Exception as e:
        error_msg = f"Failed to perform search: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        return [{"error": error_msg}]

@mcp.tool()
async def search_and_find_matching_file(
    ctx: Context,
    query: str = Field(description="検索クエリ（Dataview DQL または JsonLogic）"),
    match_keyword: str = Field(description="ファイル内で探したいキーワード"),
    content_type: str = Field(
        default="application/vnd.olrapi.dataview.dql+txt",
        description="クエリの Content-Type ヘッダー"
    ),
    as_json: bool = Field(
        default=False,
        description="ファイル内容を JSON で取得する場合は True、Markdown の場合は False"
    )
) -> Union[dict[str, Any], str]:
    """
    search の結果から複数ファイルを取得し、指定されたキーワードを含む最初のファイル内容を返します。

    サポートされるクエリ形式:
    - Dataview DQL: テキスト形式のクエリ（例: TABLE クエリ）
    - JsonLogic: JSON形式のクエリ（例: フロントマターの値でフィルタリング）

    クエリ例:
    - `inbox`ディレクトリ内の`#lang/react`タグと`#prompts`を持つノートを取得する場合:
        - Dataview DQL: TABLE FROM "inbox" WHERE contains(file.tags, "#lang/react") AND contains(file.tags, "#prompts") SORT rating DESC
    """
    search_url = f"{BASE_URL_REST_LOCAL}/search"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": content_type,
    }

    try:
        async with httpx.AsyncClient() as client:
            search_response = await client.post(search_url, headers=headers, data=query, timeout=10)
        if search_response.status_code != 200:
            error_msg = f"Search error: status code {search_response.status_code}"
            logger.error(error_msg)
            await ctx.error(error_msg)
            return {"error": error_msg}

        results = search_response.json()
        if not results:
            return {"message": "検索結果がありませんでした。"}

        # 各ファイルを1つずつ取得して条件チェック
        async with httpx.AsyncClient() as client:
            for item in results:
                filename = item.get("file", {}).get("path")
                if not filename:
                    continue

                file_url = f"{BASE_URL_REST_LOCAL}/vault/{filename}"
                file_headers = {
                    "Authorization": f"Bearer {API_KEY}",
                    "Accept": "application/vnd.olrapi.note+json" if as_json else "text/markdown"
                }

                file_response = await client.get(file_url, headers=file_headers, timeout=10)
                if file_response.status_code != 200:
                    logger.warning(f"ファイル取得失敗: {filename}")
                    continue

                content = file_response.json() if as_json else file_response.text
                if match_keyword in (str(content) if as_json else content):
                    return {
                        "filename": filename,
                        "content": content
                    }

        return {"message": f"指定されたキーワード '{match_keyword}' を含むファイルは見つかりませんでした。"}

    except Exception as e:
        error_msg = f"search_and_find_matching_file エラー: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        return {"error": error_msg}

@mcp.tool()
async def get_active_note(
    ctx: Context,
    as_json: bool = Field(
        default=False,
        description="ノートを JSON 形式で返す場合は True、Markdown 形式の場合は False"
    )
) -> Union[dict[str, Any], str]:
    """
    現在 Obsidian で開かれているアクティブなノートの内容を取得します。

    as_json が True の場合、JSON 形式（タグやメタデータ付き）のノート情報を返します。
    """
    url = f"{BASE_URL_REST_LOCAL}/active"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    if as_json:
        headers["Accept"] = "application/vnd.olrapi.note+json"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            error_msg = f"Error: Received status code {response.status_code} when retrieving active note."
            logger.error(error_msg)
            await ctx.error(error_msg)
            return {"error": error_msg}
        if as_json:
            return response.json()
        else:
            return response.text
    except Exception as e:
        error_msg = f"Failed to retrieve active note: {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        return {"error": error_msg}


@mcp.tool()
async def get_file(
    ctx: Context,
    filename: str = Field(description="Vault ルートからの相対パス（例: 'dirname/example.md'）"),
    as_json: bool = Field(
        default=False,
        description="ノートを JSON 形式で返す場合は True、Markdown 形式の場合は False"
    )
) -> Union[dict[str, Any], str]:
    """
    指定したファイルの内容を取得します。

    GET /vault/{filename} エンドポイントを呼び出し、ファイルの内容を取得します。
    """
    url = f"{BASE_URL_REST_LOCAL}/vault/{filename}"
    logger.debug(f"Retrieving file from URL: {url}")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/vnd.olrapi.note+json" if as_json else "text/markdown",
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            error_msg = f"Error: Received status code {response.status_code} when retrieving file.\n url: {url}"
            logger.error(error_msg)
            await ctx.error(error_msg)
            return {"error": error_msg}
        if as_json:
            return response.json()
        else:
            return response.text
    except Exception as e:
        error_msg = f"Failed to retrieve file '{filename}': {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        return {"error": error_msg}


@mcp.tool()
async def update_file(
    ctx: Context,
    filename: str = Field(description="Vault ルートからの相対パス（例: 'example.md'）"),
    content: str = Field(description="ファイルの内容（Markdown 形式）")
) -> str:
    """
    指定したファイルの内容を更新または新規作成します。

    PUT /vault/{filename} エンドポイントを呼び出し、Markdown コンテンツを送信します。
    """
    url = f"{BASE_URL_REST_LOCAL}/vault/{filename}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "text/markdown",
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(url, headers=headers, data=content, timeout=10)
        if response.status_code not in (200, 204):
            error_msg = f"Error: Received status code {response.status_code} when updating file."
            logger.error(error_msg)
            await ctx.error(error_msg)
            return error_msg
        return f"File '{filename}' updated successfully."
    except Exception as e:
        error_msg = f"Failed to update file '{filename}': {str(e)}"
        logger.error(error_msg)
        await ctx.error(error_msg)
        return error_msg

def main():
    """CLI 引数に対応して MCP サーバーを起動します。"""
    parser = argparse.ArgumentParser(
        description='Obsidian MCP Server using python-mcp-sdk'
    )
    parser.add_argument('--sse', action='store_true', help='SSE トランスポートを使用する場合')
    parser.add_argument('--port', type=int, default=8888, help='サーバーを起動するポート番号')
    args = parser.parse_args()

    logger.info('Starting Obsidian MCP Server')
    mcp.settings.port = args.port

    if args.sse:
        logger.info(f'Using SSE transport on port {args.port}')
        mcp.run(transport='sse')
    else:
        logger.info('Using standard stdio transport')
        mcp.run()

if __name__ == '__main__':
    main()