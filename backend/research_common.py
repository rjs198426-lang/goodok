"""Shared URL, evidence and queue rules. No search result establishes a fact."""
import datetime as dt,re,urllib.parse,unicodedata

def time_after(stamp,hours):
 return (dt.datetime.fromisoformat(stamp.replace('Z','+00:00'))+dt.timedelta(hours=hours)).isoformat(timespec='seconds').replace('+00:00','Z')

def host(url):return (urllib.parse.urlsplit(url).hostname or '').lower().removeprefix('www.')
def same_site(a,b):return bool(host(a)) and host(a)==host(b)
def norm(value):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value or ''))).strip()

def canonical_candidate(url):
 from discovery import safe_url
 if not safe_url(url):return None
 p=urllib.parse.urlsplit(url)
 pairs=[(k,v) for k,v in urllib.parse.parse_qsl(p.query,keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in {'gclid','fbclid','msclkid','_ga'}]
 return urllib.parse.urlunsplit(('https',p.netloc.lower(),p.path or '/',urllib.parse.urlencode(pairs),''))

def rejection_reason(url,title='',seeds=()):
 if not canonical_candidate(url):return 'invalid_url'
 h=host(url);p=urllib.parse.urlsplit(url);path=p.path.lower()
 if any(same_site(url,s.get('officialUrl','')) for s in seeds):return None
 if h=='news.google.com' and re.match(r'^/(rss/)?articles/',path):return None
 if h in {'google.com','bing.com','search.naver.com','map.naver.com','dict.naver.com','ader.naver.com','search.shopping.naver.com','translate.google.com','accounts.google.com','policies.google.com','support.google.com'}:return 'search_navigation'
 if h.endswith(('.google.com','.bing.com')):return 'search_navigation'
 if h in {'wikipedia.org','en.wikipedia.org','ko.wikipedia.org','facebook.com','instagram.com','linkedin.com','youtube.com','apkmirror.com','apkpure.com','reddit.com'}:return 'non_supplier_page'
 if re.search(r'/(?:login|signin|signup|privacy|terms|contact|about-us|cart|checkout)(?:/|$)',path):return 'navigation_or_legal'
 if norm(title).casefold() in {'더보기','전체','뉴스','이미지','지도','사전','쇼핑','로그인','회원가입','검색','검색결과','privacy','terms','sign in','learn more','read more','next','previous'}:return 'navigation_label'
 return None

def match_service(url,title,seeds):
 direct=next((s for s in seeds if same_site(url,s.get('officialUrl',''))),None)
 if direct:return direct['key']
 text=norm(title).casefold();matches=[]
 for s in seeds:
  for alias in [s['name'],*s.get('aliases',[])]:
   alias=norm(alias).casefold()
   if len(alias)<3:continue
   pattern=(r'(?<![a-z0-9])'+re.escape(alias)+r'(?![a-z0-9])') if re.search('[a-z]',alias) else re.escape(alias)
   if re.search(pattern,text):matches.append((len(alias),s['key']))
 return max(matches,default=(0,None))[1]

def as_offers(value):return value if isinstance(value,list) else [value] if value else []
