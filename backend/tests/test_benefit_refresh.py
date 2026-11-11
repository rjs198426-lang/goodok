"""Regression cases for stalled benefit discovery; fixtures are abbreviated official facts."""
import datetime as dt,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
import collector as c
from discovery import clean_legacy_candidates
from factcheck import verify_candidates
from research_common import canonical_candidate,rejection_reason
from offer_identity import campaign_id

class BenefitRefreshTests(unittest.TestCase):
 def source(self,kind):
  return {'id':kind,'service':kind,'name':kind,'url':'https://vendor.example/offer','parser':kind,'discover':False}
 def test_adobe_current_wording_and_full_end_date(self):
  page=c.parse_html('<p>2026년 11월 2일에 시작하여 2026년 11월 13일에 종료됩니다. 한국 처음 구독. 첫해 60% 할인된 ₩34,800/월 부가세 포함. 12개월 구독 약정.</p>')
  offer=c.extract_all(self.source('adobe'),page)[0]
  self.assertEqual(offer['benefit'],'첫해 월 ₩34,800');self.assertEqual(offer['ends'],'2026-11-13');self.assertEqual(offer['starts'],'2026-11-02')
  self.assertIsNone(c.ending('11월 13일 종료'))
 def test_proton_prices_and_renewals_stay_with_their_plan(self):
  page=c.parse_html('<h1>Black Friday</h1><h2>VPN Plus</h2><p>Billed at $35.88 for the first 12 months, then renews at $83.88 every 12 months.</p><h2>Proton Unlimited</h2><p>Billed at $1.00 for the first month, then renews at $12.99 every month.</p><h2>Eligibility</h2>All new users are eligible')
  offers=c.extract_all(self.source('proton-black-friday'),page);self.assertEqual(len(offers),2)
  plus,unlimited=offers;self.assertEqual(plus['benefit'],'첫 12개월 $35.88');self.assertIn('$83.88',plus['conditions']);self.assertNotIn('$12.99',plus['conditions']);self.assertEqual(unlimited['benefit'],'첫 1개월 $1.00');self.assertIn('$12.99',unlimited['conditions']);self.assertNotEqual(campaign_id(plus),campaign_id(unlimited))
  self.assertTrue(all(o['ends'] is None and o['audience']['newCustomer'] for o in offers))
  page=c.parse_html('<h1>Black Friday</h1><h2>VPN Plus</h2>$2.99/month')
  self.assertEqual(c.extract_all(self.source('proton-black-friday'),page),[])
 def test_student_eligibility_is_preserved_and_needs_verification_terms(self):
  text="School email; confirm you're enrolled. 50% off Lovable Pro for up to 12 months. Only valid for users on the free plan."
  offer=c.extract_all(self.source('lovable-student'),c.parse_html(text))[0]
  self.assertEqual(offer['offerType'],'eligibility');self.assertTrue(offer['audience']['student']);self.assertIn('무료 플랜',offer['conditions']);self.assertIsNone(offer['ends'])
  self.assertEqual(c.extract_all(self.source('lovable-student'),c.parse_html('50% off Lovable Pro for up to 12 months')),[])
 def add_candidate(self,db,url,title,service='tool'):
  db.execute("INSERT INTO candidates(url,title,service_key,status,first_seen,last_seen,provider,scope) VALUES(?,?,?,'pending','2026-10-01','2026-10-01','Google','subscription')",(url,title,service))
 def test_tracker_cleanup_preserves_campaign_queries_and_original_audit(self):
  db=c.init_db(':memory:');url='https://vendor.example/offer?campaign=student&msockid=abc';self.add_candidate(db,url,'Discount')
  clean='https://vendor.example/offer?campaign=student';self.assertEqual(canonical_candidate(url),clean)
  clean_legacy_candidates(db,[])
  self.assertEqual(db.execute('SELECT reason FROM candidates WHERE url=?',(url,)).fetchone()[0],'tracking_alias')
  self.assertEqual(db.execute('SELECT first_seen FROM candidates WHERE url=?',(clean,)).fetchone()[0],'2026-10-01')
  clean_legacy_candidates(db,[]);self.assertEqual(db.execute('SELECT COUNT(*) FROM candidates').fetchone()[0],2);db.close()
 def test_official_login_is_rejected_before_host_trust(self):
  seeds=[{'key':'tool','officialUrl':'https://vendor.example/'}]
  for url in ('https://vendor.example/identity/login','https://vendor.example/Login.aspx','https://account.adobe.com/plans'):
   self.assertEqual(rejection_reason(url,'',seeds),'navigation_or_legal')
  self.assertIsNone(rejection_reason('https://vendor.example/offer-terms/discount.html','',seeds))
 def test_promo_queue_precedes_noise_and_shares_budget_across_services(self):
  db=c.init_db(':memory:');seeds=[{'key':s,'name':s,'officialUrl':f'https://{s}.example/'} for s in ('tool','other')]
  for n in range(20):self.add_candidate(db,f'https://tool.example/dictionary/{n}','SaaS definition')
  for n in range(8):self.add_candidate(db,f'https://tool.example/promo/{n}','Discount')
  self.add_candidate(db,'https://other.example/offer','Discount','other');seen=[]
  def fetch(url):seen.append(url);return c.parse_html('<title>Official</title>')
  result=verify_candidates(db,seeds,[],fetch,'2026-11-11T00:00:00Z',budget=4)
  self.assertEqual(result['checked'],2);self.assertTrue(all('/promo/' in u or '/offer' in u for u in seen));self.assertTrue(any('other.example' in u for u in seen));db.close()
 def test_reconfirmation_is_not_new_and_expiry_and_future_stay_hidden(self):
  db=c.init_db(':memory:');now=dt.datetime(2026,11,11,tzinfo=dt.timezone.utc)
  offer={'service':'tool','title':'Campaign','benefit':'30% 할인','detail':'Campaign','conditions':'new','source':'https://vendor.example/offer','publisher':'Official','ends':'2026-11-13','evidence':'30%'}
  def results(o):return [{'id':'tool','name':'Tool','status':'ok','offers':[o,o],'observations':[]}]
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'feed.json'
   first=c.store_and_export(db,results(offer),now,out,{});self.assertEqual(first['research']['benefitChanges'],{'new':1,'changed':0,'reconfirmed':0})
   second=c.store_and_export(db,results(offer),now+dt.timedelta(hours=1),out,{})
   self.assertEqual(second['research']['benefitChanges'],{'new':0,'changed':0,'reconfirmed':1});self.assertEqual(first['offers'][0]['firstSeen'],second['offers'][0]['firstSeen'])
   changed=c.store_and_export(db,results(dict(offer,benefit='40% 할인')),now+dt.timedelta(hours=2),out,{})
   self.assertEqual(changed['research']['benefitChanges']['changed'],1)
   self.assertEqual(c.store_and_export(db,results(offer),now+dt.timedelta(days=3),out,{})['offers'],[])
   self.assertEqual(c.store_and_export(db,results(dict(offer,starts='2026-11-16',ends=None)),now+dt.timedelta(days=4),out,{})['offers'],[])
  db.close()

if __name__=='__main__':unittest.main()
