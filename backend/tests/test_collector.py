import importlib.util,unittest,tempfile,datetime as dt,json
from pathlib import Path
spec=importlib.util.spec_from_file_location('collector',Path(__file__).parents[1]/'collector.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
class CollectorTests(unittest.TestCase):
 def test_parsing_rejects_unverified_and_expired_conditions(self):
  source={'id':'surfshark','service':'surfshark','name':'Surfshark','url':'https://surfshark.com/pricing','parser':'surfshark'}
  page=c.Page();page.feed('<script>sale price $1.00 for the first 27 months</script><p>Surfshark One sale price $67.23 for the first 27 months</p>');offer=c.extract(source,page);self.assertIn('67.23',offer['benefit'])
  page=c.Page();page.feed('<h1>Surfshark One+ sale price $1.00 for the first 27 months</h1>');self.assertIsNone(c.extract(source,page))
 def test_database_retains_verification_on_failure_and_removes_expiry(self):
  now=dt.datetime(2026,10,25,12,tzinfo=dt.timezone.utc)
  with tempfile.TemporaryDirectory() as tmp:
   db=c.init_db(Path(tmp)/'offers.sqlite');out=Path(tmp)/'feed.json'
   offer={'id':'one','service':'surfshark','title':'Offer','benefit':'$67.23','detail':'27 months','conditions':'tax','source':'https://surfshark.com/pricing','publisher':'Surfshark','ends':None,'evidence':'test'}
   results=[{'id':'surfshark','name':'Surfshark','status':'ok','offers':[offer],'observations':[{'url':offer['source'],'status':'verified'}]}]
   feed=c.store_and_export(db,results,now,out,{});verified=feed['offers'][0]['verifiedAt'];self.assertEqual(db.execute('SELECT COUNT(*) FROM offers').fetchone()[0],1)
   failed=[dict(results[0],status='unavailable',offers=[])];feed=c.store_and_export(db,failed,now+dt.timedelta(hours=1),out,{});self.assertEqual(feed['offers'][0]['verifiedAt'],verified)
   feed=c.store_and_export(db,failed,now+dt.timedelta(hours=73),out,{});self.assertEqual(feed['offers'],[]);self.assertEqual(json.loads(out.read_text())['schemaVersion'],1);db.close()
 def test_event_requires_explicit_ending_date(self):
  source={'id':'x','service':'x','name':'Official','url':'https://example.com/event','parser':'event'}
  page=c.Page();page.feed('<title>할인 이벤트</title><p>30% 할인</p>');self.assertIsNone(c.extract(source,page))
  page.feed('<p>2026년 10월 31일까지</p>');self.assertEqual(c.extract(source,page)['ends'],'2026-10-31')
 def test_price_extraction_does_not_relabel_free_trial_as_normal_price(self):
  self.assertEqual(c.observed_price({'id':'spotify'},'₩0에 1개월. 이후에는 ₩11,990 (부가세 포함)/월')['monthly'],11990)
if __name__=='__main__':unittest.main()
