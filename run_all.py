"""
全ステップを順番に実行するエントリポイント
"""

import logging
from step1_fetch_sheets import main as step1
from step2_scrape_urls import main as step2
from step3_categorize import main as step3
from step4_write_sheets import main as step4

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("===== Step 1: シートからデータ取得 =====")
    step1()

    logger.info("===== Step 2: URLスクレイピング =====")
    step2("step1_output.csv")

    logger.info("===== Step 3: カテゴリ付与 =====")
    step3("step2_output.csv")

    logger.info("===== Step 4: Sheetsへ書き戻し =====")
    step4("step3_output.csv")

    logger.info("===== 全処理完了 =====")
