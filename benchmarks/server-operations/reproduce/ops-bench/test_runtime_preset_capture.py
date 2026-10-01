"""Capture the effective llama.cpp preset, including shared [*] options."""
from pathlib import Path
import importlib.util, unittest

spec=importlib.util.spec_from_file_location('runtime_capture',Path(__file__).with_name('capture-soak-runtime.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class PresetCaptureTests(unittest.TestCase):
    def test_llama_header_shared_defaults_and_model_override(self):
        text='version = 1\n[*]\nctx-size = 8192\nthreads = 6\ncache-ram = 0\n[qwen3.5-9b]\nmodel = /models/9b.gguf\nmmproj = /models/9b-projector.gguf\nthreads = 8\n[other]\nmodel = /models/other.gguf\n'
        result=module.parse_model_presets(text,['qwen3.5-9b'])
        self.assertEqual(set(result),{'qwen3.5-9b'})
        self.assertEqual(result['qwen3.5-9b'],{'ctx-size':'8192','threads':'8','cache-ram':'0',
            'model':'/models/9b.gguf','mmproj':'/models/9b-projector.gguf'})

    def test_real_portable_production_fixture_inherits_comparison_settings(self):
        path=Path(__file__).parent/'public-staging/reproduce/profile-runtime/production-soak-models.ini'
        if not path.exists():path=Path(__file__).parent.parent/'profile-runtime/production-soak-models.ini'
        result=module.parse_model_presets(path.read_text(),['qwen3.5-9b'])['qwen3.5-9b']
        self.assertEqual((result['threads'],result['ctx-size'],result['reasoning']),('6','8192','off'))
        self.assertTrue(result['mmproj'].endswith('mmproj-F16.gguf'))

    def test_unknown_format_or_missing_model_is_rejected(self):
        with self.assertRaises(AssertionError):module.parse_model_presets('version = 2\n[*]\n[a]\nmodel = a.gguf\n',['a'])
        with self.assertRaises(KeyError):module.parse_model_presets('version = 1\n[*]\n[a]\nmodel = a.gguf\n',['missing'])

if __name__=='__main__':unittest.main()
