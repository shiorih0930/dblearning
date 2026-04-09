"""
「補綴」シートのデータを読み込み、スクレイピング・カテゴリ付与を行い、
「補綴_整理済み」シートに書き出す専用スクリプト。
"""

import logging
import time
import requests
import re
import pandas as pd
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ─── 設定 ──────────────────────────────────────────────────────────────────────
SPREADSHEET_ID = "19BY9awGR26xc6QQzNAczl6ONlzR2ipoz3JCvcx4Smes"
CREDENTIALS_FILE = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SOURCE_SHEET = "補綴"
OUTPUT_SHEET = "補綴_整理済み"

TARGET_DOMAIN = "academy.doctorbook.jp"
REQUEST_INTERVAL = 1.0   # 秒
REQUEST_TIMEOUT = 15     # 秒

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ─── カテゴリルール ─────────────────────────────────────────────────────────────
CATEGORY_RULES: list[tuple[str, str, list[str]]] = [
    ("クラウン", "メタルセラミック",          ["メタルセラミック", "PFM", "陶材焼付", "metal ceramic"]),
    ("クラウン", "ジルコニア",               ["ジルコニア", "zirconia", "ジルコ"]),
    ("クラウン", "オールセラミック",          ["オールセラミック", "all ceramic", "emax", "e.max"]),
    ("クラウン", "クラウン一般",             ["クラウン", "crown", "被覆冠"]),
    ("インレー・アンレー", "ゴールドインレー", ["ゴールドインレー", "gold inlay"]),
    ("インレー・アンレー", "セラミックインレー",["セラミックインレー", "ceramic inlay"]),
    ("インレー・アンレー", "インレー一般",     ["インレー", "アンレー", "inlay", "onlay"]),
    ("ブリッジ", "固定性ブリッジ",            ["ブリッジ", "bridge", "固定性"]),
    ("義歯（入れ歯）", "総義歯",             ["総義歯", "完全義歯", "フルデンチャー", "full denture"]),
    ("義歯（入れ歯）", "部分床義歯",          ["部分床義歯", "パーシャルデンチャー", "partial denture", "義歯床"]),
    ("義歯（入れ歯）", "義歯一般",            ["義歯", "入れ歯", "denture"]),
    ("インプラント上部構造", "スクリュー固定", ["スクリュー", "screw"]),
    ("インプラント上部構造", "セメント固定",   ["セメント固定", "cement"]),
    ("インプラント上部構造", "インプラント補綴一般", ["インプラント上部", "アバットメント", "abutment"]),
    ("咬合・咬合再構成", "垂直的咬合",        ["垂直的咬合", "咬合高径", "VDO"]),
    ("咬合・咬合再構成", "咬合一般",          ["咬合", "咬み合わせ", "occlusion"]),
]
UNCATEGORIZED = "未分類"


# ─── ユーティリティ ─────────────────────────────────────────────────────────────
def get_service():
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def normalize(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = text.translate(str.maketrans(
        "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
        "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
        "０１２３４５６７８９",
        "abcdefghijklmnopqrstuvwxyz"
        "abcdefghijklmnopqrstuvwxyz"
        "0123456789",
    ))
    return text


# ─── Step 1: シート読み込み ──────────────────────────────────────────────────────
def fetch_source_sheet(service) -> pd.DataFrame:
    logger.info(f"'{SOURCE_SHEET}' シートのデータを取得中...")
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range=f"'{SOURCE_SHEET}'!A:D")
        .execute()
    )
    rows = result.get("values", [])
    if not rows:
        raise RuntimeError(f"'{SOURCE_SHEET}' シートが空です")

    COLUMN_NAMES = ["動画名", "動画URL", "コンテンツ名", "コンテンツURL"]
    data_rows = []
    for row in rows:
        if not row or row[0] in COLUMN_NAMES or row[0] == "動画名":
            continue
        padded = row + [""] * (4 - len(row))
        data_rows.append(padded[:4])

    if not data_rows:
        raise RuntimeError(f"'{SOURCE_SHEET}' シートに有効なデータ行がありません")

    df = pd.DataFrame(data_rows, columns=COLUMN_NAMES)
    logger.info(f"  -> {len(df)} 行取得")
    return df


# ─── Step 2: スクレイピング ──────────────────────────────────────────────────────
def scrape_page(url: str) -> str:
    """URLから概要文を取得する。失敗時は空文字を返す。"""
    if not isinstance(url, str) or not url.startswith("http"):
        return ""
    if TARGET_DOMAIN not in url:
        return ""

    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            return meta_desc["content"].strip()

        # 2. og:description
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            return og_desc["content"].strip()

        # 3. 本文先頭パラグラフ
        for tag in ["p", "div"]:
            elem = soup.find(tag)
            if elem:
                text = elem.get_text(strip=True)
                if len(text) > 20:
                    return text[:300]

    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTPエラー ({e.response.status_code}): {url}")
    except requests.exceptions.ConnectionError:
        logger.warning(f"接続エラー: {url}")
    except requests.exceptions.Timeout:
        logger.warning(f"タイムアウト: {url}")
    except Exception as e:
        logger.warning(f"予期しないエラー [{type(e).__name__}]: {url} -> {e}")

    return ""


