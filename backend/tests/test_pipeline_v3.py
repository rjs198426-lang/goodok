import json,sqlite3,unittest,tempfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]))
import collector as c
from discovery import run_discovery,news_links,init_discovery,clean_legacy_candidates
from research_common import rejection_reason,match_service
from factcheck import verify_candidates
from catalog_engine import text_plans,structured_plans,enrich_service,vendor_normal_plans
from taste_research import extract_activity,research_taste,export_taste
from research_report import write_report
NOW='2026-10-27T14:00:00Z'
SEEDS=[{'key':'new','name':'NewTool','aliases':['NewTool'],'officialUrl':'https://vendor.example/pricing','officialHost':'vendor.example','category':'AI'}]
def page(text):
 p=c.Page();p.feed(text);return p
class PipelineV3Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=c.init_db(Path(self.tmp.name)/'test.sqlite')
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def candidate(self,url,title='Unknown service',service=None,scope='subscription',**extra):
  self.db.execute("INSERT INTO candidates(url,title,provider,discovery_url,service_key,status,first_seen,last_seen,scope) VALUES(?,?,?, ?,?,'pending',?,?,?)",(url,title,'Google','https://search.example/query',service,'2026-10-25T00:00:00Z',NOW,scope));self.db.commit()
  for k,v in extra.items():self.db.execute('UPDATE candidates SET '+k+'=? WHERE url=?',(v,url))
 def test_legacy_migration_is_additive_and_idempotent(self):
  self.candidate('https://vendor.example/event','NewTool',service='new');init_discovery(self.db)
  self.assertEqual(self.db.execute('SELECT first_seen FROM candidates').fetchone()[0],'2026-10-25T00:00:00Z')
 def test_navigation_ads_and_false_brand_domain_matches_are_removed(self):
  for url in ['https://map.naver.com/v5/search/test','https://dict.naver.com/search?q=AI','https://ader.naver.com/v1/token','https://en.wikipedia.org/wiki/AI','https://www.apkmirror.com/apk/test']:
   self.assertIsNotNone(rejection_reason(url,'NewTool discount',SEEDS))
  self.assertIsNone(rejection_reason('https://vendor.example/event','NewTool discount',SEEDS))
  self.assertIsNone(match_service('https://unknown.example/naver','not NewToolbox',SEEDS))
 def test_legacy_noise_is_quarantined_not_deleted(self):
  self.candidate('https://map.naver.com/v5/search/test');self.assertEqual(clean_legacy_candidates(self.db,SEEDS),1)
  row=self.db.execute('SELECT status,first_seen FROM candidates').fetchone();self.assertEqual(row,('rejected','2026-10-25T00:00:00Z'))
 def test_longer_brand_alias_wins(self):
  seeds=[{'key':'copilot','name':'Copilot','aliases':[],'officialUrl':'https://copilot.example/'},{'key':'github','name':'GitHub Copilot','aliases':[],'officialUrl':'https://github.example/'}]
  self.assertEqual(match_service('https://deals.example/article','GitHub Copilot discount',seeds),'github')
 def test_unknown_old_leads_cannot_starve_known_lead(self):
  for i in range(30):self.candidate('https://a.example/'+str(i))
  self.candidate('https://vendor.example/event','NewTool official',service='new')
  result=verify_candidates(self.db,SEEDS,[],lambda u:page('<title>할인 이벤트</title>30% 할인 2026년 11월 30일까지'),NOW,budget=1,extract_offer=c.extract_all)
  self.assertEqual(result['checked'],1);self.assertEqual(result['confirmed'],1);self.assertEqual(result['unmatched'],30)
 def test_due_time_defers_failed_and_successful_leads(self):
  self.candidate('https://vendor.example/event','NewTool',service='new');calls=[]
  def unavailable(u):calls.append(u);raise OSError('offline')
  first=verify_candidates(self.db,SEEDS,[],unavailable,NOW);second=verify_candidates(self.db,SEEDS,[],unavailable,NOW)
  self.assertEqual(first['checked'],1);self.assertEqual(second['checked'],0);self.assertEqual(len(calls),1)
  self.assertEqual(self.db.execute('select check_attempts from candidates').fetchone()[0],1)
 def test_unrelated_official_page_does_not_reconfirm_an_old_campaign(self):
  self.candidate('https://vendor.example/help','NewTool help',service='new')
  old={'service':'new','source':'https://vendor.example/event','benefit':'30% 할인','evidence':'30% 할인'}
  result=verify_candidates(self.db,SEEDS,[old],lambda u:page('<title>Help</title>Support and FAQ'),NOW,extract_offer=c.extract_all)
  self.assertEqual(result['confirmed'],0);self.assertEqual(result['verifiedOffers'],[])
 def test_rss_keeps_article_url_not_publisher_homepage(self):
  links=news_links('<rss><channel><item><title>NewTool</title><link>https://news.google.com/rss/articles/ABC</link><source url="https://publisher.example/">Publisher</source></item></channel></rss>')
  self.assertEqual(links[0][0],'https://news.google.com/rss/articles/ABC');self.assertEqual(links[0][2],'https://publisher.example/')
 def test_blocked_provider_is_not_hammered_and_taste_queries_are_independent(self):
  calls=[]
  def fetch(url):calls.append(url);return page('captcha' if 'naver.com' in url else '<a href="https://vendor.example/event">NewTool discount</a>')
  attempts,found=run_discovery(self.db,SEEDS,fetch,NOW,fetch_xml=lambda u:'<rss/>')
  self.assertEqual(sum('search.naver.com' in u for u in calls),1)
  self.assertTrue(any(a['status']=='deferred' and a['provider']=='Naver' for a in attempts));self.assertTrue(any(a['scope']=='taste' for a in attempts))
 def test_apple_device_and_family_campaigns_remain_distinct(self):
  source={'id':'apple-music','service':'apple-music','name':'Apple','url':'https://www.apple.com/kr/apple-music/','parser':'apple-music'}
  p=page('<h2>신규 구독자</h2>1개월 무료<h2>가족 요금제</h2>1개월 무료<h2>신규 기기</h2>3개월 무료 적용 대상 기기를 구입했다면<h2>개인</h2>₩8,900/월<h2>가족</h2>₩13,500/월')
  offers=c.extract_all(source,p);self.assertEqual(len(offers),3);self.assertEqual(len({c.campaign_id(o) for o in offers}),3)
  self.assertEqual({o.get('eligibility') for o in offers},{None,'eligible_device','new_family'})
 def test_two_dated_events_on_one_page_are_not_collapsed(self):
  source={'id':'new','service':'new','name':'New','url':'https://vendor.example/event','parser':'event'}
  offers=c.extract_all(source,page('<title>혜택 이벤트</title><h2>신규 할인 이벤트</h2>30% 할인 2026년 11월 30일까지<h2>가족 할인 이벤트</h2>20% 할인 2026년 12월 31일까지'))
  self.assertEqual(len(offers),2);self.assertEqual({o['ends'] for o in offers},{'2026-11-30','2026-12-31'})
 def test_unproven_billing_does_not_become_verified_catalogue(self):
  p=page('<title>Pricing</title><h2>Pro</h2>₩12,000/월')
  plans=text_plans(p,SEEDS[0],NOW);self.assertEqual(plans[0]['status'],'candidate')
  service=enrich_service(dict(SEEDS[0],origin='discovered'),p,plans,NOW)
  self.assertEqual(service['status'],'verified_identity');self.assertFalse(service['verification']['billingTerms'])
 def test_structured_unknown_commitment_is_not_verified(self):
  p=page('<script type="application/ld+json">{"@type":"Product","name":"Pro","offers":{"priceSpecification":{"price":12000,"priceCurrency":"KRW","billingDuration":"P1M"}}}</script>')
  self.assertEqual(structured_plans(p,SEEDS[0],NOW)[0]['status'],'candidate')
 def test_paid_bundle_uses_multiple_purposes_and_skips_free_meta_description(self):
  p=page('<meta name="description" content="Free AI coding agent"><h2>Pro</h2><p>$9.99/month billed monthly · cancel any time. 500 HD images, 2000 chat messages, DeepAI Code, AI-generated songs.</p>')
  service={'key':'deepai','name':'DeepAI','category':'AI','purpose':'coding','origin':'discovered','officialUrl':'https://deepai.org/pricing'}
  plans=text_plans(p,service,NOW);enriched=enrich_service(service,p,plans,NOW)
  self.assertEqual(plans[0]['amount'],9.99);self.assertEqual(plans[0]['status'],'verified');self.assertEqual(enriched['purpose'],'assistant')
  self.assertTrue({'assistant','image','coding','music_creation'}<=set(enriched['purposes']));self.assertFalse(enriched['verification']['regionConfirmed'])
 def test_annual_equivalent_price_is_rejected(self):
  p=page('<h2>Pro</h2>$5/month billed annually cancel anytime')
  self.assertEqual(text_plans(p,{'key':'deepai','category':'AI','officialUrl':'https://deepai.org/pricing'},NOW),[])
 def test_monthly_renewal_must_corroborate_dual_billing_toggle(self):
  p=page('<h1>DeepAI Pro Pricing Overview</h1>Pro $7.50$9.99/month Billed annually at $89.99 Billed monthly cancel any time.<h2>Renewal</h2>Your price remains the same ($9.99 a month, or $89.99 a year).')
  service={'key':'deepai','name':'DeepAI','category':'AI','officialUrl':'https://deepai.org/pricing'}
  self.assertEqual(vendor_normal_plans(p,service,NOW)[0]['amount'],9.99)
  service['officialUrl']='https://fake.example/pricing';self.assertEqual(vendor_normal_plans(p,service,NOW),[])
 def test_free_features_are_not_paid_bundle_evidence(self):
  p=page('<h1>DeepAI Pro Pricing Overview</h1>Free AI coding agent Pro Everything DeepAI makes, in one subscription. $9.99/month Billed monthly cancel any time. 500 HD images, 2000 chat messages. What\'s in each plan')
  service={'key':'deepai','category':'AI','origin':'discovered','officialUrl':'https://deepai.org/pricing'}
  enriched=enrich_service(service,p,[{'status':'verified','commitmentMonths':1,'region':'unspecified'}],NOW)
  self.assertEqual(set(enriched['purposes']),{'assistant','image'});self.assertTrue(all('Free' not in e['quote'] for e in enriched['purposeEvidence']))
 def test_official_activity_requires_current_dates_and_never_fabricates_price(self):
  p=page('<script type="application/ld+json">{"@type":"Event","name":"새 전시","startDate":"2026-10-01","endDate":"2026-11-30"}</script>')
  result=extract_activity(p,'https://www.museum.go.kr/exhibit/detail/1',NOW);self.assertEqual(result['status'],'official_verified');self.assertNotIn('price',result)
  self.assertIsNone(extract_activity(p,'https://deals.example/exhibit/1',NOW));self.assertIsNone(extract_activity(p,'https://www.museum.go.kr/exhibit/detail/1','2027-01-01T00:00:00Z'))
 def test_taste_free_is_explicit_and_undated_lists_are_not_events(self):
  p=page('<title>가을 전시 관람</title><p>2026.10.01 ~ 2026.11.30 관람료 무료</p>')
  result=extract_activity(p,'https://www.mmca.go.kr/exhibit/1',NOW);self.assertEqual(result['price'],0)
  self.assertIsNone(extract_activity(page('<title>전시 안내</title>상시 전시를 확인하세요'),'https://www.mmca.go.kr/exhibitions',NOW))
 def test_verified_taste_is_stored_separately_and_expires(self):
  self.candidate('https://www.museum.go.kr/exhibit/1','전시',scope='taste')
  result=research_taste(self.db,lambda u:page('<title>가을 전시 관람</title>2026.10.01 ~ 2026.11.30'),NOW)
  self.assertEqual(result['verified'],1);self.assertEqual(len(export_taste(self.db,NOW)),1);self.assertEqual(export_taste(self.db,'2026-12-01T00:00:00Z'),[])
 def test_export_separates_pending_checks_from_confirmations_and_writes_report(self):
  feed=c.store_and_export(self.db,[],__import__('datetime').datetime.fromisoformat(NOW.replace('Z','+00:00')),Path(self.tmp.name)/'feed.json',{})
  self.assertEqual(feed['research']['pipelineVersion'],3);write_report(self.db,feed,Path(self.tmp.name))
  report=json.loads((Path(self.tmp.name)/'research-report.json').read_text());self.assertEqual(report['factCheckOutcomes'],{});self.assertEqual(report['publishedOffers'],0)
if __name__=='__main__':unittest.main()
