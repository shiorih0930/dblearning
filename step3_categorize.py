"""
Step 3: 動画名と概要文をもとにキーワードマッチングで中・小カテゴリを付与する
"""

import logging
import re
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 大カテゴリ → 中カテゴリ → 小カテゴリ のキーワード辞書
# 各エントリ: (中カテゴリ名, 小カテゴリ名, [キーワードリスト])
# ---------------------------------------------------------------------------
CATEGORY_RULES: dict[str, list[tuple[str, str, list[str]]]] = {
    "補綴": [
        ("クラウン", "メタルセラミック", ["メタルセラミック", "PFM", "陶材焼付", "metal ceramic"]),
        ("クラウン", "ジルコニア", ["ジルコニア", "zirconia", "ジルコ"]),
        ("クラウン", "オールセラミック", ["オールセラミック", "all ceramic", "emax", "e.max"]),
        ("クラウン", "クラウン一般", ["クラウン", "crown", "被覆冠"]),
        ("インレー・アンレー", "ゴールドインレー", ["ゴールドインレー", "gold inlay"]),
        ("インレー・アンレー", "セラミックインレー", ["セラミックインレー", "ceramic inlay"]),
        ("インレー・アンレー", "インレー一般", ["インレー", "アンレー", "inlay", "onlay"]),
        ("ブリッジ", "固定性ブリッジ", ["ブリッジ", "bridge", "固定性"]),
        ("義歯（入れ歯）", "総義歯", ["総義歯", "完全義歯", "フルデンチャー", "full denture"]),
        ("義歯（入れ歯）", "部分床義歯", ["部分床義歯", "パーシャルデンチャー", "partial denture", "義歯床"]),
        ("義歯（入れ歯）", "義歯一般", ["義歯", "入れ歯", "denture"]),
        ("インプラント上部構造", "スクリュー固定", ["スクリュー", "screw"]),
        ("インプラント上部構造", "セメント固定", ["セメント固定", "cement"]),
        ("インプラント上部構造", "インプラント補綴一般", ["インプラント上部", "アバットメント", "abutment"]),
        ("咬合・咬合再構成", "垂直的咬合", ["垂直的咬合", "咬合高径", "VDO"]),
        ("咬合・咬合再構成", "咬合一般", ["咬合", "咬み合わせ", "occlusion"]),
    ],
    "保存修復": [
        ("コンポジットレジン", "前歯", ["前歯", "切歯", "犬歯", "anterior"]),
        ("コンポジットレジン", "臼歯", ["臼歯", "小臼歯", "大臼歯", "posterior", "molar", "premolar"]),
        ("コンポジットレジン", "コンポジットレジン一般", ["コンポジットレジン", "CR", "composite resin", "レジン充填"]),
        ("歯質接着", "プライマー・ボンディング", ["プライマー", "ボンディング", "primer", "bonding", "接着材"]),
        ("歯質接着", "エッチング", ["エッチング", "etching", "リン酸"]),
        ("歯質接着", "接着一般", ["接着", "adhesion", "接着システム"]),
        ("虫歯治療", "う蝕検知", ["う蝕検知", "カリエスチェック", "caries detection"]),
        ("虫歯治療", "窩洞形成", ["窩洞", "cavity", "形成"]),
        ("虫歯治療", "虫歯一般", ["虫歯", "カリエス", "う蝕", "caries"]),
        ("ラミネートベニア", "ラミネートベニア", ["ラミネート", "ベニア", "veneer"]),
        ("漂白・ホワイトニング", "オフィスブリーチング", ["オフィスブリーチ", "オフィスホワイトニング"]),
        ("漂白・ホワイトニング", "ホームブリーチング", ["ホームブリーチ", "ホームホワイトニング"]),
        ("漂白・ホワイトニング", "ホワイトニング一般", ["漂白", "ホワイトニング", "whitening", "bleaching"]),
    ],
    "歯周": [
        ("歯周基本治療", "スケーリング", ["スケーリング", "scaling", "歯石除去"]),
        ("歯周基本治療", "ルートプレーニング", ["ルートプレーニング", "root planing"]),
        ("歯周基本治療", "歯周基本治療一般", ["歯周基本治療", "初期治療"]),
        ("歯周外科", "フラップ手術", ["フラップ手術", "歯周フラップ", "flap surgery"]),
        ("歯周外科", "歯周組織再生療法", ["再生療法", "GTR", "エムドゲイン", "骨移植"]),
        ("歯周外科", "歯周外科一般", ["歯周外科", "歯周手術", "periodontal surgery"]),
        ("歯周病診査", "プロービング", ["プロービング", "probing", "歯周ポケット"]),
        ("歯周病診査", "レントゲン診査", ["歯周病 レントゲン", "骨吸収"]),
        ("歯周病診査", "診査一般", ["歯周病診査", "歯周検査"]),
        ("メインテナンス", "SPT", ["SPT", "supportive periodontal therapy"]),
        ("メインテナンス", "メインテナンス一般", ["メインテナンス", "maintenance", "定期検診", "リコール"]),
        ("歯周病一般", "歯周病一般", ["歯周病", "歯周炎", "periodontitis", "歯周"]),
    ],
    "口腔外科": [
        ("抜歯", "智歯抜歯", ["親知らず", "智歯", "wisdom tooth", "水平埋伏"]),
        ("抜歯", "抜歯一般", ["抜歯", "extraction"]),
        ("インプラント外科", "骨造成", ["骨造成", "GBR", "サイナスリフト", "ridge augmentation"]),
        ("インプラント外科", "インプラント埋入", ["インプラント埋入", "フィクスチャー", "fixture", "implant placement"]),
        ("インプラント外科", "インプラント外科一般", ["インプラント外科", "インプラント手術"]),
        ("歯根端切除術", "歯根端切除術", ["歯根端切除", "apicectomy"]),
        ("嚢胞摘出", "嚢胞摘出", ["嚢胞", "cyst"]),
        ("顎関節", "顎関節一般", ["顎関節", "TMJ", "顎関節症"]),
    ],
    "矯正": [
        ("マルチブラケット", "セルフライゲーション", ["セルフライゲーション", "self-ligating"]),
        ("マルチブラケット", "ワイヤー矯正", ["ワイヤー矯正", "マルチブラケット", "ブラケット"]),
        ("マウスピース矯正", "インビザライン", ["インビザライン", "invisalign"]),
        ("マウスピース矯正", "マウスピース矯正一般", ["マウスピース矯正", "アライナー", "aligner"]),
        ("外科矯正", "外科矯正", ["外科矯正", "顎矯正手術"]),
        ("小児矯正", "小児矯正", ["小児矯正", "子ども矯正", "乳歯列", "混合歯列"]),
        ("保定", "保定", ["保定", "リテーナー", "retainer"]),
        ("矯正一般", "矯正一般", ["矯正", "orthodontic"]),
    ],
    "小児歯科": [
        ("乳歯治療", "乳歯う蝕", ["乳歯 虫歯", "乳歯 う蝕", "乳歯 カリエス"]),
        ("乳歯治療", "乳歯抜歯", ["乳歯 抜歯", "乳歯 抜去"]),
        ("乳歯治療", "乳歯治療一般", ["乳歯"]),
        ("予防・フッ素", "フッ素塗布", ["フッ素", "fluoride", "フッ化"]),
        ("予防・フッ素", "シーラント", ["シーラント", "sealant", "小窩裂溝"]),
        ("小児歯科一般", "小児歯科一般", ["小児", "子ども", "こども", "ペディアトリック"]),
    ],
    "予防歯科": [
        ("PMTC", "PMTC", ["PMTC", "professional mechanical tooth cleaning"]),
        ("TBI", "TBI", ["TBI", "歯磨き指導", "ブラッシング指導", "oral hygiene instruction"]),
        ("リスク評価", "カリエスリスク", ["カリエスリスク", "虫歯リスク", "caries risk"]),
        ("リスク評価", "歯周病リスク", ["歯周病リスク", "periodontal risk"]),
        ("予防歯科一般", "予防歯科一般", ["予防歯科", "予防", "prevention"]),
    ],
    "歯内療法": [
        ("根管治療", "根管形成", ["根管形成", "canal shaping", "ファイル", "NiTiファイル"]),
        ("根管治療", "根管洗浄", ["根管洗浄", "irrigation", "次亜塩素酸"]),
        ("根管治療", "根管充填", ["根管充填", "obturation", "ガッタパーチャ"]),
        ("根管治療", "根管治療一般", ["根管治療", "歯内療法", "endodontic", "root canal"]),
        ("歯髄保存", "直接覆髄", ["直接覆髄", "direct pulp capping"]),
        ("歯髄保存", "間接覆髄", ["間接覆髄", "indirect pulp capping"]),
        ("歯髄保存", "歯髄保存一般", ["歯髄保存", "vital pulp therapy"]),
        ("再根管治療", "再根管治療", ["再根管治療", "再治療", "retreatment"]),
    ],
}