def scrape_all(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["概要文"] = ""
    success, fail = 0, 0

    for idx, row in df.iterrows():
        url = ""
        for col in ["動画URL", "コンテンツURL"]:
            val = str(row.get(col, ""))
            if val.startswith("http"):
                url = val
                break

        if not url:
            continue

        logger.info(f"[{idx + 1}/{len(df)}] スクレイピング中: {url}")
        desc = scrape_page(url)
        df.at[idx, "概要文"] = desc

        if desc:
            success += 1
        else:
            fail += 1
            logger.warning(f"  -> 概要文取得失敗")

        time.sleep(REQUEST_INTERVAL)

    logger.info(f"スクレイピング完了 - 成功: {success} 件 / 失敗: {fail} 件")
    return df


# ─── Step 3: カテゴリ付与 ────────────────────────────────────────────────────────
def classify(title: str, summary: str) -> tuple[str, str]:
    combined = normalize(f"{title} {summary}")
    for mid_cat, small_cat, keywords in CATEGORY_RULES:
        for kw in keywords:
            if normalize(kw) in combined:
                return mid_cat, small_cat
    return UNCATEGORIZED, UNCATEGORIZED


def categorize_all(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["中カテゴリ"] = UNCATEGORIZED
    df["小カテゴリ"] = UNCATEGORIZED

    classified, unclassified = 0, 0
    for idx, row in df.iterrows():
        title = f"{row.get('動画名', '')} {row.get('コンテンツ名', '')}"
        summary = str(row.get("概要文", ""))
        mid, small = classify(title, summary)
        df.at[idx, "中カテゴリ"] = mid
        df.at[idx, "小カテゴリ"] = small
        if mid == UNCATEGORIZED:
            unclassified += 1
        else:
            classified += 1

    logger.info(f"カテゴリ付与完了 - 分類済み: {classified} 件 / 未分類: {unclassified} 件")
    return df


# ─── Step 4: 「補綴_整理済み」シートへ書き出し ──────────────────────────────────────
def ensure_output_sheet(service) -> int:
    """OUTPUT_SHEET が存在しなければ作成し、sheet_id を返す。存在する場合はクリアして返す。"""
    spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheet_map = {
        s["properties"]["title"]: s["properties"]["sheetId"]
        for s in spreadsheet.get("sheets", [])
    }

    if OUTPUT_SHEET in sheet_map:
        logger.info(f"'{OUTPUT_SHEET}' シートが既に存在します。内容をクリアします。")
        service.spreadsheets().values().clear(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{OUTPUT_SHEET}'",
        ).execute()
        return sheet_map[OUTPUT_SHEET]

    logger.info(f"'{OUTPUT_SHEET}' シートを新規作成します")
    resp = service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": [{"addSheet": {"properties": {"title": OUTPUT_SHEET}}}]},
    ).execute()
    return resp["replies"][0]["addSheet"]["properties"]["sheetId"]


def write_output_sheet(service, df: pd.DataFrame):
    OUTPUT_COLUMNS = ["動画名", "動画URL", "コンテンツ名", "コンテンツURL", "概要文", "中カテゴリ", "小カテゴリ"]

    ensure_output_sheet(service)

    values = [OUTPUT_COLUMNS]
    for _, row in df.iterrows():
        values.append([str(row.get(col, "")) for col in OUTPUT_COLUMNS])

    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{OUTPUT_SHEET}'!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()

    logger.info(f"'{OUTPUT_SHEET}' シートに {len(df)} 行書き込みました（ヘッダー含まず）")


# ─── メイン ──────────────────────────────────────────────────────────────────────
def main():
    service = get_service()

    logger.info("===== Step 1: 補綴シートからデータ取得 =====")
    df = fetch_source_sheet(service)

    logger.info("===== Step 2: URLスクレイピング =====")
    df = scrape_all(df)

    logger.info("===== Step 3: カテゴリ付与 =====")
    df = categorize_all(df)

    logger.info("===== Step 4: 補綴_整理済みシートへ書き出し =====")
    write_output_sheet(service, df)

    # ローカルCSVにも保存
    df.to_csv("hotetsu_output.csv", index=False, encoding="utf-8-sig")
    logger.info("hotetsu_output.csv にも保存しました")

    logger.info("===== 全処理完了 =====")


if __name__ == "__main__":
    main()
