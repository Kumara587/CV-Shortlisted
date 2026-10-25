const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),path=require('path');
const root=path.resolve(__dirname,'..'),esbuild=require(path.join(root,'node_modules/esbuild'));
let calls=[],downloaded=false,revoked=false;
function load(base='',origin='http://localhost:5173') {
 const code=esbuild.transformSync(fs.readFileSync(path.join(root,'src/api.js'),'utf8'),{format:'cjs',define:{'import.meta.env':JSON.stringify({VITE_API_BASE_URL:base})}}).code;
 const exports={};
 const sandbox={module:{exports},exports,URL:class extends URL {static createObjectURL(){return 'blob:test'}static revokeObjectURL(){revoked=true}},window:{location:{href:origin+'/',origin,hostname:new URL(origin).hostname}},document:{createElement:()=>({click(){downloaded=true}})},AbortController,clearTimeout:()=>{},setTimeout:(fn,delay)=>{if(delay===1000)fn();return 1},fetch:async(url,options)=>{calls.push({url,options});return {ok:true,status:200,json:async()=>({authenticated:true,retention_seconds:3600}),blob:async()=>({})};}};
 vm.runInNewContext(code,sandbox);return sandbox.module.exports;
}
(async()=>{
 const api=load();await assert.rejects(api.request('/api/test',{}),/Sign in/);assert.equal(calls.length,0);
 await api.signIn('synthetic-test-token');await api.downloadCsv('owned-snapshot',true);
 assert.equal(calls[1].url,'http://127.0.0.1:8000/api/shortlists/owned-snapshot/export?blind=true');
 assert.equal(calls[1].options.headers.Authorization,'Bearer synthetic-test-token');assert.equal(calls[1].options.redirect,'error');assert.ok(downloaded&&revoked);
 api.clearAccessToken();await assert.rejects(api.downloadCsv('owned-snapshot',false),/Sign in/);
 const foreign=load('https://thirdparty.example','https://screening.example');await assert.rejects(foreign.signIn('never-sent'),/Cross-site/);assert.equal(calls.length,2);
 const insecure=load('http://screening.example','https://screening.example');await assert.rejects(insecure.signIn('never-sent'),/HTTPS/);assert.equal(calls.length,2);
 const production=load('','https://screening.example');await production.signIn('synthetic-test-token');assert.equal(calls[2].url,'https://screening.example/api/session');
 console.log('PASS: memory-only credentials, authenticated server export, blind flag, revoked object URLs, blocked external/insecure endpoints, same-origin production.');
})().catch(e=>{console.error(e);process.exitCode=1});
