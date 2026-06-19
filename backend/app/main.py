"""
FastAPI 主入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from contextlib import asynccontextmanager
import os, time, threading, json, logging
from app.config import API_HOST, API_PORT
from app.database import init_db
from app.db_helper import db_cursor

logger = logging.getLogger(__name__)

FRONTEND_DIR = r"D:\小黄的助手\足彩预测系统\frontend"

# 预测缓存（按 match_id 缓存，5分钟过期）
_pred_cache = {}
_pred_cache_lock = threading.Lock()
PRED_CACHE_TTL = 300  # 5分钟

# 全局预测器（避免每次请求都初始化，加载6.6MB训练数据）
_global_predictor = None
_global_predictor_lock = threading.Lock()


def _get_predictor():
    """获取全局缓存的 PredictionService 实例"""
    global _global_predictor
    if _global_predictor is not None:
        return _global_predictor
    with _global_predictor_lock:
        if _global_predictor is not None:
            return _global_predictor
        from services.prediction_service import PredictionService
        _global_predictor = PredictionService()
        logger.info("Global PredictionService initialized (HybridPredictor + models loaded)")
        return _global_predictor


def _get_cached_prediction(match_id):
    with _pred_cache_lock:
        entry = _pred_cache.get(match_id)
        if entry and time.time() - entry['ts'] < PRED_CACHE_TTL:
            return entry['data']
    return None


def _set_cached_prediction(match_id, data):
    with _pred_cache_lock:
        _pred_cache[match_id] = {'ts': time.time(), 'data': data}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        from services.auto_data_service import start_background_updater
        start_background_updater()
    except Exception as e:
        logger.warning(f"Auto data updater failed to start: {e}")
    try:
        from tasks.scheduler import init_tasks
        init_tasks()
        logger.info("APScheduler tasks started")
    except Exception as e:
        logger.warning(f"APScheduler tasks failed to start: {e}")
    # 后台预热全局预测器（不阻塞启动，加载完成后预测立即可用）
    def _warm_predictor():
        try:
            _get_predictor()
            logger.info("Predictor warm-up complete")
        except Exception as e:
            logger.warning(f"Predictor warm-up failed: {e}")
    threading.Thread(target=_warm_predictor, daemon=True).start()
    yield


app = FastAPI(title="FootballPredict Pro API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

from app.api import matches, predictions, odds, statistics, history, data, predict, live
app.include_router(matches.router, prefix="/api/matches", tags=["比赛"])
app.include_router(predictions.router, prefix="/api/predictions", tags=["预测"])
app.include_router(odds.router, prefix="/api/odds", tags=["赔率"])
app.include_router(statistics.router, prefix="/api/statistics", tags=["统计"])
app.include_router(history.router, prefix="/api/history", tags=["历史记录"])
app.include_router(data.router, prefix="/api/data", tags=["数据更新"])
app.include_router(predict.router, prefix="/api/predict", tags=["综合预测"])
app.include_router(live.router, prefix="/api/live", tags=["实时比分"])


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


def _fetch_upcoming_matches():
    """从DB获取即将开始的比赛"""
    today = datetime.now().strftime('%Y-%m-%d')
    three_hours_ago = (datetime.now() - timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')
    three_days_later = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')
    with db_cursor() as cur:
        cur.execute("""SELECT match_id, league_name, home_team_name, away_team_name, match_time
            FROM matches WHERE match_time >= %s AND match_time < %s AND match_time > %s ORDER BY match_time LIMIT 30""",
            (today, three_days_later + ' 23:59:59', three_hours_ago))
        return cur.fetchall()


def _fetch_history_stats() -> dict:
    """获取历史预测统计"""
    try:
        with db_cursor() as cur:
            cur.execute("SELECT COUNT(*), SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END), SUM(CASE WHEN is_correct=2 THEN 1 ELSE 0 END) FROM prediction_history")
            ht, hc, hw = cur.fetchone()
            cur.execute("SELECT COUNT(*), SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END) FROM prediction_history WHERE match_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) AND is_correct IN (1,2)")
            r7t, r7c = cur.fetchone()
            ht, hc, hw = int(ht or 0), int(hc or 0), int(hw or 0)
            r7t_val = int(r7t or 1)
            r7c_val = int(r7c or 0)
            return {
                'total': ht, 'correct': hc, 'wrong': hw,
                'accuracy': round(hc / (hc + hw) * 100, 1) if (hc + hw) else 0,
                'recent_7d': round(r7c_val / r7t_val * 100, 1),
            }
    except Exception as e:
        logger.warning(f"Failed to fetch history stats: {e}")
        return {'total': 0, 'correct': 0, 'wrong': 0, 'accuracy': 0, 'recent_7d': 0}


def _fetch_history_rows(limit: int = 50) -> list:
    """获取历史预测记录"""
    try:
        with db_cursor() as cur:
            cur.execute('SELECT match_id, league, home_team, away_team, match_date, prediction_result, prediction_name, confidence, actual_result, actual_score, is_correct FROM prediction_history ORDER BY match_date DESC, id DESC LIMIT %s', (limit,))
            return cur.fetchall()
    except Exception as e:
        logger.warning(f"Failed to fetch history rows: {e}")
        return []


def _fetch_prediction_cache(match_id: str):
    """从DB读取预测缓存"""
    with db_cursor() as cur:
        cur.execute("SELECT id, prediction_result, prediction_name, confidence, detail_json, predicted_score, created_at FROM prediction_history WHERE match_id=%s ORDER BY id DESC LIMIT 1", (match_id,))
        return cur.fetchone()


def _check_odds_changed(match_id: str) -> bool:
    """检查赔率是否发生变化"""
    with db_cursor() as cur:
        cur.execute("SELECT home_odds, draw_odds, away_odds FROM odds WHERE match_id=%s AND bookmaker=%s ORDER BY created_at DESC LIMIT 2", (match_id, 'sporttery_cn'))
        rows = cur.fetchall()
        if len(rows) >= 2:
            if abs(float(rows[0][0]) - float(rows[1][0])) >= 0.01 or \
               abs(float(rows[0][1]) - float(rows[1][1])) >= 0.01 or \
               abs(float(rows[0][2]) - float(rows[1][2])) >= 0.01:
                return True
    return False


def _save_prediction_bg(mid, ht, at, lg, pred):
    """后台保存预测到DB"""
    try:
        p = pred['prediction']
        dc = json.dumps({
            'probabilities': p.get('probabilities', {}),
            'odds_analysis': pred.get('odds_analysis', {}),
            'team_analysis': pred.get('team_analysis', {}),
            'h2h_analysis': pred.get('h2h_analysis', {}),
            'platform_predictions': pred.get('platform_predictions', []),
            'platform_votes': pred.get('platform_votes', {}),
            'analysis_summary': pred.get('analysis_summary', []),
        }, ensure_ascii=False)
        with db_cursor() as cur:
            cur.execute("""INSERT INTO prediction_history (match_id, match_date, league, home_team, away_team, prediction_result, prediction_name, confidence, predicted_score, detail_json, is_correct)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0)
                ON DUPLICATE KEY UPDATE prediction_result=VALUES(prediction_result), prediction_name=VALUES(prediction_name), confidence=VALUES(confidence), predicted_score=VALUES(predicted_score), detail_json=VALUES(detail_json)""",
                (mid, datetime.now().strftime('%Y-%m-%d'), lg, ht, at, p['prediction'], p['prediction_name'], p['confidence'], p.get('predicted_score', ''), dc))
    except Exception as e:
        logger.warning(f"Background save failed for {mid}: {e}")


def _bg_refresh_sporttery():
    """后台刷新体彩数据"""
    try:
        import urllib.request
        API = 'https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry?channel=c'
        hdrs = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://m.sporttery.cn/mjc/jsq/zqspf/'}
        req = urllib.request.Request(API, headers=hdrs)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        with db_cursor() as cur:
            for info in data.get('value', {}).get('matchInfoList', []):
                for m in info.get('subMatchList', []):
                    h = m.get('homeTeamAllName', '')
                    a = m.get('awayTeamAllName', '')
                    mn = m.get('matchNumStr', '')
                    md = m.get('matchDate', '')
                    mt = m.get('matchTime', '00:00:00')
                    if not h or not a or not mn:
                        continue
                    mid = f'JCZQ_{mn}_{md}' if md else f'JCZQ_{mn}'
                    lg = m.get('leagueAllName', m.get('leagueName', '国际赛'))
                    full_time = f'{md} {mt}' if md else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    ho = do = ao = ''
                    for pool in m.get('oddsList', []):
                        if pool.get('poolCode') == 'HAD':
                            ho, do, ao = pool.get('h', ''), pool.get('d', ''), pool.get('a', '')
                            break
                    if ho and do and ao:
                        cur.execute('INSERT INTO odds (match_id,bookmaker,home_odds,draw_odds,away_odds,is_opening) VALUES (%s,%s,%s,%s,%s,0) ON DUPLICATE KEY UPDATE home_odds=VALUES(home_odds), draw_odds=VALUES(draw_odds), away_odds=VALUES(away_odds)',
                                    (mid, 'sporttery_cn', ho, do, ao))
                    cur.execute('INSERT INTO matches (match_id,league_name,home_team_name,away_team_name,match_time) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE league_name=VALUES(league_name),match_time=VALUES(match_time)',
                                (mid, lg, h, a, full_time))
    except Exception as e:
        logger.warning(f"Sporttery refresh failed: {e}")


def _render_match_card(p: dict) -> str:
    """渲染单个比赛预测卡片HTML"""
    pn = {'home': '主胜', 'draw': '平局', 'away': '客胜'}.get(p.get('prediction'), str(p.get('prediction', '')))
    conf = p.get('confidence', 50)
    prob = p.get('probabilities', {})
    summary = p.get('analysis_summary', [])
    plat_preds = p.get('platform_predictions', [])
    close_warn = ' <span style="font-size:14px;color:#e6a23c;">接近</span>' if p.get('is_close_match') else ''
    conf_color = '#67c23a' if conf >= 55 else ('#e6a23c' if conf >= 40 else '#f56c6c')

    html = '<div class="match-card">'
    mt_display = str(p.get('match_time', ''))[:16]
    pat = p.get('predicted_at', '')
    from_cache = p.get('from_cache', False)
    ts_label = ('赔率未变 · ' + pat) if from_cache else ('赔率变化 · ' + pat + '更新')
    html += '<div class="match-header"><span>' + str(p.get('league_name', '')) + '</span><span>比赛: ' + mt_display + ' | <span style="font-size:11px;opacity:0.8;">' + ts_label + '</span></span></div>'
    html += '<div class="match-teams"><div class="team-name home team-name-clickable" data-team="' + str(p.get('home_team_name', '')).replace('"', '&quot;') + '" onclick="event.stopPropagation();showTeamHistory(this.getAttribute(\'data-team\'))">' + str(p.get('home_team_name', '')) + '</div><div class="vs">VS</div><div class="team-name away team-name-clickable" data-team="' + str(p.get('away_team_name', '')).replace('"', '&quot;') + '" onclick="event.stopPropagation();showTeamHistory(this.getAttribute(\'data-team\'))">' + str(p.get('away_team_name', '')) + '</div></div>'
    html += '<div class="prediction-main"><div class="pred-info">'
    html += '<h2>预测: ' + pn + close_warn + '</h2>'
    html += '<div class="confidence" style="color:' + conf_color + '">置信度: ' + str(conf) + '%</div>'
    html += '<div class="prob-bar"><span class="prob-item home">主胜 ' + str(prob.get('home', 0)) + '%</span><span class="prob-item draw">平局 ' + str(prob.get('draw', 0)) + '%</span><span class="prob-item away">客胜 ' + str(prob.get('away', 0)) + '%</span></div>'
    html += '</div><div class="score-box"><div class="score">' + str(p.get('predicted_score', '?')) + '</div><div class="label">预测比分</div></div></div>'
    if summary:
        html += '<div class="section"><h4>分析理由</h4><ul class="reasons-list">'
        for s in summary[:6]:
            html += '<li>' + str(s) + '</li>'
        html += '</ul></div>'
    if plat_preds:
        html += '<div class="section"><h4>多平台预测</h4><div class="platform-grid">'
        for pl in plat_preds[:5]:
            pp = {'home': '主胜', 'draw': '平局', 'away': '客胜'}.get(pl.get('prediction', ''), '?')
            html += '<div class="platform-item"><div class="name">' + str(pl.get('platform', '?')) + '</div><div class="pred">' + pp + '</div><div class="conf">' + str(pl.get('confidence', '?')) + '%</div></div>'
        html += '</div></div>'
    html += '</div>'
    return html


def _render_history_row(r) -> str:
    """渲染单条历史记录行HTML"""
    mid, lg, ht, at, md, pr, pn, cf, ar, sc, ic = r
    ic_text = '正确' if ic == 1 else ('错误' if ic == 2 else '待定')
    ic_color = '#67c23a' if ic == 1 else ('#f56c6c' if ic == 2 else '#e6a23c')
    pr_text = {'home': '主胜', 'draw': '平局', 'away': '客胜'}.get(pr, str(pr or '?'))
    ar_text = {'home': '主胜', 'draw': '平局', 'away': '客胜'}.get(ar, str(ar or '?'))
    return '<tr><td>' + str(md)[:10] + '</td><td>' + str(lg) + '</td><td style="color:#409eff;cursor:pointer" onclick="showDetail(this)" data-mid="' + str(mid) + '">' + str(ht) + '</td><td style="color:#f56c6c;cursor:pointer" onclick="showDetail(this)" data-mid="' + str(mid) + '">' + str(at) + '</td><td>' + pr_text + '</td><td>' + str(cf or '-') + '%</td><td>' + ar_text + '</td><td>' + str(sc or '-') + '</td><td style="color:' + ic_color + '">' + ic_text + '</td></tr>'


@app.get("/")
async def root():
    """主页面 — 从数据库读取比赛和预测"""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(index_path):
        return {"message": "FootballPredict Pro API"}

    with open(index_path, 'r', encoding='utf-8') as f:
        html = f.read()

    history_stats = _fetch_history_stats()
    today_preds = []

    try:
        db_matches = _fetch_upcoming_matches()
        threading.Thread(target=_bg_refresh_sporttery, daemon=True).start()

        for row in db_matches:
            mid, lg, ht, at, mt = row
            result = None

            ph = _fetch_prediction_cache(mid)
            use_cache = ph and ph[4] and not _check_odds_changed(mid)

            if use_cache:
                try:
                    cached = json.loads(ph[4])
                    cached_pred = ph[1] or 'home'
                    cached_pname = ph[2] or '主胜'
                    cached_conf = float(ph[3]) if ph[3] else 50
                    for line in cached.get('analysis_summary', []):
                        if 'AI预测' in line:
                            if '主胜' in line:
                                cached_pred, cached_pname = 'home', '主胜'
                            elif '平局' in line:
                                cached_pred, cached_pname = 'draw', '平局'
                            elif '客胜' in line:
                                cached_pred, cached_pname = 'away', '客胜'
                            import re
                            m = re.search(r'置信度(\d+\.?\d*)%', line)
                            if m:
                                cached_conf = float(m.group(1))
                            break
                    result = {
                        'match_id': mid, 'league_name': lg,
                        'home_team_name': ht, 'away_team_name': at,
                        'match_time': str(mt) if mt else '',
                        'prediction': cached_pred,
                        'prediction_name': cached_pname,
                        'confidence': cached_conf,
                        'probabilities': cached.get('probabilities', {}),
                        'predicted_score': ph[5] or '?',
                        'platform_predictions': cached.get('platform_predictions', []),
                        'platform_votes': cached.get('platform_votes', {}),
                        'odds_analysis': cached.get('odds_analysis', {}),
                        'team_analysis': cached.get('team_analysis', {}),
                        'h2h_analysis': cached.get('h2h_analysis', {}),
                        'analysis_summary': cached.get('analysis_summary', []),
                        'from_cache': True,
                        'predicted_at': str(ph[6])[:16] if len(ph) > 6 and ph[6] else '',
                    }
                except Exception as e:
                    logger.warning(f"Cache parse failed for {mid}: {e}")
                    use_cache = False

            if not result:
                try:
                    predictor = _get_predictor()
                    pred = predictor.generate_prediction(ht, at, lg, match_id=mid)
                    p = pred['prediction']
                    result = {
                        'match_id': mid, 'league_name': lg,
                        'home_team_name': ht, 'away_team_name': at,
                        'match_time': str(mt) if mt else '',
                        'prediction': p['prediction'],
                        'prediction_name': p['prediction_name'],
                        'confidence': p['confidence'],
                        'probabilities': p.get('probabilities', {'home': 33, 'draw': 34, 'away': 33}),
                        'predicted_score': p.get('predicted_score', '?'),
                        'platform_predictions': pred.get('platform_predictions', []),
                        'platform_votes': pred.get('platform_votes', {}),
                        'odds_analysis': pred.get('odds_analysis', {}),
                        'team_analysis': pred.get('team_analysis', {}),
                        'h2h_analysis': pred.get('h2h_analysis', {}),
                        'analysis_summary': pred.get('analysis_summary', []),
                        'from_cache': False,
                        'predicted_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    }
                    threading.Thread(target=_save_prediction_bg, args=(mid, ht, at, lg, pred), daemon=True).start()
                except Exception as e:
                    logger.warning(f"Prediction generation failed for {mid}: {e}")
                    result = {
                        'match_id': mid, 'league_name': lg,
                        'home_team_name': ht, 'away_team_name': at,
                        'match_time': str(mt) if mt else '',
                        'prediction': 'home', 'prediction_name': '预测生成中', 'confidence': 0,
                        'probabilities': {'home': 33, 'draw': 34, 'away': 33}, 'predicted_score': '?',
                        'platform_predictions': [], 'platform_votes': {}, 'odds_analysis': {},
                        'team_analysis': {}, 'h2h_analysis': {},
                        'analysis_summary': ['AI预测引擎初始化中，请稍后刷新页面'],
                        'from_cache': False, 'predicted_at': '',
                    }

            if result:
                today_preds.append(result)

    except Exception as e:
        logger.error(f"SSR prediction load failed: {e}", exc_info=True)

    cards_html = ''.join(_render_match_card(p) for p in today_preds)
    if not cards_html:
        cards_html = '<div class="match-card"><div class="section" style="text-align:center;padding:40px;"><div style="color:#909399;">暂无预测数据，请点击右上角"刷新数据"按钮</div></div></div>'

    total = homes = draws = aways = 0
    acc = history_stats.get('accuracy', 0)
    r7d = history_stats.get('recent_7d', 0)

    history_rows = _fetch_history_rows(50)
    history_rows_html = ''.join(_render_history_row(r) for r in history_rows)

    try:
        with db_cursor() as cur:
            cur.execute("SELECT prediction_result, COUNT(*) FROM prediction_history WHERE is_correct>0 GROUP BY prediction_result")
            type_counts = dict(cur.fetchall())
            cur.execute("SELECT league, COUNT(*), SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END) FROM prediction_history WHERE is_correct>0 GROUP BY league ORDER BY COUNT(*) DESC LIMIT 12")
            league_rows = cur.fetchall()
    except Exception:
        type_counts, league_rows = {}, []

    stats_cards_html = ''
    for k, label in [('home', '主胜'), ('draw', '平局'), ('away', '客胜')]:
        cnt = int(type_counts.get(k, 0))
        acc2 = round(cnt / max(1, history_stats.get('total', 1)) * 100, 1)
        stats_cards_html += f'<div class="analysis-box"><h5>{label}预测</h5><div class="value">{cnt}场</div><div style="font-size:12px;color:#909399;">占比 {acc2}%</div></div>'
    for lg, cnt, corr in league_rows:
        corr = int(corr or 0)
        cnt = int(cnt)
        stats_cards_html += f'<div class="analysis-box"><h5>{lg}</h5><div class="value">{corr}/{cnt}</div><div style="font-size:12px;color:#{"67c23a" if cnt > 0 and corr / cnt >= 0.5 else "e6a23c"}">{round(corr / cnt * 100, 1) if cnt > 0 else 0}%</div></div>'

    inject_script = (
        '<script>window.PREDICTIONS = ' + json.dumps(today_preds, ensure_ascii=False) +
        ';window.HISTORY_STATS = ' + json.dumps(history_stats, ensure_ascii=False) + ';'
        'function showDetail(el){var mid=el.getAttribute("data-mid");'
        'fetch("/api/history/detail/"+encodeURIComponent(mid)).then(r=>r.json()).then(d=>{'
        'if(d.error){alert(d.error);return}'
        'var pn={\"home\":\"主胜\",\"draw\":\"平局\",\"away\":\"客胜\"};'
        'var pred=d.prediction||{};'
        'var sum=(d.analysis_summary||[]).map(function(s){return\"<li>\"+s+\"</li>\"}).join(\"\");'
        'var ar=d.actual_result?pn[d.actual_result]||d.actual_result:\"?\";'
        'var html=\"<h3>\"+d.home_team_name+\" vs \"+d.away_team_name+\"</h3>\";'
        'html+=\"<p>联赛: \"+d.league_name+\" | 时间: \"+d.match_time+\"</p>\";'
        'html+=\"<p><b>预测: \"+pred.prediction_name+\"</b> (置信度 \"+pred.confidence+\"%)</p>\";'
        'html+=\"<p>实际结果: \"+ar+\" | 比分: \"+(d.actual_score||\"?\")+\"</p>\";'
        'html+=\"<p>概率: 主\"+pred.probabilities.home+\"% 平\"+pred.probabilities.draw+\"% 客\"+pred.probabilities.away+\"%</p>\";'
        'if(sum)html+=\"<h4>分析理由</h4><ul>\"+sum+\"</ul>\";'
        'html+=\"<div style=\"text-align:center;margin-top:20px;padding-top:15px;border-top:1px solid #eee;\"><button onclick=\"closeDetail()\" style=\"padding:10px 40px;background:#f56c6c;color:white;border:none;border-radius:6px;font-size:15px;cursor:pointer;\">关闭</button></div>\";'
        'document.getElementById(\"modalBody\").innerHTML=html;'
        'var dm=document.getElementById(\"detailModal\");dm.classList.add(\"show\");dm.style.display=\"flex\"}).catch(function(e){alert(\"加载失败\")})};'
        'document.addEventListener("DOMContentLoaded",function(){'
        'document.getElementById("d_total").textContent=' + str(total) + ';'
        'document.getElementById("d_home").textContent=' + str(homes) + ';'
        'document.getElementById("d_draw").textContent=' + str(draws) + ';'
        'document.getElementById("d_away").textContent=' + str(aways) + ';'
        'document.getElementById("d_acc").textContent="' + str(acc) + '%";'
        'document.getElementById("h_total").textContent=' + str(history_stats.get('total', 0)) + ';'
        'document.getElementById("h_correct").textContent=' + str(history_stats.get('correct', 0)) + ';'
        'document.getElementById("h_wrong").textContent=' + str(history_stats.get('wrong', 0)) + ';'
        'document.getElementById("h_acc").textContent="' + str(acc) + '%";'
        'document.getElementById("h_recent").textContent="' + str(r7d) + '%";'
        'document.getElementById("s_total").textContent=' + str(history_stats.get('total', 0)) + ';'
        'document.getElementById("s_correct").textContent=' + str(history_stats.get('correct', 0)) + ';'
        'document.getElementById("s_wrong").textContent=' + str(history_stats.get('wrong', 0)) + ';'
        'document.getElementById("s_acc").textContent="' + str(acc) + '%";'
        'document.getElementById("s_recent").textContent="' + str(r7d) + '%";'
        '});'
        '</script>'
    )
    html = html.replace('</head>', inject_script + '\n</head>')
    html = html.replace('<div id="matchList"><div class="loading">加载中...</div></div>',
                        '<div id="matchList">' + cards_html + '</div>')
    if history_rows_html:
        html = html.replace('<tbody id="historyTable">',
                            '<tbody id="historyTable">' + history_rows_html)
    if stats_cards_html:
        html = html.replace('<div id="leagueStats"></div>',
                            '<div id="leagueStats">' + stats_cards_html + '</div>')
        html = html.replace('id="st_home">-', 'id="st_home">' + str(homes) + '场')
        html = html.replace('id="st_draw">-', 'id="st_draw">' + str(draws) + '场')
        html = html.replace('id="st_away">-', 'id="st_away">' + str(aways) + '场')

    try:
        from services.auto_data_service import refresh_on_demand
        threading.Thread(target=refresh_on_demand, daemon=True).start()
    except Exception as e:
        logger.debug(f"Auto data refresh skipped: {e}")

    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=60"})


# 静态页面路由
STATIC_PAGES = {
    "admin.html": os.path.join(FRONTEND_DIR, "admin.html"),
    "daily.html": os.path.join(FRONTEND_DIR, "daily.html"),
    "history.html": os.path.join(FRONTEND_DIR, "history.html"),
    "desktop_widget.html": os.path.join(os.path.dirname(FRONTEND_DIR), "desktop_widget.html"),
}

for page_name, page_path in STATIC_PAGES.items():
    if os.path.exists(page_path):
        def _make_route(path=page_path):
            async def _serve():
                return FileResponse(path)
            return _serve
        app.get(f"/{page_name}")(_make_route())

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)
