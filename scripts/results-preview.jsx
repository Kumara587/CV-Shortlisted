// Development-only visual fixture. No applicant data or API requests.
import React from 'react';
import {createRoot} from 'react-dom/client';
import '../src/styles.css';
import ScoreDetails from '../src/ScoreDetails';
const source={source_id:'fictional',line_start:7,line_end:7,quote:'Coordinated interviews, onboarding and employee records using HRIS.'};
const condition=(text,status,explanation,evidence=[])=>({text,status,explanation,evidence});
const result={name:'Fictional sample resume.pdf',score:75,method:'llm_evidence_v1',score_provisional:false,
 components:{required:{points:60,weight:80},preferred:{points:15,weight:20}},
 criterion_decisions:[
  {id:'c1',text:'Experience coordinating recruitment and onboarding',importance:'required',status:'meets',operator:'all',weight:40,points:40,evidence:[source,source],conditions_evaluated:[condition('Recruitment coordination','meets','The resume describes coordinating interviews and onboarding.',[source])]},
  {id:'c2',text:'Maintain accurate HRIS and employee records',importance:'required',status:'partially_meets',operator:'all',weight:40,points:20,evidence:[source],conditions_evaluated:[condition('Maintain HRIS records','meets','HRIS and employee record handling are explicitly described.',[source]),condition('Demonstrate accuracy of records','not_evidenced','Accuracy measures or examples are not included. Ask for clarification.')]},
  {id:'c3',text:'A relevant professional qualification',importance:'preferred',status:'needs_review',operator:'any',weight:20,points:0,evidence:[],conditions_evaluated:[condition('Relevant qualification','needs_review','The qualification title is ambiguous and needs human review.')]}
 ]};
// Points in fixture are computed to match criterion contributions.
result.score=60;result.components.preferred.points=0;
createRoot(document.getElementById('preview')).render(<main style={{maxWidth:920,margin:'20px auto'}}><div className="intro"><b>shortlist studio</b> · Fictional UI preview</div><article className="candidate"><div className="details"><ScoreDetails result={result} blind={false}/><label className="human-review">Human review <select defaultValue="pending"><option value="pending">Pending review</option></select></label><p>Review the evidence before deciding. Your choice is saved with this screening.</p></div></article></main>);
