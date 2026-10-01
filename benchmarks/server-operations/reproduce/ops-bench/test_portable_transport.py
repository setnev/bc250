"""Offline imports need no credentials; real requests require explicit settings."""
from pathlib import Path
import importlib.util, json, os, unittest
from unittest.mock import patch

def load():
    spec=importlib.util.spec_from_file_location('portable_transport',Path(__file__).with_name('soak_api.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

class TransportTests(unittest.TestCase):
    def test_offline_import_has_no_connection_or_credential_dependency(self):
        with patch.dict(os.environ,{},clear=True),patch('urllib.request.urlopen') as opening:
            load()
            opening.assert_not_called()

    def test_requests_without_explicit_settings_fail_before_network(self):
        for settings in ({},{'BC250_BASE_URL':'http://example.invalid/v1'}):
            with patch.dict(os.environ,settings,clear=True),patch('urllib.request.urlopen') as opening:
                with self.assertRaises(KeyError):load().request('/models')
                opening.assert_not_called()

    def test_configured_request_preserves_auth_payload_and_timeout(self):
        settings={'BC250_BASE_URL':'http://example.invalid/v1/','BC250_API_KEY':'public-test-only'}
        with patch.dict(os.environ,settings,clear=True),patch('urllib.request.urlopen') as opening:
            load().request('/chat/completions',{'model':'test'},17)
            req=opening.call_args.args[0]
            self.assertEqual(req.full_url,'http://example.invalid/v1/chat/completions')
            self.assertEqual(req.get_header('Authorization'),'Bearer '+'public-test-only')
            self.assertEqual(json.loads(req.data),{'model':'test'})
            self.assertEqual(opening.call_args.kwargs,{'timeout':17})

if __name__=='__main__':unittest.main()
