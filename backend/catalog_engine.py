"""Evidence-backed subscription catalogue and normal recurring plan observations."""
import datetime as dt,hashlib,json,re,urllib.parse
from pathlib import Path
from discovery import safe_url,rotating
from research_common import as_offers,rejection_reason,match_service
from plan_capabilities import enrich_plan_capabilities
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
 for category,pattern in [('보안',r'password manager|password vault|비밀번호 관리'),('백업',r'cloud backup|computer backup|클라우드 백업'),('업무 자동화',r'workflow automation|automate workflows|업무 자동화'),('웹·호스팅',r'web hosting|website hosting|웹 호스팅'),('음성·오디오',r'text.to.speech|voice cloning|speech synthesis|음성 합성'),('영상 제작',r'video generat|video edit|영상 편집|영상 생성'),('디자인',r'graphic design|design collaboration|디자인 협업'),('독서·지식',r'reading subscription|read.it.later|독서 구독'),('개발 도구',r'developer tool|code editor|개발 도구'),('학습',r'online courses|language learning|온라인 강의|언어 학습'),('VPN',r'\bVPN\b'),('음악',r'music|음악|음원'),('OTT',r'streaming video|영화|시리즈|OTT'),('AI',r'\bAI\b|인공지능|generative'),('생산성',r'productivity|workspace|협업|문서')]:
  if re.search(pattern,text,re.I):return category
 return '기타'
def purpose_for(category):return {'보안':'passwords','백업':'backup','업무 자동화':'automation','웹·호스팅':'hosting','음성·오디오':'speech','영상 제작':'video_creation','디자인':'design','독서·지식':'reading','개발 도구':'coding','학습':'learning','음악':'music','OTT':'video','VPN':'vpn','AI':'ai_unspecified','생산성':'productivity'}.get(category,'other')
def research_targets():return json.loads((Path(__file__).parent/'research-targets.json').read_text())
def enqueue_targets(db,timestamp):
 for target in research_targets():db.execute("INSERT OR IGNORE INTO candidates(url,title,provider,discovery_url,status,first_seen,last_seen,scope) VALUES(?,?,'official_target',?,'pending',?,?,'subscription')",(target['url'],target['name'],target['url'],timestamp,timestamp))
 db.commit()

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
   result.append({'id':plan_id,'service':service['key'],'name':name,'amount':amount,'currency':currency,'interval':interval,'region':'KR' if currency=='KRW' else 'unspecified','taxBasis':'included' if spec.get('valueAddedTaxIncluded') is True else 'unknown','commitmentMonths':(1 if re.search(r'cancel\s+any\s*time|언제든.{0,15}해지|무약정',page.text,re.I) else None) if interval=='monthly' else 12,'introductory':False,'eligibility':'new_only' if re.search(r'new customers only|신규.{0,10}한정',str(offer.get('description','')),re.I) else 'general','purpose':service.get('purpose') or purpose_for(service['category']),'capabilities':{},'source':service['officialUrl'],'verifiedAt':timestamp,'status':'verified','evidence':[{'field':'structured_offer','quote':raw}]})
 for plan in result:
  if plan['commitmentMonths'] is None:plan['status']='candidate'
 return result

