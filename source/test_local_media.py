"""Loopback routes and streaming above the former input size boundary."""
from pathlib import Path
import tempfile,unittest,urllib.request,urllib.error
from local_media import MediaServer
from test_large import make_sparse

class LocalMediaTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.server=MediaServer(self.root);self.server.index=b'approved desktop';self.server.start()
 def tearDown(self):self.server.close();self.temp.cleanup()
 def test_private_routes_and_range_responses(self):
  file=self.root/'source.bin';file.write_bytes(b'0123456789');url=self.server.register(file)
  with urllib.request.urlopen(urllib.request.Request(url,headers={'Range':'bytes=2-5'})) as response:
   self.assertEqual(response.status,206);self.assertEqual(response.read(),b'2345');self.assertEqual(response.headers['Content-Range'],'bytes 2-5/10')
  with urllib.request.urlopen(urllib.request.Request(url,headers={'Range':'bytes=-3'})) as response:self.assertEqual(response.read(),b'789')
  with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(urllib.request.Request(url,headers={'Range':'bytes=20-30'}))
  self.assertEqual(error.exception.code,416)
  for path in ('/','/'+self.server.token+'/../source.bin','/'+self.server.token+'/source.bin'):
   with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(self.server.origin+path)
 def test_streams_tail_of_sparse_file_larger_than_two_gib(self):
  path=self.root/'large.mp4'
  with path.open('wb') as file:
   make_sparse(file);file.seek(2*1024**3+31);file.write(b'END!')
  url=self.server.register(path)
  with urllib.request.urlopen(urllib.request.Request(url,headers={'Range':'bytes=-4'})) as response:
   self.assertEqual(response.status,206);self.assertEqual(response.read(),b'END!');self.assertIn(str(path.stat().st_size),response.headers['Content-Range'])
 def test_root_has_content_policy_and_no_directory_listing(self):
  with urllib.request.urlopen(self.server.base) as response:
   self.assertEqual(response.read(),b'approved desktop');self.assertIn("connect-src 'self'",response.headers['Content-Security-Policy'])
  with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(self.server.base+'media/')

if __name__=='__main__':unittest.main()
