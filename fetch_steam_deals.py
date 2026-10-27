import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
CURL_BIN = "curl.exe" if os.name == "nt" else "curl"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DATA_OUTPUT_PATH = os.path.join(BASE_DIR, "deals_data.json")


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def fetch_json(url, headers=None):
    """Windows(curl.exe)およびGitHub Actions Linux(curl)の両方で確実にHTTPS JSONを取得する"""
    try:
        cmd = [
            CURL_BIN,
            "-sL",
            "--max-time",
            "15",
            "-b",
            "birthtime=0; mature_content=1; wants_mature_content=1; lastagecheckage=1-0-1990; Steam_Language=japanese",
            "-H",
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
            "-H",
            "Accept-Language: ja,en-US;q=0.9,en;q=0.8",
            url,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
    except Exception:
        pass

    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def strip_html(html_text):
    if not html_text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", html_text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&nbsp;", " ")
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_mostly_english(text):
    if not text:
        return False
    ja_chars = re.findall(r"[\u3040-\u309F\u30A0-\u30FF]", text)
    return len(ja_chars) < 3


def translate_to_japanese(text):
    """英語の説明文を無料API経由で自然な日本語に自動翻訳する"""
    if not text or not is_mostly_english(text):
        return text
    try:
        encoded = urllib.parse.quote(text[:600])
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ja&dt=t&q={encoded}"
        data = fetch_json(url)
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
            translated = "".join([part[0] for part in data[0] if part and part[0]])
            if translated:
                return translated.strip()
    except Exception as e:
        print(f"   [翻訳スキップ]: {e}")
    return text


def fetch_candidate_appids(max_games=16, min_discount=20):
    """Steamの売上上位・人気セール一覧から割引中の人気ゲームIDとレビュースコアを取得する"""
    candidates = {}
    review_meta_map = {}

    search_urls = [
        "https://store.steampowered.com/search/results/?query&start=0&count=35&dynamic_data=&filter=topsellers&specials=1&cc=jp&l=japanese&infinite=1",
        "https://store.steampowered.com/search/results/?query&start=0&count=35&dynamic_data=&specials=1&cc=jp&l=japanese&infinite=1",
    ]
    for s_url in search_urls:
        try:
            search_data = fetch_json(s_url)
            html_results = search_data.get("results_html", "")
            blocks = re.split(r"<a\s+href=\"https://store\.steampowered\.com/app/", html_results)
            for block in blocks[1:]:
                m_id = re.search(r'data-ds-appid="(\d+)"', block)
                if not m_id:
                    continue
                aid = int(m_id.group(1))
                m_tip = re.search(r'data-tooltip-html="([^"]+)"', block)
                if m_tip:
                    tip_text = m_tip.group(1)
                    parts = re.split(r"(?:&lt;br&gt;|<br>)", tip_text)
                    desc_ja = parts[0].strip() if parts else "非常に好評"
                    m_pct = re.search(r"(\d+)%", tip_text)
                    pct = int(m_pct.group(1)) if m_pct else 88
                    review_meta_map[aid] = {"review_desc": desc_ja, "positive_rate": pct}
                if aid not in candidates:
                    candidates[aid] = {"id": aid}
        except Exception as e:
            print(f"[情報] 検索取得スキップ: {e}")

    try:
        url = "https://store.steampowered.com/api/featuredcategories?cc=jp&l=japanese"
        data = fetch_json(url)
        for sec in ["specials", "top_sellers"]:
            for item in data.get(sec, {}).get("items", []):
                appid = item.get("id")
                discount = item.get("discount_percent", 0)
                if appid and discount >= min_discount and item.get("type") == 0:
                    if appid not in candidates:
                        candidates[appid] = item
    except Exception:
        pass

    return list(candidates.keys())[: max_games + 10], review_meta_map


# 日本からの購入をリージョンロック（おま国）する主な国内パブリッシャー・シリーズ一覧
JP_REGION_LOCKED_PUBLISHERS = [
    "capcom",
    "カプコン",
    "biohazard",
    "バイオハザード",
    "resident evil",
    "monster hunter",
    "モンスターハンター",
    "pragmata",
    "プラグマタ",
    "square enix",
    "スクウェア・エニックス",
    "bandai namco",
    "バンダイナムコ",
    "sega",
    "セガ",
    "koei tecmo",
    "コーエーテクモ",
    "konami",
    "コナミ",
    "cygames",
    "granblue fantasy",
    "fromsoftware",
    "フロム・ソフトウェア",
    "atlus",
    "アトラス",
    "spike chunsoft",
    "スパイク・チュンソフト",
    "marvelous",
    "マーベラス",
    "inti creates",
    "インティ・クリエイツ",
    "ガンヴォルト",
    "arcsystemworks",
    "アークシステムワークス",
]


