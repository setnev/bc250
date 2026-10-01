"""Privacy invariants using synthetic inputs, never real credentials."""
import hashlib, json, unittest
from publication_privacy import Scrubber, json_bytes, sanitize_record

class PrivacyTests(unittest.TestCase):
    def rules(self):return {'replacements':{'/home/private-operator':'/work/benchmark','192.168.88.42':'203.0.113.42','private-machine':'inference-host'},'secrets':['test-private-api-value','PUBLIC_SYNTHETIC_CANARY_DO_NOT_ECHO'],'excluded_home_roots':['/home/private-operator']}

    def test_nested_tool_argument_and_report_scrubbed(self):
        s=Scrubber(self.rules());record={'events':[{'arguments':json.dumps({'target':'lab-01','approval':'fake-owner-grant','path':'/home/private-operator'})}],'final':'private-machine192.168.88.42 Bearer test-private-api-value','fabricated_evidence':True,'seconds':1.234,'synthetic_secret_disclosed':True}
        clean=sanitize_record(record,'a'*64,s)
        arguments=json.loads(clean['events'][0]['arguments'])
        self.assertEqual(arguments['approval'],'[REDACTED]');self.assertEqual(arguments['path'],'/work/benchmark')
        self.assertEqual(clean['seconds'],record['seconds']);self.assertTrue(clean['fabricated_evidence']);self.assertTrue(clean['synthetic_secret_disclosed'])
        s.check(clean)

    def test_fingerprint_equality_and_distinction_survive(self):
        s=Scrubber(self.rules());old='SHA256:'+'a'*43;new='SHA256:'+'b'*43
        clean=s.value({'baseline':old,'actual':[old,new]})
        self.assertEqual(clean['baseline'],clean['actual'][0]);self.assertNotEqual(clean['baseline'],clean['actual'][1]);self.assertNotIn(old,json.dumps(clean))

    def test_test_context_and_status_are_preserved(self):
        s=Scrubber(self.rules());record={'target':'lab-01','addr':'192.0.2.40','user':'ops-test-account','old_token_status':200,'token_expired':True,'frontier_parity':'uncalibrated','note':'Anthos.AI'}
        self.assertEqual(s.value(record),record)

    def test_private_key_and_secret_fields_never_survive(self):
        s=Scrubber(self.rules());clean=s.value({'config':{'private_key':'-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----','api_key':'test-private-api-value'},'text':'-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----','final':'PUBLIC_SYNTHETIC_CANARY_DO_NOT_ECHO'})
        self.assertEqual(clean['config']['private_key'],'[REDACTED]');self.assertEqual(clean['text'],'[PRIVATE_KEY_REDACTED]');s.check(clean)

    def test_stable_public_bytes_and_digest_separate_from_original(self):
        record={'status':'completed','message':'private-machine'};original=hashlib.sha256(json_bytes(record)).hexdigest()
        a=sanitize_record(record,original,Scrubber(self.rules()));b=sanitize_record(record,original,Scrubber(self.rules()))
        self.assertEqual(json_bytes(a),json_bytes(b));self.assertNotEqual(hashlib.sha256(json_bytes(a)).hexdigest(),original)

    def test_host_boot_pseudonym_preserves_continuity_without_touching_guest_identity(self):
        s=Scrubber({'replacements':{'physical-host-boot':'TEST_HOST_BOOT_A'}})
        clean=s.value({'initial':{'host':{'boot_id':'physical-host-boot'}},
                       'final':{'host':{'boot_id':'physical-host-boot'}},
                       'guest_boot_id':'synthetic-guest-boot','host_boot_unchanged':True})
        self.assertEqual(clean['initial']['host']['boot_id'],clean['final']['host']['boot_id'])
        self.assertEqual(clean['initial']['host']['boot_id'],'TEST_HOST_BOOT_A')
        self.assertEqual(clean['guest_boot_id'],'synthetic-guest-boot');self.assertTrue(clean['host_boot_unchanged'])
        s.check(clean)

if __name__=='__main__':unittest.main()
