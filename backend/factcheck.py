"""Cross-check discovered claims against first-party offers; keep uncertainty in the DB."""
import hashlib,json,re,urllib.parse
from discovery import safe_url

def money_tokens(text):return set(re.findall(r'(?:₩|\$|€|£)\s*[\d,]+(?:\.\d+)?',text))
def same_host(a,b):return urllib.parse.urlparse(a).hostname.removeprefix('www.')==urllib.parse.urlparse(b).hostname.removeprefix('www.')
def verify_candidates(db,seeds,offers,fetch,timestamp,budget=8):
 rows=list(db.execute("SELECT url,title,service_key FROM candidates WHERE status='pending' ORDER BY last_seen LIMIT ?",(budget,)))
 stats={'checked':0,'confirmed':0,'pending':0}
 for url,title,service_key in rows:
  seed=next((s for s in seeds if s['key']==service_key),None)
  if not seed:continue
  stats['checked']+=1;official=next((offer for offer in offers if offer['service']==service_key),None);status='needs_verification';reason='공식 페이지에서 동일 혜택을 확인하지 못했어요.';evidence='';official_url=seed['officialUrl']
  try:
   page=fetch(url)
   if official:
    official_url=official['source'];prices=money_tokens(official['benefit']);claim_prices=money_tokens(page.text)
    # A generic percentage is not sufficient: require a first-party match or full exact price/term evidence.
    if same_host(url,official_url):status='official_verified';reason='공식 출처에서 가격·혜택 조건 확인';evidence=official.get('evidence','')
    elif prices and prices<=claim_prices and official.get('evidence') and official['evidence'] in page.text:
     status='corroborated';reason='공식 원문의 가격·조건 문구와 일치';evidence=official['evidence']
    else:status='partial_match';reason='제3자 주장 전체를 공식 조건과 대조할 증거가 부족해요.'
  except Exception:reason='발견 페이지를 현재 확인할 수 없어요.'
  identifier=hashlib.sha256(url.encode()).hexdigest()[:24]
  db.execute('INSERT OR REPLACE INTO fact_checks VALUES(?,?,?,?,?,?,?)',(identifier,url,official_url,status,reason,evidence[:350],timestamp))
  db.execute('UPDATE candidates SET status=?,reason=? WHERE url=?',(status,reason,url))
  if status in ('official_verified','corroborated'):stats['confirmed']+=1
  else:stats['pending']+=1
 db.commit();return stats
