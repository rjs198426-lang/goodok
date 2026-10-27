"""Plan-scoped, explicit capability facts; never infers speed or absent features."""
import re
def enrich_plan_capabilities(plans,page):
 for plan in plans:
  name=re.sub(r'\s*[·|]\s*(월간|연간).*','',plan.get('name','')).strip();sections=[s for s in page.sections if re.sub(r'\s+',' ',s['title']).strip().casefold()==name.casefold()]
  if not sections:continue
  text=' '.join(s['text'] for s in sections);caps=dict(plan.get('capabilities',{}));evidence=list(plan.get('evidence',[]))
  def put(key,value,quote):caps[key]=value;evidence.append({'field':'capability.'+key,'quote':quote[:180]})
  for key,pattern in [('files',r'file uploads?|파일\s*(?:업로드|분석)'),('images',r'image (?:analysis|generation)|이미지\s*(?:분석|생성)'),('codeIntegration',r'IDE integration|코드\s*편집기\s*연동'),('wireGuard',r'WireGuard'),('openVPN',r'OpenVPN'),('killSwitch',r'kill switch|킬\s*스위치'),('windows',r'Windows'),('mac',r'macOS'),('android',r'Android'),('ios',r'\biOS\b'),('commercialUse',r'commercial use (?:permitted|allowed)|상업적\s*이용\s*허용'),('desktopApps',r'desktop (?:Office )?apps|설치형\s*(?:Office|앱)')]:
   match=re.search(pattern,text,re.I)
   if match:
    context=text[max(0,match.start()-25):match.end()+35]
    negative=bool(re.search(r'\bno\b|not included|미지원|지원하지|사용할 수 없|제외',context,re.I));put(key,not negative,context)
  for key,pattern in [('devices',r'(\d{1,3})\s*(?:devices|대의?\s*기기)'),('familyMembers',r'(\d{1,2})\s*(?:people|family members|명의?\s*(?:가족|사용자))'),('refundDays',r'(\d{1,3})[ -]*(?:day|일).{0,20}(?:money.back|refund|환불)'),('messagesPerMonth',r'([\d,]+)\s*(?:messages|requests)\s*(?:per|/)\s*month')]:
   match=re.search(pattern,text,re.I)
   if match:put(key,int(match[1].replace(',','')),match[0])
  storage=re.search(r'(\d+(?:\.\d+)?)\s*(TB|GB)\s*(?:storage|저장)',text,re.I)
  if storage:put('storageGB',float(storage[1])*(1024 if storage[2].upper()=='TB' else 1),storage[0])
  context=re.search(r'([\d,]+)\s*([kKmM]?)\s*(?:token context|context tokens|토큰\s*문맥)',text,re.I)
  if context:put('contextTokens',int(context[1].replace(',',''))*{'':1,'k':1000,'m':1000000}[context[2].lower()],context[0])
  models=list(dict.fromkeys(re.findall(r'GPT-\d[\w.-]*|Claude\s+(?:Sonnet|Opus|Haiku)\s*[\d.]+|Gemini\s*[\d.]+\s*(?:Pro|Flash)|Grok\s*[\d.]+',text,re.I)))
  if models:put('modelNames',models,', '.join(models))
  servers=re.search(r'(?:servers? in|서버 제공 국가)\s*[:：]?\s*([A-Za-z ,]{3,160})',text,re.I)
  if servers:
   countries=[name for name in ['United States','United Kingdom','South Korea','Japan','Germany','France','Canada','Australia','Singapore'] if re.search(r'\b'+re.escape(name)+r'\b',servers[1],re.I)]
   if countries:put('countries',countries,servers[0])
  renewal=re.search(r'(?:renews?|renewal|갱신)[^₩$]{0,40}(₩|US\$|\$)\s*([\d,.]+)\s*(?:/|per)\s*(month|year|월|년)',text,re.I)
  if renewal:plan['renewal']={'amount':float(renewal[2].replace(',','')),'currency':'KRW' if renewal[1]=='₩' else 'USD' if renewal[1]=='US$' else 'unspecified','interval':'monthly' if renewal[3].lower() in ('month','월') else 'yearly','quote':renewal[0],'source':plan.get('source'),'verifiedAt':plan.get('verifiedAt')}
  plan.update(capabilities=caps,evidence=evidence)
 return plans
