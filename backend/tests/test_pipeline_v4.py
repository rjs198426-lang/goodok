import datetime as dt,json,sqlite3,sys,tempfile,unittest,urllib.error,urllib.request
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]))
import collector as c,retrieval as r
from discovery import run_discovery
from catalog_engine import identify_new,text_plans,enrich_service,category_for,enqueue_targets
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
