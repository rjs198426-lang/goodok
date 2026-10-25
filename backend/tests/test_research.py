import sys,json,tempfile,unittest,datetime as dt
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
import collector as c
from discovery import safe_url,unwrap_search_link,rotating,init_discovery
from catalog_engine import identify_new,structured_plans,normal_plan
class ResearchTests(unittest.TestCase):
 def test_search_links_and_nonpublic_rejection(self):
  self.assertEqual(unwrap_search_link('https://www.google.com/url?q=https%3A%2F%2Fexample.com%2Fpricing'),'https://example.com/pricing')
  for url in ['http://example.com','https://127.0.0.1/','https://user:secret@example.com/','https://localhost/'] :self.assertIsNone(safe_url(url))
  self.assertEqual(rotating(list(range(53)),51,4),[51,52,0,1])
 def test_structured_catalog_identity_and_recurring_price(self):
  page=c.Page();page.feed('''<script type="application/ld+json">{"@type":"Organization","name":"NewTool","url":"https://newtool.example/"}</script><script type="application/ld+json">{"@type":"SoftwareApplication","name":"NewTool","description":"AI subscription","offers":{"name":"Pro","priceSpecification":{"price":12000,"priceCurrency":"KRW","billingDuration":"P1M","valueAddedTaxIncluded":true}}}</script>''')
  service=identify_new(page,'https://newtool.example/pricing',[],'https://appsumo.com/products/newtool/');self.assertEqual(service['name'],'NewTool');plans=structured_plans(page,service,'2026-10-25T12:00:00Z');self.assertEqual(plans[0]['amount'],12000);self.assertEqual(plans[0]['interval'],'monthly')
  self.assertNotIn('priceSpecification',page.text)
 def test_impostor_and_lifetime_cannot_become_verified_recurring_service(self):
  page=c.Page();page.feed('<script type="application/ld+json">{"@type":"Organization","name":"Netflix","url":"https://fake.example/"}</script><script type="application/ld+json">{"@type":"Product","name":"Netflix"}</script>')
  self.assertIsNone(identify_new(page,'https://fake.example/',[{'name':'Netflix','aliases':[],'officialUrl':'https://netflix.com/'}],'https://example.com/'))
  page=c.Page();page.feed('<script type="application/ld+json">{"@type":"Product","name":"Lifetime","offers":{"price":10,"priceCurrency":"USD"}}</script>');self.assertEqual(structured_plans(page,{'key':'x','name':'x','category':'AI','officialUrl':'https://example.com/'},'2026-10-25T12:00:00Z'),[])
 def test_normal_price_uses_recurring_not_trial_amount(self):
  page=c.Page();page.feed('<p>₩0에 1개월 개인 요금제. 이후에는 ₩11,990 (부가세 포함)/월. 광고 없는 음악 오프라인 감상 무손실.</p>')
  source={'id':'spotify','url':'https://www.spotify.com/kr/premium/'};price=c.observed_price(source,page.text);plan=normal_plan(source,page,price,'2026-10-25T12:00:00Z')[0];self.assertEqual(plan['amount'],11990);self.assertFalse(plan['introductory']);self.assertTrue(plan['capabilities']['offline'])
if __name__=='__main__':unittest.main()

class TextPlanTests(unittest.TestCase):
 def test_heading_scoped_normal_monthly_prices(self):
  from catalog_engine import text_plans
  page=c.Page();page.feed('<title>Plans</title><h2>Pro</h2><p>₩12,000/월</p><h2>Premium</h2><p>₩20,000/월</p>')
  plans=text_plans(page,{'key':'new','category':'AI','officialUrl':'https://new.example/pricing'},'2026-10-25T12:00:00Z');self.assertEqual([p['amount'] for p in plans],[12000,20000])
 def test_annual_monthly_equivalent_does_not_become_uncommitted_monthly_price(self):
  from catalog_engine import text_plans
  page=c.Page();page.feed('<h2>Pro</h2><p>₩12,000/월 연간 결제</p>');self.assertEqual(text_plans(page,{'key':'new','category':'AI','officialUrl':'https://new.example/'},'2026-10-25T12:00:00Z'),[])
