import React,{useEffect,useRef,useState} from 'react';
import {ArrowRight,ArrowLeft,Check,ShieldCheck,Eye,EyeOff,LoaderCircle,FileCheck2,Sparkles} from 'lucide-react';
import {authAction,authConfig,currentSession} from './api';
import './auth.css';

function readLink(){
 const hash=new URLSearchParams(window.location.hash.slice(1));
 return {reset:hash.get('reset')||'',verify:hash.get('verify')||''};
}

export default function Auth({onAuthenticated,checking=false}){
 const [link]=useState(readLink),[mode,setMode]=useState(()=>readLink().reset?'reset':'login');
 const [email,setEmail]=useState(''),[firstName,setFirstName]=useState(''),[lastName,setLastName]=useState(''),[dob,setDob]=useState(''),[password,setPassword]=useState(''),[confirm,setConfirm]=useState('');
 const passwordRules=[['8+ characters',password.length>=8],['Uppercase (A–Z)',/[A-Z]/.test(password)],['Lowercase (a–z)',/[a-z]/.test(password)],['Number (0–9)',/[0-9]/.test(password)],['Special character (!@#$…)',/[!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/.test(password)]];
 const passwordValid=passwordRules.every(([,passed])=>passed);
 const today=new Date();const maxDob=`${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
 const [visible,setVisible]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [config,setConfig]=useState(null),[googleReady,setGoogleReady]=useState(false);
 const googleButton=useRef(null),onSuccess=useRef(onAuthenticated);
 onSuccess.current=onAuthenticated;
 useEffect(()=>{
  if(link.reset||link.verify)window.history.replaceState(null,'',window.location.pathname+window.location.search);
  authConfig().then(setConfig).catch(()=>setError('Unable to connect. Check that the API is running.'));
  if(link.verify)authAction('verify-email',{token:link.verify}).then(r=>setNotice(r.message)).catch(e=>setError(e.message));
 },[]);
 useEffect(()=>{
  if(!config?.google_client_id||!['login','signup'].includes(mode))return;
  let cancelled=false;
  async function render(){
   try{
    const {nonce}=await authAction('google/nonce');
    if(cancelled||!googleButton.current)return;
    window.google.accounts.id.initialize({client_id:config.google_client_id,nonce,auto_select:false,
     callback:async ({credential})=>{
      setBusy(true);setError('');
      try{const r=await authAction('google',{credential});if(r.verification_required){setNotice(r.message);return;}onSuccess.current(await currentSession());}
      catch(e){setError(e.message);setGoogleReady(false);}
      finally{setBusy(false);}
     }});
    googleButton.current.replaceChildren();
    window.google.accounts.id.renderButton(googleButton.current,{theme:'outline',size:'large',shape:'pill',width:340,text:'continue_with'});
    setGoogleReady(true);
   }catch{if(!cancelled)setError('Google sign-in could not start. Try email sign-in or refresh.');}
  }
  if(window.google?.accounts)render();
  else{
   let script=document.getElementById('google-identity');
   if(!script){script=document.createElement('script');script.id='google-identity';script.src='https://accounts.google.com/gsi/client';script.async=true;document.head.appendChild(script);}
   script.addEventListener('load',render,{once:true});
   script.addEventListener('error',()=>{if(!cancelled)setError('Google sign-in could not load. Use email sign-in.');},{once:true});
  }
  return()=>{cancelled=true;};
 },[config,mode]);
 function switchMode(next){setMode(next);setError('');setNotice('');setPassword('');setConfirm('');setVisible(false);setGoogleReady(false);}
 async function submit(e){
  e.preventDefault();setError('');setNotice('');
  if(['signup','reset'].includes(mode)&&password!==confirm){setError('Your passwords do not match.');return;}
  if(['signup','reset'].includes(mode)&&!passwordValid){setError('Your password must meet all five requirements below.');return;}
  setBusy(true);
  try{
   if(mode==='forgot'){const r=await authAction('forgot-password',{email});setNotice(r.message);return;}
   if(mode==='reset'){const r=await authAction('reset-password',{token:link.reset,password});switchMode('login');setNotice(r.message);return;}
   const r=await authAction(mode==='signup'?'signup':'login',mode==='signup'?{email,first_name:firstName,last_name:lastName,dob,password,confirm_password:confirm}:{email,password});
   if(r.verification_required){setNotice(r.message);setPassword('');setConfirm('');return;}
   onAuthenticated(await currentSession());
  }catch(e){setError(e.message);}
  finally{setBusy(false);}
 }
 async function resend(){setBusy(true);setError('');try{setNotice((await authAction('resend-verification',{email})).message);}catch(e){setError(e.message);}finally{setBusy(false);}}
 const signup=mode==='signup',forgot=mode==='forgot',reset=mode==='reset';
 return <main className="auth-page">
  <aside className="auth-story">
   <a href="/" className="auth-brand"><span className="auth-logo">s</span><span>shortlist<span className="auth-brand-light"> studio</span></span></a>
   <div className="auth-story-main"><span className="auth-eyebrow"><Sparkles size={14}/> A clearer way to shortlist</span><h1>Great people.<br/>Clearer <em>decisions.</em></h1><p>Bring your job requirements and resumes together. Find the evidence that helps you make your next hire.</p>
    <div className="auth-preview" aria-hidden="true"><div className="auth-preview-top"><span className="auth-file-icon"><FileCheck2 size={22}/></span><div><strong>Your next shortlist</strong><small>Evidence behind every match</small></div><span className="auth-live-dot"/></div><div className="auth-preview-line"><span>Job requirements</span><span>Reviewed <Check size={13}/></span></div><div className="auth-preview-bars"><i/><i/><i/></div><div className="auth-preview-bottom"><ShieldCheck size={16}/> Your workspace, kept private</div></div>
   </div><p className="auth-story-footer">Built for thoughtful recruiting. Designed for human decisions.</p>
  </aside>
  <section className="auth-form-side"><div className="auth-mobile-brand"><span className="auth-logo">s</span> shortlist studio</div><div className="auth-form-wrap">
   {(forgot||reset)&&<button className="auth-back" onClick={()=>switchMode('login')}><ArrowLeft size={15}/> Back to sign in</button>}
   <span className="auth-kicker">YOUR RECRUITING WORKSPACE</span>
   <h2>{signup?'Start your next chapter.':forgot?'Forgot your password?':reset?'Choose a new password.':'Welcome back.'}</h2>
   <p className="auth-subtitle">{signup?'Create an account and bring your shortlist into focus.':forgot?'Enter your email and we’ll send you a secure reset link.':reset?'Choose a unique password that meets the requirements below.':'Sign in to pick up where you left off.'}</p>
   {checking?<p className="auth-checking"><LoaderCircle size={18} className="auth-spin"/> Checking your session…</p>:<>
   {['login','signup'].includes(mode)&&<><div className="auth-google" ref={googleButton}/>{!googleReady&&<button type="button" className="auth-google-placeholder" disabled><svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path fill="#4285F4" d="M21.6 12.2c0-.7-.1-1.4-.2-2.1H12v4h5.4a4.6 4.6 0 0 1-2 3v2.5h3.2c1.9-1.8 3-4.3 3-7.4z"/><path fill="#34A853" d="M12 22c2.7 0 5-.9 6.6-2.4l-3.2-2.5c-.9.6-2 1-3.4 1-2.6 0-4.8-1.8-5.6-4.2H3.1v2.6A10 10 0 0 0 12 22z"/><path fill="#FBBC05" d="M6.4 13.9a6 6 0 0 1 0-3.8V7.5H3.1a10 10 0 0 0 0 9l3.3-2.6z"/><path fill="#EA4335" d="M12 5.9c1.5 0 2.8.5 3.8 1.5l2.9-2.8A9.6 9.6 0 0 0 12 2a10 10 0 0 0-8.9 5.5l3.3 2.6A5.9 5.9 0 0 1 12 5.9z"/></svg> Continue with Google</button>}{!config?.google_client_id&&<p className="auth-setup-note">Google sign-in will be available after setup.</p>}<div className="auth-divider"><span>or continue with email</span></div></>}
   <form onSubmit={submit} className="auth-form">
    {signup&&<><div className="auth-name-row"><label>First name<input autoComplete="given-name" value={firstName} maxLength={50} required onChange={e=>setFirstName(e.target.value)} placeholder="First name"/></label><label>Last name<input autoComplete="family-name" value={lastName} maxLength={50} required onChange={e=>setLastName(e.target.value)} placeholder="Last name"/></label></div><label>Date of birth<input type="date" autoComplete="bday" value={dob} max={maxDob} required onChange={e=>setDob(e.target.value)}/></label></>}
    {!reset&&<label>Email address<input type="email" autoComplete="email" value={email} maxLength={254} required onChange={e=>setEmail(e.target.value)} placeholder="you@company.com"/></label>}
    {!forgot&&<label><span className="auth-label-row">Password{!signup&&!reset&&<button type="button" onClick={()=>switchMode('forgot')}>Forgot password?</button>}</span><span className="auth-password"><input type={visible?'text':'password'} autoComplete={signup||reset?'new-password':'current-password'} value={password} required minLength={signup||reset?8:1} maxLength={128} onChange={e=>setPassword(e.target.value)} placeholder={signup||reset?'Create a strong password':'Enter your password'}/><button type="button" aria-label={visible?'Hide password':'Show password'} onClick={()=>setVisible(!visible)}>{visible?<EyeOff size={18}/>:<Eye size={18}/>}</button></span></label>}
    {(signup||reset)&&<><ul className="auth-password-rules" aria-label="Password requirements" aria-live="polite">{passwordRules.map(([label,passed])=><li key={label} className={passed?'passed':''}><span aria-hidden="true">{passed?'✓':'○'}</span>{label}</li>)}</ul><label>Confirm password<input type={visible?'text':'password'} autoComplete="new-password" value={confirm} required minLength={8} maxLength={128} aria-invalid={!!confirm&&confirm!==password} onChange={e=>setConfirm(e.target.value)} placeholder="Enter your password again"/></label>{confirm&&confirm!==password&&<p className="auth-password-mismatch" role="status">Passwords do not match.</p>}</>}
    {error&&<p className="auth-error" role="alert">{error}</p>}{notice&&<p className="auth-notice" role="status">{notice}</p>}
    {forgot&&config?.password_reset_available===false&&<p className="auth-setup-note">Email recovery is awaiting email-service setup. Contact your workspace administrator if you need access.</p>}
    <button className="auth-submit" disabled={busy||(forgot&&config?.password_reset_available===false)} type="submit">{busy?<><LoaderCircle size={17} className="auth-spin"/> Please wait…</>:<>{signup?'Create account':forgot?'Send reset link':reset?'Update password':'Sign in'}<ArrowRight size={17}/></>}</button>
   </form>
   {!forgot&&!reset&&<p className="auth-switch">{signup?'Already have an account?':'New to Shortlist Studio?'} <button onClick={()=>switchMode(signup?'login':'signup')}>{signup?'Sign in':'Create an account'}</button></p>}
   {mode==='login'&&<button className="auth-resend" disabled={!email||busy||!config?.password_reset_available} onClick={resend}>Resend verification email</button>}
   </>}
   <p className="auth-footer"><ShieldCheck size={14}/> Secure access. Your recruiting work stays yours.</p>
  </div></section>
 </main>;
}
