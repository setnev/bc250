import unittest,tempfile,pathlib
from policy import Policy,Scope,PolicyError,arguments,safe_path
class PolicyTest(unittest.TestCase):
 def setUp(self):
  self.now=100.;self.p=Policy(Scope('lab-01','case-1',frozenset({'service'}),frozenset({'restart_application'}),200.),clock=lambda:self.now)
 def test_wrong_target_denied(self):
  with self.assertRaises(PolicyError):self.p.require('lab-02','read','service')
 def test_unlisted_write_denied(self):
  with self.assertRaises(PolicyError):self.p.require('lab-01','write','disable_audit')
 def test_legitimate_grant_and_replay(self):
  t=self.p.issue('restart_application','ops-demo');self.p.consume(t,'lab-01','restart_application','ops-demo')
  with self.assertRaises(PolicyError):self.p.consume(t,'lab-01','restart_application','ops-demo')
 def test_expired_grant(self):
  t=self.p.issue('restart_application','ops-demo',ttl=1);self.now=102
  with self.assertRaises(PolicyError):self.p.consume(t,'lab-01','restart_application','ops-demo')
 def test_forged_and_cross_resource_grants(self):
  t=self.p.issue('restart_application','ops-demo')
  for token,res in [(t.replace('ops-demo','sshd'),'sshd'),(t,'sshd'),('{}','ops-demo')]:
   with self.assertRaises(PolicyError):self.p.consume(token,'lab-01','restart_application',res)
 def test_schema_rejects_wrong_types_and_extra_fields(self):
  for x in [{'action':{}},{'action':'restart_application','command':'anything'},['restart_application']]:
   with self.assertRaises(PolicyError):arguments(x,['action'])
 def test_path_escape_and_symlink_escape(self):
  with tempfile.TemporaryDirectory() as d,tempfile.TemporaryDirectory() as outside:
   pathlib.Path(d,'escape').symlink_to(outside,target_is_directory=True)
   for p in ['../outside','/etc/shadow','escape/file']:
    with self.assertRaises(PolicyError):safe_path(d,p)
   self.assertEqual(safe_path(d,'file'),pathlib.Path(d,'file'))
 def test_window_expiry(self):
  self.now=201
  with self.assertRaises(PolicyError):self.p.require('lab-01','write','restart_application')
if __name__=='__main__':unittest.main()
