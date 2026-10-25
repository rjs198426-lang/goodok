"""Evidence-backed subscription catalogue and normal recurring plan observations."""
import datetime as dt,hashlib,json,re,urllib.parse
from discovery import safe_url,rotating
UTC=dt.timezone.utc

def host(url):return urllib.parse.urlparse(url).hostname or ''
def same_site(a,b):return host(a).removeprefix('www.')==host(b).removeprefix('www.')
def flatten(items):
 for item in items:
  if isinstance(item,list):yield from flatten(item)
  elif isinstance(item,dict):
   yield item
   if isinstance(item.get('@graph'),list):yield from flatten(item['@graph'])
def category_for(text):
 for category,pattern in [('VPN',r'\bVPN\b'),('음악',r'music|음악|음원'),('OTT',r'streaming video|영화|시리즈|OTT'),('AI',r'\bAI\b|인공지능|generative'),('생산성',r'productivity|workspace|협업|문서')]:
  if re.search(pattern,text,re.I):return category
 return '기타'
def purpose_for(category):return {'음악':'music','OTT':'video','VPN':'vpn','AI':'ai_unspecified','생산성':'productivity'}.get(category,'other')

def core_capabilities(text,purpose):
 capabilities={}
 if purpose=='music':
  capabilities['music']=True
  for key,pattern in [('adfree',r'광고 없|광고가 없|ad.free'),('offline',r'오프라인|offline'),('lossless',r'무손실|lossless'),('spatial',r'공간.?음향|spatial audio')]:
   if re.search(pattern,text,re.I):capabilities[key]=True
 return capabilities

def capability_evidence(text):
 result=[]
 for key,pattern in [('music',r'음악|music'),('adfree',r'광고 없[^.]{0,30}|ad.free'),('offline',r'오프라인[^.]{0,30}|offline'),('lossless',r'무손실[^.]{0,30}|lossless'),('spatial',r'공간.?음향[^.]{0,30}|spatial audio')]:
  match=re.search(pattern,text,re.I)
  if match:result.append({'field':'capability.'+key,'quote':match[0][:100]})
 return result

def normal_plan(source,page,observed,timestamp):
 if not observed:return []
 purpose=source.get('purpose') or purpose_for(source.get('category') or {'spotify':'음악','apple-music':'음악','disney-plus':'OTT','claude':'AI'}.get(source['id'],'기타'))
 if source['id'] not in ('spotify','apple-music','disney-plus','claude'):return []
 amount=observed['monthly'];quote=''
 if source['id']=='spotify':match=re.search(r'이후에는\s*₩[\d,]+.{0,50}',page.text)
 elif source['id']=='apple-music':match=re.search(r'개인\s*₩[\d,]+/월.{0,60}',page.text)
 elif source['id']=='disney-plus':match=re.search(r'디즈니\+ 스탠다드.{0,40}월\s*₩[\d,]+',page.text)
 else:match=re.search(r'\$\d+\s*if billed monthly',page.text,re.I)
 if not match:return []
 quote=match[0]
 return [{'id':source['id']+'-regular-monthly','service':source['id'],'name':observed['plan'],'amount':amount,'currency':observed['currency'],'interval':'monthly','region':'KR' if observed['currency']=='KRW' else 'US','taxBasis':'official_display','commitmentMonths':1,'introductory':False,'eligibility':'general','purpose':purpose,'capabilities':core_capabilities(page.text,purpose),'source':source['url'],'verifiedAt':timestamp,'status':'verified','evidence':[{'field':'amount','quote':quote[:220]}]+capability_evidence(page.text)}]

