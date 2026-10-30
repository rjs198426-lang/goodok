"""Bounded, auditable retrieval. No login, CAPTCHA solving or proxy rotation."""
import concurrent.futures,datetime as dt,os,re,socket,ssl,threading,time,urllib.error,urllib.parse,urllib.request
from discovery import safe_url,public_host
from research_common import host,time_after

class FetchFailure(Exception):
 def __init__(self,code,status=None):self.code=code;self.status=status;super().__init__(code)
def error_code(exc):
 if isinstance(exc,FetchFailure):return exc.code
 if isinstance(exc,urllib.error.HTTPError):return 'http_'+str(exc.code)
 reason=getattr(exc,'reason',exc)
 if isinstance(reason,(TimeoutError,socket.timeout)):return 'timeout'
 if isinstance(reason,ssl.SSLError):return 'tls_error'
 if isinstance(reason,socket.gaierror):return 'dns_error'
 return 'network_error' if isinstance(exc,(OSError,urllib.error.URLError)) else 'parse_error'
class PublicRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  if not safe_url(newurl) or host(newurl)!=host(req.full_url) or not public_host(urllib.parse.urlsplit(newurl).hostname):raise FetchFailure('cross_site_redirect')
  return super().redirect_request(req,fp,code,msg,headers,newurl)

LOCK=threading.RLock();CACHE={};AUDIT=[];HEALTH={};HOSTS=set();RENDERED=0;CACHE_HITS=0
def init_tables(db):
 db.executescript('''CREATE TABLE IF NOT EXISTS retrieval_attempts(id INTEGER PRIMARY KEY,url TEXT,route TEXT,result TEXT,http_status INTEGER,checked_at TEXT);
 CREATE TABLE IF NOT EXISTS retrieval_health(url TEXT PRIMARY KEY,failures INTEGER,next_check_at TEXT,last_error TEXT,last_checked TEXT);''')
def configure(db,urls=()):
 global RENDERED,CACHE_HITS
 init_tables(db)
 with LOCK:
  CACHE.clear();AUDIT.clear();HEALTH.clear();HOSTS.clear();RENDERED=0;CACHE_HITS=0
  HOSTS.update(host(u) for u in urls)
  HEALTH.update({u:{'failures':f,'next':n,'error':e} for u,f,n,e in db.execute('SELECT url,failures,next_check_at,last_error FROM retrieval_health')})
def note(url,route,result,status=None):
 with LOCK:
  if len(AUDIT)<1000:AUDIT.append({'url':url,'route':route,'result':result,'httpStatus':status})
def download(url,accept='text/html',limit=8*1024*1024,timeout=15):
 if not safe_url(url) or not public_host(urllib.parse.urlsplit(url).hostname):raise FetchFailure('non_public_url')
 for attempt in range(2):
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'DalfitResearch/4.0 (+public subscription research)','Accept':accept,'Accept-Language':'ko-KR,ko;q=0.9,en;q=0.8'})
   with urllib.request.build_opener(PublicRedirect()).open(req,timeout=timeout) as r:
    data=r.read(limit+1)
    if len(data)>limit:raise FetchFailure('response_too_large')
    return data,r.headers.get('Content-Type',''),r.headers.get_content_charset() or 'utf-8'
  except Exception as e:
   code=error_code(e);note(url,'http',code,getattr(e,'code',None) if isinstance(e,urllib.error.HTTPError) else None)
   if attempt==0 and code in ('http_500','http_502','http_503','http_504','timeout','dns_error'):
    retry=getattr(e,'headers',{}).get('Retry-After') if getattr(e,'headers',None) else None
    if retry and (not retry.isdigit() or int(retry)>1):raise
    time.sleep(0.5);continue
   raise