def text_plans(page,service,timestamp):
 result=[]
 if not re.search(r'pricing|plans?|price|subscription|compare|premium|buy|요금|가격',service['officialUrl']+' '+''.join(page.title),re.I):return []
 for section in page.sections:
  name=re.sub(r'\s+',' ',section['title']).strip();text=re.sub(r'\s+',' ',section['text']).strip()
  if len(name)>90 or not re.search(r'\b(?:Pro|Plus|Personal|Individual|Standard|Premium|Basic|Starter|Free|Max|Ultra|Business|Teams?|Growth|Professional|Developer|Family|Families|Advanced|Core|Creator|Unlimited|Essential|Complete|Reader)\b|개인|스탠다드|프리미엄|베이직',name,re.I):continue
  if re.search(r'lifetime|평생|신규 가입자만|new customers only|first year only',text,re.I):continue
  explicit=re.search(r'(US\$|\$|₩|€|£)\s*([\d,]+(?:\.\d+)?)\s*if billed monthly',text,re.I)
  if not explicit:explicit=re.search(r'(US\$|\$|₩|€|£)\s*([\d,]+(?:\.\d+)?)\s*/\s*(?:month|mo)\b\s*(?:[·|—–-]\s*)?billed monthly',text,re.I)
  matches=[explicit] if explicit else list(re.finditer(r'(US\$|\$|₩|€|£)\s*([\d,]+(?:\.\d+)?)\s*(?:/|per)?\s*(?:person per |seat per )?(?:month|mo\b|월)',text,re.I))
  prices={(m[1],m[2]) for m in matches if m}
  if len(prices)!=1:continue
  match=next(m for m in matches if m)
  if not explicit and re.search(r'annual|yearly|매년|연간|연 결제',text[max(0,match.start()-70):match.end()+100],re.I):continue
  symbol,value=next(iter(prices));amount=float(value.replace(',',''))
  if amount<=0:continue
  currency={'₩':'KRW','€':'EUR','£':'GBP','US$':'USD'}.get(symbol)
  if symbol=='$' and (re.search(r'USD|US\$',text) or host(service['officialUrl']).removeprefix('www.') in {'chatgpt.com','claude.com','cursor.com','github.com','notion.com','lovable.dev','krea.ai','suno.com','perplexity.ai','deepai.org'}):currency='USD'
  if not currency:continue
  identifier=hashlib.sha256((service['key']+'|'+name+'|'+currency+'|monthly').encode()).hexdigest()[:24]
  result.append({'id':identifier,'service':service['key'],'name':name,'amount':amount,'currency':currency,'interval':'monthly','region':'KR' if currency=='KRW' else 'unspecified','taxBasis':'official_display','commitmentMonths':1 if re.search(r'cancel\s+any\s*time|언제든.{0,15}해지|무약정',text,re.I) else None,'introductory':False,'eligibility':'general','purpose':service.get('purpose') or purpose_for(service['category']),'capabilities':core_capabilities(text,service.get('purpose') or purpose_for(service['category'])),'source':service['officialUrl'],'verifiedAt':timestamp,'status':'verified','evidence':[{'field':'amount','quote':(name+' '+match[0])[:220]}]+capability_evidence(text)})
 for plan in result:
  if plan['commitmentMonths'] is None:plan['status']='candidate'
 return result

def enrich_service(service,page,plans,timestamp):
 """Describe paid scope rather than a free sub-product's metadata."""
 service=dict(service);enrich_plan_capabilities(plans,page)
 if service.get('origin')=='discovered':
  sections=[s for s in page.sections if re.fullmatch(r'(?:Consider\s+)?(?:DeepAI\s+)?(?:Pro|Plus|Premium|Standard|Personal|Individual|Basic|Starter|Max|Ultra)(?:\s+Plan)?',s['title'].strip(),re.I) and re.search(r'(?:₩|\$|€|£)\s*\d',s['text'])]
  scope=' '.join(s['text'] for s in sections)
  if host(service['officialUrl']).removeprefix('www.')=='deepai.org':
   paid=re.search(r'\bPro\s+Everything DeepAI makes.{0,100}?subscription(.{0,2500}?)(?=What.s in each plan|$)',page.text,re.I)
   if paid:scope=paid[0]
  patterns=[('assistant',r'chat\s*(?:messages|models)|chatbot|AI\s*chat|대화형|챗봇'),('image',r'image\s*generat|이미지\s*생성|\d[\d,]*\s*(?:HD\s*)?images'),('coding',r'coding|code editor|AI\s*code|DeepAI\s*Code|코딩'),('music_creation',r'music\s*generat|AI.generated\s*songs|음악\s*생성'),('appbuilder',r'website\s*builder|앱\s*제작')]
  evidence=[];purposes=[]
  for purpose,pattern in patterns:
   match=re.search(pattern,scope,re.I)
   if match:purposes.append(purpose);evidence.append({'purpose':purpose,'quote':scope[max(0,match.start()-25):match.end()+60],'source':service['officialUrl'],'checkedAt':timestamp})
  if purposes:
   service.update(purpose=purposes[0],purposes=purposes,purposeEvidence=evidence)
   labels={'assistant':'AI 대화','image':'이미지 제작','coding':'코딩','music_creation':'음악 제작','appbuilder':'웹사이트 제작'}
   service['description']=' · '.join(labels[p] for p in purposes)+' 도구를 포함한 구독 서비스'
 service.setdefault('purposes',[service['purpose']] if service.get('purpose') and service['purpose'] not in ('ai_unspecified','other') else [])
 verified=[p for p in plans if p.get('status')=='verified']
 service['verification']={'schemaVersion':4,'identity':True,'priceObserved':bool(plans),'recurringPrice':any(p.get('amount',0)>0 and p.get('interval') in ('monthly','yearly') and p.get('evidence') for p in plans),'billingTerms':bool(verified),'regionConfirmed':any(p.get('region')=='KR' for p in verified),'paidScope':bool(service.get('purposeEvidence')),'checkedAt':timestamp}
 if service.get('origin')=='discovered':service['status']='verified' if verified else 'verified_identity'
 for plan in plans:
  plan['purpose']=service.get('purpose',plan.get('purpose'));plan['purposes']=service.get('purposes',[])
  plan['verification']={'price':True,'billingTerms':plan.get('commitmentMonths') is not None,'region':plan.get('region')!='unspecified'}
 return service

