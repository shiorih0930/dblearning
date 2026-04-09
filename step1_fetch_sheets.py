"""
Step 1: Google Sheetsから全シートのデータを取得し、DataFrameにまとめる
"""

import json
import logging
import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

SPREADSHEET_ID = "19BY9awGR26xc6QQzNAczl6ONlzR2ipoz3JCvcx4Smes"
CREDENTIALS_FILE = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

COLUMN_NAMES = ["動画名", "動画URL", "コンテンツ名", "コンテンツURL"]


def get_sheets_service():
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds)
    return service


def get_all_sheet_names(service):
    spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheets = spreadsheet.get("sheets", [])
    return [s["properties"]["title"] for s in sheets]


def fetch_sheet_data(service, sheet_name):
    range_notation = f"'{sheet_name}'!A:D"
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range=range_notation)
        .execute()
    )
    rows = result.get("values", [])
    if not rows:
        logger.warning(f"シート '{sheet_name}' にデータがありません")
        return pd.DataFrame(columns=["大カテゴリ"] + COLUMN_NAMES)

    # 1行目がヘッダーの場合はスキップ、データ行のみ取得
    data_rows = []
    for row in rows:
        # 空行やヘッダー行をスキップ
        if not row or row[0] in COLUMN_NAMES or row[0] == "動画名":
            continue
        # 列数が足りない場合は空文字で補完
        padded = row + [""] * (4 - len(row))
        data_rows.append(padded[:4])

    if not data_rows:
        logger.warning(f"シート '{sheet_name}' に有効なデータ行がありません")
        return pd.DataFrame(columns=["大カテゴリ"] + COLUMN_NAMES)

    df = pd.DataFrame(data_rows, columns=COLUMN_NAMES)
    df.insert(0, "大カテゴリ", sheet_name)
    return df


def main():
    logger.info("Google Sheets サービスを初期化中...")
    service = get_sheets_service()

    logger.info("全シート名を取得中...")
    sheet_names = get_all_sheet_names(service)
    logger.info(f"取得したシート: {sheet_names}")

    all_dfs = []
    for name in sheet_names:
        logger.info(f"シート '{name}' のデータを取得中...")
        df = fetch_sheet_data(service, name)
        if not df.empty:
            all_dfs.append(df)
            logger.info(f"  -> {len(df)} 行取得")

    if not all_dfs:
        logger.error("取得できたデータがありませんでした")
        return pd.DataFrame()

    combined_df = pd.concat(all_dfs, ignore_index=True)
    logger.info(f"全データ合計: {len(combined_df)} 行")

    combined_df.to_csv("step1_output.csv", index=False, encoding="utf-8-sig")
    logger.info("step1_output.csv に保存しました")

    return combined_df


if __name__ == "__main__":
    main()
