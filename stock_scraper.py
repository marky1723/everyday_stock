import requests
from bs4 import BeautifulSoup
import re
import os
import holidays
from datetime import datetime, timedelta

kst_now = datetime.utcnow() + timedelta(hours=9)
kr_holidays = holidays.KR(years=kst_now.year)

def is_business_day(d):
    return d.weekday() < 5 and d.date() not in kr_holidays

def get_reference_day():
    if is_business_day(kst_now) and kst_now.hour >= 16:
        return kst_now
    d = kst_now - timedelta(days=1)
    while not is_business_day(d):
        d -= timedelta(days=1)
    return d

ref_day = get_reference_day()
is_today = ref_day.date() == kst_now.date()
weekday_kr = ['월','화','수','목','금','토','일'][ref_day.weekday()]
date_display = ref_day.strftime(f'%Y년 %m월 %d일 ({weekday_kr})')
date_label = "당일" if is_today else "전영업일"
update_time = kst_now.strftime('%H:%M')

print(f"기준일: {date_display} ({date_label})")

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://finance.naver.com'
}

utc_hour = datetime.utcnow().hour
# 매시간 실행 중 오후 4시(UTC 7시)가 아니고 기존 파일이 있으면 뉴스만 업데이트
is_news_only = (utc_hour != 7) and os.path.exists('docs/index.html')
is_full_update = not is_news_only

print(f"업데이트 모드: {'뉴스만' if is_news_only else '전체'}")

# ── 기존 HTML 유지용
existing_kospi_rows = ""
existing_kosdaq_rows = ""
existing_date_display = date_display
existing_date_label = date_label

if is_news_only:
    with open('docs/index.html', 'r', encoding='utf-8') as f:
        existing_html = f.read()
    tbodies = re.findall(r'<tbody>(.*?)</tbody>', existing_html, re.DOTALL)
    if len(tbodies) >= 1: existing_kospi_rows = tbodies[0]
    if len(tbodies) >= 2: existing_kosdaq_rows = tbodies[1]
    date_match = re.search(r'기준 <strong>(.*?)</strong>', existing_html)
    if date_match: existing_date_display = date_match.group(1)
    label_match = re.search(r'id="date-label">(.*?)</span>', existing_html)
    if label_match: existing_date_label = label_match.group(1)

# ── 주가 수집 (전체 업데이트 시에만)
kospi_top20 = []
kosdaq_top20 = []
kospi_rows = existing_kospi_rows
kosdaq_rows = existing_kosdaq_rows

if is_full_update:
    for market, sosok in [('KOSPI', '0'), ('KOSDAQ', '10')]:
        url = f"https://finance.naver.com/sise/sise_rise.naver?sosok={sosok}"
        resp = requests.get(url, headers=headers)
        soup = BeautifulSoup(resp.text, 'html.parser')
        table = soup.find('table', class_='type_2')
        if not table: continue
        stocks = []
        for row in table.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) >= 6:
                try:
                    name_tag = cols[1].find('a')
                    if not name_tag: continue
                    name = name_tag.text.strip()
                    code = name_tag['href'].split('code=')[-1] if 'code=' in name_tag.get('href','') else ''
                    price_text = re.sub(r'[^\d]', '', cols[2].text)
                    price = int(price_text) if price_text else 0
                    change_raw = cols[3].text.strip()
                    is_upper = '상한가' in change_raw
                    change_amt_text = re.sub(r'[^\d,]', '', change_raw).replace(',','')
                    change_amt = int(change_amt_text) if change_amt_text else 0
                    change_rate = cols[4].text.strip()
                    vol_text = re.sub(r'[^\d]', '', cols[5].text)
                    volume = int(vol_text) if vol_text else 0
                    if name and price:
                        stocks.append({'name': name, 'code': code, 'price': price,
                            'change_amt': change_amt, 'change_rate': change_rate,
                            'volume': volume, 'market': market, 'is_upper': is_upper})
                except: pass

        stocks.sort(key=lambda s: float(s['change_rate'].replace('%','').replace('+','').strip()) if s['change_rate'].replace('%','').replace('+','').strip().replace('.','').lstrip('-').isdigit() else 0, reverse=True)
        top20 = stocks[:20]

        rows_html = ""
        for i, s in enumerate(top20):
            badge = '<span class="badge upper">상한가</span>' if s['is_upper'] else ''
            mkt_class = "kospi" if s['market'] == 'KOSPI' else "kosdaq"
            change_sign = '+' if s['change_amt'] > 0 else ''
            rows_html += f"""
            <tr>
              <td class="rank">{i+1}</td>
              <td class="name-cell">
                <a href="https://finance.naver.com/item/main.naver?code={s['code']}" target="_blank">{s['name']}</a>
                {badge}
                <span class="mkt-badge {mkt_class}">{s['market']}</span>
              </td>
              <td class="price">{s['price']:,}원</td>
              <td class="rise">{change_sign}{s['change_amt']:,}원</td>
              <td class="rate rise">{s['change_rate']}</td>
              <td class="vol">{s['volume']:,}</td>
            </tr>"""

        if market == 'KOSPI':
            kospi_top20 = top20
            kospi_rows = rows_html
        else:
            kosdaq_top20 = top20
            kosdaq_rows = rows_html

