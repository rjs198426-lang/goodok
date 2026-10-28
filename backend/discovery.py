"""Bounded public searches, clean persistent leads, and provider retry schedules."""
import base64,datetime as dt,ipaddress,re,socket,urllib.parse,xml.etree.ElementTree as ET
from research_common import canonical_candidate,rejection_reason,match_service,time_after

AGGREGATORS=[('AppSumo','https://appsumo.com/'),('Sumo 구독 할인','https://marketplace.sumo.com/'),('StackSocial','https://www.stacksocial.com/'),('Slickdeals','https://slickdeals.net/newsearch.php?q=subscription&searcharea=deals&searchin=first'),('DealMirror','https://dealmirror.com/'),('Dealify','https://dealify.com/'),('뽐뿌 해외뽐뿌','https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu4'),('퀘이사존 핫딜','https://quasarzone.com/bbs/qb_saleinfo')]
SEARCH_HOSTS={'www.google.com','google.com','search.naver.com','openapi.naver.com','www.googleapis.com','www.bing.com','bing.com'}
TASTE_QUERIES=['전시 무료 관람 site:museum.go.kr','전시 관람 일정 site:mmca.go.kr','영화 상영 일정 site:koreafilm.or.kr','문화 공연 전시 site:culture.seoul.go.kr','독서 문화 행사 site:nl.go.kr','문화 체험 행사 site:culture.go.kr']
EXPANSION_QUERIES=['AI subscription monthly pricing new tools','password manager subscription pricing','cloud backup personal subscription pricing','workflow automation subscription pricing','design collaboration subscription pricing','AI video generation subscription pricing','text to speech subscription pricing','online learning subscription pricing','reading newsletter subscription pricing','developer tools subscription pricing','website hosting subscription pricing','OTT membership subscription pricing']

def safe_url(value):
 try:
  u=urllib.parse.urlsplit(value);h=u.hostname or ''
  if u.scheme!='https' or not h or u.username or u.password or u.port not in (None,443) or h in ('localhost','localhost.localdomain') or '.' not in h:return None
  try:
   if not ipaddress.ip_address(h).is_global:return None
  except ValueError:pass
  return urllib.parse.urlunsplit((u.scheme,u.netloc,u.path or '/',u.query,''))
 except (ValueError,TypeError):return None

def public_host(h):
 try:return all(ipaddress.ip_address(item[4][0]).is_global for item in socket.getaddrinfo(h,443,type=socket.SOCK_STREAM))
 except (OSError,ValueError):return False

def unwrap_search_link(value):
 try:
  p=urllib.parse.urlsplit(value);q=urllib.parse.parse_qs(p.query)
  if p.hostname in ('www.google.com','google.com') and p.path=='/url':value=(q.get('q') or q.get('url') or [''])[0]
  if p.hostname in ('www.bing.com','bing.com') and q.get('u'):
   encoded=q['u'][0]
   if encoded.startswith('a1'):value=base64.urlsafe_b64decode(encoded[2:]+'='*((-len(encoded[2:]))%4)).decode()
 except (ValueError,UnicodeError):return None
 url=canonical_candidate(value)
 if not url or urllib.parse.urlsplit(url).hostname in SEARCH_HOSTS:return None
 return url

