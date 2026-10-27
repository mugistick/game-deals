import json
import os
import sys
from fetch_steam_deals import (
    build_deals_dataset,
    calculate_deal_score,
    fetch_english_name_and_key_info,
    is_jp_region_locked_publisher,
    load_config,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "deals_data.json")
HTML_OUTPUT_PATH = os.path.join(BASE_DIR, "index.html")


def refresh_existing_data(data):
    """既存のdeals_data.jsonの各ゲームに対して、英語タイトル＋Fanatical在庫＆おま国判定を即時反映する"""
    for g in data.get("deals", []):
        hint_texts = (g.get("publishers") or []) + [
            g.get("name", ""),
            g.get("name_en", ""),
            g.get("ai_overview", ""),
        ]
        if is_jp_region_locked_publisher(hint_texts, []):
            g["has_key_store"] = False
        elif "name_en" not in g or "has_key_store" not in g:
            name_en, has_key = fetch_english_name_and_key_info(
                g.get("appid"), g.get("name", ""), hint_texts, []
            )
            g["name_en"] = name_en
            g["has_key_store"] = has_key
        discount_pct = g.get("discount_percent", 0)
        initial_price = g.get("initial_price", 0)
        final_price = g.get("final_price", 0)
        positive_rate = g.get("positive_rate", 85)
        total_reviews = g.get("total_reviews", 500)
        genres = g.get("genres", [])
        categories = g.get("categories", [])
        gpu_hint = g.get("gpu_hint", "ミドルクラスGPU").replace("推奨", "").strip() or "ミドルクラスGPU"
        g["gpu_hint"] = gpu_hint
        is_heavy_3d = g.get("is_heavy_3d", False)
        supported_ja = g.get("supported_japanese", True)

        g["deal_score"] = calculate_deal_score(
            discount_pct, positive_rate, total_reviews, g.get("has_key_store", False)
        )

        # ゲーム仕様の強み（上のバッジと重複しない具体的なプレイ特徴）
        pros = []
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
            spec_features.append("クラウドセーブ対応")

        if spec_features:
            pros.append("・".join(spec_features[:3]) + "で快適に遊べる設計")
        else:
            pros.append(f"{' / '.join(genres[:2])}好きなら抑えておきたい注目作")

        # 本当に注意が必要な時だけ cons に入れ、動作が軽い場合は pros 側の安心材料にする
        cons = []
        if positive_rate < 50:
            cons.append(f"直近レビューで賛否あり（好評率{positive_rate}%）：PC環境との相性や動作の重さに要注意")
        elif positive_rate < 75:
            cons.append(f"好みが分かれる作品（好評率{positive_rate}%）：ゲームシステムや難易度の事前確認を推奨")

        if not supported_ja:
            cons.append("公式ストア表記は日本語非対応（有志日本語化MOD等の有無を確認推奨）")
        elif is_heavy_3d:
            cons.append(f"高負荷3Dグラフィック：快適プレイには「{gpu_hint}」以上のPC環境を推奨")
        else:
            pros.append(f"要求スペックは軽め（{gpu_hint}目安）で幅広いPCで快適動作")

        g["ai_pros"] = pros[:2]
        g["ai_cons"] = cons[:2]

    data["deals"].sort(key=lambda x: (x["deal_score"], x["discount_percent"]), reverse=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>__SITE_TITLE__</title>
  <meta name="description" content="__SITE_SUBTITLE__" />
  <meta property="og:title" content="__SITE_TITLE__" />
  <meta property="og:description" content="__SITE_SUBTITLE__" />
  <meta property="og:type" content="website" />
  <meta property="og:url" content="https://mugistick.github.io/game-deals/" />
  <meta property="og:image" content="__OG_IMAGE__" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="__SITE_TITLE__" />
  <meta name="twitter:description" content="__SITE_SUBTITLE__" />
  <meta name="twitter:image" content="__OG_IMAGE__" />
  <style>
    :root {
      /* ベースカラー（コントラスト比4.5:1以上を確保したダークテーマ） */
      --bg-main: #0b0f17;
      --bg-card: #151c28;
      --bg-card-top3: #182232;
      --bg-panel: #1d2636;
      --bg-subtle: #253042;
      --border: #334155;
      --border-gold: #f59e0b;
      --text-main: #f8fafc;
      --text-body: #e2e8f0;
      --text-sub: #cbd5e1;
      --text-muted: #94a3b8;

      /* 色相の完全分離：
         1. 緑色は「メイン購入ボタン」専用（他には一切使わない！）
         2. 割引バッジは「ホットオレンジ/レッド」でセール感を演出
         3. 高評価・メリットは「スカイブルー」で清潔感を演出
      */
      --cta-green: #10b981;
      --cta-green-dark: #059669;
      --discount-bg: #ea580c;
      --discount-border: #fb923c;
      --good-blue: #38bdf8;
      --warn-amber: #fbbf24;
      --bad-red: #f87171;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: radial-gradient(circle at top, #17253b 0%, var(--bg-main) 65%);
      color: var(--text-main);
      font-family: "Segoe UI", "Hiragino Kaku Gothic ProN", "Meiryo", sans-serif;
      line-height: 1.55;
      min-height: 100vh;
      padding-bottom: 60px;
    }
    a { color: inherit; text-decoration: none; }

    /* Top Title Area */
    .top-banner {
      background: rgba(11, 15, 23, 0.92);
      padding: 12px 20px 8px;
    }
    .top-banner-inner {
      max-width: 1380px;
      margin: 0 auto;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .title-group {
      display: flex;
      align-items: baseline;
      gap: 12px;
      flex-wrap: wrap;
    }
    .top-banner h1 {
      font-size: 1.28rem;
      font-weight: 900;
      color: #fff;
      letter-spacing: -0.01em;
    }
    .top-banner p {
      color: var(--text-sub);
      font-size: 0.84rem;
    }
    .badge-top {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: var(--bg-subtle);
      border: 1px solid var(--border);
      color: var(--text-sub);
      font-size: 0.78rem;
      font-weight: 600;
      padding: 3px 11px;
      border-radius: 999px;
    }

    /* Slim Sticky Bar (スマホではフィルタ1行のみをスリム固定し、検索・ソートはスクロールで自然に流す) */
    .non-sticky-controls {
      background: #0e1420;
      border-bottom: 1px solid rgba(51, 65, 85, 0.55);
      padding: 8px 20px;
    }
    .non-sticky-inner {
      max-width: 1380px;
      margin: 0 auto;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
    }
    .sticky-bar {
      position: sticky;
      top: 0;
      z-index: 50;
      background: rgba(11, 15, 23, 0.95);
      border-bottom: 1px solid var(--border);
      padding: 7px 20px;
      backdrop-filter: blur(10px);
    }
    .controls-wrap {
      max-width: 1380px;
      margin: 0 auto;
      display: flex;
      align-items: center;
    }
    .filter-group {
      display: flex;
      flex-wrap: nowrap;
      overflow-x: auto;
      gap: 6px;
      width: 100%;
      scrollbar-width: none;
      -ms-overflow-style: none;
    }
    .filter-group::-webkit-scrollbar {
      display: none;
    }
    .filter-btn {
      background: var(--bg-card);
      border: 1px solid var(--border);
      color: var(--text-sub);
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 0.81rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.15s;
      white-space: nowrap;
      flex-shrink: 0;
    }
    .filter-btn:hover, .filter-btn.active {
      background: rgba(56, 189, 248, 0.2);
      border-color: var(--good-blue);
      color: #fff;
    }
    .search-sort-group {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }
    .input-box, .select-box {
      background: var(--bg-subtle);
      border: 1px solid #475569;
      color: #fff;
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 0.83rem;
      outline: none;
    }
    .input-box::placeholder {
      color: var(--text-sub);
    }
    .input-box:focus, .select-box:focus {
      border-color: var(--good-blue);
      box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.2);
    }

    /* Container & Grid */
    .container {
      max-width: 1380px;
      margin: 18px auto;
      padding: 0 18px;
    }
    .deals-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(550px, 1fr));
      gap: 20px;
    }
    @media (max-width: 620px) {
      .deals-grid { grid-template-columns: 1fr; }
    }

    /* Card */
    .deal-card {
      position: relative;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      transition: transform 0.18s, border-color 0.18s, box-shadow 0.18s;
      box-shadow: 0 8px 22px rgba(0,0,0,0.35);
    }
    .deal-card:hover {
      border-color: #64748b;
      box-shadow: 0 12px 30px rgba(0,0,0,0.55);
    }

    /* TOP3 目玉カードの特別ハイライト（視線の起点を作る） */
    .deal-card.top-pick {
      background: linear-gradient(160deg, var(--bg-card-top3) 0%, var(--bg-card) 100%);
      border: 1.5px solid rgba(245, 158, 11, 0.65);
      box-shadow: 0 10px 28px rgba(245, 158, 11, 0.12);
    }
    .top-pick-ribbon {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      background: linear-gradient(90deg, #f59e0b, #d97706);
      color: #fff;
      font-size: 0.76rem;
      font-weight: 900;
      padding: 2px 10px;
      border-radius: 5px;
      width: fit-content;
      margin-bottom: -2px;
      box-shadow: 0 2px 8px rgba(245, 158, 11, 0.35);
    }

    /* Card Top: 左に画像、右にタイトル＆価格塊 */
    .card-top {
      display: flex;
      gap: 15px;
      align-items: flex-start;
    }
    .card-thumb {
      position: relative;
      width: 196px;
      min-width: 196px;
      aspect-ratio: 460 / 215;
      border-radius: 8px;
      overflow: hidden;
      background: linear-gradient(135deg, #1e293b, #0f172a);
      border: 1px solid rgba(255,255,255,0.1);
      flex-shrink: 0;
      display: block;
    }
    @media (max-width: 540px) {
      .card-top { flex-direction: column; }
      .card-thumb { width: 100%; }
    }
    .card-thumb img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
      transition: transform 0.25s;
    }
    .card-thumb:hover img {
      transform: scale(1.04);
    }
    .lang-badge {
      position: absolute;
      bottom: 6px;
      left: 6px;
      background: rgba(11, 15, 23, 0.9);
      color: #f8fafc;
      font-size: 0.74rem;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 4px;
      border: 1px solid rgba(255,255,255,0.2);
    }

    .card-top-info {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 7px;
      min-width: 0;
    }
    .title-price-row {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 10px;
    }
    /* ゲームタイトルを大きく太くして最優先で目に入るように強化 */
    .game-title {
      font-size: 1.18rem;
      font-weight: 900;
      color: #ffffff;
      line-height: 1.3;
      letter-spacing: -0.01em;
    }
    .game-title a:hover {
      color: var(--good-blue);
      text-decoration: underline;
    }

    /* 割引率（オレンジ赤）＋元値（明るいグレー）＋新価格（白太字）の塊 */
    .price-cluster {
      display: flex;
      align-items: center;
      gap: 8px;
      background: rgba(15, 23, 42, 0.75);
      padding: 4px 9px 4px 7px;
      border-radius: 7px;
      border: 1px solid var(--border);
      flex-shrink: 0;
    }
    .discount-badge {
      background: var(--discount-bg);
      border: 1px solid var(--discount-border);
      color: #ffffff;
      font-weight: 900;
      font-size: 0.95rem;
      padding: 2px 8px;
      border-radius: 5px;
      line-height: 1.15;
    }
    .price-stack {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      line-height: 1.15;
    }
    .old-price {
      font-size: 0.76rem;
      color: var(--text-sub);
      text-decoration: line-through;
    }
    .new-price {
      font-size: 1.18rem;
      font-weight: 900;
      color: #ffffff;
    }

    /* Meta Row: 補足テキストも大きめ＆高コントラスト化 */
    .meta-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
    }
    .score-pill {
      background: var(--bg-subtle);
      border: 1px solid var(--border);
      color: var(--text-main);
      font-weight: 700;
      font-size: 0.79rem;
      padding: 2px 9px;
      border-radius: 5px;
    }
    .score-pill strong {
      color: var(--good-blue);
      font-size: 0.85rem;
    }
    /* 評価バッジは緑を使わず、好評＝スカイブルー、賛否＝アンバー、不評＝レッドで主ボタンの緑と分離 */
    .review-pill {
      font-size: 0.79rem;
      font-weight: 700;
      padding: 2px 9px;
      border-radius: 5px;
      background: rgba(56, 189, 248, 0.14);
      color: var(--good-blue);
      border: 1px solid rgba(56, 189, 248, 0.4);
    }
    .review-pill.mixed {
      background: rgba(251, 191, 36, 0.15);
      color: var(--warn-amber);
      border-color: rgba(251, 191, 36, 0.45);
    }
    .review-pill.bad {
      background: rgba(248, 113, 113, 0.16);
      color: var(--bad-red);
      border-color: rgba(248, 113, 113, 0.45);
    }
    .genre-tag {
      font-size: 0.76rem;
      color: var(--text-sub);
      background: var(--bg-subtle);
      padding: 2px 8px;
      border-radius: 4px;
    }

    /* ゲーム紹介＆AI分析エリア（紹介文は省略せず全文表示し、区切りを明確化） */
    .ai-box {
      background: var(--bg-panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 9px;
    }
    .ai-overview {
      color: var(--text-body);
      font-size: 0.87rem;
      line-height: 1.58;
    }
    .ai-points {
      display: flex;
      flex-direction: column;
      gap: 5px;
      border-top: 1px solid rgba(255,255,255,0.1);
      padding-top: 8px;
      font-size: 0.83rem;
    }
    .point-item {
      display: flex;
      align-items: baseline;
      gap: 7px;
      color: var(--text-main);
      line-height: 1.42;
    }
    .point-icon-good {
      color: var(--good-blue);
      font-weight: 900;
      flex-shrink: 0;
    }
    .point-icon-warn {
      color: var(--warn-amber);
      font-weight: 900;
      flex-shrink: 0;
    }
    .point-icon-bad {
      color: var(--bad-red);
      font-weight: 900;
      flex-shrink: 0;
    }

    /* CTA Section: Steam公式（確実なセール先）＋ Amazon（100%ヒット＆24時間クッキー報酬）のツートップ設計 */
    .cta-section {
      margin-top: auto;
      padding-top: 4px;
      display: flex;
      flex-direction: column;
      gap: 7px;
      width: 100%;
      min-width: 0;
    }
    .primary-cta-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      width: 100%;
    }
    @media (max-width: 560px) {
      .primary-cta-row { grid-template-columns: 1fr; }
    }
    .btn-steam-main, .btn-amazon-main {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 5px;
      padding: 9px 10px;
      border-radius: 8px;
      font-size: 0.82rem;
      font-weight: 800;
      text-align: center;
      transition: all 0.15s;
      white-space: nowrap;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .btn-steam-main {
      background: linear-gradient(180deg, var(--cta-green), var(--cta-green-dark));
      color: #ffffff;
      box-shadow: 0 4px 12px rgba(16, 185, 129, 0.28);
    }
    .btn-steam-main:hover {
      filter: brightness(1.1);
      transform: translateY(-1px);
    }
    .btn-amazon-main {
      background: var(--bg-subtle);
      border: 1px solid #f59e0b;
      color: #fbbf24;
    }
    .btn-amazon-main:hover {
      background: rgba(245, 158, 11, 0.18);
      color: #fff;
      transform: translateY(-1px);
    }

    /* ゲーム内容に連動したおすすめ理由ボックス */
    .rec-reason-box {
      background: rgba(245, 158, 11, 0.08);
      border: 1px solid rgba(245, 158, 11, 0.32);
      border-radius: 7px;
      padding: 6px 10px;
      font-size: 0.78rem;
      color: #fde68a;
      line-height: 1.45;
    }
    .rec-reason-box strong {
      color: #fbbf24;
    }

    /* 下段の補足テキストリンク行 */
    .sub-links-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      font-size: 0.77rem;
      color: var(--text-sub);
      padding: 0 2px;
    }
    .context-links {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
    }
    .text-link {
      color: var(--text-sub);
      transition: color 0.15s;
      display: inline-flex;
      align-items: center;
      gap: 3px;
    }
    .text-link:hover {
      color: var(--good-blue);
      text-decoration: underline;
    }
  </style>