def structured_plans(page,service,timestamp):
 result=[]
 for product in flatten(page.jsonld):
  if product.get('@type') not in ('Product','SoftwareApplication','Service'):continue
  offers=product.get('offers',[]);offers=offers if isinstance(offers,list) else [offers]
  for offer in offers[:20]:
   if not isinstance(offer,dict):continue
   spec=offer.get('priceSpecification') or {};spec=spec[0] if isinstance(spec,list) and spec else spec
   if not isinstance(spec,dict):continue
   duration=spec.get('billingDuration') or spec.get('unitCode') or spec.get('unitText')
   interval={'P1M':'monthly','MON':'monthly','MONTH':'monthly','month':'monthly','P1Y':'yearly','ANN':'yearly','year':'yearly'}.get(str(duration))
   if not interval:continue
   amount=spec.get('price',offer.get('price'));currency=spec.get('priceCurrency',offer.get('priceCurrency'))
   try:amount=float(amount)
   except (ValueError,TypeError):continue
   if not 0<=amount<1e8 or currency not in ('KRW','USD','EUR','GBP','AUD','CAD'):continue
   name=str(offer.get('name') or product.get('name') or service['name'])[:100]
   # Trial, lifetime and introductory prices cannot become normal comparison prices.
   if re.search(r'trial|lifetime|first\s+(?:month|year)|체험|평생|첫\s*(?:달|개월|해)',name,re.I):continue
   ends=offer.get('priceValidUntil')
   if ends and str(ends)[:10]<timestamp[:10]:continue
   plan_id=hashlib.sha256((service['key']+name+interval+currency).encode()).hexdigest()[:24]
   raw=json.dumps(offer,ensure_ascii=False,separators=(',',':'))[:230]
   result.append({'id':plan_id,'service':service['key'],'name':name,'amount':amount,'currency':currency,'interval':interval,'region':'KR' if currency=='KRW' else 'unspecified','taxBasis':'included' if spec.get('valueAddedTaxIncluded') is True else 'unknown','commitmentMonths':(1 if re.search(r'cancel anytime|언제든.{0,15}해지|무약정',page.text,re.I) else None) if interval=='monthly' else 12,'introductory':False,'eligibility':'new_only' if re.search(r'new customers only|신규.{0,10}한정',str(offer.get('description','')),re.I) else 'general','purpose':service.get('purpose') or purpose_for(service['category']),'capabilities':{},'source':service['officialUrl'],'verifiedAt':timestamp,'status':'verified','evidence':[{'field':'structured_offer','quote':raw}]})
 return result

def text_plans(page,service,timestamp):
 result=[]
 if not re.search(r'pricing|plans?|price|subscription|compare|premium|buy|요금|가격',service['officialUrl']+' '+''.join(page.title),re.I):return []
 for section in page.sections:
  name=re.sub(r'\s+',' ',section['title']).strip();text=re.sub(r'\s+',' ',section['text']).strip()
  if len(name)>90 or not re.search(r'\b(?:Pro|Plus|Personal|Individual|Standard|Premium|Basic|Starter|Free|Max|Ultra)\b|개인|스탠다드|프리미엄|베이직',name,re.I):continue
  if re.search(r'lifetime|평생|신규 가입자만|new customers only|first year only',text,re.I):continue
  explicit=re.search(r'(US\$|\$|₩|€|£)\s*([\d,]+(?:\.\d+)?)\s*if billed monthly',text,re.I)
  matches=[explicit] if explicit else list(re.finditer(r'(US\$|\$|₩|€|£)\s*([\d,]+(?:\.\d+)?)\s*(?:/|per)?\s*(?:person per |seat per )?(?:month|mo\b|월)',text,re.I))
  prices={(m[1],m[2]) for m in matches if m}
  if len(prices)!=1:continue
  match=next(m for m in matches if m)
  if not explicit and re.search(r'annual|yearly|매년|연간|연 결제',text[max(0,match.start()-70):match.end()+100],re.I):continue
  symbol,value=next(iter(prices));amount=float(value.replace(',',''))
  if amount<=0:continue
  currency={'₩':'KRW','€':'EUR','£':'GBP','US$':'USD'}.get(symbol)
  if symbol=='$' and (re.search(r'USD|US\$',page.text) or host(service['officialUrl']).removeprefix('www.') in {'chatgpt.com','claude.com','cursor.com','github.com','notion.com','lovable.dev','krea.ai','suno.com','perplexity.ai'}):currency='USD'
  if not currency:continue
  identifier=hashlib.sha256((service['key']+'|'+name+'|'+currency+'|monthly').encode()).hexdigest()[:24]
  result.append({'id':identifier,'service':service['key'],'name':name,'amount':amount,'currency':currency,'interval':'monthly','region':'KR' if currency=='KRW' else 'unspecified','taxBasis':'official_display','commitmentMonths':1 if re.search(r'cancel anytime|언제든.{0,15}해지|무약정',text,re.I) else None,'introductory':False,'eligibility':'general','purpose':service.get('purpose') or purpose_for(service['category']),'capabilities':core_capabilities(text,service.get('purpose') or purpose_for(service['category'])),'source':service['officialUrl'],'verifiedAt':timestamp,'status':'verified','evidence':[{'field':'amount','quote':(name+' '+match[0])[:220]}]+capability_evidence(text)})
 for plan in result:
  if plan['commitmentMonths'] is None:plan['status']='candidate'
 return result

