import requests
from bs4 import BeautifulSoup
import re
import os
from datetime import datetime, timedelta

def get_prev_business_day():
    d = datetime.now() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d

prev = get_prev_business_day()
weekday_kr = ['월','화','수','목','금','토','일'][prev.weekday()]
date_display = prev.strftime(f'%Y년 %m월 %d일 ({weekday_kr})')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://finance.naver.com'
}

# 상승률 상위 20개 수집
all_stocks = []
for market, sosok in [('KOSPI', '0'), ('KOSDAQ', '10')]:
    url = f"https://finance.naver.com/sise/sise_rise.naver?sosok={sosok}"
    resp = requests.get(url, headers=headers)
    soup = BeautifulSoup(resp.text, 'html.parser')
    table = soup.find('table', class_='type_2')
    if not table: continue
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
                    all_stocks.append({'name': name, 'code': code, 'price': price,
                        'change_amt': change_amt, 'change_rate': change_rate,
                        'volume': volume, 'market': market, 'is_upper': is_upper})
            except: pass

def sort_key(s):
    r = s['change_rate'].replace('%','').replace('+','').strip()
    try: return float(r)
    except: return 0

all_stocks.sort(key=sort_key, reverse=True)
top20 = all_stocks[:20]

# 뉴스 수집
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
for s in top20[:10]:
    stock_news.extend(get_stock_news(s['code'], s['name'], 2))
eco_news = get_economy_news(8)

# HTML 생성 (위에서 만든 것과 동일한 HTML 코드)
stock_rows = ""
for i, s in enumerate(top20):
    badge = '<span class="badge upper">상한가</span>' if s['is_upper'] else ''
    mkt_class = "kospi" if s['market'] == 'KOSPI' else "kosdaq"
    change_sign = '+' if s['change_amt'] > 0 else ''
    stock_rows += f"""
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

stock_news_html = "".join([f'<div class="news-item"><span class="news-tag">{n["stock"]}</span><a href="{n["url"]}" target="_blank">{n["title"]}</a><span class="news-date">{n["date"]}</span></div>' for n in stock_news])
eco_news_html = "".join([f'<div class="news-item"><a href="{n["url"]}" target="_blank">{n["title"]}</a></div>' for n in eco_news])

html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>한국 주식 현황 | {date_display}</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{font-family:'Noto Sans KR',-apple-system,sans-serif;background:#0d1117;color:#e6edf3;min-height:100vh}}
  header{{background:linear-gradient(135deg,#161b22,#1f2937);border-bottom:1px solid #30363d;padding:20px 32px;display:flex;align-items:center;justify-content:space-between}}
  .logo{{font-size:22px;font-weight:700;color:#58a6ff}}.logo span{{color:#f0883e}}
  .header-date{{font-size:13px;color:#8b949e;background:#21262d;padding:6px 14px;border-radius:20px;border:1px solid #30363d}}
  .header-date strong{{color:#e6edf3}}
  .container{{max-width:1400px;margin:0 auto;padding:28px 24px;display:grid;grid-template-columns:1fr 420px;gap:24px}}
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
  .news-scroll{{max-height:360px;overflow-y:auto}}
  footer{{text-align:center;padding:20px;color:#6e7681;font-size:12px;border-top:1px solid #21262d;margin-top:8px}}
  footer a{{color:#58a6ff;text-decoration:none}}
  @media(max-width:900px){{.container{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<header>
  <div class="logo">📈 주식<span>레이더</span></div>
  <div class="header-date">전영업일 기준 <strong>{date_display}</strong> · 데이터 출처: 네이버 금융</div>
</header>
<div class="container">
  <div class="card">
    <div class="card-header"><span>🔥</span><h2>상승률 상위 종목 TOP 20</h2><span class="card-subtitle">상한가 포함 · 등락률 순</span></div>
    <table>
      <thead><tr><th>#</th><th>종목명</th><th>현재가</th><th>전일비</th><th>등락률</th><th>거래량</th></tr></thead>
      <tbody>{stock_rows}</tbody>
    </table>
  </div>
  <div class="news-panel">
    <div class="card">
      <div class="card-header"><span>📰</span><h2>급등 종목 관련 뉴스</h2></div>
      <div class="news-scroll">{stock_news_html}</div>
    </div>
    <div class="card">
      <div class="card-header"><span>🌐</span><h2>주요 경제 뉴스</h2></div>
      <div class="news-scroll">{eco_news_html}</div>
    </div>
  </div>
</div>
<footer>
  ※ 투자 판단의 책임은 본인에게 있습니다. | 데이터 기준일: {date_display} | <a href="https://finance.naver.com" target="_blank">네이버 금융</a>
</footer>
</body>
</html>"""

os.makedirs('docs', exist_ok=True)
with open('docs/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("index.html 생성 완료!")
