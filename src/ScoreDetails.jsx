import React,{useState} from 'react';
import {Check,ChevronDown,FileText,Info,ShieldCheck,AlertCircle,SlidersHorizontal} from 'lucide-react';
import './results.css';

const labels={meets:'Meets requirement',partially_meets:'Partially meets',not_evidenced:'Not evidenced',contradicted:'Conflicting evidence',needs_review:'Needs review'};
const number=value=>Number.isFinite(value)?value:0;
const format=value=>number(value).toFixed(1).replace(/\.0$/,'');

export default function ScoreDetails({result:r,blind}){
 const [filter,setFilter]=useState('all');
 const criteria=r.criterion_decisions||[];
 const supported=criteria.filter(c=>c.status==='meets').length;
 const partial=criteria.filter(c=>c.status==='partially_meets').length;
 const attention=criteria.filter(c=>!['meets','partially_meets'].includes(c.status)).length;
 const filters=[['all','All requirements',criteria.length],['attention','Needs attention',criteria.length-supported],['required','Required',criteria.filter(c=>c.importance==='required').length],['preferred','Preferred',criteria.filter(c=>c.importance==='preferred').length]];
 const visible=criteria.filter(c=>filter==='all'||filter==='attention'&&c.status!=='meets'||c.importance===filter);
 return <div className="result-insights">
  <div className="insight-heading"><div><span className="insight-eyebrow"><ShieldCheck size={13}/> EVIDENCE BREAKDOWN</span><h3>A clearer view of this match</h3><p>See what the resume supports, and what needs a closer look.</p></div><span className={'insight-score '+(r.score_provisional?'is-provisional':'')}><b>{r.score==null?'—':format(r.score)}<small>{r.score==null?'':' / 100'}</small></b><span>{r.score_provisional?'Provisional coverage':'Evidence coverage'}</span></span></div>
  {criteria.length>0&&<div className="insight-stats"><div><span className="stat-icon supported"><Check size={17}/></span><b>{supported}</b><span>Supported</span></div><div><span className="stat-icon partial"><SlidersHorizontal size={16}/></span><b>{partial}</b><span>Partially supported</span></div><div><span className="stat-icon attention"><AlertCircle size={17}/></span><b>{attention}</b><span>Missing or uncertain</span></div></div>}
  <div className="coverage-cards">{Object.entries(r.components||{}).map(([name,c])=><div className={'coverage-card '+name} key={name}><div className="coverage-title"><span>{name==='required'?'Required criteria':name==='preferred'?'Preferred criteria':name}</span><b>{format(c.points)}<small> / {format(c.weight)} pts</small></b></div><div className="coverage-track"><span style={{width:`${Math.max(0,Math.min(100,c.weight?100*c.points/c.weight:0))}%`}}/></div><small>{c.weight?`${format(c.weight)}% of the total score`:'No criteria in this category'}</small></div>)}</div>
  <p className="insight-context"><Info size={14}/><span>Scores show evidence in the resume, not hiring suitability. “Not evidenced” means information is missing, not that the candidate lacks the qualification.</span></p>
  {r.score_provisional&&<p className="insight-alert"><AlertCircle size={16}/><span>Some source references need verification. Treat this score as provisional and review the flagged requirements.</span></p>}
  <details className="score-policy"><summary><Info size={14}/> How is this score calculated?<ChevronDown size={14}/></summary><div><p>{r.method==='llm_evidence_v1'?'Required criteria have weight 3; preferred criteria have weight 1. Meets receives full credit, partially meets half credit, and missing or uncertain evidence receives zero. Review-only criteria do not contribute. The backend combines AND/OR conditions and calculates the score.':'This is a historical keyword/embedding result. It is not an LLM evaluation.'}</p><p>Missing evidence and required gaps need human review. The scoring policy is provisional and has not been calibrated to predict job performance.</p></div></details>
  {criteria.length>0&&<section className="criteria-review"><div className="criteria-heading"><h4>Requirements, at a glance</h4><span>{criteria.length} criteria assessed</span></div><div className="criteria-filters" aria-label="Filter requirements">{filters.map(([value,label,count])=><button type="button" key={value} aria-pressed={filter===value} className={filter===value?'active':''} onClick={()=>setFilter(value)}>{label}<span>{count}</span></button>)}</div>
   <div className="criteria-cards">{visible.map(c=>{
    const evidence=[...new Map((c.evidence||[]).map(e=>[`${e.source_id}:${e.line_start}:${e.line_end}:${e.quote}`,e])).values()];
    return <details className={'requirement-card '+c.status} key={c.id}><summary><span className={'requirement-icon '+c.status}>{c.status==='meets'?<Check size={16}/>:<AlertCircle size={16}/>}</span><span className="requirement-title"><strong>{c.text}</strong><span><em>{c.importance==='required'?'Required':c.importance==='preferred'?'Preferred':'Review only'}</em><span className={'decision-pill '+c.status}>{labels[c.status]||c.status}</span></span></span><span className="requirement-points"><b>+{format(c.points)}</b><small>of {format(c.weight)} pts</small></span><ChevronDown size={16} className="requirement-chevron"/></summary><div className="requirement-body">
     <div className="condition-heading"><span>{(c.conditions_evaluated||[]).length>1?(c.operator==='any'?'Any one condition can meet this requirement':'All conditions must be met'):'Assessment'}</span><span>{format(c.weight)}% score weight</span></div>
     {(c.conditions_evaluated||[]).map((condition,index)=><div className="condition-assessment" key={index}><div>{(c.conditions_evaluated||[]).length>1&&<strong>{condition.text}</strong>}<span className={'decision-pill '+condition.status}>{labels[condition.status]||condition.status}</span></div><p>{condition.explanation}</p></div>)}
     <details className="source-evidence"><summary><FileText size={14}/>{evidence.length?`View resume evidence · ${evidence.length} source${evidence.length===1?'':'s'}`:'No verified source evidence'}<ChevronDown size={14}/></summary><div>{evidence.length?evidence.map((e,index)=><figure key={index}><figcaption><FileText size={12}/>{blind?'Resume source':r.name||'Resume'}<span>Line {e.line_start}{e.line_end!==e.line_start?`–${e.line_end}`:''}</span></figcaption><blockquote>{e.quote}</blockquote></figure>):<p>No verified source text supports this requirement. Ask the candidate for clarification before making a decision.</p>}</div></details>
    </div></details>;
   })}</div>{!visible.length&&<div className="criteria-empty"><Check size={20}/><b>{filter==='attention'?'Nothing flagged for attention':'No criteria in this category'}</b><span>Switch to All requirements to see the full breakdown.</span></div>}
  </section>}
 </div>;
}