def init_discovery(db):
 db.executescript('''CREATE TABLE IF NOT EXISTS discovery_queries(id INTEGER PRIMARY KEY,provider TEXT,query TEXT,status TEXT,result_count INTEGER,checked_at TEXT);
 CREATE TABLE IF NOT EXISTS candidates(url TEXT PRIMARY KEY,title TEXT,provider TEXT,discovery_url TEXT,service_key TEXT,status TEXT,first_seen TEXT,last_seen TEXT,reason TEXT);
 CREATE TABLE IF NOT EXISTS research_state(key TEXT PRIMARY KEY,value TEXT);
 CREATE TABLE IF NOT EXISTS fact_checks(id TEXT PRIMARY KEY,candidate_url TEXT,official_url TEXT,status TEXT,reason TEXT,evidence TEXT,checked_at TEXT);
 CREATE TABLE IF NOT EXISTS service_catalog(service_key TEXT PRIMARY KEY,payload TEXT,first_seen TEXT,last_checked TEXT);
 CREATE TABLE IF NOT EXISTS plan_facts(plan_id TEXT PRIMARY KEY,service_key TEXT,payload TEXT,last_verified TEXT);
 CREATE TABLE IF NOT EXISTS plan_history(plan_id TEXT,payload TEXT,observed_at TEXT);
 CREATE TABLE IF NOT EXISTS provider_health(provider TEXT PRIMARY KEY,failures INTEGER,next_check_at TEXT,last_status TEXT,last_checked TEXT);
 ''')
 for table,fields in {
  'candidates':{'catalog_status':"TEXT DEFAULT 'pending'",'catalog_checked_at':'TEXT','fact_checked_at':'TEXT','next_check_at':'TEXT','check_attempts':'INTEGER DEFAULT 0','scope':"TEXT DEFAULT 'subscription'",'publisher_url':'TEXT'},
  'discovery_queries':{'raw_count':'INTEGER DEFAULT 0','rejected_count':'INTEGER DEFAULT 0','scope':"TEXT DEFAULT 'subscription'",'error_code':'TEXT'},
 }.items():
  columns={r[1] for r in db.execute('PRAGMA table_info('+table+')')}
  for field,kind in fields.items():
   if field not in columns:db.execute('ALTER TABLE '+table+' ADD COLUMN '+field+' '+kind)
 db.execute('CREATE INDEX IF NOT EXISTS candidate_due ON candidates(scope,status,next_check_at)')

def rotating(items,cursor,budget):return [items[(cursor+i)%len(items)] for i in range(min(len(items),budget))] if items else []

def clean_legacy_candidates(db,seeds):
 """Quarantine old junk; preserve original URLs, timestamps and audit history."""
 removed=0
 for url,title in db.execute("SELECT url,title FROM candidates WHERE status!='rejected'").fetchall():
  reason=rejection_reason(url,title,seeds)
  if reason:
   db.execute("UPDATE candidates SET status='rejected',catalog_status='rejected',reason=? WHERE url=?",(reason,url));removed+=1
 db.commit();return removed

def news_links(payload):
 root=ET.fromstring(payload);links=[]
 for item in root.findall('.//item')[:8]:
  link=item.findtext('link') or ''
  # Preserve the article URL. A publisher home page is never an article claim.
  if safe_url(link):links.append((link,item.findtext('title') or '',item.find('source').get('url') if item.find('source') is not None else None))
 return links

def sitemap_links(payload,base):
 from research_common import same_site
 raw=payload.decode('utf-8',errors='replace') if isinstance(payload,bytes) else payload
 if re.search(r'<!DOCTYPE|<!ENTITY',raw,re.I):raise ValueError('DTD not accepted')
 root=ET.fromstring(raw);result=[]
 for loc in root.findall('.//{*}loc')[:1000]:
  url=safe_url((loc.text or '').strip())
  if url and same_site(url,base) and re.search(r'pricing|promotion|offer|event|benefit|할인|이벤트',url,re.I):result.append((url,'공식 요금·이벤트 상세 페이지'))
 return result[:10]

