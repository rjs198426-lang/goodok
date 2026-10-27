import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
import collector
from plan_capabilities import enrich_plan_capabilities
class CapabilityTests(unittest.TestCase):
 def test_scoped_vpn_and_office_facts(self):
  page=collector.Page();page.feed('<h2>Free</h2>No file uploads<h2>Pro</h2>10 devices WireGuard OpenVPN kill switch Windows macOS Android iOS 30-day money-back 2 TB storage<h2>Personal</h2>desktop Office apps 6 family members')
  plans=[{'name':'Pro','capabilities':{},'evidence':[]},{'name':'Personal','evidence':[]}];enrich_plan_capabilities(plans,page)
  self.assertEqual(plans[0]['capabilities']['devices'],10);self.assertTrue(plans[0]['capabilities']['wireGuard']);self.assertEqual(plans[0]['capabilities']['storageGB'],2048);self.assertNotIn('files',plans[0]['capabilities']);self.assertEqual(plans[1]['capabilities']['familyMembers'],6)
 def test_no_global_feature_inference_or_speed_ranking(self):
  page=collector.Page();page.feed('<h1>Pricing Overview</h1>200 devices Fastest VPN GPT-4o')
  plans=[{'name':'Pro','capabilities':{},'evidence':[]}];enrich_plan_capabilities(plans,page);self.assertEqual(plans[0]['capabilities'],{})