# ── 뉴스 수집
def get_stock_news(code, name, max_items=2):
    url = f"https://finance.naver.com/item/news_news.naver?code={code}&page=1"
    try:
        r = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        news_list = []
        for row in soup.select('table.type5 tr'):
            a = row.find('a')
            td_date = row.find('td', class_='date')
            if a and td_date:
                title = a.text.strip()
                href = 'https://finance.naver.com' + a['href'] if a['href'].startswith('/') else a['href']
                if title:
                    news_list.append({'title': title, 'url': href, 'date': td_date.text.strip(), 'stock': name})
            if len(news_list) >= max_items: break
        return news_list
    except: return []

def get_economy_news(max_items=8):
    url = "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258"
    try:
        r = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        news_list = []
        for a in soup.select('dd.articleSubject a'):
            title = a.text.strip()
            href = 'https://finance.naver.com' + a['href'] if a['href'].startswith('/') else a['href']
            if title: news_list.append({'title': title, 'url': href})
            if len(news_list) >= max_items: break
        return news_list
    except: return []

stock_news = []
all_top20 = kospi_top20 + kosdaq_top20
if is_full_update and all_top20:
    for s in all_top20[:10]:
        stock_news.extend(get_stock_news(s['code'], s['name'], 2))
elif is_news_only:
    with open('docs/index.html', 'r', encoding='utf-8') as f:
        existing_html = f.read()
    codes = re.findall(r'code=(\d+)', existing_html)[:10]
    names = re.findall(r'code=\d+" target="_blank">([^<]+)</a>', existing_html)[:10]
    for code, name in zip(codes, names):
        stock_news.extend(get_stock_news(code, name, 2))

eco_news = get_economy_news(8)

final_date = date_display if is_full_update else existing_date_display
final_label = date_label if is_full_update else existing_date_label

stock_news_html = "".join([
    f'<div class="news-item"><span class="news-tag">{n["stock"]}</span><a href="{n["url"]}" target="_blank">{n["title"]}</a><span class="news-date">{n["date"]}</span></div>'
    for n in stock_news])
eco_news_html = "".join([
    f'<div class="news-item"><a href="{n["url"]}" target="_blank">{n["title"]}</a></div>'
    for n in eco_news])

def make_table(rows):
    return f"""
    <table>
      <thead><tr><th>#</th><th>종목명</th><th>현재가</th><th>전일비</th><th>등락률</th><th>거래량</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>"""

