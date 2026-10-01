"""Verify the current production configuration, not historical profile assumptions."""
import pathlib,subprocess,json,sys
root=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(root.parent))
from test_api import request
p=subprocess.run(['python3',str(root.parent/'remote.py'),'--sudo'],input="cat /etc/bc250-ai/profiles.json\n",text=True,capture_output=True,check=True)
profiles=json.loads(p.stdout)
result,elapsed=request('/chat/completions',{'model':'qwen3.5-9b','messages':[{'role':'user','content':'Reply only with the result: 17 multiplied by 23.'}],'temperature':0,'max_tokens':16})
assert result['choices'][0]['message']['content'].strip()=='391'
h,_=request('/hardware');name=profiles['models']['qwen3.5-9b'];expected=profiles['profiles'][name]
assert h['profile']==name and h['actual']['gfx_frequency_mhz']==expected['mhz'] and h['actual']['gfx_vid']==expected['vid'],h
assert h['cpu']['mode']=='idle' and h['cpu']['latency_request_us'] is None and not h['latched'],h
(root/'production-recovery.json').write_text(json.dumps({'response':'391','elapsed_seconds':elapsed,'hardware':h,'expected_profile':expected},indent=2)+'\n')
print('Production inference, current profile, CPU idle release and unlatched guard verified.')
