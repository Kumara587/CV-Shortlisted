import React, { useEffect,useRef, useState } from 'react';
import Auth from './Auth';
import ScoreDetails from './ScoreDetails';
import {currentSession,authAction} from './api';

import { createRoot } from 'react-dom/client';

import { UploadCloud, ChevronDown, X, FileText, Plus, Download, ShieldCheck } from 'lucide-react';

import './styles.css';

import { request, parseResume, matchShortlist, saveReview, deleteShortlist, deleteAllShortlists, downloadCsv, listJobs, getJob, persistJob, removeJob, listRuns, getRun, removeRun } from './api';



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

 const [criteria,setCriteria]=useState([]);
 const [extractionReceipt,setExtractionReceipt]=useState(null),[aiConfigured,setAiConfigured]=useState(null);
 const [syntheticConfirmed,setSyntheticConfirmed]=useState(false);
 const [extracting,setExtracting]=useState(false), [apiNote,setApiNote]=useState('');

 const input=useRef(), revision=useRef(0), uploadLock=useRef(false), uploads=useRef(new Map());

 const [uploading,setUploading]=useState(false), [reviewed,setReviewed]=useState(false), [matchNotice,setMatchNotice]=useState('');
 const [authenticated,setAuthenticated]=useState(false),[authChecking,setAuthChecking]=useState(true),[snapshot,setSnapshot]=useState(''),[retention,setRetention]=useState(3600),[deletionNote,setDeletionNote]=useState(''),[reviewSaving,setReviewSaving]=useState(false),[exporting,setExporting]=useState(false);
 const currentSnapshot=useRef('');
 const [jobTitle,setJobTitle]=useState(''),[savedJobId,setSavedJobId]=useState('');
 const [savedJobs,setSavedJobs]=useState([]),[history,setHistory]=useState([]),[libraryBusy,setLibraryBusy]=useState(false),[libraryNote,setLibraryNote]=useState('');
 const libraryVersion=useRef(0);
 const candidateInputs=()=>files.map(f=>({id:f.id,text:f.text,display_label:(f.person||f.name).slice(0,160),parse_status:f.unparsed?(f.status==='needs_text'?'needs_text':'error'):'parsed',warnings:f.warnings||[]}));
 async function refreshJobs(){const version=libraryVersion.current;try{const data=await listJobs();if(version===libraryVersion.current)setSavedJobs(data.jobs);}catch(e){if(version===libraryVersion.current)setError(e.message);}}
 function restoreWorkspace(workspace,id){
  changed();setJob(workspace.job_description);setJobTitle(workspace.title);setSavedJobId(id);
  setSkills(workspace.requirements.skills);setCriteria(workspace.requirements.criteria||[]);setExtractionReceipt(workspace.requirements.extraction_receipt||null);setYears(workspace.requirements.minimum_years??'');setDegree(workspace.requirements.education);
  setFiles(workspace.candidates.map(c=>({id:c.id,name:c.display_label||c.id,text:c.text,status:c.parse_status,unparsed:c.parse_status!=='parsed',warnings:c.warnings})));
  setResults([]);setOpen({});setSnapshot('');currentSnapshot.current='';setMatchNotice('');setApiNote('');setResumeText('');setPaste(false);setFilter('all');
 }
 function showResults(data,sourceFiles){
  setResults(data.results.map(r=>{const f=sourceFiles.find(f=>f.id===r.id);const index=sourceFiles.indexOf(f);return {...f,...r,index,person:f.person||f.name,email:f.email||'',unparsed:r.score===null,matched:r.skills.filter(s=>s.status==='supported'),missing:r.skills.filter(s=>s.status!=='supported')};}));
  setMatchNotice(data.notice);setDirty(false);setOpen({});
 }
 async function saveWorkspace(){
  const data=await persistJob(savedJobId,{title:jobTitle.trim(),job_description:job,requirements:requirements(),candidates:candidateInputs()});
  setSavedJobId(data.id);return data.id;
 }
 async function saveCurrent(){
  if(!jobTitle.trim()){setError('Enter a job title before saving.');return;}
  setLibraryBusy(true);setError('');
  try{await saveWorkspace();await refreshJobs();setLibraryNote('Job and parsed CV text saved. They remain until you delete the job.');}catch(e){setError(e.message);}finally{setLibraryBusy(false);}
 }
 async function openSavedJob(id){
  if(busy||uploading||libraryBusy)return;
  setLibraryBusy(true);setError('');const version=libraryVersion.current;
  try{const [data,runs]=await Promise.all([getJob(id),listRuns(id)]);if(version!==libraryVersion.current)return;restoreWorkspace(data.workspace,data.id);setHistory(runs.runs);setLibraryNote('Saved job opened. Review requirements before a new match.');}catch(e){setError(e.message);}finally{setLibraryBusy(false);}
 }
 async function openScreening(id){
  setLibraryBusy(true);setError('');const version=libraryVersion.current;
  try{const data=await getRun(id);if(version!==libraryVersion.current)return;restoreWorkspace(data.workspace,data.job_id);const sourceFiles=data.workspace.candidates.map(c=>({id:c.id,name:c.display_label||c.id,text:c.text,warnings:c.warnings}));showResults(data.result,sourceFiles);setSnapshot(data.id);currentSnapshot.current=data.id;setLibraryNote('Historical screening opened. Saved scores and reviews are restored.');}catch(e){setError(e.message);}finally{setLibraryBusy(false);}
 }
 async function deleteSavedJob(id){
  setLibraryBusy(true);setError('');try{await removeJob(id);if(savedJobId===id){await clearResumes();setJob('');setJobTitle('');setSkills([]);setCriteria([]);setExtractionReceipt(null);setYears('');setDegree('');setSavedJobId('');setSnapshot('');currentSnapshot.current='';setHistory([]);}await refreshJobs();setLibraryNote('Job, its saved CV text and screening history deleted.');}catch(e){setError(e.message);}finally{setLibraryBusy(false);}
 }
 async function deleteScreening(id){
  setLibraryBusy(true);setError('');try{await removeRun(id);setHistory(previous=>previous.filter(r=>r.id!==id));if(currentSnapshot.current===id){setResults([]);setSnapshot('');currentSnapshot.current='';}await refreshJobs();setLibraryNote('Screening deleted. The saved job and its CV text remain.');}catch(e){setError(e.message);}finally{setLibraryBusy(false);}
 }
 async function newJob(){await clearResumes();setJob('');setJobTitle('');setSkills([]);setCriteria([]);setExtractionReceipt(null);setYears('');setDegree('');setSavedJobId('');setHistory([]);setSnapshot('');currentSnapshot.current='';setLibraryNote('New unsaved job. Save it to keep CVs and screening history.');}


 const requirements=()=>({skills,criteria,extraction_receipt:extractionReceipt,minimum_years:years===''?null:Number(years),education:degree});

 const changed=()=>{revision.current+=1;setDirty(true);setReviewed(false);};
 function acceptSession(session){setAuthenticated(true);setAuthChecking(false);setRetention(session.retention_seconds);setAiConfigured(session.ai_configured??null);setError('');void refreshJobs();}
 useEffect(()=>{
  if(/^#(?:reset|verify)=/.test(window.location.hash)){setAuthChecking(false);return;}
  let active=true;
  currentSession().then(session=>{if(active)acceptSession(session);}).catch(()=>{}).finally(()=>{if(active)setAuthChecking(false);});
  return()=>{active=false;};
 },[]);
 async function deleteServerExports() {
  try{await deleteAllShortlists();setDeletionNote('Temporary export snapshots deleted. Saved history is unchanged.');if(!currentSnapshot.current.startsWith('run_')){setSnapshot('');currentSnapshot.current='';}return true;}
  catch(e){setDeletionNote('Server deletion failed. Retry below; retained snapshots expire automatically. '+e.message);return false;}
 }
 async function logout(){try{await authAction('logout');}catch(e){setError(e.message);return;}revision.current+=1;libraryVersion.current+=1;uploads.current.forEach(c=>c.abort());uploads.current.clear();setFiles([]);setResults([]);setAuthenticated(false);setSavedJobs([]);setHistory([]);setJob('');setJobTitle('');setSavedJobId('');setSkills([]);setCriteria([]);setExtractionReceipt(null);setYears('');setDegree('');setSnapshot('');currentSnapshot.current='';setLibraryNote('');setSyntheticConfirmed(false);}


 function extract(text) { setJob(text); changed(); }

 async function extractRequirements() {

  const version=revision.current; setExtracting(true);setApiNote('');

  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),165000);

  try {

   const data=await request('/api/ai/requirements/extract',{job_description:job,synthetic_data_confirmed:syntheticConfirmed},controller.signal);

   if(revision.current!==version){setApiNote('Inputs changed during extraction. Kept your edits; extract again when ready.');return;}

   setSkills(data.requirements.skills);setCriteria(data.requirements.criteria||[]);setExtractionReceipt(data.requirements.extraction_receipt||null);setYears(data.requirements.minimum_years??'');setDegree(data.requirements.education);changed();

   setApiNote((data.method==='llm_structured'?'LLM structured extraction. ':'Legacy source extraction. ')+data.warnings.join(' '));

  } catch(e) {setApiNote(e.name==='AbortError'?'Extraction timed out. Your edits are preserved.':'Could not extract requirements. '+e.message);}

  finally {clearTimeout(timer);setExtracting(false);}

 }

 function addSkill(e) {e.preventDefault(); const name=newSkill.trim(); if(name&&criteria.length<100&&!criteria.some(c=>c.text.toLowerCase()===name.toLowerCase())) {setCriteria([...criteria,{id:crypto.randomUUID(),text:name,category:'skill',importance:'preferred',source_quote:'',source_line:1,operator:'all',conditions:[name]}]);changed();} setNewSkill('');}

 function removeResume(id) {

  uploads.current.get(id)?.abort();uploads.current.delete(id);

  setFiles(previous=>previous.filter(f=>f.id!==id));setResults([]);setOpen({});changed();
  if(authenticated&&currentSnapshot.current&&!currentSnapshot.current.startsWith('run_'))void deleteServerExports();

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

 async function sample() {await newJob();extract(sampleJob);setYears('1');setDegree('Diploma');setCriteria(['Manual Testing','Automation Testing','SQL','Communication'].map((name,i)=>({id:`sample-${i}`,text:name,category:'skill',importance:'required',source_quote:name,source_line:1,operator:'all',conditions:[name]})));setApiNote('Sample criteria are provided for demonstration. Review or re-extract before evaluation.');setFiles(samplePeople.map(([name,email,text])=>({id:crypto.randomUUID(),name:`${name.replaceAll(' ','_')}.txt`,person:name,email,text:`${name}\n${email}\n${text}`})));setResults([]);setError('');}

 async function screen() {

  if(uploading){setError('Wait for parsing to finish.');return;}

  if(!reviewed){setError('Review the job requirements and confirm them before matching.');return;}

  if(!files.length){setError('Add at least one resume to match.');return;}

  setError('');setBusy(true);const version=revision.current;

  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),165000);

  try {

   let activeJob=savedJobId;
   if(activeJob) activeJob=await saveWorkspace();
   if(version!==revision.current)return;
   const data=await matchShortlist({requirements:requirements(),reviewed:true,synthetic_data_confirmed:syntheticConfirmed,candidates:candidateInputs(),...(activeJob?{job_id:activeJob}:{})},controller.signal);
   if(version!==revision.current){if(!data.snapshot_id.startsWith('run_'))await deleteShortlist(data.snapshot_id).catch(()=>{});setError('Inputs changed while matching. Review requirements and match again.');return;}
   const previous=currentSnapshot.current;setSnapshot(data.snapshot_id);currentSnapshot.current=data.snapshot_id;
   if(previous&&previous!==data.snapshot_id&&!previous.startsWith('run_'))void deleteShortlist(previous).catch(()=>setDeletionNote('Previous export snapshot will expire automatically.'));
   showResults(data,files);
   if(activeJob){const runs=await listRuns(activeJob);if(version===revision.current)setHistory(runs.runs);await refreshJobs();}


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
 if(!authenticated)return <Auth onAuthenticated={acceptSession} checking={authChecking}/>;
 return <main className="mx-auto w-full max-w-[1080px]">

  <div className="intro flex items-center justify-between gap-3"><span className="flex items-center gap-2"><span className="brandmark">s</span><b>shortlist<span className="font-normal"> studio</span></b></span><span className="demo-label">PRIVATE · EVIDENCE MATCHING</span><button className="text-link" disabled={libraryBusy||busy||uploading} onClick={logout}>Sign out</button></div>

  <details className="library-panel">
   <summary>Saved jobs & demo settings</summary>
   <h2>Saved jobs & screening history</h2>
   <p>Save a job to retain its requirements, parsed CV text and future screenings until you delete them. Original PDF/DOCX files are not stored. Sign-out and Clear all only clear the current workspace.</p>
   <div className="library-actions"><label htmlFor="job-title">Job title <input id="job-title" maxLength={160} value={jobTitle} disabled={libraryBusy||busy||uploading} onChange={e=>{setJobTitle(e.target.value);changed();}} placeholder="e.g. QA Engineer"/></label>
   <button className="outline" disabled={libraryBusy||busy||uploading||!jobTitle.trim()} onClick={saveCurrent}>{savedJobId?'Update saved job & CVs':'Save job & CVs'}</button>
   <button className="outline" disabled={libraryBusy||busy||uploading} onClick={newJob}>New job</button>
   <button className="text-link" disabled={libraryBusy||busy||uploading} onClick={refreshJobs}>Refresh saved jobs</button></div>
   {aiConfigured===false&&<p className="error" role="status">AI is not configured. Set up the backend AI provider, then retry. Keyword scores are not substituted.</p>}
   <p className="helper">Gemini demo: JD and CV text are sent to Google for AI processing. Use fake/sample data only; free-tier content may be used for product improvement.</p>
   <label><input type="checkbox" checked={syntheticConfirmed} onChange={e=>setSyntheticConfirmed(e.target.checked)}/> I confirm the job description and every CV used for AI processing are fake/sample data.</label>
   {libraryNote&&<p role="status">{libraryNote}</p>}
   <div className="library-list">{savedJobs.length?savedJobs.map(item=><div className="library-row" key={item.id}><span><b>{item.title}</b> · {item.run_count} screenings</span><button className="outline" disabled={libraryBusy||busy||uploading} onClick={()=>openSavedJob(item.id)}>Open job</button><details><summary>Delete job</summary><p>Delete this job, its saved CV text and every screening? This cannot be undone.</p><button className="outline" disabled={libraryBusy||busy||uploading} onClick={()=>deleteSavedJob(item.id)}>Delete job and all history</button></details></div>):<p>No saved jobs yet.</p>}</div>
   {savedJobId&&<div><h3>Screening history</h3>{history.length?history.map(run=><div className="library-row" key={run.id}><span>{new Date(run.created*1000).toLocaleString()}</span><button className="outline" disabled={libraryBusy||busy||uploading} onClick={()=>openScreening(run.id)}>Open screening</button><details><summary>Delete screening</summary><button className="outline" disabled={libraryBusy||busy||uploading} onClick={()=>deleteScreening(run.id)}>Permanently delete screening</button></details></div>):<p>No screenings saved yet. Match resumes for this saved job to create one.</p>}</div>}
  </details>
  {error&&<p className="error" role="alert">{error}</p>}

  <fieldset disabled={libraryBusy}><section className="screener"><header className="flex items-center justify-between gap-3"><h1>Resume screener</h1><span className="remaining">{10-files.length} of 10 resume slots available</span></header>

   <div className="grid md:grid-cols-[1.05fr_1fr]">

    <section className="column job-column"><h2><span className="step">Step 1</span> Paste the job description</h2>

     <textarea aria-label="Job description" className="job-text" placeholder={'Paste your job description here…\n\nInclude the skills, experience and qualifications you’re looking for.'} value={job} onChange={e=>extract(e.target.value)}/>

     <div className="flex flex-wrap gap-2 mt-3"><button className="outline" disabled={extracting||job.trim().length<20} onClick={extractRequirements}>{extracting?'Extracting…':'Extract requirements'}</button><span className="text-xs">Re-extraction replaces the requirements below.</span></div>

     {apiNote&&<p className="helper" role="status">{apiNote}</p>}

     <div className="quick-criteria">
      <p className="helper">Review the requirements found in your job description. Tap a chip to mark it as required. ★ Required · other chips are preferred or need review.</p>
      <div className="skills flex flex-wrap gap-2">{criteria.length?criteria.map(c=><span className="skill-control" key={c.id}><button type="button" title={c.text} aria-pressed={c.importance==='required'} className={'chip '+(c.importance==='required'?'must':'')} onClick={()=>{setCriteria(criteria.map(x=>x.id===c.id?{...x,importance:x.importance==='required'?'preferred':'required'}:x));changed();}}>{c.importance==='required'?'★ ':''}{c.text}{c.importance==='review'?' · Review':''}</button><button type="button" className="remove-skill" aria-label={`Remove requirement ${c.text}`} onClick={()=>{setCriteria(criteria.filter(x=>x.id!==c.id));changed();}}>×</button></span>):<span className="empty-skills">Extract the job description to see its requirements here.</span>}</div>
      <form className="flex gap-2" onSubmit={addSkill}><input aria-label="Add requirement" className="min-w-0 flex-1" placeholder="Add a skill, e.g. Kubernetes" maxLength={60} value={newSkill} onChange={e=>setNewSkill(e.target.value)}/><button className="outline" type="submit" disabled={!newSkill.trim()||criteria.length>=100}>Add</button></form>
     </div>
     <p className="helper">Extract requirements from the job description, then review the criteria below before AI scoring.</p>

     {criteria.length>0&&<details className="extracted-criteria"><summary>Edit requirement details · {criteria.length}</summary><p className="helper">Required qualifications, preferred criteria and duties are preserved below. Edit labels/text or remove irrelevant clauses. Every required/preferred criterion below is part of AI evaluation. Required weight: 3; preferred: 1; needs-review/duty: 0. Skill chips and minimum-degree/year fields are legacy controls; AI scoring uses these structured criteria.</p>{criteria.map((c,index)=><section className="source-criterion" key={c.id}><div className="flex items-center justify-between gap-2"><select aria-label={`Category for criterion ${index+1}`} value={c.category} onChange={e=>{setCriteria(criteria.map(x=>x.id===c.id?{...x,category:e.target.value}:x));changed();}}>{['skill','education','experience','certification','language','responsibility','other'].map(v=><option key={v} value={v}>{v}</option>)}</select><select aria-label={`Priority for criterion ${index+1}`} value={c.importance} onChange={e=>{setCriteria(criteria.map(x=>x.id===c.id?{...x,importance:e.target.value}:x));changed();}}><option value="required">Required</option><option value="preferred">Preferred / added advantage</option><option value="review">Needs review / duty</option></select><button className="text-link" aria-label={`Remove criterion ${index+1}`} onClick={()=>{setCriteria(criteria.filter(x=>x.id!==c.id));changed();}}>Remove</button></div><textarea aria-label={`Requirement clause ${index+1}`} maxLength={1000} value={c.text} onChange={e=>{setCriteria(criteria.map(x=>x.id===c.id?{...x,text:e.target.value,conditions:[]}:x));changed();}}/>{(c.conditions||[]).length>1&&<div><label>Condition logic <select aria-label={`Logic for criterion ${index+1}`} value={c.operator||'all'} onChange={e=>{setCriteria(criteria.map(x=>x.id===c.id?{...x,operator:e.target.value}:x));changed();}}><option value="all">All conditions (AND)</option><option value="any">Any condition (OR)</option></select></label>{c.conditions.map((condition,i)=><textarea key={i} aria-label={`Criterion ${index+1} condition ${i+1}`} value={condition} maxLength={500} onChange={e=>{setCriteria(criteria.map(x=>x.id===c.id?{...x,conditions:x.conditions.map((v,j)=>j===i?e.target.value:v)}:x));changed();}}/>)}</div>}<small>Job description line {c.source_line}</small><details><summary>Original source</summary><blockquote>{c.source_quote}</blockquote></details></section>)}</details>}

     <label className="review-confirm"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/> I reviewed these requirements and confirmed they describe job qualifications, without protected or personal attributes.</label>

    </section>

    <section className="column"><h2><span className="step">Step 2</span> Add up to 10 resumes</h2>

     <div className={'dropzone '+(drag?'dragging':'')} onDragOver={e=>{e.preventDefault();setDrag(true);}} onDragLeave={()=>setDrag(false)} onDrop={e=>{e.preventDefault();setDrag(false);addFiles(e.dataTransfer.files);}}><UploadCloud size={28} strokeWidth={1.4}/><h3>Drop resumes here</h3><p>PDF, DOCX or TXT, up to 5 MB each.</p><button className="outline bg-white" disabled={uploading} onClick={()=>input.current.click()}>{uploading?'Parsing…':'Choose files'}</button><input ref={input} type="file" accept=".pdf,.docx,.txt" multiple hidden onChange={e=>addFiles(e.target.files)}/></div>

     <button className="text-link paste-link" onClick={()=>setPaste(!paste)} aria-expanded={paste}>Or paste resume text</button>

     {paste&&<div className="paste-box"><label htmlFor="resume">Resume text</label><textarea id="resume" value={resumeText} onChange={e=>setResumeText(e.target.value)} placeholder="Paste a candidate’s resume, including name, skills and experience…"/><div className="flex justify-end gap-2"><button className="outline" onClick={()=>setPaste(false)}>Cancel</button><button className="small-primary" onClick={addPaste} disabled={uploading||!resumeText.trim()}>Add resume</button></div></div>}

     <p className="helper">Original files are not stored. Save job & CVs retains parsed text on the server until job deletion. Removing CVs or Clear all clears this workspace; update the saved job to change its CV list. Historical screenings retain their own CV text until you delete them. Gemini AI processing sends text to Google; use fake/sample data only.</p>

     {files.length>0&&<button className="text-link" onClick={clearResumes}>Clear all resumes</button>}
     <p className="helper">Temporary export retention: {Math.round(retention/60)} minutes. Downloads are separate copies on your device.</p><button className="text-link" onClick={deleteServerExports}>Delete temporary exports</button>{deletionNote&&<p role="status" className="helper">{deletionNote}</p>}

     <ul className="file-list">{files.map(f=><li key={f.id}><FileText size={16}/><div className="min-w-0 flex-1 break-words"><span>{f.name}</span><small role="status">{f.status==='parsing'?'Parsing locally…':f.parseError||((f.status==='needs_text')?'No readable text — paste text instead.':`${f.text.length.toLocaleString()} characters available`)}</small>{f.warnings?.map((warning,i)=><small key={i}>{warning}</small>)}{f.text&&<details><summary>Review parsed text</summary><pre className="parsed-preview">{f.text}</pre></details>}</div><button className="remove" aria-label={`Remove ${f.name}`} onClick={()=>removeResume(f.id)}>{f.status==='parsing'?'Cancel':'Remove'}</button></li>)}</ul>

     {!files.length&&<p className="upload-hint">Start with your own resumes or explore the sample below.</p>}

    </section>

   </div>

   <div className="action-bar"><div><div className="flex flex-wrap items-center gap-x-4 gap-y-3"><button className="primary" onClick={screen} disabled={busy||uploading||libraryBusy}>{busy?'Matching…':`${results.length?'Re-match':'Match'} ${files.length||''} resume${files.length===1?'':'s'}`}</button><button className="text-link" disabled={uploading} onClick={sample}>Try a sample job and 5 resumes</button></div><p className="action-note">{results.length?'Review requirements again after changing inputs.':'Evidence matching supports your review; it does not decide who to hire.'}</p></div><p className="privacy"><ShieldCheck size={18}/><span><b>Authenticated parsing and matching.</b><br/>Saved jobs retain CV text and screening history until deletion. Unsaved matches use temporary export snapshots.</span></p></div>

   {error&&<p className="error" role="alert">{error}</p>}

   <section className="shortlist"><div className="results-header"><div className="flex flex-wrap items-center justify-between gap-4"><h2>Ranked shortlist</h2><div className="filters flex flex-wrap items-center gap-3"><label className="flex items-center gap-2"><input type="checkbox" checked={blind} onChange={e=>setBlind(e.target.checked)}/>Blind mode</label><label>Show <select aria-label="Candidate status filter" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All candidates</option><option value="requirements_review">Qualification review</option><option value="must_have_review">Must-have review</option><option value="unscored">Unscored</option><option value="pending">Pending human review</option><option value="shortlisted">Human shortlisted</option></select></label><button className="outline flex items-center gap-2" onClick={csv} disabled={!results.length||dirty||!snapshot||reviewSaving||exporting}><Download size={14}/>{exporting?'Downloading…':'Download CSV'}</button></div></div><div className="counts flex flex-wrap gap-2"><span className="chip">{results.length} assessed</span>{['requirements_review','must_have_review','unscored'].map(group=><span className="chip" key={group}>{results.filter(r=>r.group===group).length} {groupLabel(group)}</span>)}</div>{dirty&&results.length>0&&<p className="stale" role="status">Inputs changed. These results use the previous requirements; review and re-match before using them.</p>}</div>

    {!results.length?<div className="empty-results"><span className="empty-icon"><FileText size={25}/></span><h3>Review evidence before deciding</h3><p>Add resumes, review the requirements, then match to see supporting text and uncertainty.</p></div>:<><details className="scoring-note"><summary>How to read these results</summary><p>{matchNotice} Protected and personal attributes are excluded. CV claims and employment durations require verification; this is decision support. Blind mode only hides row labels; source text can contain identifying information.</p></details>{results.filter(r=>shown(r,filter)).map(r=><article className="candidate" key={r.id}><button className="candidate-summary" aria-expanded={!!open[r.id]} onClick={()=>setOpen({...open,[r.id]:!open[r.id]})}><span className="rank">#{r.rank}</span><span className="ring" style={{'--score':`${r.score??0}%`}}><b>{r.score??'—'}</b></span><span className="candidate-name"><strong>{blind?`Candidate ${String(r.index+1).padStart(2,'0')}`:r.person}</strong><small>Evidence coverage{r.score_provisional?' · Provisional':''} · {r.review_status.replaceAll('_',' ')}</small></span><span className={'status '+(r.group==='must_have_review'?'partial':r.unparsed?'low':'good')}>{groupLabel(r.group)}</span><ChevronDown size={18} className={open[r.id]?'rotate-180':''}/></button>{open[r.id]&&<div className="details"><ScoreDetails result={r} blind={blind}/>
      {r.versions&&<details><summary>Model & scoring versions</summary><pre className="parsed-preview">{JSON.stringify(r.versions,null,2)}</pre></details>}

      {!r.criterion_decisions&&<div><h4>Legacy skill evidence</h4>{r.skills.length?r.skills.map(c=><section className="criterion" key={c.name}><b>{c.name}{c.must?' ★':''} · {c.status.replaceAll('_',' ')}</b><p>{c.reason}</p>{c.similarity!=null&&<p>Semantic similarity: {c.similarity.toFixed(3)} · human verification required</p>}<Evidence items={c.evidence} sourceName={blind?'Resume source':r.name}/></section>):<p>No skill requirements.</p>}</div>}

      {!r.criterion_decisions&&(r.additional_criteria||[]).length>0&&<div><h4>Additional requirements · human review</h4><p>These source requirements are retained for verification and are not included in the numeric score.</p>{r.additional_criteria.map(c=><section className="criterion" key={c.id}><b>{c.importance} · {c.category}</b><p>{c.text}</p><small>From job description line {c.source_line}. Verify against the candidate's CV and supporting documents.</small></section>)}</div>}

      {!r.criterion_decisions&&['experience','education'].map(key=><section className="criterion" key={key}><h4>{key==='experience'?'Experience':'Education'} · {r[key].status.replaceAll('_',' ')}</h4><p>{r[key].reason}</p><Evidence items={r[key].evidence} sourceName={blind?'Resume source':r.name}/></section>)}

      {r.warnings.map((warning,i)=><p className="stale" key={i}>{warning}</p>)}

      {r.text&&<details><summary>View source text with line references</summary><div className="parsed-preview">{r.text.split(/\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/).map((line,i)=><div key={i}><span className="source-line">{i+1}</span>{line||' '}</div>)}</div></details>}

      <label className="human-review">Human review <select aria-label={`Human review for candidate ${r.index+1}`} value={r.review_status} disabled={dirty||reviewSaving||!snapshot} onChange={e=>humanReview(r.id,e.target.value)}><option value="pending">Pending review</option><option value="reviewed">Reviewed — undecided</option><option value="shortlisted">Shortlist after human review</option><option value="not_progressing">Do not progress — human decision</option></select></label><p className="text-xs">Review evidence and missing information with the candidate before deciding. Your choice is saved with this screening. Saved job history remains until deletion; temporary screenings expire. Reviews do not alter scores or ranking.</p>

     </div>}</article>)}{!results.some(r=>shown(r,filter))&&<p className="p-8 text-center">No candidates in this category.</p>}</>}

   </section>

  </section></fieldset><footer className="page-footer">Built for a more thoughtful shortlist. <span>Original interface · Step 4 private export</span></footer>

 </main>;

}

createRoot(document.getElementById('root')).render(<App/>);