html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>한국 주식 현황 | {final_date}</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{font-family:'Noto Sans KR',-apple-system,sans-serif;background:#0d1117;color:#e6edf3;min-height:100vh}}
  header{{background:linear-gradient(135deg,#161b22,#1f2937);border-bottom:1px solid #30363d;padding:20px 32px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}}
  .logo{{font-size:22px;font-weight:700;color:#58a6ff}}.logo span{{color:#f0883e}}
  .header-right{{display:flex;flex-direction:column;align-items:flex-end;gap:4px}}
  .header-date{{font-size:13px;color:#8b949e;background:#21262d;padding:6px 14px;border-radius:20px;border:1px solid #30363d}}
  .header-date strong{{color:#e6edf3}}
  .header-update{{font-size:11px;color:#6e7681;text-align:right}}
  .news-live{{color:#3fb950;font-weight:600}}
  .container{{max-width:1400px;margin:0 auto;padding:28px 24px;display:grid;grid-template-columns:1fr 420px;gap:24px}}
  .left-panel{{display:flex;flex-direction:column;gap:24px}}
  .card{{background:#161b22;border:1px solid #30363d;border-radius:12px;overflow:hidden}}
  .card-header{{padding:18px 24px 14px;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:10px}}
  .card-header h2{{font-size:16px;font-weight:600}}
  .card-subtitle{{font-size:12px;color:#8b949e;margin-left:auto}}
  table{{width:100%;border-collapse:collapse}}
  thead th{{font-size:12px;color:#8b949e;font-weight:500;padding:10px 16px;text-align:right;background:#0d1117;border-bottom:1px solid #21262d}}
  thead th:nth-child(1),thead th:nth-child(2){{text-align:left}}
  tbody tr:hover{{background:#1f2937}}
  tbody tr+tr{{border-top:1px solid #21262d}}
  td{{padding:11px 16px;font-size:13.5px;text-align:right;vertical-align:middle}}
  td.rank{{text-align:left;color:#8b949e;font-size:12px;width:32px}}
  td.name-cell{{text-align:left}}
  td.name-cell a{{color:#e6edf3;text-decoration:none;font-weight:500}}
  td.name-cell a:hover{{color:#58a6ff}}
  td.price{{color:#e6edf3;font-weight:500}}
  td.rise{{color:#ff7b72;font-weight:600}}
  td.rate.rise{{color:#ff7b72;font-weight:700;font-size:14px}}
  td.vol{{color:#8b949e;font-size:12px}}
  .badge{{display:inline-block;font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;margin-left:6px;vertical-align:middle}}
  .badge.upper{{background:#ff7b72;color:#0d1117}}
  .mkt-badge{{display:inline-block;font-size:10px;padding:2px 5px;border-radius:3px;margin-left:4px;vertical-align:middle;font-weight:500}}
  .mkt-badge.kospi{{background:#1f3a5f;color:#58a6ff}}
  .mkt-badge.kosdaq{{background:#1e3a2f;color:#3fb950}}
  .news-panel{{display:flex;flex-direction:column;gap:24px}}
  .news-item{{padding:14px 20px;border-bottom:1px solid #21262d}}
  .news-item:last-child{{border-bottom:none}}
  .news-item a{{color:#c9d1d9;text-decoration:none;font-size:13.5px;line-height:1.6;display:block}}
  .news-item a:hover{{color:#58a6ff}}
  .news-tag{{display:inline-block;background:#1f3a5f;color:#58a6ff;font-size:11px;font-weight:600;padding:2px 7px;border-radius:4px;margin-bottom:5px}}
  .news-date{{display:block;font-size:11px;color:#6e7681;margin-top:4px}}
  .news-scroll{{max-height:400px;overflow-y:auto}}
  .news-scroll::-webkit-scrollbar{{width:4px}}
  .news-scroll::-webkit-scrollbar-thumb{{background:#30363d;border-radius:2px}}
  .live-badge{{display:inline-block;background:#1e3a2f;color:#3fb950;font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;margin-left:8px}}
  footer{{text-align:center;padding:20px;color:#6e7681;font-size:12px;border-top:1px solid #21262d;margin-top:8px}}
  footer a{{color:#58a6ff;text-decoration:none}}
  @media(max-width:900px){{.container{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<header>
  <div class="logo">📈 주식<span>레이더</span></div>
  <div class="header-right">
    <div class="header-date"><span id="date-label">{final_label}</span> 기준 <strong>{final_date}</strong> · 네이버 금융</div>
    <div class="header-update">주가 평일 오후 4시 업데이트 · 경제 뉴스 <span class="news-live">매시간 자동 업데이트</span> · 최근 갱신 {update_time} KST</div>
  </div>
</header>
<div class="container">
  <div class="left-panel">
    <div class="card">
      <div class="card-header"><span>🔵</span><h2>코스피 상승률 TOP 20</h2><span class="card-subtitle">KRX 종가 기준 · 등락률 순</span></div>
      {make_table(kospi_rows)}
    </div>
    <div class="card">
      <div class="card-header"><span>🟢</span><h2>코스닥 상승률 TOP 20</h2><span class="card-subtitle">KRX 종가 기준 · 등락률 순</span></div>
      {make_table(kosdaq_rows)}
    </div>
  </div>
  <div class="news-panel">
    <div class="card">
      <div class="card-header"><span>📰</span><h2>급등 종목 관련 뉴스</h2></div>
      <div class="news-scroll">{stock_news_html}</div>
    </div>
    <div class="card">
      <div class="card-header"><span>🌐</span><h2>주요 경제 뉴스</h2><span class="live-badge">매시간 업데이트</span></div>
      <div class="news-scroll">{eco_news_html}</div>
    </div>
  </div>
</div>
<footer>
  ※ 투자 판단의 책임은 본인에게 있습니다. | 데이터 기준일: {final_date} | <a href="https://finance.naver.com" target="_blank">네이버 금융</a>
</footer>
</body>
</html>"""

os.makedirs('docs', exist_ok=True)
with open('docs/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"완료! {'뉴스만' if is_news_only else '전체'} 업데이트 | 기준일: {final_date} ({final_label}) | {update_time} KST")
