"""Promotion identity independent of crawl source, tracking and Korean URL aliases."""
import datetime as dt,hashlib,json,re,unicodedata,urllib.parse

def normalized(value):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value or '')).strip()).lower()
def canonical_url(value):
 parsed=urllib.parse.urlsplit(value);host=(parsed.hostname or '').lower().removeprefix('www.')
 if parsed.port and parsed.port!=443:host+=':'+str(parsed.port)
 path=re.sub(r'^/(?:ko-kr|kr-ko|kr)(?=/|$)','/kr',parsed.path,flags=re.I).rstrip('/') or '/'
 pairs=sorted((k,v) for k,v in urllib.parse.parse_qsl(parsed.query,keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in {'gclid','fbclid','msclkid','_ga'})
 return host+path+('?'+urllib.parse.urlencode(pairs) if pairs else '')
def campaign_key(offer):
 service=normalized(offer.get('service'));title=normalized(offer.get('title') or offer.get('detail') or offer.get('benefit'));benefit=normalized(offer.get('benefit'));slot=title
 if offer.get('campaignId'):slot='campaign:'+normalized(offer['campaignId'])
 elif service=='spotify' and '개인' in title and ('체험' in title or 'trial' in title):slot='premium-individual-trial'
 elif service=='apple-music' and '개인' in title and ('신규' in title or '체험' in title):slot='individual-trial'
 elif service=='surfshark' and re.search(r'\bsurfshark\s+one\b(?!\s*\+)',title):slot='surfshark-one-intro'
 elif service=='nordvpn' and re.match(r'basic\b',benefit):slot='basic-intro'
 elif service=='adobe' and 'creative cloud' in title and ('모든 앱' in title or 'all apps' in title):slot='all-apps-intro'
 return json.dumps([service,canonical_url(offer.get('source','')),slot,normalized(offer.get('planId')),normalized(offer.get('eligibility')),normalized(offer.get('region'))],ensure_ascii=False,separators=(',',':'))
def campaign_id(offer):return hashlib.sha256(campaign_key(offer).encode()).hexdigest()[:24]
def verification_time(value):
 try:return dt.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
 except (ValueError,TypeError,AttributeError):return float('-inf')
def deduplicate_offers(offers):
 newest={}
 for offer in offers:
  key=campaign_key(offer);old=newest.get(key)
  score=(verification_time(offer.get('verifiedAt') or offer.get('checked')), -len(offer.get('source','')))
  if old is None or score>(verification_time(old.get('verifiedAt') or old.get('checked')),-len(old.get('source',''))):newest[key]=offer
 return sorted(newest.values(),key=lambda offer:verification_time(offer.get('verifiedAt') or offer.get('checked')),reverse=True)
def compact_offers(db):
 """Archive original observations and keep only each campaign's last verified payload."""
 newest={};first_seen={};rows=list(db.execute('SELECT id,source_id,payload,first_seen,last_verified FROM offers ORDER BY last_verified DESC,id'))
 for old_id,source,payload,first,last in rows:
  offer=json.loads(payload);key=campaign_key(offer);identity=campaign_id(offer)
  db.execute('INSERT OR IGNORE INTO offer_history VALUES(?,?,?,?,?)',(old_id,key,payload,last,source))
  if identity not in first_seen or first<first_seen[identity]:first_seen[identity]=first
  old=newest.get(identity)
  score=(verification_time(last),-len(offer.get('source','')))
  if old is None or score>old[0]:
   offer['id']=identity;newest[identity]=(score,source,json.dumps(offer,ensure_ascii=False),last)
 db.execute('DELETE FROM offers')
 db.executemany('INSERT INTO offers VALUES(?,?,?,?,?)',[(identity,value[1],value[2],first_seen[identity],value[3]) for identity,value in newest.items()])
 return len(rows)-len(newest)
