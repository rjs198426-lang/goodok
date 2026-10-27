"""Optional official search APIs. Credentials never enter URLs, logs or app feeds."""
import os,json,re,urllib.request,urllib.parse,html
def configured_providers():
 return [p for p,ready in [('Google',bool(os.environ.get('GOOGLE_SEARCH_API_KEY') and os.environ.get('GOOGLE_SEARCH_ENGINE_ID'))),('Naver',bool(os.environ.get('NAVER_CLIENT_ID') and os.environ.get('NAVER_CLIENT_SECRET')))] if ready]
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None
def search_api(provider,query):
 if provider=='Naver':url='https://openapi.naver.com/v1/search/webkr.json?'+urllib.parse.urlencode({'query':query,'display':10});headers={'X-Naver-Client-Id':os.environ['NAVER_CLIENT_ID'],'X-Naver-Client-Secret':os.environ['NAVER_CLIENT_SECRET']}
 elif provider=='Google':url='https://www.googleapis.com/customsearch/v1?'+urllib.parse.urlencode({'q':query,'cx':os.environ['GOOGLE_SEARCH_ENGINE_ID'],'num':10});headers={'X-Goog-Api-Key':os.environ['GOOGLE_SEARCH_API_KEY']}
 else:raise ValueError('unsupported provider')
 headers.update({'Accept':'application/json','User-Agent':'DalfitResearch/4.0'})
 with urllib.request.build_opener(NoRedirect()).open(urllib.request.Request(url,headers=headers),timeout=15) as response:
  payload=response.read(1024*1024+1)
  if len(payload)>1024*1024:raise ValueError('oversize')
 data=json.loads(payload)
 if not isinstance(data,dict) or 'error' in data:raise ValueError('search API unavailable')
 return [(item['link'],html.unescape(re.sub('<[^>]+>','',item.get('title','')))) for item in data.get('items',[]) if isinstance(item,dict) and isinstance(item.get('link'),str) and isinstance(item.get('title'),str)][:10]
