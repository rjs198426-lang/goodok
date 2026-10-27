"""Publish one stable catalogue per Korea-time 01:00 boundary."""
import datetime as dt,json,re
KST=dt.timezone(dt.timedelta(hours=9))
def release_day(timestamp):
 now=dt.datetime.fromisoformat(timestamp.replace('Z','+00:00')).astimezone(KST)
 return (now-dt.timedelta(hours=1)).date().isoformat()
def publish_catalog(db,catalog,timestamp):
 day=release_day(timestamp);row=db.execute("SELECT value FROM research_state WHERE key='published_catalog'").fetchone()
 previous=json.loads(row[0]) if row else None
 if previous and previous.get('version','')>=day:return previous
 services=[dict(s) for s in catalog if s.get('status') in ('verified','verified_identity') and (s.get('origin')=='seed' or s.get('status')=='verified' and s.get('verification',{}).get('billingTerms') is True)]
 categories=[{'name':name,'kind':'subscription','count':sum(s.get('category')==name for s in services)} for name in sorted({s.get('category','') for s in services}) if re.fullmatch(r'[가-힣a-zA-Z0-9 ·_-]{1,16}',name)]
 result={'version':day,'publishedAt':timestamp,'timezone':'Asia/Seoul','scheduledTime':'01:00','categories':categories,'services':services}
 db.execute("INSERT OR REPLACE INTO research_state VALUES('published_catalog',?)",(json.dumps(result,ensure_ascii=False),));db.commit();return result
