"""
Step 4: Google Sheetsに概要文・中カテゴリ・小カテゴリを書き戻し、
        「目次」シートに階層一覧を書き込む
"""

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

TOC_SHEET_NAME = "目次"

# 既存列 A〜D の後ろに追記する新規列
NEW_COLUMNS = ["概要文", "中カテゴリ", "小カテゴリ"]
# E列から追記（0-indexed: 4）
NEW_COL_START_INDEX = 4


def get_sheets_service():
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds)
    return service


def get_sheet_metadata(service) -> dict:
    """シート名 → sheet_id の辞書を返す"""
    spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    return {
        s["properties"]["title"]: s["properties"]["sheetId"]
        for s in spreadsheet.get("sheets", [])
    }


def ensure_toc_sheet(service, sheet_metadata: dict) -> int:
    """目次シートが存在しなければ作成し、sheet_id を返す"""
    if TOC_SHEET_NAME in sheet_metadata:
        return sheet_metadata[TOC_SHEET_NAME]

    logger.info(f"'{TOC_SHEET_NAME}' シートを新規作成します")
    body = {
        "requests": [
            {"addSheet": {"properties": {"title": TOC_SHEET_NAME}}}
        ]
    }
    resp = service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID, body=body
    ).execute()
    new_sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    return new_sheet_id


def col_letter(zero_indexed: int) -> str:
    """0-indexed の列番号をスプレッドシートの列文字に変換（A=0, Z=25, AA=26...）"""
    result = ""
    n = zero_indexed
    while True:
        result = chr(ord("A") + n % 26) + result
        n = n // 26 - 1
        if n < 0:
            break
    return result


def write_columns_to_sheet(service, sheet_name: str, df_sheet: pd.DataFrame):
    """
    対象シートのE列以降に概要文・中カテゴリ・小カテゴリのヘッダーとデータを書き込む。
    既存データと行を対応させるため、A列の動画名で順序を合わせる。
    """
    if df_sheet.empty:
        logger.warning(f"  シート '{sheet_name}' のデータが空のためスキップ")
        return

    # ヘッダー行
    header_values = [NEW_COLUMNS]

    # データ行：動画名の順に合わせて書き込む
    data_values = []
    for _, row in df_sheet.iterrows():
        data_values.append([
            str(row.get("概要文", "")),
            str(row.get("中カテゴリ", "")),
            str(row.get("小カテゴリ", "")),
        ])

    start_col = col_letter(NEW_COL_START_INDEX)
    end_col = col_letter(NEW_COL_START_INDEX + len(NEW_COLUMNS) - 1)
    range_notation = f"'{sheet_name}'!{start_col}1:{end_col}{1 + len(data_values)}"

    all_values = header_values + data_values

    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=range_notation,
        valueInputOption="RAW",
        body={"values": all_values},
    ).execute()

    logger.info(f"  '{sheet_name}' に {len(data_values)} 行書き込みました")


def build_toc_rows(df: pd.DataFrame) -> list[list[str]]:
    """
    大カテゴリ→中カテゴリ→小カテゴリ→動画名 の階層一覧を生成する。
    """
    header = ["大カテゴリ", "中カテゴリ", "小カテゴリ", "動画名", "動画URL", "コンテンツ名", "コンテンツURL"]
    rows = [header]

    grouped = (
        df.sort_values(["大カテゴリ", "中カテゴリ", "小カテゴリ", "動画名"])
        .groupby(["大カテゴリ", "中カテゴリ", "小カテゴリ"], sort=False)
    )

    for (major, mid, small), group in grouped:
        for _, row in group.iterrows():
            rows.append([
                str(major),
                str(mid),
                str(small),
                str(row.get("動画名", "")),
                str(row.get("動画URL", "")),
                str(row.get("コンテンツ名", "")),
                str(row.get("コンテンツURL", "")),
            ])

    return rows


def write_toc_sheet(service, toc_rows: list[list[str]]):
    """目次シートにデータを書き込む"""
    range_notation = f"'{TOC_SHEET_NAME}'!A1"
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=range_notation,
        valueInputOption="RAW",
        body={"values": toc_rows},
    ).execute()
    logger.info(f"'{TOC_SHEET_NAME}' シートに {len(toc_rows) - 1} 行書き込みました（ヘッダー除く）")


def main(input_csv: str = "step3_output.csv") -> pd.DataFrame:
    logger.info(f"{input_csv} を読み込み中...")
    df = pd.read_csv(input_csv, encoding="utf-8-sig")

    logger.info("Google Sheets サービスを初期化中...")
    service = get_sheets_service()

    sheet_metadata = get_sheet_metadata(service)
    logger.info(f"既存シート: {list(sheet_metadata.keys())}")

    # --- 各大カテゴリシートへの書き戻し ---
    for sheet_name, df_sheet in df.groupby("大カテゴリ"):
        if sheet_name == TOC_SHEET_NAME:
            continue
        if sheet_name not in sheet_metadata:
            logger.warning(f"シート '{sheet_name}' がスプレッドシートに存在しません。スキップ。")
            continue
        logger.info(f"シート '{sheet_name}' に書き戻し中...")
        write_columns_to_sheet(service, sheet_name, df_sheet.reset_index(drop=True))

    # --- 目次シートの作成・書き込み ---
    ensure_toc_sheet(service, sheet_metadata)
    toc_rows = build_toc_rows(df)
    write_toc_sheet(service, toc_rows)

    # --- output.csv 出力 ---
    output_path = "output.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logger.info(f"{output_path} に全データを保存しました")

    total = len(df)
    errors = df[df["概要文"].isna() | (df["概要文"] == "")].shape[0]
    logger.info(f"\n=== 処理完了 ===")
    logger.info(f"総件数  : {total} 件")
    logger.info(f"概要文なし（エラー）: {errors} 件")

    return df


if __name__ == "__main__":
    main()
