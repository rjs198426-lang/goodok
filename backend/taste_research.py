"""Dated activities from public cultural institutions. Never creates actual expenses."""
import hashlib,json,re,urllib.parse
from discovery import safe_url
from research_common import host,time_after

OFFICIAL_HOSTS=('museum.go.kr','mmca.go.kr','koreafilm.or.kr','culture.seoul.go.kr','nl.go.kr','culture.go.kr')
OFFICIAL_INDEXES=('https://www.museum.go.kr/MUSEUM/contents/M0202010000.do?menuId=current&schM=list','https://www.mmca.go.kr/','https://culture.seoul.go.kr/culture/main/main.do?ready=Y')
def official_activity_url(url):
 h=host(url)
 return bool(safe_url(url)) and any(h==d or h.endswith('.'+d) for d in OFFICIAL_HOSTS)

def flatten(value):
 if isinstance(value,list):
  for item in value:yield from flatten(item)
 elif isinstance(value,dict):
  yield value
  for key in ('@graph','subEvent'):
   if key in value:yield from flatten(value[key])

def category(title):return '영화' if re.search(r'영화|상영',title) else '도서 구입' if re.search(r'도서|독서|책|서점',title) else '공연·전시' if re.search(r'전시|공연|음악회',title) else '취미·레저'

def extract_activity(page,url,timestamp):
 if not official_activity_url(url):return None
 events=[e for e in flatten(page.jsonld) if 'Event' in ([e.get('@type')] if isinstance(e.get('@type'),str) else e.get('@type',[]))]
 for event in events:
  title=event.get('name');start=str(event.get('startDate',''))[:10];end=str(event.get('endDate',''))[:10]
  if not isinstance(title,str) or not 3<=len(title)<=100 or not valid_period(start,end,timestamp):continue
  result={'name':title,'starts':start,'ends':end,'evidence':'공식 행사 구조화 데이터의 제목·시작일·종료일'}
  raw=event.get('offers');raw=raw[0] if isinstance(raw,list) and raw else raw
  if isinstance(raw,dict) and raw.get('priceCurrency')=='KRW':
   try:
    amount=float(raw['price'])
    if 0<=amount<=1e7:result['price']=amount;result['currency']='KRW'
   except (TypeError,ValueError,KeyError):pass
  location=event.get('location')
  if isinstance(location,dict) and isinstance(location.get('name'),str):result['location']=location['name'][:100]
  return finish(result,url,timestamp)
 if url in OFFICIAL_INDEXES or re.search(r'(?:schM|act)=list(?:&|$)',url,re.I):return None
 title=str(page.meta.get('og:title') or ''.join(page.title)).strip()
 if not 3<=len(title)<=100 or not re.search(r'전시|공연|영화|상영|독서|체험|교육|행사',title):return None
 text=page.text[:5000]
 period=re.search(r'(20\d{2})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})\.?\s*(?:\([^)]{1,4}\))?\s*[~∼–—]\s*(20\d{2})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})',text)
 if not period:return None
 y,m,d,ey,em,ed=map(int,period.groups());start=f'{y:04}-{m:02}-{d:02}';end=f'{ey:04}-{em:02}-{ed:02}'
 if not valid_period(start,end,timestamp):return None
 result={'name':title,'starts':start,'ends':end,'evidence':period[0][:150]}
 if re.search(r'(?:관람료|참가비|이용료|입장료)\s*[:：]?\s*무료',text):result.update(price=0,currency='KRW')
 return finish(result,url,timestamp)

def valid_period(start,end,timestamp):
 import datetime as dt
 try:return dt.date.fromisoformat(start)<=dt.date.fromisoformat(end) and end>=timestamp[:10] and (dt.date.fromisoformat(end)-dt.date.fromisoformat(start)).days<=730
 except ValueError:return False

def finish(result,url,timestamp):
 return {**result,'id':hashlib.sha256((url+'|'+result['name']+'|'+result['starts']).encode()).hexdigest()[:24],'category':category(result['name']),'source':url,'publisher':host(url),'status':'official_verified','verifiedAt':timestamp}

