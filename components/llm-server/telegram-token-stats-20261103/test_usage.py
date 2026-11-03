import runpy,sqlite3,tempfile,json,unittest
u=runpy.run_path('/home/somdutta/.config/opencode/scripts/openrouter-usage')
class UsageTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=self.tmp.name+'/usage.db';c=sqlite3.connect(self.db);c.execute('create table session_message (id text,session_id text,type text,data text,time_created integer)')
  for mid,sid,provider,tokens,cost in [('a','s','evo-agent',{'input':100,'output':20,'cache':{'read':10}},0),('b','s','openrouter',{'input':50,'output':5,'reasoning':7,'cache':{'read':200}},0.002),('c','s','evo-agent',{'input':900000,'output':99999},0),('d','other','openrouter',{'input':800000,'output':123},9),('e','s','evo-agent',None,0)]:
   c.execute('insert into session_message values (?,?,?,?,?)',(mid,sid,'assistant',json.dumps({'model':{'providerID':provider},'tokens':tokens,'cost':cost}),1000))
  c.commit();c.close()
 def tearDown(self):self.tmp.cleanup()
 def test_scoped_mixed_providers_and_cache(self):
  t=u['collect'](self.db,'s',['a','b','d'],all_providers=True);self.assertEqual(t['fresh'],50);self.assertEqual(t['cached'],200);self.assertEqual(t['by_provider']['evo-agent']['peak'],110);self.assertEqual(t['by_provider']['openrouter']['peak'],250);self.assertEqual(t['cost'],0.002);self.assertNotIn('900',u['format_usage'](t));self.assertIn('Tokens (local)',u['format_usage'](t));self.assertIn('Tokens (cloud)',u['format_usage'](t))
 def test_incomplete_usage_not_reported_as_zero(self):
  t=u['collect'](self.db,'s',['e'],all_providers=True);self.assertEqual(t['unknown_steps'],1);self.assertIn('unavailable',u['format_usage'](t))
 def test_legacy_cloud_only_mode_preserved(self):
  t=u['collect'](self.db,'s',['a','b']);self.assertEqual(t['requests'],1);self.assertEqual(t['output'],5);self.assertNotIn('by_provider',t);self.assertIn('Usage: $0.0020',u['format_usage'](t))
if __name__=='__main__':unittest.main()
