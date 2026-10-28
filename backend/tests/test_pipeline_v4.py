import datetime as dt,json,sqlite3,sys,tempfile,unittest,urllib.error,urllib.request
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]))
import collector as c,retrieval as r
from discovery import run_discovery,sitemap_links
from catalog_engine import identify_new,text_plans,yearly_text_plans,enrich_service,category_for,enqueue_targets
from catalog_publish import publish_catalog

class PipelineV4Tests(unittest.TestCase):
 def setUp(self):
  self.db=c.init_db(':memory:');r.configure(self.db,[])
 def tearDown(self):self.db.close()
 def test_failure_codes_are_distinct(self):
  for status in (403,404,429,503):self.assertEqual(r.error_code(urllib.error.HTTPError('https://vendor.example',status,'bad',{},None)),'http_'+str(status))
  self.assertEqual(r.error_code(TimeoutError()),'timeout');self.assertEqual(r.error_code(r.FetchFailure('captcha')),'captcha')
 def test_one_run_cache_prevents_repeated_requests(self):
  with patch.object(r,'download',return_value=(('<h1>Pricing</h1>'+('public content '*30)).encode(),'text/html','utf-8')) as fetch:
   a=c.fetch('https://vendor.example/pricing');b=c.fetch('https://vendor.example/pricing');self.assertIs(a,b);self.assertEqual(fetch.call_count,1)
 def test_captcha_is_not_rendered_or_bypassed(self):
  r.configure(self.db,['https://vendor.example/pricing'])
  with patch.object(r,'download',return_value=(b'<p>captcha verify you are human</p>','text/html','utf-8')),patch.object(r,'render') as browser:
   with self.assertRaisesRegex(r.FetchFailure,'captcha'):c.fetch('https://vendor.example/pricing')
   browser.assert_not_called()
 def test_403_is_persisted_and_future_attempt_deferred(self):
  url='https://vendor.example/pricing'
  with patch.object(r,'download',side_effect=urllib.error.HTTPError(url,403,'denied',{},None)):
   with self.assertRaises(urllib.error.HTTPError):c.fetch(url)
  audit=r.persist(self.db,'2099-01-01T00:00:00Z');self.assertEqual(audit['recentFailures'][0]['reason'],'http_403');r.configure(self.db,[])
  with patch.object(r,'download') as fetch:
   with self.assertRaisesRegex(r.FetchFailure,'deferred_http_403'):c.fetch(url)
   fetch.assert_not_called()
 def test_standard_rss_and_directory_work_when_html_fails(self):
  seed={'key':'tool','name':'Tool','aliases':[],'officialUrl':'https://tool.example/'}
  def fail(_):raise TimeoutError()
  xml='<rss><channel><item><title>New subscription pricing</title><link>https://new.example/pricing</link></item></channel></rss>'
  attempts,found=run_discovery(self.db,[seed],fail,'2026-10-28T00:00:00Z',fetch_xml=lambda _:xml,fetch_text=lambda _:'[Other subscription](https://other.example/pricing)')
  self.assertTrue(any(a['provider']=='Bing RSS' and a['results'] for a in attempts));self.assertTrue(any(a['provider']=='Public tool directory' and a['results'] for a in attempts));self.assertTrue(any(c['url']=='https://other.example/pricing' for c in found))
 def test_curated_official_target_can_establish_brand_without_jsonld(self):
  page=c.parse_html('<title>1Password Pricing</title><a href="/privacy">Privacy</a><h2>Individual</h2><p>US$4 per month</p>')
  service=identify_new(page,'https://1password.com/pricing',[],'https://1password.com/pricing');self.assertEqual(service['category'],'보안');self.assertEqual(service['purpose'],'passwords')
  plans=text_plans(page,service,'2026-10-28T00:00:00Z');self.assertEqual(plans[0]['status'],'candidate')
  service=enrich_service(service,page,plans,'2026-10-28T00:00:00Z');self.assertTrue(service['verification']['recurringPrice']);self.assertFalse(service['verification']['billingTerms'])
  released=publish_catalog(self.db,[service],'2026-10-28T00:00:00Z');self.assertEqual(released['categories'][0]['name'],'보안')
 def test_new_category_taxonomy_and_targets_are_persistent(self):
  self.assertEqual(category_for('cloud backup subscription'),'백업');self.assertEqual(category_for('text to speech subscription'),'음성·오디오')
  enqueue_targets(self.db,'2026-10-28T00:00:00Z');enqueue_targets(self.db,'2026-10-28T01:00:00Z');self.assertEqual(self.db.execute("SELECT COUNT(*) FROM candidates WHERE provider='official_target'").fetchone()[0],12)
 def test_redirect_keeps_https_public_same_site(self):
  req=urllib.request.Request('https://vendor.example/pricing')
  with patch.object(r,'public_host',return_value=True):
   self.assertIsNotNone(r.PublicRedirect().redirect_request(req,None,301,'m',{},'https://www.vendor.example/pricing'))
   for url in ('https://other.example/pricing','http://vendor.example/','https://user:secret@vendor.example/'):
    with self.assertRaises(r.FetchFailure):r.PublicRedirect().redirect_request(req,None,301,'m',{},url)
 def test_full_year_price_is_preserved_without_annual_equivalent_inference(self):
  service={'key':'x','category':'보안','purpose':'passwords','officialUrl':'https://x.example/pricing'}
  full=c.parse_html('<h2>Premium</h2>US$19.80/year')
  result=yearly_text_plans(full,service,'2026-10-28T00:00:00Z')[0];self.assertEqual(result['amount'],19.8);self.assertEqual(result['interval'],'yearly');self.assertEqual(result['commitmentMonths'],12)
  self.assertEqual(yearly_text_plans(c.parse_html('<h2>Premium</h2>US$1.65/month billed annually'),service,'2026-10-28T00:00:00Z'),[])
 def test_trial_and_ambiguous_dollar_are_not_normal_annual_prices(self):
  service={'key':'x','category':'보안','officialUrl':'https://x.example/pricing'}
  for text in ('<h2>Premium</h2>US$10/year first year offer','<h2>Premium</h2>$10/year'):
   self.assertEqual(yearly_text_plans(c.parse_html(text),service,'2026-10-28T00:00:00Z'),[])
 def test_parser_upgrade_rechecks_price_unknown_targets_once(self):
  enqueue_targets(self.db,'2026-10-28T00:00:00Z');self.db.execute("UPDATE candidates SET catalog_status='needs_price',catalog_checked_at='2026-10-28T00:00:00Z' WHERE provider='official_target'")
  self.db.execute("UPDATE research_state SET value='4.0' WHERE key='catalog_parser_revision'")
  enqueue_targets(self.db,'2026-10-28T01:00:00Z');self.assertEqual(self.db.execute("SELECT COUNT(*) FROM candidates WHERE catalog_checked_at IS NULL").fetchone()[0],12)
 def test_optional_monthly_render_keeps_static_evidence_when_budget_exhausted(self):
  r.configure(self.db,['https://vendor.example/pricing']);html='<div id="root"><h2>Pro</h2>US$10/mo billed annually; US$20/mo billed monthly cancel any time. '+('public pricing description '*8)+'</div>'
  with patch.object(r,'download',return_value=(html.encode(),'text/html','utf-8')),patch.object(r,'render',side_effect=r.FetchFailure('render_budget_exhausted')):
   self.assertIn('US$20',c.fetch('https://vendor.example/pricing').text)
 def test_fact_changes_publish_another_same_day_revision(self):
  service={'key':'s','name':'S','category':'AI','status':'verified_identity','origin':'seed','purpose':'assistant'}
  first=publish_catalog(self.db,[service],'2026-10-28T00:00:00Z');second=publish_catalog(self.db,[dict(service,purposes=['assistant','image'])],'2026-10-28T01:00:00Z');self.assertGreater(second['revision'],first['revision'])
 def test_sitemap_rejects_offsite_and_entities(self):
  xml='<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://vendor.example/event/1</loc></url><url><loc>https://evil.example/pricing</loc></url></urlset>'
  self.assertEqual(sitemap_links(xml,'https://vendor.example/'),[('https://vendor.example/event/1','공식 요금·이벤트 상세 페이지')])
  with self.assertRaises(ValueError):sitemap_links('<!DOCTYPE x><urlset/>','https://vendor.example/')
 def test_404_event_entry_uses_public_homepage_and_preserves_original_failure(self):
  source={'id':'new','name':'New','service':'new','parser':'event','url':'https://vendor.example/old-event','discover':False}
  def fake(url):
   if 'old-event' in url:raise urllib.error.HTTPError(url,404,'missing',{},None)
   return c.parse_html('<title>New official</title>'+('public homepage '*20))
  with patch.object(c,'fetch',side_effect=fake):result=c.investigate(source)
  self.assertEqual(result['status'],'ok');self.assertEqual(result['observations'][0]['status'],'http_404');self.assertEqual(result['observations'][1]['url'],'https://vendor.example/')
