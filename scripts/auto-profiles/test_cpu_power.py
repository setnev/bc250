import pathlib,tempfile,unittest,os
from unittest.mock import patch
from cpu_power import CpuPower
class CpuTests(unittest.TestCase):
 def test_release_expiry_and_restore(self):
  with tempfile.TemporaryDirectory() as d:
   r=pathlib.Path(d);p=r/'policy0';p.mkdir()
   (p/'scaling_available_governors').write_text('performance schedutil')
   (p/'scaling_governor').write_text('performance')
   qos=r/'qos';qos.touch()
   c=CpuPower(r,r/'saved',str(qos))
   self.assertEqual((p/'scaling_governor').read_text(),'schedutil')
   c.boost();fd=c.fd;self.assertEqual(c.status()['latency_request_us'],100)
   c.deadline=0;c.expire();self.assertEqual(c.mode,'idle')
   with self.assertRaises(OSError):os.fstat(fd)
   c.boost();c.idle();self.assertIsNone(c.fd)
   c.restore();self.assertEqual((p/'scaling_governor').read_text(),'performance')
 def test_failed_boost_releases_constraint(self):
  with tempfile.TemporaryDirectory() as d:
   r=pathlib.Path(d);p=r/'policy0';p.mkdir()
   (p/'scaling_available_governors').write_text('performance schedutil');(p/'scaling_governor').write_text('schedutil')
   c=CpuPower(r,r/'saved',str(r/'missing'))
   with self.assertRaises(OSError):c.boost()
   self.assertEqual(c.mode,'idle');self.assertIsNone(c.fd)
if __name__=='__main__':unittest.main()