</head>
<body>

  <!-- スクロールすると自然に上に隠れるタイトル＆検索・並び替えエリア（スマホで画面を圧迫しない設計） -->
  <div class="top-banner">
    <div class="top-banner-inner">
      <div class="title-group">
        <h1>__SITE_TITLE__</h1>
        <p>__SITE_SUBTITLE__</p>
      </div>
      <div class="badge-top">⚡ 自動収集＆AI解析 ｜ 最終更新: <span id="updatedAt"></span></div>
    </div>
  </div>

  <div class="non-sticky-controls">
    <div class="non-sticky-inner">
      <span style="font-size: 0.78rem; color: var(--text-muted);">🔍 タイトル・ジャンル絞り込み＆並び替え（スクロール時はフィルタのみ上部固定）</span>
      <div class="search-sort-group">
        <input type="text" id="searchInput" class="input-box" placeholder="🔍 ゲーム名・ジャンルで検索..." />
        <select id="sortSelect" class="select-box">
          <option value="score">AIお得度スコア順</option>
          <option value="discount">割引率が高い順</option>
          <option value="price_asc">価格が安い順</option>
          <option value="rating">好評率が高い順</option>
        </select>
      </div>
    </div>
  </div>

  <!-- スクロール時に上部に固定されるスリム1行フィルタバー -->
  <header class="sticky-bar">
    <div class="controls-wrap">
      <div class="filter-group" id="filterGroup">
        <button class="filter-btn active" data-filter="all">すべて表示</button>
        <button class="filter-btn" data-filter="discount50">🔥 50%OFF以上</button>
        <button class="filter-btn" data-filter="discount70">💎 70%OFF以上</button>
        <button class="filter-btn" data-filter="under1000">🪙 ¥1,000以下</button>
        <button class="filter-btn" data-filter="verypos">🏆 非常に好評以上</button>
        <button class="filter-btn" data-filter="ja">🗾 日本語対応</button>
      </div>
    </div>
  </header>

  <main class="container">
    <div class="deals-grid" id="dealsGrid"></div>
  </main>

  <script>
    const DEALS_DATA = __DEALS_JSON__;

    document.getElementById("updatedAt").textContent = DEALS_DATA.updated_at;

    let currentFilter = "all";
    let currentSearch = "";
    let currentSort = "score";

    function buildExternalLinks(game) {
      const aff = DEALS_DATA.affiliate || {};
      const encodedJa = encodeURIComponent(game.name);
      const encodedEn = encodeURIComponent(game.name_en || game.name);

      // 審査通過済みの公認キーショップIDがある場合のみ有効化
      const hasApprovedFanatical = aff.fanatical_ref && !aff.fanatical_ref.startsWith("your-");
      const hasApprovedGmg = aff.gmg_ref && !aff.gmg_ref.startsWith("your-");
      const fanaticalUrl = hasApprovedFanatical
        ? `https://www.fanatical.com/ja/search?search=${encodedEn}&ref=${aff.fanatical_ref}`
        : "";
      const gmgUrl = hasApprovedGmg
        ? `https://www.greenmangaming.com/ja/search?query=${encodedEn}&tap_a=${aff.gmg_ref}`
        : "";

      const amazonControllerUrl = `https://www.amazon.co.jp/s?k=${encodeURIComponent('PC ゲームパッド コントローラー ホールエフェクト')}&tag=${aff.amazon_tag || ''}`;
      const hasCustomBto = aff.bto_pc_link && !aff.bto_pc_link.includes("DUMMY_");
      const btoPcUrl = hasCustomBto
        ? aff.bto_pc_link
        : `https://www.amazon.co.jp/s?k=${encodeURIComponent('ゲーミングPC ' + game.gpu_hint)}&tag=${aff.amazon_tag || ''}`;

      // ゲームのジャンル・特徴・仕様にもとづいて「なぜこの商品がおすすめか」と「最適なAmazon検索リンク」を自動生成
      const combinedText = [
        game.name || "",
        (game.publishers || []).join(" "),
        (game.genres || []).join(" "),
        (game.categories || []).join(" "),
        game.ai_overview || ""
      ].join(" ").toLowerCase();

      const isJpMajorConsole = /capcom|カプコン|biohazard|バイオハザード|monster hunter|モンスターハンター|pragmata|プラグマタ|square enix|スクウェア|bandai|バンダイ|sega|セガ|koei|コーエー|konami|コナミ|cygames|granblue|atlus|アトラス|fromsoftware/.test(combinedText);
      const isCoopOrSoundKey = /協力|マルチプレイヤー|pvp|ホラー|サバイバル|fps|シューティング|dead by daylight|rust|7 days|r\.e\.p\.o|mycopunk/.test(combinedText);
      const isStrategyOrSim = /ストラテジー|シミュレーション|建築|運営|rimworld|civilization/.test(combinedText);

      let recReason = "";
      let recBtnLabel = "";
      let recQuery = "";

      if (isJpMajorConsole) {
        recReason = "💡 <strong>関連アイテム：</strong>家庭用機（PS5/Switch等）のパッケージ版や、公式設定資料集・サントラ・関連グッズも展開されている人気シリーズです";
        recBtnLabel = "📦 Amazonで他機種版・関連グッズを見る ↗";
        recQuery = `${game.name} ゲーム`;
      } else if (isCoopOrSoundKey) {
        recReason = "💡 <strong>このゲームにおすすめ：</strong>敵の足音・方角の聴き分けやフレンドとのVC連携が重要な作品！定位感の良いヘッドセットがあると生存率と没入感が段違いです";
        recBtnLabel = "🎧 足音・VCに最適！定番ヘッドセットを見る ↗";
        recQuery = "ゲーミングヘッドセット PC マイク付き サラウンド";
      } else if (game.is_heavy_3d) {
        recReason = `💡 <strong>このゲームにおすすめ：</strong>高精細3Dマップと大容量データを読み込む重量級タイトル！ロード時間を劇的に短縮する高速NVMe SSDの増設が快適プレイに直結します`;
        recBtnLabel = "💾 ロード爆速化！PC増設用SSDを見る ↗";
        recQuery = "内蔵SSD 1TB 2TB NVMe M.2 PCゲーム";
      } else if (game.has_controller || (game.genres || []).includes("アクション")) {
        recReason = "💡 <strong>このゲームにおすすめ：</strong>素早い回避や直感的なキャラ操作が楽しいアクション作品！キーボードより高耐久スティック搭載のPCゲームパッドが圧倒的に快適です";
        recBtnLabel = "🎮 このゲームが快適になる定番パッドを見る ↗";
        recQuery = "PC ゲームパッド コントローラー ホールエフェクト";
      } else if (isStrategyOrSim) {
        recReason = "💡 <strong>このゲームにおすすめ：</strong>1プレイが数十〜数百時間に及ぶ中毒性の高い作品！長時間マウス操作しても手首が疲れにくい軽量ワイヤレスマウスが相性抜群です";
        recBtnLabel = "🖱️ 長時間でも疲れない軽量マウスを見る ↗";
        recQuery = "ゲーミングマウス 軽量 ワイヤレス サイドボタン";
      } else {
        recReason = "💡 <strong>このゲームにおすすめ：</strong>休日のじっくりプレイに最適な注目作！目の疲れを軽減するモニターライトや快適デスク環境を整えるとさらに集中して楽しめます";
        recBtnLabel = "🖥️ 目の疲れを軽減！モニターライトを見る ↗";
        recQuery = "モニターライト PC デスクライト";
      }

      const amazonRecUrl = `https://www.amazon.co.jp/s?k=${encodeURIComponent(recQuery)}&tag=${aff.amazon_tag || ''}`;

      return { fanaticalUrl, gmgUrl, amazonControllerUrl, amazonRecUrl, recReason, recBtnLabel, btoPcUrl };
    }

    function renderDeals() {
      const grid = document.getElementById("dealsGrid");
      let list = [...DEALS_DATA.deals];

      list = list.filter(g => {
        if (currentFilter === "discount50" && g.discount_percent < 50) return false;
        if (currentFilter === "discount70" && g.discount_percent < 70) return false;
        if (currentFilter === "under1000" && g.final_price > 1000) return false;
        if (currentFilter === "verypos" && g.positive_rate < 80) return false;
        if (currentFilter === "ja" && !g.supported_japanese) return false;

        if (currentSearch) {
          const q = currentSearch.toLowerCase();
          const inName = g.name.toLowerCase().includes(q);
          const inGenre = (g.genres || []).some(tag => tag.toLowerCase().includes(q));
          const inOverview = (g.ai_overview || "").toLowerCase().includes(q);
          if (!inName && !inGenre && !inOverview) return false;
        }
        return true;
      });

      list.sort((a, b) => {
        if (currentSort === "discount") return b.discount_percent - a.discount_percent;
        if (currentSort === "price_asc") return a.final_price - b.final_price;
        if (currentSort === "rating") return b.positive_rate - a.positive_rate;
        return b.deal_score - a.deal_score;
      });

      if (list.length === 0) {
        grid.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding: 40px; color: var(--text-sub);">条件に一致するセール中タイトルがありません。フィルタを変更してみてください。</div>`;
        return;
      }

      grid.innerHTML = list.map((game, idx) => {
        const links = buildExternalLinks(game);
        const fallbackImg = `https://cdn.akamai.steamstatic.com/steam/apps/${game.appid}/header.jpg`;

        // 上位3件（初期表示時）に「本日の目玉」ハイライトを付与して視線の起点を作る
        const isTopPick = (currentFilter === "all" && !currentSearch && currentSort === "score" && idx < 3 && game.deal_score >= 75);
        const topPickClass = isTopPick ? "top-pick" : "";
        const topPickRibbon = isTopPick
          ? `<div class="top-pick-ribbon">👑 本日の目玉セール TOP${idx + 1}（お得度 ${game.deal_score}点）</div>`
          : "";

        // 好評率の3段階カラー分け（75%以上:スカイブルー / 50〜74%:アンバー / 49%以下:レッド）
        let reviewClass = "";
        let warnIconClass = "point-icon-warn";
        if (game.positive_rate < 50) {
          reviewClass = "bad";
          warnIconClass = "point-icon-bad";
        } else if (game.positive_rate < 75) {
          reviewClass = "mixed";
        }

        const jaBadge = game.supported_japanese ? "🗾 日本語対応" : "🌐 英語/他言語";

        const prosHtml = (game.ai_pros || []).map(p =>
          `<div class="point-item"><span class="point-icon-good">✔</span><span>${p}</span></div>`
        ).join("");

        // 注意点（⚠️）は本当に注意がある時だけ表示される
        const consHtml = (game.ai_cons || []).map(c =>
          `<div class="point-item"><span class="${warnIconClass}">⚠️</span><span>${c}</span></div>`
        ).join("");

        // 審査通過済みの公認キーショップ（Fanatical / GMG）のみ表示
        const keyLinksArr = [];
        if (game.has_key_store && links.fanaticalUrl) {
          keyLinksArr.push(`<a class="text-link" style="color:#34d399; font-weight:700;" href="${links.fanaticalUrl}" target="_blank" rel="noopener">🔑 Fanatical(公認キー)で価格比較 ↗</a>`);
        }
        if (game.has_key_store && links.gmgUrl) {
          keyLinksArr.push(`<a class="text-link" style="color:#34d399; font-weight:700;" href="${links.gmgUrl}" target="_blank" rel="noopener">🔑 GMG(公認キー)で価格比較 ↗</a>`);
        }
        const keyStoreLink = keyLinksArr.join(" ");

        const hardwareLink = `<a class="text-link" href="${links.amazonControllerUrl}" target="_blank" rel="noopener">🎮 定番PCゲームパッド(Amazon) ↗</a>`;

        const pcLink = `<a class="text-link" href="${links.btoPcUrl}" target="_blank" rel="noopener">💻 推奨:${game.gpu_hint} 快適PC ↗</a>`;

        const savedAmount = Math.max(0, (game.initial_price || 0) - (game.final_price || 0));
        const steamBtnText = savedAmount > 0
          ? `🎮 Steamで見る（¥${savedAmount.toLocaleString()}得）↗`
          : `🎮 Steam公式でセールを見る ↗`;

        return `
          <article class="deal-card ${topPickClass}">
            ${topPickRibbon}
            <div class="card-top">
              <a class="card-thumb" href="${game.steam_url}" target="_blank" rel="noopener" title="${game.name} のSteamページを開く">
                <img src="${game.header_image}" alt="${game.name}" onerror="if(this.src!=='${fallbackImg}'){this.src='${fallbackImg}';}" />
                <div class="lang-badge">${jaBadge}</div>
              </a>

              <div class="card-top-info">
                <div class="title-price-row">
                  <h2 class="game-title"><a href="${game.steam_url}" target="_blank" rel="noopener">${game.name}</a></h2>

                  <div class="price-cluster">
                    <span class="discount-badge">-${game.discount_percent}%</span>
                    <div class="price-stack">
                      <span class="old-price">${game.initial_formatted}</span>
                      <span class="new-price">${game.final_formatted}</span>
                    </div>
                  </div>
                </div>

                <div class="meta-row">
                  <span class="score-pill">お得度 <strong>${game.deal_score}</strong>点</span>
                  <span class="review-pill ${reviewClass}">${game.review_desc} (${game.positive_rate}% / ${game.total_reviews.toLocaleString()}件)</span>
                </div>

                <div class="meta-row">
                  ${(game.genres || []).slice(0, 4).map(g => `<span class="genre-tag">${g}</span>`).join("")}
                </div>
              </div>
            </div>

            <div class="ai-box">
              <div class="ai-overview">${game.ai_overview}</div>
              <div class="ai-points">
                ${prosHtml}
                ${consHtml}
              </div>
            </div>

            <div class="cta-section">
              <div class="rec-reason-box">${links.recReason}</div>
              <div class="primary-cta-row">
                <a class="btn-steam-main" href="${game.steam_url}" target="_blank" rel="noopener">${steamBtnText}</a>
                <a class="btn-amazon-main" href="${links.amazonRecUrl}" target="_blank" rel="noopener">${links.recBtnLabel}</a>
              </div>
              <div class="sub-links-row">
                <div class="context-links">
                  ${keyStoreLink}
                  ${hardwareLink}
                  ${pcLink}
                </div>
              </div>
            </div>
          </article>
        `;
      }).join("");
    }

    document.querySelectorAll(".filter-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        currentFilter = btn.dataset.filter;
        renderDeals();
      });
    });

    document.getElementById("searchInput").addEventListener("input", e => {
      currentSearch = e.target.value.trim();
      renderDeals();
    });

    document.getElementById("sortSelect").addEventListener("change", e => {
      currentSort = e.target.value;
      renderDeals();
    });

    renderDeals();
  </script>
