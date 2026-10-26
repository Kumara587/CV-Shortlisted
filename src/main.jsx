import React, { useRef, useState } from 'react';

import { createRoot } from 'react-dom/client';

import { UploadCloud, ChevronDown, X, FileText, Plus, Download, ShieldCheck } from 'lucide-react';

import './styles.css';

import { request, parseResume, matchShortlist, signIn, clearAccessToken, saveReview, deleteShortlist, deleteAllShortlists, downloadCsv } from './api';



const sampleJob = `Software Quality Assurance (QA) Intern – Requirements\n\nEducational qualifications\nCurrently pursuing or recently completed a degree, diploma, or higher diploma in Information Technology or Software Engineering.\n\nSkills & experience\nKnowledge of Manual Testing, Automation Testing, Selenium, SQL, MySQL, REST API and API Testing. Familiarity with Git, Excel and Jira. Good Communication skills.\nMinimum 1 year of practical experience. Diploma or higher preferred.`;

const samplePeople = [

 ['Amelia Bennett', 'amelia.bennett@example.com', '3 years of experience. Bachelor degree. Manual Testing Automation Testing Selenium SQL MySQL REST API API Testing Git Excel Jira Communication.'],

 ['Noah Williams', 'noah.williams@example.com', '2 years of experience. Diploma. Manual Testing SQL MySQL REST API API Testing Git Excel Jira Communication.'],

 ['Isabella Chen', 'isabella.chen@example.com', '1 year of experience. Bachelor degree. Manual Testing Selenium SQL Git Jira Communication.'],

 ['Oliver Davis', 'oliver.davis@example.com', '1 year of experience. Diploma. Manual Testing SQL Excel Communication.'],

 ['Sophia Wilson', 'sophia.wilson@example.com', '0 years of experience. High school. Excel Communication.']

];

const groupLabel = group => ({requirements_review:'Qualification review',must_have_review:'Must-have review',unscored:'Unscored'})[group];

const shown = (r,filter) => filter==='all'||filter===r.group||filter===r.review_status;

function Evidence({items,sourceName}) {

 return items.length?<ul className="evidence">{items.map((ev,i)=><li key={i}><b>{sourceName} · parsed text line {ev.line_start}</b><blockquote>{ev.truncated_before?'…':''}{ev.quote}{ev.truncated?'…':''}</blockquote></li>)}</ul>:<p className="text-xs">No supporting source text found.</p>;

}

