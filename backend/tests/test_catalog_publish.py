import unittest,sqlite3,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
from catalog_publish import release_day,publish_catalog
class CataloguePublishTests(unittest.TestCase):
 def test_korea_one_am_boundary(self):
  self.assertEqual(release_day('2026-10-27T15:59:59Z'),'2026-10-27');self.assertEqual(release_day('2026-10-27T16:00:00Z'),'2026-10-28')
 def test_incremental_release_preserves_daily_boundary_and_verification(self):
  db=sqlite3.connect(':memory:');db.execute('CREATE TABLE research_state(key TEXT PRIMARY KEY,value TEXT)')
  seed={'key':'a','category':'AI','status':'verified_identity','origin':'seed'};bad={'key':'b','category':'신규','origin':'discovered','status':'verified_identity'};good=dict(bad,status='verified',verification={'billingTerms':True})
  first=publish_catalog(db,[seed,bad],'2026-10-27T16:00:00Z');same=publish_catalog(db,[seed,good],'2026-10-28T15:59:59Z');self.assertEqual(same['revision'],2);self.assertEqual(len(first['services']),1);self.assertEqual(len(same['services']),2);self.assertEqual(publish_catalog(db,[seed,good],'2026-10-28T15:59:59Z'),same)
  next=publish_catalog(db,[seed,good],'2026-10-28T16:00:00Z');self.assertEqual(len(next['services']),2);self.assertEqual(next['version'],'2026-10-29');db.close()
