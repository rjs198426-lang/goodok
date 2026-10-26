import unittest,tempfile,json,datetime as dt
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]))
import collector as c
from offer_identity import campaign_key,campaign_id,deduplicate_offers,compact_offers

def offer(**changes):
 return dict(dict(id='legacy',service='spotify',title='Spotify 한국 개인 요금제 체험',benefit='Premium 개인 1개월 ₩0',detail='개인 체험',conditions='이후 월 11990',source='https://www.spotify.com/kr/premium/',publisher='Spotify',ends=None,verifiedAt='2026-10-26T05:00:00Z',checked='2026-10-26',evidence='official'),**changes)
class OfferIdentityTests(unittest.TestCase):
 def test_url_alias_tracking_and_latest_atomic_payload(self):
  old=offer();new=offer(id='discovery',source='https://spotify.com/kr-ko/premium/?utm_source=naver#top',benefit='Premium 개인 2개월 ₩0',conditions='새 대상 조건',verifiedAt='2026-10-26T06:00:00Z')
  self.assertEqual(campaign_key(old),campaign_key(new));self.assertEqual(deduplicate_offers([new,old]),[new]);self.assertEqual(deduplicate_offers([old,new]),[new])
 def test_distinct_plan_campaign_region_or_coupon_not_merged(self):
  base=offer();variants=[offer(title='Spotify 한국 가족 요금제 체험'),offer(source=base['source']+'?coupon=ABC'),offer(source=base['source']+'?coupon=DEF'),offer(planId='student'),offer(region='US'),offer(service='different')]
  self.assertEqual(len({campaign_key(item) for item in [base]+variants}),7)
 def test_storage_migrates_legacy_ids_and_updates_without_new_verification_on_failure(self):
  now=dt.datetime(2026,10,26,6,tzinfo=dt.timezone.utc)
  with tempfile.TemporaryDirectory() as tmp:
   db=c.init_db(Path(tmp)/'offers.sqlite');old=offer();new=offer(id='legacy2',source='https://www.spotify.com/kr-ko/premium/',benefit='Premium 개인 2개월 ₩0')
   db.execute('INSERT INTO offers VALUES(?,?,?,?,?)',('legacy','seed',json.dumps(old),'2026-10-24T00:00:00Z','2026-10-26T04:00:00Z'))
   db.execute('INSERT INTO offers VALUES(?,?,?,?,?)',('legacy2','discovered',json.dumps(new),'2026-10-25T00:00:00Z','2026-10-26T05:00:00Z'));db.commit()
   failed=[dict(id='spotify',name='Spotify',status='unavailable',offers=[],observations=[])]
   result=c.store_and_export(db,failed,now,Path(tmp)/'feed.json',{});self.assertEqual(len(result['offers']),1);winner=result['offers'][0];self.assertEqual(winner['id'],campaign_id(old));self.assertEqual(winner['benefit'],new['benefit']);self.assertEqual(winner['firstSeen'],'2026-10-24T00:00:00Z');self.assertEqual(winner['verifiedAt'],'2026-10-26T05:00:00Z');self.assertEqual(db.execute('SELECT COUNT(*) FROM offer_history').fetchone()[0],2)
   updated=offer(id='changing-source',benefit='Premium 개인 3개월 ₩0',conditions='갱신된 조건');success=[dict(failed[0],status='ok',offers=[updated])];result=c.store_and_export(db,success,now+dt.timedelta(hours=1),Path(tmp)/'feed.json',{});self.assertEqual(len(result['offers']),1);self.assertEqual(result['offers'][0]['benefit'],updated['benefit']);self.assertEqual(result['offers'][0]['conditions'],updated['conditions']);self.assertEqual(db.execute('SELECT COUNT(*) FROM offers').fetchone()[0],1)
   ended=offer(ends='2026-10-25');success=[dict(failed[0],status='ok',offers=[ended])];result=c.store_and_export(db,success,now+dt.timedelta(hours=2),Path(tmp)/'feed.json',{});self.assertEqual(result['offers'],[]);db.close()
if __name__=='__main__':unittest.main()