def identify_new(page,url,seeds,reference):
 if not reference:return None
 organizations=[item for item in flatten(page.jsonld) if item.get('@type') in ('Organization','Corporation')]
 products=[item for item in flatten(page.jsonld) if item.get('@type') in ('Product','SoftwareApplication','Service')]
 organization=next((item for item in organizations if safe_url(item.get('url')) and same_site(item['url'],url)),None)
 if not organization:return None
 name=str(organization.get('name') or (products[0].get('name') if products else '') or '').strip()
 if not products:
  legal=any(re.search(r'terms|privacy|이용약관|개인정보',label,re.I) for _,label in page.links)
  if not legal or name.casefold() not in ''.join(page.title).casefold():return None
 elif not any(name.casefold() in str(product.get('name','')).casefold() or str(product.get('name','')).casefold() in name.casefold() for product in products):return None
 if not name or len(name)>80:return None
 for seed in seeds:
  if any(alias.casefold() in name.casefold() for alias in [seed['name'],*seed.get('aliases',[])] if len(alias)>=4) and not same_site(seed['officialUrl'],url):return None
 description=str((products[0].get('description') if products else None) or page.meta.get('description') or page.meta.get('og:description') or '')[:240]
 return {'key':'discovered-'+hashlib.sha256(host(url).encode()).hexdigest()[:12],'name':name,'category':category_for(name+' '+description),'aliases':[name],'officialUrl':url,'officialHost':host(url),'origin':'discovered','status':'verified_identity','description':description,'discoveredFrom':reference,'purpose':('music_creation' if re.search(r'music generat|음악 생성|작곡',description,re.I) else 'image' if re.search(r'image generat|이미지 생성',description,re.I) else 'coding' if re.search(r'coding|code editor|코딩',description,re.I) else 'assistant' if re.search(r'chatbot|AI assistant|대화형|챗봇',description,re.I) else purpose_for(category_for(name+' '+description))), 'identityEvidence':{'organizationName':name,'organizationUrl':organization['url'],'method':'referring_site_and_first_party_structured_identity'}}