def vendor_normal_plans(page,service,timestamp):
 """An explicit monthly renewal statement disambiguates dual billing toggles."""
 if host(service['officialUrl']).removeprefix('www.')!='deepai.org':return []
 text=page.text
 monthly=re.search(r'\$([\d,.]+)\s+a\s+month\s*,\s*or\s*\$[\d,.]+\s+a\s+year',text,re.I)
 if not monthly or not re.search(r'billed monthly',text,re.I) or not re.search(r'cancel\s+any\s*time',text,re.I):return []
 amount=float(monthly[1].replace(',',''))
 matching=[s for s in page.sections if re.search(r'\bPro\b',s['title']) and re.search(r'\$'+re.escape(monthly[1])+r'\s*/\s*month',s['text'])]
 if not matching or not 0<amount<1e5:return []
 return [{'id':service['key']+'-regular-monthly','service':service['key'],'name':'Pro · 월간','amount':amount,'currency':'USD','interval':'monthly','region':'unspecified','taxBasis':'official_display','commitmentMonths':1,'introductory':False,'eligibility':'general','purpose':service.get('purpose'),'capabilities':{},'source':service['officialUrl'],'verifiedAt':timestamp,'status':'verified','evidence':[{'field':'amount','quote':monthly[0]},{'field':'billing','quote':'Billed monthly · cancel any time'}]}]

def identify_new(page,url,seeds,reference):
 if not reference:return None
 organizations=[item for item in flatten(page.jsonld) if item.get('@type') in ('Organization','Corporation')]
 products=[item for item in flatten(page.jsonld) if item.get('@type') in ('Product','SoftwareApplication','Service')]
 organization=next((item for item in organizations if safe_url(item.get('url')) and same_site(item['url'],url)),None)
 target=next((t for t in research_targets() if same_site(t['url'],url)),None)
 if not organization and target:
  legal=any(re.search(r'terms|privacy|이용약관|개인정보',href+' '+label,re.I) for href,label in page.links)
  brand=re.search(re.escape(target['name']),''.join(page.title)+' '+page.meta.get('og:site_name',''),re.I)
  if legal and brand:organization={'name':target['name'],'url':target['url']}
 if not organization:return None
 name=str(organization.get('name') or (products[0].get('name') if products else '') or '').strip()
 if target and target['name'].casefold() in ''.join(page.title).casefold():name=target['name']
 if not products:
  legal=any(re.search(r'terms|privacy|이용약관|개인정보',label,re.I) for _,label in page.links)
  if not legal or name.casefold() not in ''.join(page.title).casefold():return None
 elif not any(name.casefold() in str(product.get('name','')).casefold() or str(product.get('name','')).casefold() in name.casefold() for product in products):return None
 if not name or len(name)>80:return None
 for seed in seeds:
  if any(alias.casefold() in name.casefold() for alias in [seed['name'],*seed.get('aliases',[])] if len(alias)>=4) and not same_site(seed['officialUrl'],url):return None
 description=str((products[0].get('description') if products else None) or page.meta.get('description') or page.meta.get('og:description') or '')[:240]
 category=target['category'] if target else category_for(name+' '+description)
 return {'key':'discovered-'+hashlib.sha256(host(url).removeprefix('www.').encode()).hexdigest()[:12],'name':name,'category':category,'aliases':[name],'officialUrl':url,'officialHost':host(url),'origin':'discovered','status':'verified_identity','description':description,'discoveredFrom':reference,'purpose':('music_creation' if re.search(r'music generat|음악 생성|작곡',description,re.I) else 'image' if re.search(r'image generat|이미지 생성',description,re.I) else 'coding' if re.search(r'coding|code editor|코딩',description,re.I) else 'assistant' if re.search(r'chatbot|AI assistant|대화형|챗봇',description,re.I) else purpose_for(category)), 'identityEvidence':{'organizationName':name,'organizationUrl':organization['url'],'method':'curated_official_target_and_first_party_brand' if target else 'referring_site_and_first_party_structured_identity'}}

