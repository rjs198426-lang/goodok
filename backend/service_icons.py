"""Collect first-party brand icons as bounded, offline PNGs; never execute downloaded SVGs."""
import base64,concurrent.futures,datetime as dt,hashlib,io,json,re,warnings,xml.etree.ElementTree as ET
from urllib.parse import urljoin,urlsplit
from pathlib import Path
from research_common import time_after
import retrieval

# Curated artwork is used only for the named official domain, never guessed from a search result.
CURATED={
 'todoist.com':'https://raw.githubusercontent.com/homarr-labs/dashboard-icons/main/svg/todoist.svg',
 'webflow.com':'https://raw.githubusercontent.com/homarr-labs/dashboard-icons/main/svg/webflow.svg',
}
CATEGORY_STYLES={
 'AI':('category-0','#a93754'),'OTT':('category-1','#d52d3a'),'쇼핑':('category-2','#e16957'),
 '통신·결합':('category-3','#c44781'),'VPN':('category-4','#9d657d'),'생산성':('category-5','#bd7a87'),
 '카카오':('category-6','#d2a364'),'음악':('category-7','#f07882'),'학습':('category-8','#b592a6'),
 '콘텐츠':('category-9','#cd939d'),'생활':('category-10','#efb2a7'),'기타':('category-11','#d3c0c8'),
 '웹·호스팅':('category-hosting','#657aa4'),'업무 자동화':('category-automation','#8869a7'),
 '보안':('category-security','#628a87'),'백업':('category-backup','#6b88a7'),
 '음성·오디오':('category-audio','#b36e8a'),'영상 제작':('category-video','#9a769b'),
 '디자인':('category-design','#bb7967'),'독서·지식':('category-reading','#729787'),
 '개발 도구':('category-code','#7082a3'),
}
def category_style(name):
 icon,color=CATEGORY_STYLES.get(name,('category-11','#b56d87'))
 return {'icon':icon,'color':color}

