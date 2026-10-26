const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),path=require('path');
const root=path.resolve(__dirname,'..');
const esbuild=require(path.join(root,'node_modules/esbuild'));
let slots=[],cursor=0,App,apiBody,delayed;
const react={createElement:(type,props,...children)=>({type,props:{...props,children}}),useState(initial){const i=cursor++;if(!(i in slots))slots[i]=initial;return [slots[i],value=>slots[i]=typeof value==='function'?value(slots[i]):value];},useRef(initial){const i=cursor++;if(!(i in slots))slots[i]={current:initial};return slots[i];}};
const fixture={score:100,group:'requirements_review',skills:[{name:'Python',status:'semantic_review',similarity:0.72,must:false,reason:'AI related evidence',evidence:[{source_id:'a',line_start:1,quote:'Python'}]}],experience:{status:'not_required',reason:'Not required',evidence:[]},education:{status:'not_required',reason:'Not required',evidence:[]},components:{skills:{weight:100,points:100}},must_have_issues:[],missing_or_uncertain:[],review_status:'pending',warnings:[],rank:1};
const api={signIn:async()=>({retention_seconds:3600}),clearAccessToken:()=>{},saveReview:async()=>({saved:true}),deleteAllShortlists:async()=>({deleted:1}),deleteShortlist:async()=>{},downloadCsv:async()=>{},request:async()=>({requirements:{skills:[{name:'Python',must:false}],minimum_years:null,education:''},warnings:[]}),matchShortlist:async body=>{apiBody=body;if(delayed)return delayed;return {snapshot_id:'snapshot-1',notice:'Human review required',results:body.candidates.map((c,i)=>({...fixture,id:c.id,rank:i+1}))};}};
const source=fs.readFileSync(path.join(root,'src/main.jsx'),'utf8');
const compiled=esbuild.transformSync(source,{loader:'jsx',format:'cjs'}).code;
const sandbox={require(name){if(name==='react')return {__esModule:true,default:react,...react};if(name==='react-dom/client')return {createRoot:()=>({render:node=>App=node.type})};if(name==='./api')return api;if(name==='lucide-react')return new Proxy({},{get:()=>()=>null});if(name.endsWith('.css'))return {};throw Error(name);},document:{getElementById:()=>({})},exports:{},crypto:require('node:crypto').webcrypto,AbortController,setTimeout,clearTimeout,console};
vm.runInNewContext(compiled,sandbox);
const render=()=>{cursor=0;return App();};
function nodes(node){if(!node||typeof node!=='object')return [];if(Array.isArray(node))return node.flatMap(nodes);return [node,...nodes(node.props?.children)];}
function text(node){if(node==null||typeof node==='boolean')return '';if(typeof node!=='object')return String(node);if(Array.isArray(node))return node.map(text).join('');return text(node.props.children);}
const find=(tree,predicate)=>{const node=nodes(tree).find(predicate);assert.ok(node,'Control not found');return node;};
const button=(tree,label)=>find(tree,n=>n.type==='button'&&text(n).includes(label));
(async()=>{
 let tree=render();assert.match(text(tree),/Sign in/);find(tree,n=>n.props.id==='access-token').props.onChange({target:{value:'example-token'}});tree=render();await find(tree,n=>n.type==='form').props.onSubmit({preventDefault(){}});tree=render();await button(tree,'Try a sample').props.onClick();tree=render();
 await button(tree,'Match 5 resumes').props.onClick();tree=render();assert.match(text(tree),/Review the job requirements and confirm/);
 const confirm=find(tree,n=>n.props.className==='review-confirm');find(confirm,n=>n.type==='input').props.onChange({target:{checked:true}});tree=render();
 await button(tree,'Match 5 resumes').props.onClick();tree=render();assert.equal(apiBody.reviewed,true);assert.equal(apiBody.candidates.length,5);assert.equal(apiBody.candidates[0].name,undefined);assert.match(text(tree),/5 assessed/);
 button(tree,'#1').props.onClick();tree=render();assert.match(text(tree),/Score explanation/);assert.match(text(tree),/Human review/);assert.match(text(tree),/Semantic similarity: 0.720/);
 await find(tree,n=>n.type==='select'&&n.props['aria-label']==='Human review for candidate 1').props.onChange({target:{value:'shortlisted'}});tree=render();assert.match(text(tree),/shortlisted/);
 const years=find(tree,n=>n.type==='input'&&n.props.id==='years');years.props.onChange({target:{value:'2'}});tree=render();assert.match(text(tree),/Inputs changed/);assert.equal(button(tree,'Download CSV').props.disabled,true);assert.equal(find(find(tree,n=>n.props.className==='review-confirm'),n=>n.type==='input').props.checked,false);
 let resolve;delayed=new Promise(r=>resolve=r);
 find(find(tree,n=>n.props.className==='review-confirm'),n=>n.type==='input').props.onChange({target:{checked:true}});tree=render();
 const pending=button(tree,'Re-match').props.onClick();
 await button(tree,'Clear all resumes').props.onClick();tree=render();
 resolve({snapshot_id:'snapshot-stale',notice:'Review',results:apiBody.candidates.map((c,i)=>({...fixture,id:c.id,rank:i+1}))});await pending;tree=render();assert.doesNotMatch(text(tree),/Score explanation/);assert.match(text(tree),/0 assessed/);
 await button(tree,'Sign out').props.onClick();tree=render();assert.match(text(tree),/Sign in/);
 console.log('PASS: sign-in/sign-out, server review persistence,  requirement confirmation, backend request contract, result breakdown, human decision, stale-state protection, clear-all removal.');
})().catch(e=>{console.error(e);process.exitCode=1});