UNCATEGORIZED = "未分類"


def normalize(text: str) -> str:
    """テキストを小文字化・全角→半角変換して正規化する。"""
    if not isinstance(text, str):
        return ""
    text = text.lower()
    # 全角英数を半角に変換
    text = text.translate(str.maketrans(
        "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
        "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
        "０１２３４５６７８９",
        "abcdefghijklmnopqrstuvwxyz"
        "abcdefghijklmnopqrstuvwxyz"
        "0123456789",
    ))
    return text


def classify_row(
    title: str,
    summary: str,
    major_category: str,
) -> tuple[str, str]:
    """
    動画名（title）と概要文（summary）からキーワードマッチで中・小カテゴリを返す。
    """
    rules = CATEGORY_RULES.get(major_category, [])
    if not rules:
        return UNCATEGORIZED, UNCATEGORIZED

    combined = normalize(f"{title} {summary}")

    for mid_cat, small_cat, keywords in rules:
        for kw in keywords:
            if normalize(kw) in combined:
                return mid_cat, small_cat

    return UNCATEGORIZED, UNCATEGORIZED


def main(input_csv: str = "step2_output.csv") -> pd.DataFrame:
    logger.info(f"{input_csv} を読み込み中...")
    df = pd.read_csv(input_csv, encoding="utf-8-sig")

    df["中カテゴリ"] = UNCATEGORIZED
    df["小カテゴリ"] = UNCATEGORIZED

    classified = 0
    unclassified = 0

    for idx, row in df.iterrows():
        major = row.get("大カテゴリ", "")
        title = str(row.get("動画名", "")) + " " + str(row.get("コンテンツ名", ""))
        summary = str(row.get("概要文", ""))

        mid, small = classify_row(title, summary, major)
        df.at[idx, "中カテゴリ"] = mid
        df.at[idx, "小カテゴリ"] = small

        if mid == UNCATEGORIZED:
            unclassified += 1
            logger.debug(f"未分類: [{major}] {title[:40]}")
        else:
            classified += 1

    logger.info(f"\n--- カテゴリ付与完了 ---")
    logger.info(f"分類済み: {classified} 件")
    logger.info(f"未分類  : {unclassified} 件")

    df.to_csv("step3_output.csv", index=False, encoding="utf-8-sig")
    logger.info("step3_output.csv に保存しました")

    return df


if __name__ == "__main__":
    main()