def render(url):
 global RENDERED
 with LOCK:
  limit=int(os.environ.get('DALFIT_BROWSER_RENDER_LIMIT','0'))
  if host(url) not in HOSTS:raise FetchFailure('render_not_official_target')
  if RENDERED>=limit:raise FetchFailure('render_budget_exhausted')
  RENDERED+=1
 try:
  from playwright.sync_api import sync_playwright
 except ImportError:raise FetchFailure('renderer_unavailable')
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,args=['--disable-dev-shm-usage'])
  try:
   context=browser.new_context(service_workers='block',accept_downloads=False,locale='ko-KR')
   dns={}
   def route(r):
    u=r.request.url;h=urllib.parse.urlsplit(u).hostname
    if h not in dns:dns[h]=public_host(h) if h else False
    if r.request.resource_type in ('image','media','font') or not safe_url(u) or not dns[h]:r.abort()
    else:r.continue_()
   context.route('**/*',route)
   if hasattr(context,'route_web_socket'):context.route_web_socket('**/*',lambda ws:ws.close())
   page=context.new_page();response=page.goto(url,wait_until='domcontentloaded',timeout=20000)
   if not response or response.status>=400:raise FetchFailure('render_http_'+str(response.status if response else 0))
   if host(page.url)!=host(url):raise FetchFailure('cross_site_redirect')
   page.wait_for_timeout(1200)
   text=page.locator('body').inner_text(timeout=5000)
   if re.search(r'captcha|verify you are human|unusual traffic|자동입력 방지|로봇이 아닙니다',text,re.I):raise FetchFailure('captcha')
   # Select only a public billing-period control, never signup/payment buttons.
   for role in ('tab','radio','button'):
    choices=page.get_by_role(role,name=re.compile(r'^(monthly(?: billing)?|월간(?: 결제)?|월별(?: 결제)?|월 결제)$',re.I))
    if choices.count()==1 and choices.first.is_visible() and choices.first.is_enabled():
     choices.first.click(timeout=2000);page.wait_for_timeout(350);break
   html=page.evaluate('''()=>{const copy=document.documentElement.cloneNode(true),original=[...document.documentElement.querySelectorAll('*')],nodes=[...copy.querySelectorAll('*')];for(let i=original.length-1;i>=0;i--){const e=original[i],keep=e.tagName==='SCRIPT'&&e.type==='application/ld+json';if(keep)continue;const style=getComputedStyle(e);if(e.hidden||e.getAttribute('aria-hidden')==='true'||style.display==='none'||style.visibility==='hidden'||['SCRIPT','STYLE','NOSCRIPT'].includes(e.tagName))nodes[i].remove();}return copy.outerHTML}''')
   if len(html.encode())>3*1024*1024:raise FetchFailure('response_too_large')
   return html
  finally:browser.close()
def fetch_html(url,parse):
 global CACHE_HITS
 with LOCK:
  future=CACHE.get(url)
  if future:CACHE_HITS+=1
  else:future=concurrent.futures.Future();CACHE[url]=future
  owner=not getattr(future,'started',False)
  if owner:future.started=True
 if not owner:return future.result()
 try:
  now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
  if HEALTH.get(url,{}).get('next') and HEALTH[url]['next']>now:raise FetchFailure('deferred_'+HEALTH[url]['error'])
  raw,mime,charset=download(url)
  if 'html' not in mime:raise FetchFailure('unexpected_content_type')
  html=raw.decode(charset,errors='replace');page=parse(html)
  if re.search(r'captcha|verify you are human|unusual traffic|자동입력 방지|로봇이 아닙니다',page.text,re.I):raise FetchFailure('captcha')
  shell=bool(re.search(r'id=["\'](?:app|root|__next)["\']|enable javascript|자바스크립트',html,re.I))
  required=len(page.text)<100 or shell and not re.search(r'[$₩€£]\s*[1-9]\d*',page.text)
  ambiguous=shell and any(re.search(r'annual|yearly|연간',s['text'],re.I) and re.search(r'monthly|월간',s['text'],re.I) and len(set(re.findall(r'[$₩€£]\s*([\d,.]+)',s['text'])))>1 for s in page.sections)
  if host(url) in HOSTS and (required or ambiguous):
   try:page=parse(render(url));note(url,'browser','ok')
   except Exception as e:
    note(url,'browser',error_code(e))
    if required:raise
  note(url,'page','ok');future.set_result(page);return page
 except Exception as e:
  note(url,'page',error_code(e),getattr(e,'code',None) if isinstance(e,urllib.error.HTTPError) else None);future.set_exception(e);raise
def persist(db,stamp):
 init_tables(db)
 with LOCK:rows=list(AUDIT)
 for r in rows:db.execute('INSERT INTO retrieval_attempts(url,route,result,http_status,checked_at) VALUES(?,?,?,?,?)',(r['url'],r['route'],r['result'],r['httpStatus'],stamp))
 for r in rows:
  if r['route']!='page' or r['result'].startswith('deferred_'):continue
  if r['result']=='ok':db.execute('DELETE FROM retrieval_health WHERE url=?',(r['url'],));continue
  old=db.execute('SELECT failures FROM retrieval_health WHERE url=?',(r['url'],)).fetchone();count=(old[0] if old else 0)+1
  hours=24 if r['result'] in ('captcha','http_403') else min(12,2**min(count-1,4))
  db.execute('INSERT OR REPLACE INTO retrieval_health VALUES(?,?,?,?,?)',(r['url'],count,time_after(stamp,hours),r['result'],stamp))
 db.execute('DELETE FROM retrieval_attempts WHERE checked_at<?',(time_after(stamp,-24*30),));db.commit()
 return {'outcomes':dict(db.execute('SELECT result,COUNT(*) FROM retrieval_attempts WHERE checked_at>=? GROUP BY result',(time_after(stamp,-24),))),'cacheHitsThisRun':CACHE_HITS,'renderAttemptsThisRun':RENDERED,'recentFailures':[{'url':u,'reason':e,'nextCheckAt':n} for u,e,n in db.execute('SELECT url,last_error,next_check_at FROM retrieval_health ORDER BY last_checked DESC LIMIT 30')]}
