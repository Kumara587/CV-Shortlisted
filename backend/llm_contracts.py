"""Provider-independent schemas: models supply decisions, never scores."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated

Short = Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=1000)]
Status = Literal['meets','partially_meets','not_evidenced','contradicted','needs_review']


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')


class Criterion(Strict):
    id: Annotated[str,StringConstraints(min_length=1,max_length=64)]
    text: Short
    category: Literal['skill','education','experience','certification','responsibility','language','other']='other'
    importance: Literal['required','preferred','review']='review'
    source_quote: str=Field(default='',max_length=1000)
    source_line: int=Field(default=1,ge=1,le=20000)
    operator: Literal['all','any']='all'
    conditions: list[Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=500)]]=Field(default_factory=list,max_length=12)


class Extracted(Strict):
    text: Short
    category: Literal['skill','education','experience','certification','responsibility','language','other']
    importance: Literal['required','preferred','review']
    source_quote: Short
    operator: Literal['all','any']
    conditions: list[Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=500)]]=Field(min_length=1,max_length=12)


class Extraction(Strict):
    criteria: list[Extracted]=Field(min_length=1,max_length=100)


class Quote(Strict):
    quote: Short
    line_start: int=Field(ge=1,le=200000)
    line_end: int=Field(ge=1,le=200000)


class ConditionDecision(Strict):
    condition_index: int=Field(ge=0,le=11)
    status: Status
    explanation: Short
    evidence: list[Quote]=Field(max_length=3)


class Decision(Strict):
    criterion_id: Annotated[str,StringConstraints(min_length=1,max_length=64)]
    conditions: list[ConditionDecision]=Field(min_length=1,max_length=12)


class Evaluation(Strict):
    decisions: list[Decision]=Field(min_length=1,max_length=100)


class SourceLines(Strict):
    line_start: int=Field(ge=1,le=200000)
    line_end: int=Field(ge=1,le=200000)


class ReferencedCondition(Strict):
    condition_index: int=Field(ge=0,le=11)
    status: Status
    explanation: Short
    evidence: list[SourceLines]=Field(max_length=3)


class ReferencedDecision(Strict):
    criterion_id: Annotated[str,StringConstraints(min_length=1,max_length=64)]
    conditions: list[ReferencedCondition]=Field(min_length=1,max_length=12)


class ReferencedEvaluation(Strict):
    decisions: list[ReferencedDecision]=Field(min_length=1,max_length=100)


def prohibited_criterion(criterion):
    from matching import prohibited_requirement
    for text in [criterion.text,*criterion.conditions]:
        if criterion.category in {'language','education'} and text.casefold() in {'sinhala','tamil'}:
            continue  # language proficiency / examination subjects, not ethnicity
        if prohibited_requirement(text): return True
    return False