def expand_catalog(db,seeds,candidates,fetch,observed_price,timestamp,budget=10):
 for seed in seeds:db.execute('INSERT INTO service_catalog VALUES(?,?,?,?) ON CONFLICT(service_key) DO UPDATE SET payload=excluded.payload',(seed['key'],json.dumps(seed,ensure_ascii=False),timestamp,None))
 known={key:json.loads(payload) for key,payload in db.execute('SELECT service_key,payload FROM service_catalog')}
 cursor=int((db.execute("SELECT value FROM research_state WHERE key='catalog_cursor'").fetchone() or ['0'])[0]);selected=rotating(list(known.values()),cursor,budget)
 results=[];new_count=0
 for service in selected:
  try:
   page=fetch(service['officialUrl']);source={'id':service['key'],'category':service['category'],'purpose':service.get('purpose'),'url':service['officialUrl']};price=observed_price(source,page.text)
   plans=normal_plan(source,page,price,timestamp)+structured_plans(page,service,timestamp)+text_plans(page,service,timestamp)
   for plan in plans:
    payload=json.dumps(plan,ensure_ascii=False);db.execute('INSERT OR REPLACE INTO plan_facts VALUES(?,?,?,?)',(plan['id'],service['key'],payload,timestamp));db.execute('INSERT INTO plan_history VALUES(?,?,?)',(plan['id'],payload,timestamp))
   db.execute('UPDATE service_catalog SET last_checked=? WHERE service_key=?',(timestamp,service['key']));results.append({'service':service['key'],'status':'checked','plans':len(plans)})
  except Exception:results.append({'service':service['key'],'status':'unavailable','plans':0})
 known_hosts={item['officialHost'].removeprefix('www.') for item in known.values()}
 market_hosts={'appsumo.com','marketplace.sumo.com','stacksocial.com','www.stacksocial.com','slickdeals.net','dealmirror.com','dealify.com','www.ppomppu.co.kr','quasarzone.com'}
 # Pending discovery pages are revisited in later runs; a growing queue is not a fixed source list.
 cutoff=(dt.datetime.fromisoformat(timestamp.replace('Z','+00:00'))-dt.timedelta(days=1)).isoformat(timespec='seconds').replace('+00:00','Z')
 pending=list(db.execute("SELECT url,title,discovery_url FROM candidates WHERE catalog_status NOT IN ('known','verified') AND (catalog_checked_at IS NULL OR catalog_checked_at<?) ORDER BY catalog_checked_at NULLS FIRST,last_seen LIMIT 6",(cutoff,)))
 for url,title,reference in pending:
  if host(url).removeprefix('www.') in known_hosts:
   db.execute("UPDATE candidates SET catalog_status='known',catalog_checked_at=? WHERE url=?",(timestamp,url));continue
  db.execute('UPDATE candidates SET catalog_checked_at=? WHERE url=?',(timestamp,url))
  try:
   page=fetch(url)
   # Deal listing -> vendor website: the reseller itself is not registered as the subscription provider.
   if host(url) in market_hosts:
    external=[]
    for href,label in page.links:
     target=safe_url(urllib.parse.urljoin(url,href))
     if target and host(target) not in market_hosts and re.search(r'website|visit site|official|developer|홈페이지|공식',label,re.I):external.append((target,label))
    for target,label in external[:2]:db.execute("INSERT OR IGNORE INTO candidates(url,title,provider,discovery_url,service_key,status,first_seen,last_seen,reason) VALUES(?,?,?, ?,NULL,'pending',?,?,NULL)",(target,label,'vendor_link',url,timestamp,timestamp))
    db.execute("UPDATE candidates SET catalog_status='discovered_links' WHERE url=?",(url,));continue
   service=identify_new(page,url,seeds,reference)
   if not service:db.execute("UPDATE candidates SET catalog_status='needs_identity',reason='공식 사업자·구독 상품 증거 미확인' WHERE url=?",(url,));continue
   plans=structured_plans(page,service,timestamp)+text_plans(page,service,timestamp)
   if not plans:
    pricing=[safe_url(urllib.parse.urljoin(url,href)) for href,label in page.links if re.search(r'pricing|plans|요금|가격',label,re.I)]
    for target in [p for p in pricing if p and same_site(p,url)][:2]:
     pricing_page=fetch(target);service['officialUrl']=target;plans.extend(structured_plans(pricing_page,service,timestamp)+text_plans(pricing_page,service,timestamp))
   if not plans:db.execute("UPDATE candidates SET catalog_status='needs_price',reason='정기 결제 요금 증거 미확인' WHERE url=?",(url,));continue
   service.update(status='verified',verifiedAt=timestamp);known[service['key']]=service;new_count+=1
   db.execute('INSERT OR REPLACE INTO service_catalog VALUES(?,?,?,?)',(service['key'],json.dumps(service,ensure_ascii=False),timestamp,timestamp))
   for plan in plans:db.execute('INSERT OR REPLACE INTO plan_facts VALUES(?,?,?,?)',(plan['id'],service['key'],json.dumps(plan,ensure_ascii=False),timestamp))
   db.execute("UPDATE candidates SET catalog_status='verified',status='catalog_verified',reason=NULL WHERE url=?",(url,))
  except Exception:db.execute("UPDATE candidates SET reason='현재 페이지 접근 불가' WHERE url=?",(url,))
 db.execute("INSERT OR REPLACE INTO research_state VALUES('catalog_cursor',?)",(str(cursor+budget),));db.commit()
 return {'checked':results,'newServices':new_count,'catalogSize':len(known)}
