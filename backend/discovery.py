"""Search and deal-site discovery. Discovery alone never establishes a verified offer."""
import base64,datetime as dt,hashlib,ipaddress,json,os,re,socket,urllib.parse,urllib.request,xml.etree.ElementTree as ET
from pathlib import Path
AGGREGATORS=[
 ('AppSumo','https://appsumo.com/'),('Sumo 구독 할인','https://marketplace.sumo.com/'),
 ('StackSocial','https://www.stacksocial.com/'),('Slickdeals','https://slickdeals.net/newsearch.php?q=subscription&searcharea=deals&searchin=first'),
 ('DealMirror','https://dealmirror.com/'),('Dealify','https://dealify.com/'),
 ('뽐뿌 해외뽐뿌','https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu4'),
 ('퀘이사존 핫딜','https://quasarzone.com/bbs/qb_saleinfo')]
SEARCH_HOSTS={'www.google.com','news.google.com','search.naver.com','openapi.naver.com','www.googleapis.com','www.bing.com'}
def safe_url(value):
 try:
  u=urllib.parse.urlsplit(value);host=u.hostname or ''
  if u.scheme!='https' or not host or u.username or u.password or u.port not in (None,443) or host in ('localhost','localhost.localdomain') or '.' not in host:return None
  try:
   if not ipaddress.ip_address(host).is_global:return None
  except ValueError:pass
  return urllib.parse.urlunsplit((u.scheme,u.netloc,u.path or '/',u.query,''))
 except (ValueError,TypeError):return None

def public_host(host):
 try:return all(ipaddress.ip_address(item[4][0]).is_global for item in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM))
 except (OSError,ValueError):return False

def unwrap_search_link(value):
 try:
  parsed=urllib.parse.urlsplit(value);query=urllib.parse.parse_qs(parsed.query)
  if parsed.hostname in ('www.google.com','google.com') and parsed.path=='/url':value=(query.get('q') or query.get('url') or [''])[0]
  if parsed.hostname and parsed.hostname.endswith('bing.com') and query.get('u'):
   encoded=query['u'][0]
   if encoded.startswith('a1'):value=base64.urlsafe_b64decode(encoded[2:]+'='*((-len(encoded[2:]))%4)).decode()
 except (ValueError,UnicodeError):return None
 url=safe_url(value)
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
 ''')

def rotating(items,cursor,budget):
 if not items:return []
 return [items[(cursor+i)%len(items)] for i in range(min(len(items),budget))]

def run_discovery(db,seeds,fetch,stamp,budget=3):
 cursor=int((db.execute("SELECT value FROM research_state WHERE key='cursor'").fetchone() or ['0'])[0]);selected=rotating(seeds,cursor,budget)
 month=dt.datetime.now().strftime('%Y %m');queries=[f'{item["name"]} 구독 할인 프로모션 가격 {month}' for item in selected]
 queries.append(['AI 구독 할인 신규 서비스','OTT 멤버십 할인 이벤트','SaaS subscription discount alternatives','생산성 구독 신규 요금제'][cursor%4])
 attempts=[];found=[]
 def remember(provider,query,url,links,status='ok'):
  links=links[:10];attempts.append({'provider':provider,'query':query,'status':status,'results':len(links)})
  db.execute('INSERT INTO discovery_queries(provider,query,status,result_count,checked_at) VALUES(?,?,?,?,?)',(provider,query,status,len(links),stamp))
  for link,title in links:
   link=unwrap_search_link(link)
   if not link:continue
   service=next((s['key'] for s in seeds if any(alias.casefold() in (title+' '+link).casefold() for alias in [s['name'],*s.get('aliases',[])])),None)
   row={'url':link,'title':title[:180],'provider':provider,'discoveryUrl':url,'service':service};found.append(row)
   db.execute('''INSERT INTO candidates VALUES(?,?,?,?,?,'pending',?,?,NULL) ON CONFLICT(url) DO UPDATE SET last_seen=excluded.last_seen,title=excluded.title''',(link,title[:180],provider,url,service,stamp,stamp))
 for query in queries:
  for provider,url in [('Google','https://www.google.com/search?q='+urllib.parse.quote(query)),('Naver','https://search.naver.com/search.naver?where=web&query='+urllib.parse.quote(query)),('Bing','https://www.bing.com/search?q='+urllib.parse.quote(query))]:
   try:
    page=fetch(url);text=page.text.lower()
    if re.search(r'unusual traffic|captcha|자동입력 방지|로봇이 아닙니다',text):remember(provider,query,url,[],'blocked');continue
    links=[(urllib.parse.urljoin(url,h),label) for h,label in page.links if unwrap_search_link(urllib.parse.urljoin(url,h))]
    remember(provider,query,url,links,'ok' if links else 'no_results')
   except Exception:remember(provider,query,url,[],'unavailable')
 # Public Google News RSS remains usable when ordinary web search is blocked.
 for query in queries[:2]:
  url='https://news.google.com/rss/search?q='+urllib.parse.quote(query)+'&hl=ko&gl=KR&ceid=KR:ko'
  try:
   request=urllib.request.Request(url,headers={'User-Agent':'GoodokBenefits/2.1','Accept':'application/rss+xml'})
   with urllib.request.urlopen(request,timeout=15) as response:
    payload=response.read(1024*1024+1)
    if len(payload)>1024*1024:raise ValueError('oversize RSS')
   root=ET.fromstring(payload);links=[]
   for item in root.findall('.//item')[:8]:
    source=item.find('source');publisher=source.get('url') if source is not None else None
    if publisher:links.append((publisher,item.findtext('title') or ''))
   remember('Google News',query,url,links,'publisher_candidates' if links else 'no_results')
  except Exception:remember('Google News',query,url,[],'unavailable')
 for name,url in rotating(AGGREGATORS,cursor,4):
  try:
   page=fetch(url);links=[(urllib.parse.urljoin(url,h),label) for h,label in page.links if re.search(r'구독|할인|요금|subscription|deal|lifetime|annual|month|%|premium',label,re.I)]
   remember(name,'할인 사이트 탐색',url,links,'ok' if links else 'no_results')
  except Exception:remember(name,'할인 사이트 탐색',url,[],'unavailable')
 db.execute("INSERT OR REPLACE INTO research_state VALUES('cursor',?)",(str(cursor+budget),));db.commit()
 return attempts,found