function App() {

 const [job,setJob]=useState(''), [skills,setSkills]=useState([]), [newSkill,setNewSkill]=useState(''), [years,setYears]=useState(''), [degree,setDegree]=useState('');

 const [files,setFiles]=useState([]), [paste,setPaste]=useState(false), [resumeText,setResumeText]=useState(''), [results,setResults]=useState([]), [blind,setBlind]=useState(false), [filter,setFilter]=useState('all'), [open,setOpen]=useState({}), [error,setError]=useState(''), [drag,setDrag]=useState(false), [busy,setBusy]=useState(false), [dirty,setDirty]=useState(false);

 const [extracting,setExtracting]=useState(false), [apiNote,setApiNote]=useState('');

 const input=useRef(), revision=useRef(0), uploadLock=useRef(false), uploads=useRef(new Map());

 const [uploading,setUploading]=useState(false), [reviewed,setReviewed]=useState(false), [matchNotice,setMatchNotice]=useState('');
 const [authenticated,setAuthenticated]=useState(false),[tokenDraft,setTokenDraft]=useState(''),[snapshot,setSnapshot]=useState(''),[retention,setRetention]=useState(3600),[deletionNote,setDeletionNote]=useState(''),[reviewSaving,setReviewSaving]=useState(false),[exporting,setExporting]=useState(false);
 const currentSnapshot=useRef('');

 const requirements=()=>({skills,minimum_years:years===''?null:Number(years),education:degree});

 const changed=()=>{revision.current+=1;setDirty(true);setReviewed(false);};
 async function login(e) {
  e.preventDefault();setError('');
  try{const session=await signIn(tokenDraft);setAuthenticated(true);setRetention(session.retention_seconds);setTokenDraft('');}
  catch(e){setError(e.message);setTokenDraft('');}
 }
 async function deleteServerExports() {
  try{await deleteAllShortlists();setDeletionNote('Server export snapshots deleted.');setSnapshot('');currentSnapshot.current='';return true;}
  catch(e){setDeletionNote('Server deletion failed. Retry below; retained snapshots expire automatically. '+e.message);return false;}
 }
 async function logout(){const cleanup=clearResumes();clearAccessToken();setAuthenticated(false);setTokenDraft('');await cleanup;}


 function extract(text) { setJob(text); changed(); }

 async function extractRequirements() {

  const version=revision.current; setExtracting(true);setApiNote('');

  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),10000);

  try {

   const data=await request('/api/requirements/extract',{job_description:job},controller.signal);

   if(revision.current!==version){setApiNote('Inputs changed during extraction. Kept your edits; extract again when ready.');return;}

   setSkills(data.requirements.skills);setYears(data.requirements.minimum_years??'');setDegree(data.requirements.education);changed();

   setApiNote(data.warnings.join(' '));

  } catch(e) {setApiNote(e.name==='AbortError'?'Extraction timed out. Your edits are preserved.':'Could not extract. Start the local API, then retry. '+e.message);}

  finally {clearTimeout(timer);setExtracting(false);}

 }

 function addSkill(e) {e.preventDefault(); const name=newSkill.trim(); if(name&&!skills.some(s=>s.name.toLowerCase()===name.toLowerCase())) {setSkills([...skills,{name,must:false}]);changed();} setNewSkill('');}

 function removeResume(id) {

  uploads.current.get(id)?.abort();uploads.current.delete(id);

  setFiles(previous=>previous.filter(f=>f.id!==id));setResults([]);setOpen({});changed();
  if(authenticated)void deleteServerExports();

 }

 async function clearResumes() {

  for(const controller of uploads.current.values())controller.abort();uploads.current.clear();

  setFiles([]);setResults([]);setOpen({});setResumeText('');setPaste(false);setError('');changed();

  if(input.current)input.current.value='';

 }

 async function addFiles(list) {

  if(uploadLock.current)return;

  uploadLock.current=true;setUploading(true);setError('');const errors=[];

  const selected=Array.from(list), capacity=10-files.length;

  const batch=[];

  for(const file of selected) {

   if(!/\.(pdf|docx|txt)$/i.test(file.name)){errors.push(`${file.name}: use PDF, DOCX or TXT.`);continue;}

   if(file.size>5*1024*1024){errors.push(`${file.name}: exceeds 5 MB.`);continue;}

   if(file.size===0){errors.push(`${file.name}: file is empty.`);continue;}

   if(file.name.length>255){errors.push('Filename exceeds 255 characters. Rename the file.');continue;}

   if(batch.length>=capacity){errors.push('Only 10 resumes can be added. Extra files skipped.');break;}

   const id=crypto.randomUUID(), controller=new AbortController();uploads.current.set(id,controller);

   batch.push({file,id,controller});

  }

  setFiles(previous=>[...previous,...batch.map(({file,id})=>({id,name:file.name,text:'',status:'parsing',unparsed:true,warnings:[]}))]);

  setError(errors.join(' '));changed();

  try {

   for(const {file,id,controller} of batch) {

    if(controller.signal.aborted)continue;

    const timer=setTimeout(()=>controller.abort(),30000);

    try {

     const data=await parseResume(file,controller.signal);

     setFiles(previous=>previous.map(f=>f.id===id?{...f,name:data.filename,text:data.text||'',status:data.status,unparsed:data.status!=='parsed',warnings:data.warnings||[],parseError:data.error?.message}:f));

    } catch(e) {

     setFiles(previous=>previous.map(f=>f.id===id?{...f,status:'error',parseError:e.name==='AbortError'?'Upload timed out. Remove and choose this file again.':e.message}:f));

    } finally {clearTimeout(timer);uploads.current.delete(id);}

   }

  } finally {uploadLock.current=false;setUploading(false);if(input.current)input.current.value='';}

 }

 function addPaste() {if(uploading)return;if(!resumeText.trim())return; if(resumeText.length>200000){setError('Resume text exceeds 200,000 characters.');return;} if(files.length>=10){setError('Remove a resume before adding another.');return;}setFiles([...files,{id:crypto.randomUUID(),name:`Pasted resume ${files.filter(f=>f.pasted).length+1}`,text:resumeText,pasted:true,status:'parsed'}]);setResumeText('');setPaste(false);changed();}

 async function sample() {await clearResumes();extract(sampleJob);setYears('1');setDegree('Diploma');setFiles(samplePeople.map(([name,email,text])=>({id:crypto.randomUUID(),name:`${name.replaceAll(' ','_')}.txt`,person:name,email,text:`${name}\n${email}\n${text}`})));setResults([]);setError('');}

 async function screen() {

  if(uploading){setError('Wait for parsing to finish.');return;}

  if(!reviewed){setError('Review the job requirements and confirm them before matching.');return;}

  if(!files.length){setError('Add at least one resume to match.');return;}

  setError('');setBusy(true);const version=revision.current;

  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),30000);

  try {

   const data=await matchShortlist({requirements:requirements(),reviewed:true,candidates:files.map(f=>({id:f.id,text:f.text,display_label:(f.person||f.name).slice(0,160),parse_status:f.unparsed?(f.status==='needs_text'?'needs_text':'error'):'parsed',warnings:f.warnings||[]}))},controller.signal);

   if(version!==revision.current){await deleteShortlist(data.snapshot_id).catch(()=>setDeletionNote('Unused export snapshot deletion failed; it will expire automatically.'));setError('Inputs changed while matching. Review requirements and match again.');return;}
   const previous=currentSnapshot.current;setSnapshot(data.snapshot_id);currentSnapshot.current=data.snapshot_id;
   if(previous&&previous!==data.snapshot_id)void deleteShortlist(previous).catch(()=>setDeletionNote('Previous export snapshot will expire automatically.'));

   setResults(data.results.map(r=>{

    const f=files.find(f=>f.id===r.id), index=files.indexOf(f);

    return {...f,...r,index,person:f.person||f.name,email:f.email||'',unparsed:r.score===null,matched:r.skills.filter(s=>s.status==='supported'),missing:r.skills.filter(s=>s.status!=='supported')};

   }));setMatchNotice(data.notice);setDirty(false);setOpen({});

  } catch(e) {setError(e.name==='AbortError'?'Matching timed out. Existing results are preserved.':'Matching failed. '+e.message);}

  finally {clearTimeout(timer);setBusy(false);}

 }

 async function humanReview(id,status){
  if(dirty||!snapshot)return;setReviewSaving(true);setError('');const target=snapshot,version=revision.current;
  try{await saveReview(target,id,status);if(target!==currentSnapshot.current||version!==revision.current)return;setResults(previous=>previous.map(r=>r.id===id?{...r,review_status:status}:r));}
  catch(e){setError(e.message);}
  finally{setReviewSaving(false);}
 }
 async function csv(){if(dirty||!snapshot)return;setExporting(true);setError('');try{await downloadCsv(snapshot,blind);}catch(e){setError(e.message);}finally{setExporting(false);}}
 if(!authenticated)return <main className="mx-auto w-full max-w-[600px] auth-panel"><h1>Resume screener</h1><p>Sign in with the personal access token issued by your administrator. Tokens stay in this tab and are cleared on sign-out or refresh.</p><form onSubmit={login}><label htmlFor="access-token">Access token</label><input id="access-token" type="password" autoComplete="off" value={tokenDraft} onChange={e=>setTokenDraft(e.target.value)}/><button className="primary" disabled={!tokenDraft.trim()} type="submit">Sign in</button></form>{error&&<p className="error" role="alert">{error}</p>}{deletionNote&&<p role="status">{deletionNote}</p>}</main>;
 return <main className="mx-auto w-full max-w-[1080px]">

  <div className="intro flex items-center justify-between gap-3"><span className="flex items-center gap-2"><span className="brandmark">s</span><b>shortlist<span className="font-normal"> studio</span></b></span><span className="demo-label">PRIVATE · EVIDENCE MATCHING</span><button className="text-link" onClick={logout}>Sign out</button></div>

  <section className="screener"><header className="flex items-center justify-between gap-3"><h1>Resume screener</h1><span className="remaining">{10-files.length} of 10 resume slots available</span></header>

   <div className="grid md:grid-cols-[1.05fr_1fr]">

    <section className="column job-column"><h2><span className="step">Step 1</span> Paste the job description</h2>

     <textarea aria-label="Job description" className="job-text" placeholder={'Paste your job description here…\n\nInclude the skills, experience and qualifications you’re looking for.'} value={job} onChange={e=>extract(e.target.value)}/>

     <div className="flex flex-wrap gap-2 mt-3"><button className="outline" disabled={extracting||job.trim().length<20} onClick={extractRequirements}>{extracting?'Extracting…':'Extract requirements'}</button><span className="text-xs">Re-extraction replaces the requirements below.</span></div>

     {apiNote&&<p className="helper" role="status">{apiNote}</p>}

     <p className="helper">Review extracted requirements or enter them manually. Skills found in your job description. Tap a skill to make it a must-have. Unverified must-haves appear in a separate review group; they are never automatically rejected.</p>

     <div className="skills flex flex-wrap gap-2">{skills.length?skills.map(s=><button key={s.name} aria-pressed={s.must} className={'chip '+(s.must?'must':'')} onClick={()=>{setSkills(skills.map(x=>x.name===s.name?{...x,must:!x.must}:x));changed();}}>{s.must&&<span>★ </span>}{s.name}</button>):<span className="empty-skills">Your skill chips will appear here</span>}</div>

     <form className="flex gap-2" onSubmit={addSkill}><input aria-label="New skill" className="min-w-0 flex-1" placeholder="Add a skill, e.g. Kubernetes" maxLength={60} value={newSkill} onChange={e=>setNewSkill(e.target.value)}/><button className="outline" type="submit">Add</button></form>

     <div className="requirements flex flex-wrap items-center gap-3"><label htmlFor="years">Minimum years</label><input id="years" type="number" min="0" max="60" step="0.5" value={years} onChange={e=>{setYears(e.target.value);changed();}}/><label htmlFor="degree">Minimum<br/>degree</label><select id="degree" value={degree} onChange={e=>{setDegree(e.target.value);changed();}}><option value="">Any degree</option><option>Diploma</option><option>Bachelor</option><option>Master</option><option>PhD</option></select></div>

     <label className="review-confirm"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/> I reviewed these requirements and confirmed they describe job qualifications, without protected or personal attributes.</label>

    </section>

    <section className="column"><h2><span className="step">Step 2</span> Add up to 10 resumes</h2>

     <div className={'dropzone '+(drag?'dragging':'')} onDragOver={e=>{e.preventDefault();setDrag(true);}} onDragLeave={()=>setDrag(false)} onDrop={e=>{e.preventDefault();setDrag(false);addFiles(e.dataTransfer.files);}}><UploadCloud size={28} strokeWidth={1.4}/><h3>Drop resumes here</h3><p>PDF, DOCX or TXT, up to 5 MB each.</p><button className="outline bg-white" disabled={uploading} onClick={()=>input.current.click()}>{uploading?'Parsing…':'Choose files'}</button><input ref={input} type="file" accept=".pdf,.docx,.txt" multiple hidden onChange={e=>addFiles(e.target.files)}/></div>

     <button className="text-link paste-link" onClick={()=>setPaste(!paste)} aria-expanded={paste}>Or paste resume text</button>

     {paste&&<div className="paste-box"><label htmlFor="resume">Resume text</label><textarea id="resume" value={resumeText} onChange={e=>setResumeText(e.target.value)} placeholder="Paste a candidate’s resume, including name, skills and experience…"/><div className="flex justify-end gap-2"><button className="outline" onClick={()=>setPaste(false)}>Cancel</button><button className="small-primary" onClick={addPaste} disabled={uploading||!resumeText.trim()}>Add resume</button></div></div>}

     <p className="helper">Original files are not saved. Parsed text stays in this tab; minimal server export snapshots expire automatically. Remove or Clear all to discard text and delete server exports. No external OCR or AI.</p>

     {files.length>0&&<button className="text-link" onClick={clearResumes}>Clear all resumes</button>}
     <p className="helper">Server export retention: {Math.round(retention/60)} minutes. Downloads are separate copies on your device.</p><button className="text-link" onClick={deleteServerExports}>Delete all my server exports</button>{deletionNote&&<p role="status" className="helper">{deletionNote}</p>}

     <ul className="file-list">{files.map(f=><li key={f.id}><FileText size={16}/><div className="min-w-0 flex-1 break-words"><span>{f.name}</span><small role="status">{f.status==='parsing'?'Parsing locally…':f.parseError||((f.status==='needs_text')?'No readable text — paste text instead.':`${f.text.length.toLocaleString()} characters available`)}</small>{f.warnings?.map((warning,i)=><small key={i}>{warning}</small>)}{f.text&&<details><summary>Review parsed text</summary><pre className="parsed-preview">{f.text}</pre></details>}</div><button className="remove" aria-label={`Remove ${f.name}`} onClick={()=>removeResume(f.id)}>{f.status==='parsing'?'Cancel':'Remove'}</button></li>)}</ul>

     {!files.length&&<p className="upload-hint">Start with your own resumes or explore the sample below.</p>}

    </section>

   </div>

   <div className="action-bar"><div><div className="flex flex-wrap items-center gap-x-4 gap-y-3"><button className="primary" onClick={screen} disabled={busy||uploading}>{busy?'Matching…':`${results.length?'Re-match':'Match'} ${files.length||''} resume${files.length===1?'':'s'}`}</button><button className="text-link" disabled={uploading} onClick={sample}>Try a sample job and 5 resumes</button></div><p className="action-note">{results.length?'Review requirements again after changing inputs.':'Evidence matching supports your review; it does not decide who to hire.'}</p></div><p className="privacy"><ShieldCheck size={18}/><span><b>Authenticated parsing and matching.</b><br/>Full CV text is not retained on the server. Export fields have a limited retention period.</span></p></div>

   {error&&<p className="error" role="alert">{error}</p>}

   <section className="shortlist"><div className="results-header"><div className="flex flex-wrap items-center justify-between gap-4"><h2>Ranked shortlist</h2><div className="filters flex flex-wrap items-center gap-3"><label className="flex items-center gap-2"><input type="checkbox" checked={blind} onChange={e=>setBlind(e.target.checked)}/>Blind mode</label><label>Show <select aria-label="Candidate status filter" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All candidates</option><option value="requirements_review">Qualification review</option><option value="must_have_review">Must-have review</option><option value="unscored">Unscored</option><option value="pending">Pending human review</option><option value="shortlisted">Human shortlisted</option></select></label><button className="outline flex items-center gap-2" onClick={csv} disabled={!results.length||dirty||!snapshot||reviewSaving||exporting}><Download size={14}/>{exporting?'Downloading…':'Download CSV'}</button></div></div><div className="counts flex flex-wrap gap-2"><span className="chip">{results.length} assessed</span>{['requirements_review','must_have_review','unscored'].map(group=><span className="chip" key={group}>{results.filter(r=>r.group===group).length} {groupLabel(group)}</span>)}</div>{dirty&&results.length>0&&<p className="stale" role="status">Inputs changed. These results use the previous requirements; review and re-match before using them.</p>}</div>

    {!results.length?<div className="empty-results"><span className="empty-icon"><FileText size={25}/></span><h3>Review evidence before deciding</h3><p>Add resumes, review the requirements, then match to see supporting text and uncertainty.</p></div>:<><div className="scoring-note">{matchNotice} Protected and personal fields, employment dates, institution prestige and graduation years are not scoring criteria. Blind mode only hides row labels; source text can contain identifying information.</div>{results.filter(r=>shown(r,filter)).map(r=><article className="candidate" key={r.id}><button className="candidate-summary" aria-expanded={!!open[r.id]} onClick={()=>setOpen({...open,[r.id]:!open[r.id]})}><span className="rank">#{r.rank}</span><span className="ring" style={{'--score':`${r.score??0}%`}}><b>{r.score??'—'}</b></span><span className="candidate-name"><strong>{blind?`Candidate ${String(r.index+1).padStart(2,'0')}`:r.person}</strong><small>Evidence coverage · {r.review_status.replaceAll('_',' ')}</small></span><span className={'status '+(r.group==='must_have_review'?'partial':r.unparsed?'low':'good')}>{groupLabel(r.group)}</span><ChevronDown size={18} className={open[r.id]?'rotate-180':''}/></button>{open[r.id]&&<div className="details"><div className="score-breakdown"><h4>Score explanation</h4><p>Only active requirements count. Explicitly supported skills receive full credit. AI semantic matches receive half credit and require verification. Uncertain or missing evidence receives no points. Score measures documented evidence, not ability.</p><table><thead><tr><th>Criterion</th><th>Weight</th><th>Points</th></tr></thead><tbody>{Object.entries(r.components).map(([name,c])=><tr key={name}><td>{name}</td><td>{c.weight.toFixed(1)}%</td><td>{r.score===null?'Unscored':c.points.toFixed(2)}</td></tr>)}</tbody></table></div>

      {r.must_have_issues.length>0&&<div className="must-issues"><h4>Must-haves requiring verification</h4><p>{r.must_have_issues.map(s=>`${s.name}: ${s.status.replaceAll('_',' ')}`).join(' · ')}. This is a review flag, not an automatic rejection.</p></div>}

      <div><h4>Skill evidence</h4>{r.skills.length?r.skills.map(c=><section className="criterion" key={c.name}><b>{c.name}{c.must?' ★':''} · {c.status.replaceAll('_',' ')}</b><p>{c.reason}</p>{c.similarity!=null&&<p>Semantic similarity: {c.similarity.toFixed(3)} · human verification required</p>}<Evidence items={c.evidence} sourceName={blind?'Resume source':r.name}/></section>):<p>No skill requirements.</p>}</div>

      {['experience','education'].map(key=><section className="criterion" key={key}><h4>{key==='experience'?'Experience':'Education'} · {r[key].status.replaceAll('_',' ')}</h4><p>{r[key].reason}</p><Evidence items={r[key].evidence} sourceName={blind?'Resume source':r.name}/></section>)}

      {r.warnings.map((warning,i)=><p className="stale" key={i}>{warning}</p>)}

      {r.text&&<details><summary>View source text with line references</summary><div className="parsed-preview">{r.text.split(/\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/).map((line,i)=><div key={i}><span className="source-line">{i+1}</span>{line||' '}</div>)}</div></details>}

      <label className="human-review">Human review <select aria-label={`Human review for candidate ${r.index+1}`} value={r.review_status} disabled={dirty||reviewSaving||!snapshot} onChange={e=>humanReview(r.id,e.target.value)}><option value="pending">Pending review</option><option value="reviewed">Reviewed — undecided</option><option value="shortlisted">Shortlist after human review</option><option value="not_progressing">Do not progress — human decision</option></select></label><p className="text-xs">Review evidence and missing information with the candidate before deciding. Your choice is saved in your private export snapshot until deletion or expiry; it does not alter scores or ranking.</p>

     </div>}</article>)}{!results.some(r=>shown(r,filter))&&<p className="p-8 text-center">No candidates in this category.</p>}</>}

   </section>

  </section><footer className="page-footer">Built for a more thoughtful shortlist. <span>Original interface · Step 4 private export</span></footer>

 </main>;

}

createRoot(document.getElementById('root')).render(<App/>);



