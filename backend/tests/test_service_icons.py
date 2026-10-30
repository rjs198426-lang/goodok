import base64,io,json,sqlite3,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]))
from service_icons import normalize_image,collect_icons,icon_candidates,category_style
from collector import parse_html
from catalog_publish import publish_catalog

class ServiceIconTests(unittest.TestCase):
 def png(self):
  from PIL import Image
  out=io.BytesIO();Image.new('RGB',(32,32),'red').save(out,format='PNG');return out.getvalue()
 def db(self):
  db=sqlite3.connect(':memory:');db.executescript('CREATE TABLE service_catalog(service_key TEXT PRIMARY KEY,payload TEXT);CREATE TABLE research_state(key TEXT PRIMARY KEY,value TEXT);');return db
 def service(self):return {'key':'fresh','name':'Fresh','category':'웹·호스팅','officialUrl':'https://fresh.example/pricing','origin':'discovered','status':'verified_identity','verification':{'recurringPrice':True}}
 def test_normalized_png_is_bounded_and_reencoded(self):
  from PIL import Image
  result=normalize_image(self.png());image=Image.open(io.BytesIO(result));self.assertEqual(image.size,(96,96));self.assertEqual(image.format,'PNG');self.assertLess(len(result),7500)
 def test_active_external_and_oversized_images_rejected(self):
  for svg in [b'<svg><script>x</script></svg>',b'<svg><image href="https://bad.example/a"/></svg>',b'<svg xml:base="https://bad.example/"></svg>',b'<!DOCTYPE svg><svg/>',b'<svg style="fill:url(https://bad.example/a)"/>']:
   with self.subTest(svg=svg),self.assertRaises((ValueError,Exception)):normalize_image(svg)
  with self.assertRaises(ValueError):normalize_image(b'a'*(256*1024+1))
 def test_svg_converted_to_pixels_without_executing_it(self):
  result=normalize_image(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24" fill="#f00"/></svg>');self.assertTrue(result.startswith(b'\x89PNG\r\n\x1a\n'))
 def test_first_party_icon_links_are_resolved_without_og_promo_art(self):
  page=parse_html('<link rel="apple-touch-icon" href="/brand.png"><link rel="icon" href="/favicon.svg"><meta property="og:image" content="https://ad.example/banner.png">');candidates=icon_candidates(self.service(),lambda url:page)
  self.assertEqual(candidates[0][0],'https://fresh.example/brand.png');self.assertFalse(any('banner' in url for url,_ in candidates))
 def test_cache_retains_last_good_icon_on_failure_and_defers_retry(self):
  db=self.db();service=self.service();db.execute('INSERT INTO service_catalog VALUES(?,?)',(service['key'],json.dumps(service)))
  with patch('service_icons.retrieval.download',return_value=(self.png(),'image/png','utf-8')):
   first=collect_icons(db,[service],lambda url:parse_html(''),'2026-10-30T00:00:00Z');self.assertEqual(first['updated'],1)
  data=service['icon']['data'];self.assertTrue(base64.b64decode(data.split(',')[1]).startswith(b'\x89PNG'))
  with patch('service_icons.retrieval.download',side_effect=OSError('blocked')) as get:
   self.assertEqual(collect_icons(db,[service],lambda url:parse_html(''),'2026-10-30T01:00:00Z')['attempted'],0);get.assert_not_called()
   failed=collect_icons(db,[service],lambda url:parse_html(''),'2026-12-01T00:00:00Z');self.assertEqual(failed['updated'],0);self.assertEqual(service['icon']['data'],data)
  self.assertEqual(service['verification'],{'recurringPrice':True})
 def test_icon_and_category_changes_publish_same_day_revision(self):
  db=self.db();service=self.service();first=publish_catalog(db,[service],'2026-10-30T00:00:00Z');self.assertEqual(first['categories'][0]['icon'],'category-hosting')
  service['icon']={'sha256':'a'*64,'checkedAt':'2026-10-30T00:30:00Z'};next=publish_catalog(db,[service],'2026-10-30T00:30:00Z');self.assertEqual(next['revision'],first['revision']+1)
  service['icon']={**service['icon'],'checkedAt':'2026-10-30T00:45:00Z'};self.assertEqual(publish_catalog(db,[service],'2026-10-30T00:45:00Z'),next)
  self.assertNotEqual(category_style('업무 자동화')['icon'],category_style('웹·호스팅')['icon'])
