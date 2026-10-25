"""Hourly official-site discovery, evidence checks, SQLite history and public JSON export."""
import argparse,concurrent.futures,datetime as dt,hashlib,json,re,sqlite3,time,urllib.parse,urllib.request
from pathlib import Path
from html.parser import HTMLParser
from discovery import safe_url,public_host,init_discovery,run_discovery
from catalog_engine import normal_plan,expand_catalog
from factcheck import verify_candidates
ROOT=Path(__file__).resolve().parent
MAX_BYTES=3*1024*1024
UTC=dt.timezone.utc

def stamp(value=None):return (value or dt.datetime.now(UTC)).isoformat(timespec='seconds').replace('+00:00','Z')
class Page(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.skip=0;self.links=[];self.href=None;self.label=[];self.title=[];self.in_title=False;self.jsonld=[];self.ld_buffer=None;self.sections=[];self.section=None;self.meta={}
 def handle_starttag(self,tag,attrs):
  if tag in ('script','style','noscript'):self.skip+=1
  if tag=='script' and dict(attrs).get('type','').lower()=='application/ld+json':self.ld_buffer=[]
  if tag=='meta':
   info=dict(attrs);key=info.get('property') or info.get('name')
   if key:self.meta[key]=info.get('content','')
  if tag=='title':self.in_title=True
  if re.fullmatch(r'h[1-4]',tag):self.section={'title':'','text':''};self.sections.append(self.section);self.heading=True
  if tag=='a':self.href=dict(attrs).get('href');self.label=[]
  if not self.skip:self.parts.append(' ')
 def handle_endtag(self,tag):
  if tag=='script' and self.ld_buffer is not None:
   try:self.jsonld.append(json.loads(''.join(self.ld_buffer)))
   except (ValueError,TypeError):pass
   self.ld_buffer=None
  if tag in ('script','style','noscript'):self.skip=max(0,self.skip-1)
  if tag=='title':self.in_title=False
  if re.fullmatch(r'h[1-4]',tag):self.heading=False
  if tag=='a' and self.href:self.links.append((self.href,''.join(self.label)));self.href=None
  if not self.skip:self.parts.append(' ')
 def handle_data(self,data):
  if self.ld_buffer is not None:self.ld_buffer.append(data)
  if not self.skip:
   self.parts.append(data)
   if self.section is not None:
    self.section['text']+=' '+data
    if getattr(self,'heading',False):self.section['title']+=data
   if self.href:self.label.append(data)
   if self.in_title:self.title.append(data)
 @property
 def text(self):return re.sub(r'\s+',' ',''.join(self.parts)).strip()
class SafeRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  old,new=urllib.parse.urlparse(req.full_url),urllib.parse.urlparse(newurl)
  if new.scheme!='https' or new.hostname!=old.hostname or not public_host(new.hostname):raise ValueError('cross-site redirect rejected')
  return super().redirect_request(req,fp,code,msg,headers,newurl)
def fetch(url):
 if not safe_url(url) or not public_host(urllib.parse.urlparse(url).hostname):raise ValueError('non-public URL')
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 GoodokBenefits/2.0 (+public-offer-monitor)','Accept':'text/html','Accept-Language':'ko-KR,ko;q=0.9,en;q=0.8'})
 with urllib.request.build_opener(SafeRedirect()).open(req,timeout=18) as response:
  if 'text/html' not in response.headers.get('Content-Type',''):raise ValueError('not HTML')
  data=response.read(MAX_BYTES+1)
  if len(data)>MAX_BYTES:raise ValueError('oversize')
  page=Page();page.feed(data.decode(response.headers.get_content_charset() or 'utf-8',errors='replace'));return page

def ending(text):
 m=re.search(r'(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})\s*일?\s*(?:까지|종료)',text)
 if m:
  try:return dt.date(*map(int,m.groups())).isoformat()
  except ValueError:return None
 return None

def extract(source,page,url=None):
 text=page.text;kind=source['parser'];url=url or source['url'];benefit=detail=conditions=None;evidence='';ends=None
 if kind=='surfshark':
  m=re.search(r'Surfshark\s+One(?!\s*\+)(.{0,650})',text,re.I)
  if m:
   p=re.search(r'sale price\s*((?:(?:US|AU|CA)\s*)?\$|€|£)\s*([\d,]+\.\d{2})\s*for the first\s*(\d{1,2})\s*months',m[1],re.I)
   if p:
    benefit=f'첫 {p[3]}개월 {p[1]}{p[2]}';detail='Surfshark One 첫 이용 기간 선결제';conditions='세금·갱신 가격 별도. 표시 통화와 지역별 적용 조건 확인.';evidence=m[0][:300];ends=ending(m[1])
 elif kind=='adobe':
  p=re.search(r'첫\s*1\s*년[^₩]{0,180}₩\s*([\d,]+)\s*/\s*월',text)
  if p and all(re.search(x,text) for x in ['한국','처음 구독',r'12\s*개월\s*약정','부가세 포함']):
   benefit=f'첫해 월 ₩{p[1]}';detail='Creative Cloud 모든 앱 · 한국 신규 개인 구독';conditions='부가세 포함, 12개월 약정·월별 청구. 이후 당시 요금으로 자동 갱신. 해지 조건 확인.';evidence=text[max(0,p.start()-40):p.end()+80];ends=ending(text)
 elif kind=='spotify':
  trial=re.search(r'₩0에\s*(\d{1,2})개월',text);renewal=re.search(r'이후에는\s*₩([\d,]+)',text)
  if trial and renewal:benefit=f'Premium 개인 {trial[1]}개월 ₩0';detail='Spotify 한국 개인 요금제 체험';conditions=f'이용 자격 제한. 체험 이후 월 ₩{renewal[1]}(부가세 포함) 자동 결제. 결제 수단별 체험 금액 확인.';evidence=trial[0]+' / '+renewal[0];ends=ending(text)
 elif kind=='apple-music':
  trial=re.search(r'신규 구독자\s*(\d{1,2})개월 무료',text);renewal=re.search(r'개인\s*₩([\d,]+)/월',text)
  if trial and renewal:benefit=f'Apple Music 신규 {trial[1]}개월 무료';detail='Apple Music 한국 신규 개인 체험';conditions=f'신규 가입 자격 확인. 체험 이후 개인 월 ₩{renewal[1]}. 자동 갱신과 기기별 혜택 중복 조건 확인.';evidence=trial[0]+' / '+renewal[0];ends=ending(text)
 elif kind=='nordvpn':
  m=re.search(r'Basic\s+Save\s*(\d{1,2})%(.{0,500})',text,re.I)
  if m:
   p=re.search(r'((?:A|US|CA)?\$|€|£)\s*([\d,.]+)\s*for the first\s*(\d{1,2})\s*months',m[2],re.I)
   if p:benefit=f'Basic 첫 {p[3]}개월 {p[1]}{p[2]}';detail=f'공식 페이지 {m[1]}% 절약 표기';conditions='첫 기간 선결제 기준. 갱신 가격·세금과 표시 통화를 확인하세요.';evidence=m[0][:300];ends=ending(m[0])
 else:
  # Only a dated, explicit promotion detail can become a deal. Undated marketing stays a candidate.
  title=''.join(page.title).strip()
  benefit_match=re.search(r'(?:최대\s*)?\d{1,2}\s*%\s*할인|\d{1,2}\s*개월\s*무료|\d{1,2}\s*%\s*off',text,re.I)
  ends=ending(text[max(0,benefit_match.start()-300):benefit_match.end()+500]) if benefit_match else None
  if benefit_match and ends and re.search(r'할인|혜택|프로모션|event|offer|sale',title,re.I):
   benefit=benefit_match[0];detail=title[:120];conditions='대상·결제 방식·쿠폰 조건은 공식 행사 상세 페이지에서 확인하세요.';evidence=text[max(0,benefit_match.start()-70):benefit_match.end()+160]
 if not benefit:return None
 return {'id':hashlib.sha256((source['id']+'|'+url+'|'+detail).encode()).hexdigest()[:24],'service':source['service'],'title':detail[:120],'benefit':benefit,'detail':detail,'conditions':conditions,'source':url,'publisher':source['name']+' 공식','ends':ends,'evidence':evidence[:350]}

def observed_price(source,text):
 key=source['id'];match=None;currency='KRW';plan=''
 if key=='spotify':match=re.search(r'이후에는\s*₩([\d,]+)',text);plan='Premium 개인 · 월간'
 elif key=='apple-music':match=re.search(r'개인\s*₩([\d,]+)/월',text);plan='개인 · 월간'
 elif key=='disney-plus':match=re.search(r'디즈니\+ 스탠다드.{0,30}월\s*₩([\d,]+)',text);plan='스탠다드 · 월간'
 elif key=='claude':match=re.search(r'\$(\d+)\s*if billed monthly',text,re.I);currency='USD';plan='Pro · 월간'
 if match:
  value=float(match[1].replace(',',''))
  if value>0:return {'monthly':value,'currency':currency,'plan':plan,'checked':dt.datetime.now(UTC).date().isoformat(),'conditions':'공식 페이지 정상 월간 표시 가격. 국가·세금·결제 경로에 따른 최종 금액 확인.'}
 return None

def investigate(source):
 observations=[];offers=[]
 try:
  page=fetch(source['url']);offer=extract(source,page)
  if offer:offers.append(offer)
  observations.append({'url':source['url'],'status':'verified' if offer else 'no_verified_offer'})
  if source.get('discover'):
   urls=[]
   for href,label in page.links:
    url=urllib.parse.urljoin(source['url'],href);parsed=urllib.parse.urlparse(url)
    if parsed.scheme=='https' and parsed.hostname==urllib.parse.urlparse(source['url']).hostname and url!=source['url'] and re.search(r'할인|혜택|프로모션|무료|%|이벤트',label) and url not in urls:urls.append(url)
   for url in urls[:3]:
    try:
     detail=fetch(url);offer=extract(source,detail,url)
     if offer:offers.append(offer)
     observations.append({'url':url,'status':'verified' if offer else 'no_verified_offer'})
    except Exception:observations.append({'url':url,'status':'unavailable'})
  return {'id':source['id'],'name':source['name'],'status':'ok','offers':offers,'observations':observations,'price':observed_price(source,page.text),'plans':normal_plan(source,page,observed_price(source,page.text),stamp())}
 except Exception as exc:return {'id':source['id'],'name':source['name'],'status':'unavailable','offers':[],'observations':[{'url':source['url'],'status':'unavailable'}]}

def init_db(path):
 db=sqlite3.connect(path)
 db.executescript('''CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY,started_at TEXT,finished_at TEXT,successful_sources INTEGER,total_sources INTEGER);
 CREATE TABLE IF NOT EXISTS observations(run_id INTEGER,source_id TEXT,url TEXT,status TEXT,checked_at TEXT);
 CREATE TABLE IF NOT EXISTS offers(id TEXT PRIMARY KEY,source_id TEXT,payload TEXT,first_seen TEXT,last_verified TEXT);
 CREATE TABLE IF NOT EXISTS comparison_profiles(service TEXT PRIMARY KEY,payload TEXT,checked_at TEXT);
 ''');init_discovery(db);return db

def store_and_export(db,results,now,out,profiles):
 profiles=json.loads(json.dumps(profiles));timestamp=stamp(now);day=now.astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat()
 with db:
  run=db.execute('INSERT INTO runs(started_at,finished_at,successful_sources,total_sources) VALUES(?,?,?,?)',(timestamp,timestamp,sum(r['status']=='ok' for r in results),len(results))).lastrowid
  for result in results:
   if result.get('price') and result['id'] in profiles:profiles[result['id']]['price']=result['price']
   for plan in result.get('plans',[]):
    payload=json.dumps(plan,ensure_ascii=False);db.execute('INSERT OR REPLACE INTO plan_facts VALUES(?,?,?,?)',(plan['id'],plan['service'],payload,plan['verifiedAt']));db.execute('INSERT INTO plan_history VALUES(?,?,?)',(plan['id'],payload,plan['verifiedAt']))
   for observation in result['observations']:db.execute('INSERT INTO observations VALUES(?,?,?,?,?)',(run,result['id'],observation['url'],observation['status'],timestamp))
   for offer in result['offers']:
    db.execute('INSERT INTO offers VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,last_verified=excluded.last_verified',(offer['id'],result['id'],json.dumps(offer,ensure_ascii=False),timestamp,timestamp))
  for service,profile in profiles.items():
   previous=db.execute('SELECT payload FROM comparison_profiles WHERE service=?',(service,)).fetchone()
   if previous:
    old=json.loads(previous[0]);old_price=old.get('price');new_price=profile.get('price')
    if old_price and (not new_price or old_price.get('checked','')>new_price.get('checked','')):profile['price']=old_price
   db.execute('INSERT OR REPLACE INTO comparison_profiles VALUES(?,?,?)',(service,json.dumps(profile,ensure_ascii=False),profile.get('checked',day)))
  db.execute('DELETE FROM observations WHERE checked_at < ?', (stamp(now-dt.timedelta(days=30)),))
 offers=[]
 for payload,first,last in db.execute('SELECT payload,first_seen,last_verified FROM offers ORDER BY last_verified DESC'):
  offer=json.loads(payload)
  if last<stamp(now-dt.timedelta(hours=72)) or (offer['ends'] and offer['ends']<day):continue
  offer.update(checked=last[:10],verifiedAt=last,firstSeen=first);offer.pop('evidence',None);offer['factCheck']={'status':'official_verified','checkedAt':last,'officialSource':offer['source']};offers.append(offer)
 latest_success=db.execute('SELECT MAX(finished_at) FROM runs WHERE successful_sources>0').fetchone()[0]
 feed={'schemaVersion':1,'generatedAt':timestamp,'lastSuccessAt':latest_success,'offers':offers,'comparisons':profiles,'sources':[{'id':r['id'],'name':r['name'],'status':r['status'],'verifiedOffers':len(r['offers'])} for r in results]}
 catalog=[json.loads(row[0]) for row in db.execute('SELECT payload FROM service_catalog')]
 plans=[json.loads(row[0]) for row in db.execute('SELECT payload FROM plan_facts WHERE last_verified>=?',(stamp(now-dt.timedelta(days=7)),))]
 # Preserve old price evidence timestamps while correcting incomplete plan status and purpose metadata.
 purpose_index={item['key']:item.get('purpose') for item in catalog}
 for plan in plans:
  if plan.get('commitmentMonths') is None:plan['status']='candidate'
  if purpose_index.get(plan['service']):plan['purpose']=purpose_index[plan['service']]
  db.execute('UPDATE plan_facts SET payload=? WHERE plan_id=?',(json.dumps(plan,ensure_ascii=False),plan['id']))
 db.commit()
 query_rows=list(db.execute('SELECT provider,status,COUNT(*) FROM discovery_queries WHERE checked_at>=? GROUP BY provider,status',(stamp(now-dt.timedelta(days=1)),)))
 feed.update(catalog=catalog,plans=plans,research={'providers':[{'name':p,'status':s,'attempts':n} for p,s,n in query_rows],'candidateCount':db.execute('SELECT COUNT(*) FROM candidates').fetchone()[0],'factChecks':db.execute('SELECT COUNT(*) FROM fact_checks').fetchone()[0],'verifiedCatalogCount':sum(item.get('status')=='verified' for item in catalog),'catalogCount':len(catalog)})
 out.parent.mkdir(parents=True,exist_ok=True);temp=out.with_suffix('.tmp');temp.write_text(json.dumps(feed,ensure_ascii=False,indent=2)+'\n');temp.replace(out);return feed

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--database',default=str(ROOT/'data/benefits.sqlite'));parser.add_argument('--output',default=str(ROOT/'data/feed.json'));args=parser.parse_args()
 sources=json.loads((ROOT/'sources.json').read_text());profiles=json.loads((ROOT/'comparisons.json').read_text());seeds=json.loads((ROOT/'catalog-seeds.json').read_text());Path(args.database).parent.mkdir(parents=True,exist_ok=True)
 for source in sources:source['purpose']=next((seed.get('purpose') for seed in seeds if seed['key']==source['id']),None)
 db=init_db(args.database);now=dt.datetime.now(UTC);timestamp=stamp(now)
 attempts,candidates=run_discovery(db,seeds,fetch,timestamp)
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(investigate,sources))
 catalogue=expand_catalog(db,seeds,candidates,fetch,observed_price,timestamp,extract_offer=extract)
 discovered_offers=catalogue.pop('verifiedOffers',[])
 all_catalog=[json.loads(row[0]) for row in db.execute('SELECT payload FROM service_catalog')]
 checks=verify_candidates(db,all_catalog,[offer for result in results for offer in result['offers']]+discovered_offers,fetch,timestamp,extract_offer=extract)
 discovered_offers+=checks.pop('verifiedOffers',[])
 existing={offer['id'] for result in results for offer in result['offers']}
 for offer in discovered_offers:
  if offer['id'] in existing:continue
  existing.add(offer['id']);results.append({'id':'discovered-'+offer['service'],'name':offer['publisher'],'status':'ok','offers':[offer],'observations':[{'url':offer['source'],'status':'verified'}]})
 feed=store_and_export(db,results,dt.datetime.now(UTC),Path(args.output),profiles);db.close()
 print(json.dumps({'sources':len(results),'available':sum(r['status']=='ok' for r in results),'offers':len(feed['offers']),'searchAttempts':len(attempts),'candidates':len(candidates),'catalogue':catalogue,'factChecks':checks}))
 if not any(r['status']=='ok' for r in results):raise SystemExit('All sources unavailable; previous verified results retained with original verification times')
if __name__=='__main__':main()
