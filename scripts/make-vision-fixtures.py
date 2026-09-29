"""Generate synthetic, non-personal vision fixtures; requires Pillow."""
from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
import json,hashlib
root=Path(__file__).parent; out=root/'fixtures';out.mkdir(exist_ok=True)
font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
def canvas(title):
 im=Image.new('RGB',(1024,768),'#101827'); d=ImageDraw.Draw(im)
 d.text((35,25),'Anthos.AI | '+title,font=ImageFont.truetype(font,30),fill='white')
 return im,d
def text(d,xy,s,size=25,color='white'):d.text(xy,s,font=ImageFont.truetype(font,size),fill=color)
def save(im,name):im.save(out/(name+'.png'))
im,d=canvas('Service dashboard')
for y,vals in zip([140,245,350],[('Service','Status','CPU','RAM'),('web','HEALTHY','24%','2.1 GB'),('worker','DEGRADED','91%','5.8 GB')]):
 for x,s in zip([45,290,600,780],vals):text(d,(x,y),s)
text(d,(45,490),'Queue depth: 137 jobs',30);text(d,(45,560),'Alert: worker CPU above 90%',30,color='#ffbd69');save(im,'dashboard')
im,d=canvas('Deployment log')
for y,s in zip(range(145,600,65),['$ deploy service-web --dry-run','Checking configuration ... OK','Connecting to database ... FAILED','ERROR E_CONN_REFUSED: database port 5432','No changes applied.','Exit status: 2']):text(d,(40,y),s,26)
save(im,'terminal')
im,d=canvas('Synthetic equipment label')
for y,s,z in [(150,'MODEL: AX-250',36),(230,'BATCH: TEST-042',32),(310,'INPUT: 12 V DC / 8 A',28),(400,'CODE: O0-I1-S5-B8',22),(475,'Calibration: 2026-01-01',18),(550,'SYNTHETIC TEST DATA',24)]:text(d,(50,y),s,z)
save(im,'ocr')
im,d=canvas('Request path')
for x,label in [(40,'Client'),(375,'API'),(710,'Database')]:
 d.rounded_rectangle((x,260,x+265,400),radius=15,outline='#7dcfff',width=4);text(d,(x+20,310),label,32)
for a,b in [(305,375),(640,710)]:
 d.line((a,330,b-8,330),fill='white',width=5);d.polygon([(b,330),(b-16,320),(b-16,340)],fill='white')
d.line((505,400,505,540),fill='white',width=4);d.polygon([(505,550),(495,533),(515,533)],fill='white');d.rectangle((375,550,640,650),outline='#7dcfff',width=4);text(d,(415,580),'Cache',32)
save(im,'diagram')
im,d=canvas('Completed jobs')
for x,h,label,val in [(120,120,'A',12),(330,280,'B',28),(540,190,'C',19),(750,350,'D',35)]:
 d.rectangle((x,600-h,x+120,600),fill='#4cc9a6');text(d,(x+35,610),label,28);text(d,(x+30,550-h),str(val),28)
text(d,(40,110),'Jobs per worker (count)',26);save(im,'chart')
im,d=canvas('Object layout')
d.ellipse((120,160,310,350),fill='#f24e4e');d.rectangle((660,160,850,350),fill='#3999ff');d.polygon([(500,425),(390,635),(610,635)],fill='#4ed079')
text(d,(45,700),'Flat shapes on a dark background',22);save(im,'spatial')
cases=[
 dict(id='dashboard',prompt='Read the dashboard. Return JSON with keys degraded_service, cpu_percent (integer), ram_gb (number), queue_jobs (integer).',expected={'degraded_service':'worker','cpu_percent':91,'ram_gb':5.8,'queue_jobs':137}),
 dict(id='terminal',prompt='Read this terminal screenshot. Return JSON with keys error_code, database_port (integer), exit_status (integer), changes_applied (boolean).',expected={'error_code':'E_CONN_REFUSED','database_port':5432,'exit_status':2,'changes_applied':False}),
 dict(id='ocr',prompt='Transcribe the equipment label. Return JSON with keys model, batch, input, code, calibration. Preserve punctuation and distinguish similar characters.',expected={'model':'AX-250','batch':'TEST-042','input':'12 V DC / 8 A','code':'O0-I1-S5-B8','calibration':'2026-01-01'}),
 dict(id='diagram',prompt='Read the arrow directions. Return JSON with keys main_path (array of three labels in order), branch_source, branch_target.',expected={'main_path':['Client','API','Database'],'branch_source':'API','branch_target':'Cache'}),
 dict(id='chart',prompt='Read the bar chart. Return JSON with keys highest_worker, highest_count (integer), total_jobs (integer), difference_D_A (integer).',expected={'highest_worker':'D','highest_count':35,'total_jobs':94,'difference_D_A':23}),
 dict(id='spatial',prompt='Describe the layout. Return JSON with keys top_left, top_right, bottom_center, circle_count (integer). Use color and shape names.',expected={'top_left':'red circle','top_right':'blue square','bottom_center':'green triangle','circle_count':1})]
for c in cases:
 c['image']=c['id']+'.png';c['sha256']=hashlib.sha256((out/c['image']).read_bytes()).hexdigest()
(root/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
