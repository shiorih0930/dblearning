"""
Step 2: academy.doctorbook.jp の各URLにアクセスし、タイトル・概要文を取得する
"""

import logging
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

REQUEST_INTERVAL = 1.0  # 秒
REQUEST_TIMEOUT = 15    # 秒
TARGET_DOMAIN = "academy.doctorbook.jp"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def scrape_page(url: str) -> dict:
    """URLからタイトルと概要文を取得する。失敗時は空文字を返す。"""
    result = {"タイトル": "", "概要文": ""}

    if not isinstance(url, str) or not url.startswith("http"):
        return result
    if TARGET_DOMAIN not in url:
        logger.debug(f"対象外ドメインのためスキップ: {url}")
        return result

    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # タイトル取得
        title_tag = soup.find("title")
        if title_tag:
            result["タイトル"] = title_tag.get_text(strip=True)

        # 概要文取得（優先順位順に試みる）
        description = ""

        # 1. meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            description = meta_desc["content"].strip()

        # 2. og:description
        if not description:
            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                description = og_desc["content"].strip()

        # 3. ページ本文の先頭パラグラフ
        if not description:
            for tag in ["p", "div"]:
                elem = soup.find(tag)
                if elem:
                    text = elem.get_text(strip=True)
                    if len(text) > 20:
                        description = text[:300]
                        break

        result["概要文"] = description

    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTPエラー ({e.response.status_code}): {url}")
    except requests.exceptions.ConnectionError:
        logger.warning(f"接続エラー: {url}")
    except requests.exceptions.Timeout:
        logger.warning(f"タイムアウト: {url}")
    except Exception as e:
        logger.warning(f"予期しないエラー [{type(e).__name__}]: {url} -> {e}")

    return result


def main(input_csv: str = "step1_output.csv") -> pd.DataFrame:
    logger.info(f"{input_csv} を読み込み中...")
    df = pd.read_csv(input_csv, encoding="utf-8-sig")

    df["タイトル"] = ""
    df["概要文"] = ""

    error_count = 0
    success_count = 0

    url_columns = ["動画URL", "コンテンツURL"]

    for idx, row in df.iterrows():
        # 動画URLを優先、なければコンテンツURLを使用
        url = ""
        for col in url_columns:
            if col in row and isinstance(row[col], str) and row[col].startswith("http"):
                url = row[col]
                break

        if not url:
            logger.debug(f"行 {idx}: URLなし、スキップ")
            continue

        logger.info(f"[{idx + 1}/{len(df)}] スクレイピング中: {url}")
        scraped = scrape_page(url)

        if scraped["タイトル"] or scraped["概要文"]:
            df.at[idx, "タイトル"] = scraped["タイトル"]
            df.at[idx, "概要文"] = scraped["概要文"]
            success_count += 1
        else:
            error_count += 1
            logger.warning(f"  -> データ取得失敗: {url}")

        time.sleep(REQUEST_INTERVAL)

    logger.info(f"\n--- スクレイピング完了 ---")
    logger.info(f"成功: {success_count} 件")
    logger.info(f"失敗: {error_count} 件")

    df.to_csv("step2_output.csv", index=False, encoding="utf-8-sig")
    logger.info("step2_output.csv に保存しました")

    return df


if __name__ == "__main__":
    main()
