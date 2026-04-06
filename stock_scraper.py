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

def fetch_stocks(sosok, market, limit=10):
    stocks = []
    url = f"https://finance.naver.com/sise/sise_rise.naver?sosok={sosok}"
    resp = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(resp.text, 'html.parser')
    table = soup.find('table', class_='type_2')
    if not table:
        print(f"{market} 테이블 없음")
        return []
    for row in table.find_all('tr'):
        cols = row.find_all('td')
        if len(cols) >= 6:
            try:
                name_tag = cols[1].find('a')
                if not name_tag: continue
                name = name_tag.text.strip()
                code = name_tag['href'].split('code=')[-1] if 'code=' in name_tag.get('href','') else ''
                price = int(re.sub(r'[^\d]', '', cols[2].text) or 0)
                change_raw = cols[3].text.strip()
                is_upper = '상한가' in change_raw
                change_amt = int(re.sub(r'[^\d,]', '', change_raw).replace(',','') or 0)
                change_rate = cols[4].text.strip()
                volume = int(re.sub(r'[^\d]', '', cols[5].text) or 0)
                if name and price:
                    stocks.append({'name': name, 'code': code, 'price': price,
                        'change_amt': change_amt, 'change_rate': change_rate,
                        'volume': volume, 'market': market, 'is_upper': is_upper})
            except: pass
    stocks.sort(key=lambda s: float(s['change_rate'].replace('%','').replace('+','').strip() or 0), reverse=True)
    print(f"{market} {len(stocks[:limit])}개 수집")
    return stocks[:limit]

def make_rows(stocks):
    rows_html = ""
    for i, s in enumerate(stocks):
        badge = '<span class="badge upper">상한가</span>' if s['is_upper'] else ''
        mkt_class = "kospi" if s['market'] == 'KOSPI' else "kosdaq"
        change_sign = '+' if s['change_amt'] > 0 else ''
        rows_html += f"""<tr>
          <td class="rank">{i+1}</td>
          <td class="name-cell">
            <a href="https://finance.naver.com/item/main.naver?code={s['code']}" target="_blank">{s['name']}</a>
            {badge}<span class="mkt-badge {mkt_class}">{s['market']}</span>
          </td>
          <td class="price">{s['price']:,}원</td>
          <td class="rise">{change_sign}{s['change_amt']:,}원</td>
          <td class="rate rise">{s['change_rate']}</td>
          <td class="vol">{s['volume']:,}</td>
        </tr>"""
    return rows_html

def make_table(rows):
    return f"""<table>
      <thead><tr><th>#</th><th>종목명</th><th>현재가</th><th>전일비</th><th>등락률</th><th>거래량</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>"""

def get_stock_news(code, name, max_items=2):
    try:
        r = requests.get(f"https://finance.naver.com/item/news_news.naver?code={code}&page=1", headers=headers, timeout=5)
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
    try:
        r = requests.get("https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258", headers=headers, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        news_list = []
        for a in soup.select('dd.articleSubject a'):
            title = a.text.strip()
            href = 'https://finance.naver.com' + a['href'] if a['href'].startswith('/') else a['href']
            if title: news_list.append({'title': title, 'url': href})
            if len(news_list) >= max_items: break
        return news_list
    except: return []

# 항상 전부 수집
kospi = fetch_stocks('0', 'KOSPI', 10)
kosdaq = fetch_stocks('10', 'KOSDAQ', 10)

stock_news = []
for s in (kospi + kosdaq)[:10]:
    stock_news.extend(get_stock_news(s['code'], s['name'], 2))
eco_news = get_economy_news(8)

stock_news_html = "".join([
    f'<div class="news-item"><span class="news-tag">{n["stock"]}</span><a href="{n["url"]}" target="_blank">{n["title"]}</a><span class="news-date">{n["date"]}</span></div>'
    for n in stock_news])
eco_news_html = "".join([
    f'<div class="news-item"><a href="{n["url"]}" target="_blank">{n["title"]}</a></div>'
    for n in eco_news])

html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>한국 주식 현황 | {date_display}</title>
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
    <div class="header-date"><span id="date-label">{date_label}</span> 기준 <strong>{date_display}</strong> · 네이버 금융</div>
    <div class="header-update">주가 평일 오후 4시 업데이트 · 경제 뉴스 <span class="news-live">매시간 자동 업데이트</span> · 최근 갱신 {update_time} KST</div>
  </div>
</header>
<div class="container">
  <div class="left-panel">
    <div class="card">
      <div class="card-header"><span>🔵</span><h2>코스피 상승률 TOP 10</h2><span class="card-subtitle">KRX 종가 기준 · 등락률 순</span></div>
      {make_table(make_rows(kospi))}
    </div>
    <div class="card">
      <div class="card-header"><span>🟢</span><h2>코스닥 상승률 TOP 10</h2><span class="card-subtitle">KRX 종가 기준 · 등락률 순</span></div>
      {make_table(make_rows(kosdaq))}
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
  ※ 투자 판단의 책임은 본인에게 있습니다. | 데이터 기준일: {date_display} | <a href="https://finance.naver.com" target="_blank">네이버 금융</a>
</footer>
</body>
</html>"""

os.makedirs('docs', exist_ok=True)
with open('docs/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"완료! 코스피 {len(kospi)}개, 코스닥 {len(kosdaq)}개 | {date_display} ({date_label}) | {update_time} KST")
