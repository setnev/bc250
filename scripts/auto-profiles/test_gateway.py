"""Hardware-free checks of authorization, serial transitions, streaming and guards."""
import concurrent.futures,http.client,importlib.util,json,os,pathlib,tempfile,threading,time,unittest
ROOT=pathlib.Path(__file__).parent
class GatewayTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(self.tmp.name);(p/'key').write_text('test-key')
  (p/'gateway.json').write_text(json.dumps({'key_file':str(p/'key'),'models':['a','b'],'listen_host':'127.0.0.1','listen_port':0}))
  os.environ['BC250_GATEWAY_CONFIG']=str(p/'gateway.json')
  spec=importlib.util.spec_from_file_location('gateway_tested',ROOT/'gateway.py');self.g=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.g)
  self.events=[];self.loaded=None;self.busy=False;outer=self
  def control(op,model=None):
   if op=='apply':
    assert not outer.busy,'Profile changed during inference';outer.events.append(('profile',model))
   return {'profile':model or 'idle','actual':{'gfx_frequency_mhz':1700,'gfx_voltage_mv':900}}
  def backend(path,payload=None):
   if path=='/models':return {'data':[{'id':x,'status':{'value':'loaded' if x==outer.loaded else 'unloaded'}} for x in ['a','b']]}
   if path=='/models/load':outer.loaded=payload['model']
   if path=='/models/unload':assert not outer.busy;outer.loaded=None
   return {'success':True}
  class Response:
   status=200
   def __init__(self,model):self.model=model;self.i=0
   def getheader(self,*args):return 'text/event-stream'
   def read1(self,n):
    if self.i==0:
     outer.busy=True;outer.events.append(('start',self.model));self.i+=1;return b'data: {"delta":"hello"}\n\n'
    if self.i==1:time.sleep(.2);self.i+=1;return b'data: [DONE]\n\n'
    outer.busy=False;outer.events.append(('end',self.model));return b''
  class Connection:
   def request(self,method,path,body=None,headers=None):self.model=json.loads(body)['model']
   def getresponse(self):return Response(self.model)
   def close(self):pass
  self.g.control=control;self.g.backend=backend;self.g.connection=Connection;self.g.workers_alive=lambda:set()
  self.server=self.g.Server(('127.0.0.1',0),self.g.Handler);self.port=self.server.server_address[1]
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):self.server.shutdown();self.server.server_close();self.tmp.cleanup()
 def request(self,model='a',key='test-key',disconnect=False):
  c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5);c.request('POST','/v1/chat/completions',json.dumps({'model':model,'messages':[],'stream':True}),{'Authorization':'Bearer '+key,'Content-Type':'application/json'})
  r=c.getresponse();status=r.status
  if disconnect:r.read(5);c.close();return status,b''
  body=r.read();c.close();return status,body
 def test_auth_and_model_validation_do_not_touch_hardware(self):
  self.assertEqual(self.request(key='wrong')[0],401);self.assertEqual(self.request(model='arbitrary')[0],400);self.assertEqual(self.events,[])
 def test_concurrent_requests_serialize_profile_and_inference(self):
  with concurrent.futures.ThreadPoolExecutor(2) as e:
   futures=[e.submit(self.request,x) for x in ['a','b']]
   for f in futures:self.assertIn(b'[DONE]',f.result()[1])
  kinds=[x[0] for x in self.events];self.assertEqual(kinds,['profile','start','end','profile','start','end'])
 def test_disconnected_stream_is_drained_before_next_profile(self):
  self.assertEqual(self.request(disconnect=True)[0],200);self.assertEqual(self.request('b')[0],200)
  self.assertEqual([x[0] for x in self.events],['profile','start','end','profile','start','end'])
 def test_same_model_keeps_one_loaded_worker(self):
  self.request();self.request();self.assertEqual(self.loaded,'a')

 def test_unload_ack_waits_for_worker_exit_before_applying_profile(self):
  self.loaded='a';self.g.active='a';started=time.monotonic()
  self.g.workers_alive=lambda: {123} if time.monotonic()-started<.25 else set()
  self.assertEqual(self.request('b')[0],200)
  self.assertGreaterEqual(time.monotonic()-started,.45)
 def test_router_reaping_race_is_retried_without_changing_profile(self):
  original=self.g.backend;attempts=[]
  def delayed(path,payload=None):
   if path=='/models/load' and not attempts:
    attempts.append(True);raise self.g.ModelBusy('reaping')
   return original(path,payload)
  self.g.backend=delayed
  self.assertEqual(self.request()[0],200)
  self.assertEqual([x[0] for x in self.events],['profile','start','end'])

class ControllerTests(unittest.TestCase):
 def test_named_allowlist_and_latched_thermal_fallback(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/'profiles.json';p.write_text(json.dumps({'clock_control':'unused','socket':'unused','cutoff_c':85,'profiles':{'idle':{'mhz':1200,'vid':100},'qwen':{'mhz':1700,'vid':104}},'models':{'a':'qwen'}}));os.environ['BC250_PROFILE_CONFIG']=str(p)
   spec=importlib.util.spec_from_file_location('controller_tested',ROOT/'controller.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
   stopped=[];m.stop_backend=lambda:stopped.append(True);m.temperature=lambda:60
   registers={'gfx_frequency_mhz':1200,'gfx_vid':100,'gfx_voltage_mv':925}
   def clock(*args):
    if args:registers.update(gfx_frequency_mhz=args[1],gfx_vid=args[2],gfx_voltage_mv=1550-args[2]*6.25)
    return dict(registers)
   m.clock=clock
   with self.assertRaises(ValueError):m.dispatch({'op':'apply','model':'not-allowed'})
   self.assertEqual(m.dispatch({'op':'apply','model':'a'})['actual']['gfx_voltage_mv'],900)
   m.temperature=lambda:85
   with self.assertRaises(RuntimeError):m.dispatch({'op':'apply','model':'a'})
   self.assertTrue(m.state['latched']);self.assertEqual(registers['gfx_frequency_mhz'],1200);self.assertEqual(stopped,[True])
   m.temperature=lambda:50
   with self.assertRaises(RuntimeError):m.dispatch({'op':'apply','model':'a'})
if __name__=='__main__':unittest.main()