def run_discovery(db,seeds,fetch,stamp,budget=3,fetch_xml=None,api_search=None,api_providers=(),fetch_text=None):
 clean_legacy_candidates(db,seeds)
 cursor=int((db.execute("SELECT value FROM research_state WHERE key='cursor'").fetchone() or ['0'])[0]);selected=rotating(seeds,cursor,budget)
 month=dt.datetime.fromisoformat(stamp.replace('Z','+00:00')).strftime('%Y %m')
 queries=[(f'{s["name"]} 구독 할인 프로모션 가격 {month}','subscription') for s in selected]
 queries.append((['AI 구독 할인 신규 서비스','OTT 멤버십 할인 이벤트','SaaS subscription discount alternatives','생산성 구독 신규 요금제'][cursor%4],'subscription'))
 queries.append((TASTE_QUERIES[(cursor//max(1,budget))%len(TASTE_QUERIES)]+' '+month,'taste'))
 queries.insert(-1,(EXPANSION_QUERIES[(cursor//max(1,budget))%len(EXPANSION_QUERIES)],'subscription'))
 attempts=[];found=[]
 def remember(provider,query,url,links,status='ok',scope='subscription',error=None):
  raw=len(links);kept=[];seen=set()
  for entry in links:
   link,title=entry[:2];link=unwrap_search_link(link)
   if not link or link in seen or rejection_reason(link,title,seeds):continue
   seen.add(link);kept.append((link,title,entry[2] if len(entry)>2 else None))
   if len(kept)>=10:break
  if status=='ok' and not kept:status='no_relevant_results'
  attempts.append({'provider':provider,'query':query,'status':status,'results':len(kept),'raw':raw,'rejected':max(0,raw-len(kept)),'scope':scope,'error':error})
  db.execute('INSERT INTO discovery_queries(provider,query,status,result_count,checked_at,raw_count,rejected_count,scope,error_code) VALUES(?,?,?,?,?,?,?,?,?)',(provider,query,status,len(kept),stamp,raw,max(0,raw-len(kept)),scope,error))
  if status not in ('deferred',):
   health=db.execute('SELECT failures FROM provider_health WHERE provider=?',(provider,)).fetchone();failures=(health[0] if health else 0)+1 if status in ('blocked','unavailable','no_relevant_results') else 0
   due=time_after(stamp,12 if status=='blocked' else min(6 if status=='no_relevant_results' else 24,2**min(failures,5))) if failures else None
   db.execute('INSERT OR REPLACE INTO provider_health VALUES(?,?,?,?,?)',(provider,failures,due,status,stamp))
  for link,title,publisher in kept:
   service=match_service(link,title,seeds) if scope=='subscription' else None
   found.append({'url':link,'title':title[:180],'provider':provider,'discoveryUrl':url,'service':service,'scope':scope})
   db.execute('''INSERT INTO candidates(url,title,provider,discovery_url,service_key,status,first_seen,last_seen,reason,scope,publisher_url) VALUES(?,?,?,?,?,'pending',?,?,NULL,?,?) ON CONFLICT(url) DO UPDATE SET last_seen=excluded.last_seen,title=excluded.title,service_key=COALESCE(excluded.service_key,candidates.service_key),publisher_url=COALESCE(excluded.publisher_url,candidates.publisher_url)''',(link,title[:180],provider,url,service,stamp,stamp,scope,publisher))
 def deferred(provider):
  row=db.execute('SELECT next_check_at FROM provider_health WHERE provider=?',(provider,)).fetchone()
  return row and row[0] and row[0]>stamp
 for query,scope in queries:
  for provider,url in [('Google','https://www.google.com/search?q='+urllib.parse.quote(query)),('Naver','https://search.naver.com/search.naver?where=web&query='+urllib.parse.quote(query)),('Bing','https://www.bing.com/search?q='+urllib.parse.quote(query))]:
   if provider in api_providers and api_search and not deferred(provider+' API'):
    try:remember(provider+' API',query,url,api_search(provider,query),'ok',scope);continue
    except Exception as e:remember(provider+' API',query,url,[],'unavailable',scope,type(e).__name__)
   if deferred(provider):remember(provider,query,url,[],'deferred',scope);continue
   try:
    page=fetch(url)
    if re.search(r'unusual traffic|captcha|자동입력 방지|로봇이 아닙니다',page.text,re.I):remember(provider,query,url,[],'blocked',scope);continue
    links=[(urllib.parse.urljoin(url,h),label) for h,label in page.links if len(label.strip())>=3]
    remember(provider,query,url,links,'ok',scope)
   except Exception as e:
    from retrieval import error_code
    remember(provider,query,url,[],'unavailable',scope,error_code(e))
 # A standard public RSS interface is independent of the HTML search parser.
 for query,scope in [queries[0],queries[-2],queries[-1]]:
  url='https://www.bing.com/search?format=rss&q='+urllib.parse.quote(query)
  if deferred('Bing RSS'):remember('Bing RSS',query,url,[],'deferred',scope);continue
  try:
   if fetch_xml is None:raise ValueError('RSS fetcher not configured')
   remember('Bing RSS',query,url,news_links(fetch_xml(url)),'ok',scope)
  except Exception as e:
   from retrieval import error_code
   remember('Bing RSS',query,url,[],'unavailable',scope,error_code(e))
 # Curated public links are leads, never verified prices or endorsements.
 if fetch_text:
  url='https://raw.githubusercontent.com/mahseema/awesome-ai-tools/main/README.md'
  if not deferred('Public tool directory'):
   try:
    links=re.findall(r'\[([^\]\n]{2,120})\]\((https://[^\s)]+)\)',fetch_text(url))
    subset=rotating([(u,t) for t,u in links if 'github.com' not in u and not rejection_reason(u,t,seeds)],cursor*10,10)
    remember('Public tool directory','새 서비스 공식 사이트 후보',url,subset)
   except Exception as e:
    from retrieval import error_code
    remember('Public tool directory','새 서비스 공식 사이트 후보',url,[],'unavailable',error=error_code(e))
 # First-party navigation and sitemap discovery continue without search engines.
 from research_common import same_site
 for service in selected:
  url=service['officialUrl'];name='Official links: '+service['key']
  try:
   page=fetch(url);links=[(urllib.parse.urljoin(url,h),label) for h,label in page.links if same_site(urllib.parse.urljoin(url,h),url) and re.search(r'pricing|plans|offer|event|promo|benefit|할인|혜택|이벤트|요금',h+' '+label,re.I)]
   remember(name,service['name']+' 공식 내부 링크',url,links)
   sitemap=urllib.parse.urlunsplit(('https',urllib.parse.urlsplit(url).netloc,'/sitemap.xml','',''))
   if fetch_xml and not deferred('Sitemap: '+service['key']):
    try:remember('Sitemap: '+service['key'],'공식 사이트맵',sitemap,sitemap_links(fetch_xml(sitemap),url))
    except Exception as e:
     from retrieval import error_code
     remember('Sitemap: '+service['key'],'공식 사이트맵',sitemap,[],'unavailable',error=error_code(e))
  except Exception as e:
   from retrieval import error_code
   remember(name,'공식 내부 링크',url,[],'unavailable',error=error_code(e))
 # Ordinary RSS access; never bypass a provider's CAPTCHA or login wall.
 for query,scope in [queries[0],queries[-1]]:
  url='https://news.google.com/rss/search?q='+urllib.parse.quote(query)+'&hl=ko&gl=KR&ceid=KR:ko'
  if deferred('Google News'):remember('Google News',query,url,[],'deferred',scope);continue
  try:
   if fetch_xml is None:raise ValueError('RSS fetcher not configured')
   remember('Google News',query,url,news_links(fetch_xml(url)),'ok',scope)
  except Exception:remember('Google News',query,url,[],'unavailable',scope)
 for name,url in rotating(AGGREGATORS,cursor,4):
  if deferred(name):remember(name,'할인 사이트 탐색',url,[],'deferred');continue
  try:
   page=fetch(url);links=[(urllib.parse.urljoin(url,h),label) for h,label in page.links if re.search(r'구독|할인|요금|subscription|deal|lifetime|annual|month|%|premium',label,re.I)]
   remember(name,'할인 사이트 탐색',url,links)
  except Exception:remember(name,'할인 사이트 탐색',url,[],'unavailable')
 db.execute("INSERT OR REPLACE INTO research_state VALUES('cursor',?)",(str(cursor+budget),));db.commit()
 return attempts,found