</body>
</html>
"""

ADMIN_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8" />
  <title>【自分専用】X（Twitter）集客ポスト作成ツール</title>
  <style>
    body { background: #0d1117; color: #f0f6fc; font-family: "Segoe UI", "Meiryo", sans-serif; padding: 24px; max-width: 960px; margin: 0 auto; }
    h1 { font-size: 1.3rem; margin-bottom: 6px; color: #58a6ff; }
    p { font-size: 0.85rem; color: #8b949e; margin-bottom: 18px; }
    .item { background: #161b22; border: 1px solid #2d3644; border-radius: 10px; padding: 14px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; gap: 16px; }
    .info h2 { font-size: 1rem; margin-bottom: 4px; }
    .info div { font-size: 0.82rem; color: #8b949e; }
    .copy-btn { background: #10b981; color: #fff; border: none; border-radius: 8px; padding: 10px 16px; font-weight: 700; cursor: pointer; flex-shrink: 0; }
    .copy-btn:hover { background: #059669; }
    .toast { position: fixed; bottom: 20px; right: 20px; background: #10b981; color: #fff; padding: 10px 18px; border-radius: 8px; font-weight: 700; display: none; }
  </style>
</head>
<body>
  <h1>🐦 【自分専用・非公開ファイル】X（Twitter）集客ポスト作成ツール</h1>
  <p>※このファイル（admin_x_tool.html）はあなたのPC専用の管理ツールです。公開用の index.html からは運営者向けのコードや文字を100%完全に削除してあるので、誰にソースコードを見られても安全です。</p>
  <div id="list"></div>
  <div class="toast" id="toast">📋 X投稿文をコピーしました！</div>
  <script>
    const DEALS_DATA = __DEALS_JSON__;
    const listEl = document.getElementById("list");
    function copyPost(appid) {
      const g = DEALS_DATA.deals.find(x => x.appid === appid);
      if (!g) return;
      const siteUrl = "https://mugistick.github.io/game-deals/";
      const prosText = (g.ai_pros && g.ai_pros[0]) ? "✔ " + g.ai_pros[0] : "";
      const text = `【Steam特選セール🔥 ${g.discount_percent}%OFF】\\n『${g.name}』が ${g.initial_formatted} → ${g.final_formatted}！\\n\\n📊 評価：${g.review_desc}（好評率${g.positive_rate}%）\\n🤖 要約：${g.ai_overview.slice(0, 65)}...\\n${prosText}\\n\\n▼AIレビュー分析＆セール一覧はこちら\\n${siteUrl}\\n#Steamセール #Steam #PCゲーム #PR`;
      navigator.clipboard.writeText(text).then(() => {
        const t = document.getElementById("toast");
        t.style.display = "block";
        setTimeout(() => { t.style.display = "none"; }, 2200);
      });
    }
    listEl.innerHTML = DEALS_DATA.deals.map(g => `
      <div class="item">
        <div class="info">
          <h2>${g.name} （-${g.discount_percent}% / ${g.final_formatted}）</h2>
          <div>評価: ${g.review_desc} (${g.positive_rate}%) ｜ お得度: ${g.deal_score}点</div>
        </div>
        <button class="copy-btn" onclick="copyPost(${g.appid})">📋 X紹介ポストをコピー</button>
      </div>
    `).join("");
  </script>
</body>
</html>
"""