def normalize_image(raw):
 """Re-encode to pixels: no SVG/script/URL reaches the device or resulting PNG."""
 if not raw or len(raw)>2*1024*1024:raise ValueError('icon_size')
 if b'<svg' in raw[:4096].lower():
  if len(raw)>256*1024:raise ValueError('icon_size')
  if re.search(br'<!DOCTYPE|<!ENTITY|<\?xml-stylesheet|@import|@font-face|xml:base|\\|url\(\s*[\'"]?(?!#)[^\s)]',raw,re.I):raise ValueError('external_svg')
  root=ET.fromstring(raw)
  if root.tag.split('}')[-1]!='svg':raise ValueError('not_svg')
  for node in root.iter():
   if node.tag.split('}')[-1] in ('script','foreignObject','image','animate','animateTransform','set'):raise ValueError('active_svg')
   for key,value in node.attrib.items():
    if key.split('}')[-1].lower().startswith('on') or key.split('}')[-1]=='href' and not value.startswith('#'):raise ValueError('active_svg')
  import cairosvg
  raw=cairosvg.svg2png(bytestring=raw,output_width=96,output_height=96)
 from PIL import Image
 with warnings.catch_warnings():
  warnings.simplefilter('error',Image.DecompressionBombWarning)
  with Image.open(io.BytesIO(raw)) as image:
   if image.width<8 or image.height<8 or image.width*image.height>4096*4096:raise ValueError(f'icon_dimensions_{image.width}x{image.height}')
   image=image.convert('RGBA');image.thumbnail((96,96),Image.Resampling.LANCZOS)
   canvas=Image.new('RGBA',(96,96));canvas.alpha_composite(image,((96-image.width)//2,(96-image.height)//2))
   if not canvas.getbbox():raise ValueError('empty_icon')
   result=io.BytesIO();canvas.quantize(colors=96,method=Image.Quantize.FASTOCTREE).save(result,format='PNG',optimize=True)
 data=result.getvalue()
 if len(data)>7500:raise ValueError('icon_size')
 return data

def icon_candidates(service,fetch):
 page_url=service['officialUrl'];parts=urlsplit(page_url);root=f'https://{parts.netloc}/';domain=parts.hostname.removeprefix('www.')
 candidates=[]
 if domain in CURATED:candidates.append((CURATED[domain],'curated_brand_artwork'))
 for url in dict.fromkeys([page_url,root]):
  try:
   page=fetch(url)
   for icon in sorted(getattr(page,'icons',[]),key=lambda i:0 if 'apple-touch-icon' in i['rel'] else 1):
    asset=urljoin(url,icon['href'])
    if asset.startswith('https:'):candidates.append((asset,'official_site_icon'))
   if candidates:break
  except Exception:pass
 for name in ('favicon.ico','apple-touch-icon.png'):candidates.append((urljoin(root,name),'official_site_icon'))
 return list(dict.fromkeys(candidates))[:5]

def init_icons(db):
 db.execute('CREATE TABLE IF NOT EXISTS service_icons(service TEXT PRIMARY KEY,payload TEXT,checked_at TEXT,next_check_at TEXT,last_error TEXT)');db.commit()

def collect_icons(db,catalog,fetch,timestamp,limit=24):
 init_icons(db)
 revision=db.execute("SELECT value FROM research_state WHERE key='icon_parser_revision'").fetchone()
 if not revision or revision[0]!='3':
  db.execute("UPDATE service_icons SET next_check_at=NULL WHERE last_error LIKE '%response_too_large%' OR last_error LIKE '%icon_dimensions%'")
  db.execute("INSERT OR REPLACE INTO research_state VALUES('icon_parser_revision','3')");db.commit()
 previous={key:{'icon':json.loads(payload) if payload else None,'due':due} for key,payload,due in db.execute('SELECT service,payload,next_check_at FROM service_icons')}
 eligible=[s for s in catalog if s.get('status') in ('verified','verified_identity') and (s.get('origin')=='seed' or s.get('verification',{}).get('recurringPrice') is True)]
 pending=sorted((s for s in eligible if not previous.get(s['key'],{}).get('due') or previous[s['key']]['due']<=timestamp),key=lambda s:(bool(previous.get(s['key'],{}).get('icon')),s.get('origin')=='seed',s['key']))[:limit]
 def investigate(service):
  failures=[]
  for url,method in icon_candidates(service,fetch):
   try:
    raw,_,_=retrieval.download(url,'image/png,image/svg+xml,image/x-icon,image/webp',2*1024*1024,timeout=7)
    png=normalize_image(raw);digest=hashlib.sha256(png).hexdigest()
    return service['key'],{'data':'data:image/png;base64,'+base64.b64encode(png).decode(),'sha256':digest,'source':url,'method':method,'checkedAt':timestamp,'width':96,'height':96},None
   except Exception as exc:failures.append(retrieval.error_code(exc) if not isinstance(exc,ValueError) else str(exc))
  return service['key'],None,','.join(dict.fromkeys(failures))[:300] or 'no_icon'
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(investigate,pending))
 for key,icon,error in results:
  saved=icon or previous.get(key,{}).get('icon')
  db.execute('INSERT OR REPLACE INTO service_icons VALUES(?,?,?,?,?)',(key,json.dumps(saved) if saved else None,timestamp,time_after(timestamp,24*30 if icon else 6),error))
 icons={key:json.loads(payload) for key,payload in db.execute('SELECT service,payload FROM service_icons WHERE payload IS NOT NULL')}
 for service in catalog:
  if service['key'] in icons:service['icon']=icons[service['key']]
  db.execute('UPDATE service_catalog SET payload=? WHERE service_key=?',(json.dumps(service,ensure_ascii=False),service['key']))
 db.commit()
 return {'attempted':len(pending),'updated':sum(bool(icon) for _,icon,_ in results),'available':len(icons),'failures':[{'service':key,'reason':err} for key,icon,err in results if err]}

def refresh_only(database,output):
 """Backfill icons without changing offer, price or feature verification timestamps."""
 import sqlite3
 from collector import fetch
 from catalog_publish import publish_catalog
 db=sqlite3.connect(database);feed=json.loads(Path(output).read_text());catalog=[json.loads(r[0]) for r in db.execute('SELECT payload FROM service_catalog')]
 timestamp=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z');retrieval.configure(db,[s['officialUrl'] for s in catalog])
 report=collect_icons(db,catalog,fetch,timestamp,limit=100)
 feed.update(catalog=catalog,catalogUpdate=publish_catalog(db,catalog,timestamp),iconsUpdatedAt=timestamp)
 feed.setdefault('research',{})['icons']=report
 target=Path(output);temp=target.with_suffix('.tmp');temp.write_text(json.dumps(feed,ensure_ascii=False,indent=2)+'\n');temp.replace(target);db.close();print(json.dumps(report))

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--database',default=str(Path(__file__).parent/'data/benefits.sqlite'));parser.add_argument('--output',default=str(Path(__file__).parent/'data/feed.json'));args=parser.parse_args();refresh_only(args.database,args.output)
