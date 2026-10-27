import unittest,unittest.mock as mock,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
from search_api import configured_providers,search_api
class SearchApiTests(unittest.TestCase):
 def test_configuration_is_optional_and_does_not_expose_values(self):
  with mock.patch.dict('os.environ',{},clear=True):self.assertEqual(configured_providers(),[])
  with mock.patch.dict('os.environ',{'NAVER_CLIENT_ID':'test-id','NAVER_CLIENT_SECRET':'test-secret'},clear=True):self.assertEqual(configured_providers(),['Naver'])
 def test_keys_are_headers_and_never_in_published_result_urls(self):
  class Response:
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,n):return b'{"items":[{"link":"https://vendor.example/event","title":"<b>offer</b>"}]}'
  opener=mock.Mock();opener.open.return_value=Response()
  with mock.patch.dict('os.environ',{'NAVER_CLIENT_ID':'test-id','NAVER_CLIENT_SECRET':'test-secret'},clear=True),mock.patch('urllib.request.build_opener',return_value=opener):
   result=search_api('Naver','public search');request=opener.open.call_args.args[0];self.assertNotIn('test-secret',request.full_url);self.assertEqual(result,[('https://vendor.example/event','offer')])