def generate_html():
    config = load_config()
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["affiliate"] = config.get("affiliate", {})
        data = refresh_existing_data(data)
    else:
        data = build_deals_dataset()

    top_img = "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/2050650/header.jpg"
    if data.get("deals") and data["deals"][0].get("header_image"):
        top_img = data["deals"][0]["header_image"]

    html = HTML_TEMPLATE
    html = html.replace("__SITE_TITLE__", config.get("site_title", "Steam神セールAI調査団"))
    html = html.replace("__SITE_SUBTITLE__", config.get("site_subtitle", "毎日自動更新！Steamセール＆日本語レビュー要約"))
    html = html.replace("__OG_IMAGE__", top_img)
    html = html.replace("__DEALS_JSON__", json.dumps(data, ensure_ascii=False))

    with open(HTML_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    admin_path = os.path.join(BASE_DIR, "admin_x_tool.html")
    admin_html = ADMIN_HTML_TEMPLATE.replace("__DEALS_JSON__", json.dumps(data, ensure_ascii=False))
    with open(admin_path, "w", encoding="utf-8") as f:
        f.write(admin_html)

    print(f"[OK] 公開用サイト生成完了: {HTML_OUTPUT_PATH}")
    print(f"[OK] 自分専用Xツール生成完了: {admin_path}")


if __name__ == "__main__":
    if "--html-only" not in sys.argv:
        build_deals_dataset()
    generate_html()