def init_taste(db):db.execute('CREATE TABLE IF NOT EXISTS taste_suggestions(id TEXT PRIMARY KEY,payload TEXT,last_verified TEXT)')

def research_taste(db,fetch,timestamp,budget=6):
 init_taste(db);stats={'checked':0,'verified':0,'waitingOfficial':0}
 cursor=int((db.execute("SELECT value FROM research_state WHERE key='taste_cursor'").fetchone() or ['0'])[0]);index=OFFICIAL_INDEXES[cursor%len(OFFICIAL_INDEXES)]
 db.execute("INSERT OR IGNORE INTO candidates(url,title,provider,discovery_url,status,first_seen,last_seen,scope) VALUES(?,'공식 문화 행사 목록','official_activity_index',?,'pending',?,?,'taste')",(index,index,timestamp,timestamp))
 db.execute("INSERT OR REPLACE INTO research_state VALUES('taste_cursor',?)",(str(cursor+1),))
 rows=list(db.execute("SELECT url FROM candidates WHERE scope='taste' AND status!='rejected' AND (next_check_at IS NULL OR next_check_at<=?) ORDER BY CASE WHEN provider='official_activity_index' THEN 0 WHEN provider='official_activity_link' THEN 1 ELSE 2 END,fact_checked_at NULLS FIRST,first_seen LIMIT ?",(timestamp,budget)))
 for (url,) in rows:
  status='needs_official';reason='공식 문화 기관의 행사 상세 페이지 확인 대기';found=None
  try:
   if official_activity_url(url):
    stats['checked']+=1;page=fetch(url);found=extract_activity(page,url,timestamp)
    if not found:
     # A list page can lead to dated first-party detail pages, but is not an event.
     linked=0
     for href,label in page.links:
      target=safe_url(urllib.parse.urljoin(url,href))
      if target and target!=url and official_activity_url(target) and re.search(r'전시|공연|상영|체험|독서|exhi|exhibit|detail|view',target+' '+label,re.I) and len(label.strip())>=5 and not re.search(r'로그인|회원가입|개인정보|이용약관',label):
       db.execute("INSERT OR IGNORE INTO candidates(url,title,provider,discovery_url,status,first_seen,last_seen,scope) VALUES(?,?,?,?,'pending',?,?,'taste')",(target,label[:180],'official_activity_link',url,timestamp,timestamp))
       linked+=1
       if linked>=12:break
   else:
    # News is a lead only; never turn the article itself into a verified activity.
    stats['waitingOfficial']+=1
    page=fetch(url)
    for href,label in page.links:
     target=safe_url(urllib.parse.urljoin(url,href))
     if target and official_activity_url(target):db.execute("INSERT OR IGNORE INTO candidates(url,title,provider,discovery_url,status,first_seen,last_seen,scope) VALUES(?,?,?,?,'pending',?,?,'taste')",(target,label[:180] or '공식 행사 정보','official_activity_link',url,timestamp,timestamp))
   if found:
    db.execute('INSERT OR REPLACE INTO taste_suggestions VALUES(?,?,?)',(found['id'],json.dumps(found,ensure_ascii=False),timestamp));status='official_verified';reason='공식 행사 제목·기간 확인';stats['verified']+=1
   elif official_activity_url(url):status='needs_dates';reason='행사 제목·유효 기간 근거 미확인'
  except Exception:status='unavailable';reason='현재 행사 페이지 접근 불가'
  db.execute('UPDATE candidates SET status=?,reason=?,fact_checked_at=?,next_check_at=? WHERE url=?',(status,reason,timestamp,time_after(timestamp,12 if found else 24),url))
 db.commit();return stats

def export_taste(db,timestamp):
 init_taste(db)
 return [json.loads(payload) for payload,last in db.execute('SELECT payload,last_verified FROM taste_suggestions ORDER BY last_verified DESC') if last>=time_after(timestamp,-72) and json.loads(payload)['ends']>=timestamp[:10]][:100]
