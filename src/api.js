const configured = import.meta.env.VITE_API_BASE_URL || '';
const base = (configured || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? 'http://127.0.0.1:8000' : window.location.origin)).replace(/\/$/, '');
let accessToken = '';
function safeEndpoint() {
  const url = new URL(base, window.location.href);
  const local = ['127.0.0.1','localhost','[::1]'].includes(url.hostname);
  if (url.username || url.password || url.search || url.hash || (url.protocol !== 'https:' && !(local && url.protocol === 'http:'))) throw new Error('Use HTTPS or a local API address.');
  if (!local && url.origin !== window.location.origin) throw new Error('Candidate data requires the same secure site. Cross-site processing is not enabled.');
}
export function clearAccessToken() { accessToken = ''; }
async function call(path, options={}) {
  safeEndpoint();
  if (!accessToken) throw new Error('Sign in with your access token first.');
  const controller=new AbortController(),forward=()=>controller.abort();
  if(options.signal?.aborted)controller.abort();else options.signal?.addEventListener('abort',forward,{once:true});
  const timer=setTimeout(()=>controller.abort(),30000);
  let response;
  try{response=await fetch(`${base}${path}`, {...options,signal:controller.signal,headers:{...options.headers,Authorization:`Bearer ${accessToken}`},cache:'no-store',credentials:'omit',redirect:'error'});}
  finally{clearTimeout(timer);options.signal?.removeEventListener('abort',forward);}
  if (!response.ok) {
    if (response.status === 401) throw new Error('Access token is invalid or revoked. Sign in again.');
    if (response.status === 404) {
      if(path==='/api/jobs')throw new Error('Saved jobs API is unavailable. Restart the backend to load the latest project code, then retry.');
      throw new Error('Record not found, deleted or expired. Refresh saved jobs or match again.');
    }
    if (response.status === 409) throw new Error('Saved storage limit reached. Delete an old job or screening and retry.');
    if (response.status === 429) throw new Error('Request limit reached. Wait one minute and retry.');
    if (response.status === 413) throw new Error('Request exceeds the permitted size.');
    if (response.status === 422) throw new Error('Check job requirements, resume inputs and review confirmation.');
    throw new Error(`Request failed (${response.status}). Retry or check the local API.`);
  }
  return response;
}
export async function signIn(token) {
  accessToken = token.trim();
  try { return await (await call('/api/session')).json(); }
  catch(e) {accessToken='';throw e;}
}
export async function request(path, body, signal) {
  return (await call(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal})).json();
}
export async function parseResume(file,signal) {
  return (await call('/api/resumes/parse',{method:'POST',headers:{'Content-Type':file.type||'application/octet-stream','X-Filename':encodeURIComponent(file.name)},body:file,signal})).json();
}
export function matchShortlist(body,signal) {return request('/api/shortlist/match',body,signal);}
export async function listJobs(){return (await call('/api/jobs')).json();}
export async function getJob(id){return (await call(`/api/jobs/${encodeURIComponent(id)}`)).json();}
export async function persistJob(id,body){return (await call(id?`/api/jobs/${encodeURIComponent(id)}`:'/api/jobs',{
  method:id?'PATCH':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();}
export async function removeJob(id){return call(`/api/jobs/${encodeURIComponent(id)}`,{method:'DELETE'});}
export async function listRuns(id){return (await call(`/api/jobs/${encodeURIComponent(id)}/runs`)).json();}
export async function getRun(id){return (await call(`/api/screenings/${encodeURIComponent(id)}`)).json();}
export async function removeRun(id){return call(`/api/screenings/${encodeURIComponent(id)}`,{method:'DELETE'});}
export async function saveReview(snapshot,candidate,status) {
  return (await call(`/api/shortlists/${encodeURIComponent(snapshot)}/reviews`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidate_id:candidate,status})})).json();
}
export async function deleteShortlist(snapshot) {
  return call(`/api/shortlists/${encodeURIComponent(snapshot)}`,{method:'DELETE'});
}
export async function deleteAllShortlists() {return (await call('/api/shortlists',{method:'DELETE'})).json();}
export async function downloadCsv(snapshot,blind) {
  const response=await call(`/api/shortlists/${encodeURIComponent(snapshot)}/export?blind=${blind?'true':'false'}`);
  const blob=await response.blob();
  const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='shortlist.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
