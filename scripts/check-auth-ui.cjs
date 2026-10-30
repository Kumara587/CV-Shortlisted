// Isolated local UI render check. Does not create accounts or enter credentials.
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const profile=path.join(root,'backend','data','auth-render-check-'+Date.now());
fs.mkdirSync(profile,{recursive:true});
const browser=spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',[
 '--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',
 '--user-data-dir='+profile,'http://127.0.0.1:5173/'
],{windowsHide:true,stdio:'ignore'});
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 let ws;
 try{
  const portFile=path.join(profile,'DevToolsActivePort');
  for(let i=0;i<80&&!fs.existsSync(portFile);i++)await delay(250);
  const port=fs.readFileSync(portFile,'utf8').split('\n')[0].trim();
  assert.match(port,/^\d+$/);
  const tabs=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const target=tabs.find(t=>t.type==='page'&&t.url==='http://127.0.0.1:5173/');
  assert(target,'Own local render tab must exist');
  ws=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let id=0;const waiting=new Map();
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&waiting.has(m.id)){const p=waiting.get(m.id);waiting.delete(m.id);m.error?p.reject(new Error(m.error.message)):p.resolve(m.result);}};
  function command(method,params={}){return new Promise((resolve,reject)=>{const n=++id;waiting.set(n,{resolve,reject});ws.send(JSON.stringify({id:n,method,params}));setTimeout(()=>{if(waiting.delete(n))reject(new Error('UI check timed out: '+method));},10000).unref();});}
  async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true});if(r.exceptionDetails)throw new Error('UI expression failed');return r.result.value;}
  await command('Page.enable');
  for(const [label,width,height] of [['desktop',1440,1000],['mobile',390,844]]){
   await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:label==='mobile'});
   await command('Page.reload',{ignoreCache:true});
   for(let i=0;i<40;i++){if(await evaluate("document.querySelector('.auth-submit')?.textContent.includes('Sign in')"))break;await delay(250);}
   const size=await evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})');
   assert(size.scroll<=size.width,`${label} layout overflows: ${JSON.stringify(size)}`);
   assert.equal(await evaluate("document.querySelector('input[type=email]')!==null"),true);
   assert.equal(await evaluate("document.querySelector('#access-token')===null"),true);
   const image=await command('Page.captureScreenshot',{format:'png'});
   fs.writeFileSync(path.join(root,'backend','data',`auth-${label}.png`),Buffer.from(image.data,'base64'));
   await evaluate("document.querySelector('.auth-switch button').click()");
   assert.equal(await evaluate("document.querySelector('h2').textContent"),'Start your next chapter.');
   assert.equal(await evaluate("document.querySelectorAll('input[type=password]').length"),2);
   assert.equal(await evaluate("document.querySelector('input[autocomplete=given-name]')!==null && document.querySelector('input[autocomplete=family-name]')!==null && document.querySelector('input[type=date]')!==null"),true);
   assert.equal(await evaluate("document.querySelectorAll('.auth-password-rules li').length"),5);
   await evaluate("Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(document.querySelector('input[autocomplete=new-password]'),'Abcd12!x');document.querySelector('input[autocomplete=new-password]').dispatchEvent(new Event('input',{bubbles:true}))");
   for(let i=0;i<20;i++){if(await evaluate("document.querySelectorAll('.auth-password-rules li.passed').length===5"))break;await delay(100);}
   assert.equal(await evaluate("document.querySelectorAll('.auth-password-rules li.passed').length"),5);
   const signupImage=await command('Page.captureScreenshot',{format:'png'});
   fs.writeFileSync(path.join(root,'backend','data',`auth-signup-${label}.png`),Buffer.from(signupImage.data,'base64'));
   await evaluate("document.querySelector('.auth-switch button').click()");
   for(let i=0;i<20;i++){if(await evaluate("document.querySelector('.auth-label-row button')!==null"))break;await delay(100);}
   await evaluate("document.querySelector('.auth-label-row button').click()");
   assert.equal(await evaluate("document.querySelector('h2').textContent"),'Forgot your password?');
   assert.equal(await evaluate("document.querySelector('.auth-submit').disabled"),true);
   console.log(`${label}: login/signup/forgot-password and viewport layout passed`);
  }
  await command('Browser.close');
 }finally{if(ws)ws.close();browser.kill();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
