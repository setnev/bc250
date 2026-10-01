"""Read-only runtime/projector verification before the timed operational soak."""
from pathlib import Path
import argparse, configparser, importlib.util, inspect, json

R=Path(__file__).resolve().parent

def parse_model_presets(text, wanted):
    """llama.cpp presets have a version header and a shared [*] section."""
    ini=configparser.ConfigParser(interpolation=None)
    ini.read_string('[__preset_header__]\n'+text)
    assert ini['__preset_header__'].get('version')=='1', 'Unsupported preset version'
    shared=dict(ini['*'])
    return {name:{**shared,**dict(ini[name])} for name in wanted}

def capture(candidate):
    spec=importlib.util.spec_from_file_location('driver',R/'main-agent.py')
    driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    wanted=['qwen3.5-2b','qwen3.5-9b'] if candidate=='worker2b-planner9b' else [candidate]
    projections=[p for p in json.loads((R/'soak-projection-manifest.json').read_text()) if p['model'] in wanted]
    pins=json.loads((R/'soak-runtime-pins.json').read_text())
    script="""python3 - <<'PY'
from pathlib import Path
import configparser, hashlib, json
WANTED=__WANTED__
PROJECTIONS=__PROJECTIONS__
PINS=__PINS__
__PARSER__
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(8*1024**2),b''):h.update(chunk)
 return h.hexdigest()
runtime={}
for name,pin in PINS.items():
 observed=sha(pin['installed_path'])
 assert observed==pin['sha256'],('Runtime helper changed',name)
 runtime[name]={'sha256':observed}
model_options=parse_model_presets(Path('/etc/bc250-ai/models.ini').read_text(),WANTED)
projectors=[]
for entry in PROJECTIONS:
 path=model_options[entry['model']].get('mmproj')
 assert path and Path(path).name==entry['filename'],('Unexpected projector',entry['model'])
 actual=sha(path);size=Path(path).stat().st_size
 assert actual==entry['sha256'] and size==entry['size'],('Projector changed',entry['model'])
 projectors.append({**entry,'observed_sha256':actual,'observed_bytes':size})
profiles=json.loads(Path('/etc/bc250-ai/profiles.json').read_text())
names={profiles['models'][model] for model in WANTED}|{'idle','baseline'}
selected_profiles={name:profiles['profiles'][name] for name in names}
config_hashes={name:sha('/etc/bc250-ai/'+name) for name in ['profiles.json','gateway.json','models.ini']}
print(json.dumps({'runtime_helpers':runtime,'llama_server_sha256':sha('/opt/bc250-ai/llama.cpp/build/bin/llama-server'),'production_config_sha256':config_hashes,'models':model_options,'projectors':projectors,'model_profiles':{model:profiles['models'][model] for model in WANTED},'profiles':selected_profiles,'projector_configuration':'Existing production vision projectors retained for text-only requests; fixed-clock comparison presets omit projectors. Memory/load figures are separate configurations.'}))
PY
""".replace('__WANTED__',repr(wanted)).replace('__PROJECTIONS__',repr(projections)).replace('__PINS__',repr(pins)).replace('__PARSER__',inspect.getsource(parse_model_presets))
    return json.loads(driver.host(script,timeout=180))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('candidate');args=parser.parse_args()
    print(json.dumps(capture(args.candidate),indent=2))
