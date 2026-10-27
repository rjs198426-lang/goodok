"""Fair retry queues and first-party evidence matching for discovered claims."""
import hashlib,re,urllib.parse
from discovery import safe_url
from research_common import same_site,match_service,rejection_reason,time_after,as_offers

def money_tokens(text):return set(re.sub(r'\s+','',v) for v in re.findall(r'(?:₩|\$|€|£)\s*[\d,]+(?:\.\d+)?',text))
def same_host(a,b):return same_site(a,b)

def verify_candidates(db,seeds,offers,fetch,timestamp,budget=12,extract_offer=None):
 rows=list(db.execute("SELECT url,title,service_key,check_attempts FROM candidates WHERE scope='subscription' AND status NOT IN ('rejected','catalog_verified') AND (next_check_at IS NULL OR next_check_at<=?) ORDER BY fact_checked_at NULLS FIRST,first_seen,url LIMIT ?",(timestamp,max(200,budget*40))))
 stats={'checked':0,'confirmed':0,'pending':0,'unmatched':0,'rejected':0,'verifiedOffers':[]}
 for url,title,service_key,attempts in rows:
  reason=rejection_reason(url,title,seeds)
  if reason:
   db.execute("UPDATE candidates SET status='rejected',catalog_status='rejected',reason=?,fact_checked_at=? WHERE url=?",(reason,timestamp,url));stats['rejected']+=1;continue
  service_key=match_service(url,title,seeds) or service_key
  seed=next((s for s in seeds if s['key']==service_key),None)
  if not seed:
   db.execute("UPDATE candidates SET status='needs_service',reason='공식 서비스 연결 대기',fact_checked_at=?,next_check_at=? WHERE url=?",(timestamp,time_after(timestamp,24),url));stats['unmatched']+=1;continue
  if stats['checked']>=budget:break
  stats['checked']+=1;status='needs_verification';reason='공식 페이지에서 동일 혜택을 확인하지 못했어요.';evidence='';official_url=seed['officialUrl'];observed=[];unavailable=False
  try:
   page=fetch(url)
   pages=[(url,page)] if same_site(url,seed['officialUrl']) else []
   for href,label in page.links:
    candidate=safe_url(urllib.parse.urljoin(url,href))
    if candidate and same_site(candidate,seed['officialUrl']) and re.search(r'offer|event|promo|coupon|pricing|할인|이벤트|혜택',candidate+' '+label,re.I):
     try:pages.append((candidate,fetch(candidate)))
     except Exception:pass
     if len(pages)>=3:break
   if extract_offer:
    for page_url,official_page in pages:
     source={'id':seed['key'],'service':seed['key'],'name':seed['name'],'url':page_url,'parser':seed['key'] if seed['key'] in ('surfshark','adobe','spotify','apple-music','nordvpn') else 'event'}
     observed.extend(o for o in as_offers(extract_offer(source,official_page,page_url)) if not o.get('ends') or o['ends']>=timestamp[:10])
   # Only freshly extracted first-party observations can enter the published feed.
   stats['verifiedOffers'].extend(observed)
   options=observed+[o for o in offers if o['service']==service_key]
   for official in options:
    official_url=official['source'];proof=official.get('evidence','');prices=money_tokens(official['benefit'])
    if same_site(url,official_url) and any(o is official for o in observed):status='official_verified';reason='해당 공식 페이지에서 가격·조건 확인';evidence=proof;break
    if prices and prices<=money_tokens(page.text) and proof and proof in page.text:
     status='corroborated';reason='공식 원문의 가격·조건 문구와 일치';evidence=proof;break
    status='partial_match';reason='제3자 주장 전체를 공식 조건과 대조할 증거가 부족해요.'
  except Exception:reason='발견 페이지를 현재 확인할 수 없어요.';unavailable=True
  attempts=(attempts or 0)+1;hours=min(48,2**min(attempts,5)) if unavailable else 6 if status in ('official_verified','corroborated') else 24
  identifier=hashlib.sha256(url.encode()).hexdigest()[:24]
  db.execute('INSERT OR REPLACE INTO fact_checks VALUES(?,?,?,?,?,?,?)',(identifier,url,official_url,status,reason,evidence[:350],timestamp))
  db.execute('UPDATE candidates SET status=?,reason=?,service_key=?,fact_checked_at=?,next_check_at=?,check_attempts=? WHERE url=?',(status,reason,service_key,timestamp,time_after(timestamp,hours),attempts,url))
  if status in ('official_verified','corroborated'):stats['confirmed']+=1
  else:stats['pending']+=1
 db.commit();return stats