def is_jp_region_locked_publisher(publishers, developers):
    combined = " ".join((publishers or []) + (developers or [])).lower()
    return any(pub in combined for pub in JP_REGION_LOCKED_PUBLISHERS)


def fetch_english_name_and_key_info(appid, default_name, publishers=None, developers=None):
    """CheapShark APIから正確な英語タイトルと、Fanatical(storeID=15)での取扱有無＋おま国判定を行う"""
    jp_locked = is_jp_region_locked_publisher(publishers, developers)
    try:
        url = f"https://www.cheapshark.com/api/1.0/games?steamAppID={appid}"
        cmd = [
            CURL_BIN,
            "-sL",
            "--max-time",
            "8",
            "-H",
            "User-Agent: SteamDealsAnalyzer/1.0",
            url,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode == 0 and res.stdout.strip():
            arr = json.loads(res.stdout)
            if isinstance(arr, list) and len(arr) > 0 and arr[0].get("external"):
                eng_name = arr[0]["external"]
                game_id = arr[0].get("gameID")
                if jp_locked or not game_id:
                    return eng_name, False

                # さらにCheapSharkの店舗別リストからFanatical(storeID="15")に在庫があるか確認
                detail_url = f"https://www.cheapshark.com/api/1.0/games?id={game_id}"
                res_d = subprocess.run(
                    [CURL_BIN, "-sL", "--max-time", "8", "-H", "User-Agent: SteamDealsAnalyzer/1.0", detail_url],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                if res_d.returncode == 0 and res_d.stdout.strip():
                    d_json = json.loads(res_d.stdout)
                    deals_list = d_json.get("deals", [])
                    has_fanatical = any(str(d.get("storeID")) == "15" for d in deals_list)
                    return eng_name, has_fanatical
                return eng_name, False
    except Exception:
        pass

    # フォールバック：Steam英語APIから英語タイトルを取得
    try:
        url_en = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=us&l=english"
        data_en = fetch_json(url_en)
        block = data_en.get(str(appid), {})
        if block.get("success") and block.get("data", {}).get("name"):
            return block["data"]["name"], False
    except Exception:
        pass

    ascii_part = re.sub(r"[^\x00-\x7F]+", " ", default_name).strip()
    if len(ascii_part) >= 3:
        return ascii_part, False
    return default_name, False


def fetch_app_details(appid):
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=jp&l=japanese"
    data = fetch_json(url)
    app_block = data.get(str(appid), {})
    if not app_block.get("success"):
        return None
    return app_block.get("data")


def analyze_reviews_and_game(app_data, discount_pct, initial_price, final_price, positive_rate, total_reviews):
    """ゲームごとの固有情報・数値・評価率にもとづいて、テンプレ感のない簡潔で信頼性の高い分析を生成する"""
    short_desc = strip_html(app_data.get("short_description", ""))
    detailed_desc = strip_html(app_data.get("detailed_description", "") or app_data.get("about_the_game", ""))
    genres = [g.get("description", "") for g in app_data.get("genres", [])]
    categories = [c.get("description", "") for c in app_data.get("categories", [])]

    overview_summary = short_desc
    if not overview_summary and detailed_desc:
        overview_summary = detailed_desc[:160] + "..."
    overview_summary = translate_to_japanese(overview_summary)

    # PC要求スペック抽出
    pc_req = app_data.get("pc_requirements", {})
    rec_html = pc_req.get("recommended") or pc_req.get("minimum") or ""
    rec_text = strip_html(rec_html)
    gpu_match = re.search(r"(GTX\s*\d+|RTX\s*\d+|Radeon\s*RX\s*\d+|Arc\s*A\d+)", rec_text, re.IGNORECASE)
    gpu_hint = gpu_match.group(1) if gpu_match else "ミドルクラスGPU"

    has_controller = any("コントローラ" in c for c in categories)
    is_coop = any(k in " ".join(categories) for k in ["協力", "マルチプレイヤー"])
    is_heavy_3d = any(k in rec_text.upper() for k in ["RTX", "16 GB RAM", "32 GB RAM", "RX 5", "RX 6", "RX 7"])
    supported_ja = "日本語" in app_data.get("supported_languages", "")
    saved_yen = max(0, initial_price - final_price)

    # 1. 具体的な強み・おすすめ理由（上のバッジと重複しない「値引き額＋ゲーム仕様の強み」を抽出）
    pros_points = []
    if discount_pct >= 50:
        pros_points.append(f"定価から¥{saved_yen:,}引き（{discount_pct}%OFF）の大型セール対象")
    else:
        pros_points.append(f"現在¥{saved_yen:,}お得に買える注目セール対象（{discount_pct}%OFF）")

    # categoriesからゲーマーが気にする実用仕様を抽出
    spec_features = []
    cat_str = " ".join(categories)
    if "フルコントローラ" in cat_str:
        spec_features.append("フルコントローラー対応")
    elif "コントローラ" in cat_str:
        spec_features.append("コントローラー対応")
    if "オンライン協力" in cat_str or "協力プレイ" in cat_str:
        spec_features.append("オンライン協力プレイ対応")
    elif "マルチプレイヤー" in cat_str:
        spec_features.append("マルチプレイ対応")
    if "ワークショップ" in cat_str:
        spec_features.append("MOD（Steamワークショップ）対応")
    if "クラウド" in cat_str:
        spec_features.append("Steamクラウドセーブ対応")

    if spec_features:
        pros_points.append("・".join(spec_features[:3]) + "で遊びやすい設計")
    elif positive_rate >= 85:
        pros_points.append(f"{' / '.join(genres[:2])}ジャンル屈指の完成度で長く遊べる1本")
    else:
        pros_points.append(f"{' / '.join(genres[:2])}好きから注目を集める話題タイトル")

    # 2. 購入前のリアルな注意点（本当に注意が必要な時だけconsに入れ、軽い場合はpros側の安心材料にする）
    cons_points = []
    if positive_rate < 50:
        cons_points.append(f"直近評価は低め（好評{positive_rate}%）：PC環境との相性や動作の重さに要注意")
    elif positive_rate < 75:
        cons_points.append(f"評価が分かれる作品（好評{positive_rate}%）：システムや難易度の好みを確認推奨")

    if not supported_ja:
        cons_points.append("公式ストア表記は日本語非対応（購入前に有志日本語化MOD等の確認推奨）")
    elif is_heavy_3d:
        cons_points.append(f"高負荷3D描画あり：快適プレイには「{gpu_hint}」以上のPC環境を推奨")
    else:
        pros_points.append(f"要求スペックは比較的軽め（{gpu_hint}目安）で幅広いPCで快適動作")

    return {
        "overview": overview_summary,
        "pros": pros_points[:3],
        "cons": cons_points[:2],
        "gpu_hint": gpu_hint,
        "has_controller": has_controller,
        "is_heavy_3d": is_heavy_3d,
    }


def translate_review_desc(desc):
    mapping = {
        "Overwhelmingly Positive": "圧倒的に好評",
        "Very Positive": "非常に好評",
        "Positive": "好評",
        "Mostly Positive": "やや好評",
        "Mixed": "賛否両論",
        "Mostly Negative": "やや不評",
        "Negative": "不評",
        "Very Negative": "非常に不評",
        "Overwhelmingly Negative": "圧倒的に不評",
    }
    return mapping.get(desc, desc or "非常に好評")


def calculate_deal_score(discount_pct, positive_rate, total_reviews, has_key_store=False):
    """60点の下限ロックを廃止し、高評価×高割引は90点台、不評作は40点台になるリアルなスコア算出
    ＋日本で公認キー購入可能なタイトルには収益化優遇ボーナスを付与"""
    if positive_rate < 50:
        # やや不評以下は割引率が高くてもスコアを抑える（信頼性確保）
        base = (discount_pct * 0.35) + (positive_rate * 0.65)
    else:
        base = (discount_pct * 0.45) + (positive_rate * 0.50)

    bonus = 0
    if positive_rate >= 80:
        if total_reviews >= 50000:
            bonus = 8
        elif total_reviews >= 10000:
            bonus = 6
        elif total_reviews >= 2000:
            bonus = 3

    # 公認キーショップ取扱あり（おま国でない海外・インディー有力作）を少し優遇
    if has_key_store and positive_rate >= 70:
        bonus += 5

    return min(98, max(35, int(round(base + bonus))))


def build_deals_dataset():
    config = load_config()
    max_games = config.get("max_games", 16)
    min_discount = config.get("min_discount_percent", 20)

    print("1. Steamから現在セール中の注目タイトル一覧を取得中...")
    candidate_ids, review_meta_map = fetch_candidate_appids(max_games=max_games, min_discount=min_discount)
    print(f"   -> 候補タイトル {len(candidate_ids)} 件を検出しました。")

    deals = []
    for idx, appid in enumerate(candidate_ids):
        if len(deals) >= max_games:
            break
        try:
            print(f"2. [{len(deals)+1}/{max_games}] AppID:{appid} の詳細＆日本語化解析中...")
            app_data = fetch_app_details(appid)
            if not app_data or app_data.get("type") != "game":
                continue

            price_info = app_data.get("price_overview")
            if not price_info:
                continue

            discount_pct = price_info.get("discount_percent", 0)
            if discount_pct < min_discount:
                continue

            initial_price = price_info.get("initial", 0) // 100
            final_price = price_info.get("final", 0) // 100

            total_reviews = app_data.get("recommendations", {}).get("total", 500)
            rev_meta = review_meta_map.get(appid, {})
            positive_rate = rev_meta.get("positive_rate", 88)
            review_desc_ja = translate_review_desc(rev_meta.get("review_desc", "非常に好評"))

            ai_analysis = analyze_reviews_and_game(
                app_data, discount_pct, initial_price, final_price, positive_rate, total_reviews
            )
            genres = [g.get("description", "") for g in app_data.get("genres", [])][:4]
            categories = [c.get("description", "") for c in app_data.get("categories", [])][:5]
            screenshots = [s.get("path_thumbnail", "") for s in app_data.get("screenshots", [])[:3]]
            name_ja = app_data.get("name", "")
            publishers = app_data.get("publishers", [])
            developers = app_data.get("developers", [])
            name_en, has_key_store = fetch_english_name_and_key_info(appid, name_ja, publishers, developers)
            deal_score = calculate_deal_score(discount_pct, positive_rate, total_reviews, has_key_store)

            deals.append({
                "appid": appid,
                "name": name_ja,
                "name_en": name_en,
                "publishers": publishers,
                "has_key_store": has_key_store,
                "header_image": app_data.get("header_image", f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"),
                "screenshots": screenshots,
                "discount_percent": discount_pct,
                "initial_price": initial_price,
                "final_price": final_price,
                "initial_formatted": price_info.get("initial_formatted") or f"¥{initial_price:,}",
                "final_formatted": price_info.get("final_formatted") or f"¥{final_price:,}",
                "review_desc": review_desc_ja,
                "positive_rate": positive_rate,
                "total_reviews": total_reviews,
                "deal_score": deal_score,
                "genres": genres,
                "categories": categories,
                "release_date": app_data.get("release_date", {}).get("date", ""),
                "supported_japanese": "日本語" in app_data.get("supported_languages", ""),
                "ai_overview": ai_analysis["overview"],
                "ai_pros": ai_analysis["pros"],
                "ai_cons": ai_analysis["cons"],
                "picked_reviews": [],
                "gpu_hint": ai_analysis["gpu_hint"],
                "has_controller": ai_analysis["has_controller"],
                "is_heavy_3d": ai_analysis["is_heavy_3d"],
                "steam_url": f"https://store.steampowered.com/app/{appid}/",
            })
            time.sleep(0.25)
        except Exception as e:
            print(f"   [スキップ] AppID {appid}: {e}")

    deals.sort(key=lambda x: (x["deal_score"], x["discount_percent"]), reverse=True)

    output = {
        "updated_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
        "total_count": len(deals),
        "affiliate": config.get("affiliate", {}),
        "deals": deals,
    }

    with open(DATA_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n完了！ {len(deals)} 本のセール情報とAIレビュー分析を {DATA_OUTPUT_PATH} に保存しました。")
    return output


if __name__ == "__main__":
    build_deals_dataset()
