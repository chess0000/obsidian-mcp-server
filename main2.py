import httpx
import asyncio
from mcp.server.fastmcp import FastMCP
from typing import Any

TAG_PREFIX = "%23"

class OmnisearchFastMCPClient:
    def __init__(self, host: str = "127.0.0.0", port: int = 27123):
        """
        MCPを使用してOmnisearchにアクセスするクライアント

        Args:
            host: MCPサーバーのホスト名
            port: MCPサーバーのポート番号
        """
        self.mcp_url = f"http://{host}:{port}"
        self.app = FastMCP(service_name="omnisearch-client")

    async def search(self, query: str) -> list[dict[str, Any]]:
        """
        Omnisearchで検索を実行する

        Args:
            query: 検索クエリ

        Returns:
            検索結果のリスト
        """
        async with httpx.AsyncClient() as client:
            # MCPを通じてOmnisearchのAPIにアクセス
            response = await client.post(
                f"{self.mcp_url}/messages",
                json={
                    "method": "invoke",
                    "args": {
                        "plugin": "omnisearch",
                        "method": "search",
                        "args": [query]
                    }
                }
            )

            if response.status_code == 200:
                result = response.json()
                if "result" in result:
                    return result["result"]
                else:
                    return []
            else:
                raise Exception(f"検索エラー: {response.status_code} - {response.text}")

    async def search_by_tags(self, tags: list[str]) -> list[dict[str, Any]]:
        """
        指定したタグでOmnisearchを検索する

        Args:
            tags: 検索するタグのリスト

        Returns:
            検索結果のリスト
        """
        query = " ".join([f"tag:{tag}" for tag in tags])
        return await self.search(query)

    async def get_file_content(self, file_path: str) -> str:
        """
        MCPを通じてファイルの内容を取得する

        Args:
            file_path: ファイルパス

        Returns:
            ファイルの内容
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.mcp_url}/messages",
                json={
                    "method": "invoke",
                    "args": {
                        "plugin": "app",
                        "method": "vault.read",
                        "args": [file_path]
                    }
                }
            )

            if response.status_code == 200:
                result = response.json()
                if "result" in result:
                    return result["result"]
                else:
                    return ""
            else:
                raise Exception(f"ファイル読み込みエラー: {response.status_code} - {response.text}")

    async def refresh_index(self) -> None:
        """Omnisearchのインデックスを更新する"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.mcp_url}/messages",
                json={
                    "method": "invoke",
                    "args": {
                        "plugin": "omnisearch",
                        "method": "refreshIndex",
                        "args": []
                    }
                }
            )

            if response.status_code != 200:
                raise Exception(f"インデックス更新エラー: {response.status_code} - {response.text}")


async def search_and_extract_content(tags: list[str]) -> list[dict[str, Any]]:
    """
    指定したタグにマッチするファイルを検索し、内容を取得する

    Args:
        tags: 検索するタグのリスト

    Returns:
        検索結果と内容を含むリスト
    """
    client = OmnisearchFastMCPClient()
    results = await client.search_by_tags(tags)

    enriched_results = []
    for result in results:
        path = result["path"]
        content = await client.get_file_content(path)
        enriched_results.append({
            "path": path,
            "basename": result["basename"],
            "score": result["score"],
            "content": content
        })

    return enriched_results


async def main():
    # 特定のタグを持つノートを検索
    tags = ["lang/react"]

    try:
        results = await search_and_extract_content(tags)
        print(f"{len(results)}件の結果が見つかりました")

        for i, result in enumerate(results):
            print(f"\n--- 結果 {i+1}: {result['basename']} (スコア: {result['score']}) ---")
            print(f"パス: {result['path']}")
            print("内容の一部:")
            print(result['content'][:200] + "..." if len(result['content']) > 200 else result['content'])
    except Exception as e:
        print(f"エラーが発生しました: {e}")


# 非同期メイン関数を実行
if __name__ == "__main__":
    asyncio.run(main())