def expand_catalog(db,seeds,candidates,fetch,observed_price,timestamp,budget=16,extract_offer=None):
 for seed in seeds:db.execute('INSERT INTO service_catalog VALUES(?,?,?,?) ON CONFLICT(service_key) DO UPDATE SET payload=excluded.payload',(seed['key'],json.dumps(seed,ensure_ascii=False),timestamp,None))
 known={key:json.loads(payload) for key,payload in db.execute('SELECT service_key,payload FROM service_catalog')}
 cursor=int((db.execute("SELECT value FROM research_state WHERE key='catalog_cursor'").fetchone() or ['0'])[0]);priority=[s for s in known.values() if s.get('origin')=='discovered' and s.get('verification',{}).get('schemaVersion')!=4]
 selected=(priority+rotating([s for s in known.values() if s not in priority],cursor,max(0,budget-len(priority))))[:budget]
 results=[];new_count=0;verified_offers=[]
 known_hosts={item['officialHost'].removeprefix('www.') for item in known.values()}
 market_hosts={'appsumo.com','marketplace.sumo.com','stacksocial.com','www.stacksocial.com','slickdeals.net','dealmirror.com','dealify.com','www.ppomppu.co.kr','quasarzone.com'}
 # Pending discovery pages are revisited in later runs; a growing queue is not a fixed source list.
 cutoff=(dt.datetime.fromisoformat(timestamp.replace('Z','+00:00'))-dt.timedelta(days=1)).isoformat(timespec='seconds').replace('+00:00','Z')
 pending=list(db.execute("SELECT url,title,discovery_url FROM candidates WHERE scope='subscription' AND catalog_status NOT IN ('known','verified','rejected') AND (catalog_checked_at IS NULL OR catalog_checked_at<?) ORDER BY CASE WHEN provider='official_target' THEN 0 WHEN provider='vendor_link' THEN 1 ELSE 2 END,catalog_checked_at NULLS FIRST,first_seen LIMIT 28",(cutoff,)))
 for url,title,reference in pending:
  if host(url).removeprefix('www.') in known_hosts:
   db.execute("UPDATE candidates SET catalog_status='known',catalog_checked_at=? WHERE url=?",(timestamp,url));continue
  db.execute('UPDATE candidates SET catalog_checked_at=? WHERE url=?',(timestamp,url))
  try:
   reason=rejection_reason(url,title,seeds)
   if reason:
    db.execute("UPDATE candidates SET catalog_status='rejected',status='rejected',reason=? WHERE url=?",(reason,url));continue
   page=fetch(url)
   # Deal listing -> vendor website: the reseller itself is not registered as the subscription provider.
   if host(url) in market_hosts or host(url)=='news.google.com':
    external=[]
    for href,label in page.links:
     target=safe_url(urllib.parse.urljoin(url,href))
     if target and host(target) not in market_hosts and not rejection_reason(target,label,seeds) and re.search(r'website|visit site|official|developer|홈페이지|공식|pricing|offer|event|article|news',target+' '+label,re.I):external.append((target,label))
    for target,label in external[:3]:db.execute("INSERT OR IGNORE INTO candidates(url,title,provider,discovery_url,service_key,status,first_seen,last_seen,reason) VALUES(?,?,?,?,?,'pending',?,?,NULL)",(target,label,'article_link' if host(url)=='news.google.com' else 'vendor_link',url,match_service(target,label,seeds),timestamp,timestamp))
    db.execute("UPDATE candidates SET catalog_status='discovered_links' WHERE url=?",(url,));continue
   service=identify_new(page,url,seeds,reference)
   if not service:db.execute("UPDATE candidates SET catalog_status='needs_identity',reason='공식 사업자·구독 상품 증거 미확인' WHERE url=?",(url,));continue
   plans=structured_plans(page,service,timestamp)+text_plans(page,service,timestamp)+vendor_normal_plans(page,service,timestamp)
   if not plans:
    pricing=[safe_url(urllib.parse.urljoin(url,href)) for href,label in page.links if re.search(r'pricing|plans|요금|가격',label,re.I)]
    for target in [p for p in pricing if p and same_site(p,url)][:2]:
     pricing_page=fetch(target);service['officialUrl']=target;plans.extend(structured_plans(pricing_page,service,timestamp)+text_plans(pricing_page,service,timestamp)+vendor_normal_plans(pricing_page,service,timestamp))
     if plans:page=pricing_page;break
   if not plans:db.execute("UPDATE candidates SET catalog_status='needs_price',reason='정기 결제 요금 증거 미확인' WHERE url=?",(url,));continue
   service=enrich_service(service,page,plans,timestamp);service['verifiedAt']=timestamp;known[service['key']]=service;new_count+=1
   db.execute('INSERT OR REPLACE INTO service_catalog VALUES(?,?,?,?)',(service['key'],json.dumps(service,ensure_ascii=False),timestamp,timestamp))
   for plan in plans:db.execute('INSERT OR REPLACE INTO plan_facts VALUES(?,?,?,?)',(plan['id'],service['key'],json.dumps(plan,ensure_ascii=False),timestamp))
   db.execute("UPDATE candidates SET catalog_status='verified',status='catalog_verified',reason=NULL WHERE url=?",(url,))
  except Exception:db.execute("UPDATE candidates SET catalog_status='unavailable',reason='현재 페이지 접근 불가' WHERE url=?",(url,))
 for service in selected:
  try:
   page=fetch(service['officialUrl']);source={'id':service['key'],'category':service['category'],'purpose':service.get('purpose'),'url':service['officialUrl']};price=observed_price(source,page.text)
   if extract_offer:
    offer_source={**source,'service':service['key'],'name':service['name'],'parser':service['key'] if service['key'] in ('surfshark','adobe','spotify','apple-music','nordvpn') else 'event'}
    verified_offers.extend(as_offers(extract_offer(offer_source,page)))
   plans=normal_plan(source,page,price,timestamp)+structured_plans(page,service,timestamp)+text_plans(page,service,timestamp)+vendor_normal_plans(page,service,timestamp)
   service=enrich_service(service,page,plans,timestamp);known[service['key']]=service
   db.execute('UPDATE service_catalog SET payload=? WHERE service_key=?',(json.dumps(service,ensure_ascii=False),service['key']))
   for plan in plans:
    payload=json.dumps(plan,ensure_ascii=False);db.execute('INSERT OR REPLACE INTO plan_facts VALUES(?,?,?,?)',(plan['id'],service['key'],payload,timestamp));db.execute('INSERT INTO plan_history VALUES(?,?,?)',(plan['id'],payload,timestamp))
   db.execute('UPDATE service_catalog SET last_checked=? WHERE service_key=?',(timestamp,service['key']));results.append({'service':service['key'],'status':'checked','plans':len(plans)})
  except Exception:results.append({'service':service['key'],'status':'unavailable','plans':0})
 db.execute("INSERT OR REPLACE INTO research_state VALUES('catalog_cursor',?)",(str(cursor+budget),));db.commit()
 return {'checked':results,'newServices':new_count,'catalogSize':len(known),'verifiedOffers':verified_offers}
