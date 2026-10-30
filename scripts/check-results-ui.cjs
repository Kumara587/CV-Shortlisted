// Local development fixture only. No accounts, CV uploads or AI requests.
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const profile=path.join(root,'backend','data','results-check-'+Date.now());
fs.mkdirSync(profile,{recursive:true});
const url='http://127.0.0.1:5173/scripts/results-preview.html';
const browser=spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',[
 '--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,url
],{windowsHide:true,stdio:'ignore'});
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 let ws;
 try{
  const portFile=path.join(profile,'DevToolsActivePort');
  for(let i=0;i<80&&!fs.existsSync(portFile);i++)await delay(250);
  const port=fs.readFileSync(portFile,'utf8').split('\n')[0].trim();assert.match(port,/^\d+$/);
  const tabs=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const target=tabs.find(t=>t.type==='page'&&t.url===url);assert(target);
  ws=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let id=0;const waiting=new Map();
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&waiting.has(m.id)){const p=waiting.get(m.id);waiting.delete(m.id);m.error?p.reject(new Error(m.error.message)):p.resolve(m.result);}};
  function command(method,params={}){return new Promise((resolve,reject)=>{const n=++id;waiting.set(n,{resolve,reject});ws.send(JSON.stringify({id:n,method,params}));setTimeout(()=>{if(waiting.delete(n))reject(new Error('Timed out: '+method));},10000).unref();});}
  async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true});assert(!r.exceptionDetails,'UI expression failed');return r.result.value;}
  async function wait(expression){for(let i=0;i<40;i++){if(await evaluate(expression))return;await delay(100);}throw new Error('UI state timed out');}
  for(const [label,width,height] of [['desktop',1280,1200],['mobile',390,1000]]){
   await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:label==='mobile'});
   await command('Page.reload',{ignoreCache:true});await wait("document.querySelectorAll('.requirement-card').length===3");
   const size=await evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})');assert(size.scroll<=size.width,'Horizontal overflow');
   assert.equal(await evaluate("document.querySelectorAll('.requirement-card[open]').length"),0);
   await evaluate("document.querySelector('.requirement-card>summary').click();document.querySelector('.requirement-card .source-evidence>summary').click()");
   assert.equal(await evaluate("document.querySelector('.source-evidence').querySelectorAll('figure').length"),1,'Repeated evidence must be deduplicated');
   const picture=await command('Page.captureScreenshot',{format:'png'});
   fs.writeFileSync(path.join(root,'backend','data',`results-${label}.png`),Buffer.from(picture.data,'base64'));
   await evaluate("document.querySelectorAll('.criteria-filters button')[1].click()");await wait("document.querySelectorAll('.requirement-card').length===2");
   await evaluate("document.querySelectorAll('.criteria-filters button')[3].click()");await wait("document.querySelectorAll('.requirement-card').length===1");
   assert.equal(await evaluate("document.querySelector('.requirement-title em').textContent"),'Preferred');
   console.log(`${label}: layout, evidence accordion, deduplication and filters passed`);
  }
  await command('Browser.close');
 }finally{if(ws)ws.close();browser.kill();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
