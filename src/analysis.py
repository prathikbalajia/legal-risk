import json, re
from typing import List, Dict, Any
from src.models import RiskCheck

# Severity weights
RISK_WEIGHTS = {'LOW': 0.2, 'MEDIUM': 0.5, 'HIGH': 1.0}

def local_rule_check(clause_name: str, policy_rule: str, relevant_text: str) -> RiskCheck:
    # Basic deterministic checks for demo purposes
    txt = (relevant_text or '').lower()
    clause = clause_name
    is_violation = False
    risk_level = 'LOW'
    reasoning = ''
    citation = 'SECTION (in-file)'

    # Confidentiality rule check
    if 'confidential' in clause.lower() or 'confidenti' in txt:
        # expect at least 3 years
        m = re.search(r'(\b(\d+)\s*years?)', txt)
        if m:
            years = int(m.group(2))
            if years < 3:
                is_violation = True
                risk_level = 'MEDIUM'
                reasoning = f'Found confidentiality duration {years} year(s) but policy requires >= 3 years.'
            else:
                is_violation = False
                risk_level = 'LOW'
                reasoning = f'Confidentiality duration {years} year(s) meets policy.'
        else:
            is_violation = True
            risk_level = 'MEDIUM'
            reasoning = 'No explicit confidentiality duration found.'

    # Liability rule check
    elif 'liability' in clause.lower() or 'liability' in policy_rule.lower():
        if re.search(r'(\b(\d+\.?\d*)\s*(x|times)\b)', txt) or ('1.5' in txt) or ('total fees' in txt):
            m = re.search(r'(\b(\d+\.?\d*)\s*(x|times)\b)', txt)
            if m:
                val = float(m.group(2))
                if val <= 1.5:
                    is_violation = False
                    risk_level = 'LOW'
                    reasoning = f'Liability capped at {val}x which meets policy.'
                else:
                    is_violation = True
                    risk_level = 'HIGH'
                    reasoning = f'Liability capped at {val}x which exceeds policy 1.5x.'
            else:
                if '1.5' in txt:
                    is_violation = False
                    risk_level = 'LOW'
                    reasoning = 'Liability text contains 1.5 token; treated as compliant (heuristic).'
                else:
                    # ambiguous 'total fees paid' -> treat as violation (no multiplier)
                    if 'total fees' in txt:
                        is_violation = True
                        risk_level = 'HIGH'
                        reasoning = 'Liability limited to total fees paid (no multiplier) -> treated as violation per policy.'
                    else:
                        is_violation = True
                        risk_level = 'HIGH'
                        reasoning = 'Liability cap not numeric or absent; treated as violation.'
        else:
            is_violation = True
            risk_level = 'HIGH'
            reasoning = 'No explicit safe liability cap found.'

    # Data sale prohibition
    elif 'data' in clause.lower() or 'sell' in policy_rule.lower() or 'commercialize' in policy_rule.lower():
        if 'sell' in txt or 'commercial' in txt:
            is_violation = True
            risk_level = 'HIGH'
            reasoning = 'Clause allows selling or commercializing client data without consent.'
        else:
            is_violation = False
            risk_level = 'LOW'
            reasoning = 'No data sale detected.'

    # Termination notice
    elif 'terminat' in clause.lower() or 'termination' in policy_rule.lower():
        if '30 days' in txt or '30-day' in txt or 'payment in lieu' in txt:
            is_violation = False
            risk_level = 'LOW'
            reasoning = 'Adequate termination notice found.'
        else:
            is_violation = True
            risk_level = 'MEDIUM'
            reasoning = 'No adequate termination notice found.'

    # Indemnity scope
    elif 'indemn' in clause.lower() or 'indemn' in policy_rule.lower():
        if 'neglig' in txt and ('client' in txt and 'indemn' in txt):
            # if client indemnifies including provider negligence -> violation
            if 'provider' in txt or 'company' in txt:
                is_violation = True
                risk_level = 'HIGH'
                reasoning = 'Client indemnifies provider even for provider negligence -> violation.'
            else:
                is_violation = True
                risk_level = 'MEDIUM'
                reasoning = 'Broad indemnity language present; needs narrowing.'
        else:
            is_violation = False
            risk_level = 'LOW'
            reasoning = 'Indemnity language not overly broad.'

    # Service availability
    elif 'availability' in clause.lower() or 'uptime' in policy_rule.lower() or 'suspend' in txt:
        if '99.5' in txt or 'uptime' in txt or 'guarantee' in txt or 'compens' in txt:
            is_violation = False
            risk_level = 'LOW'
            reasoning = 'Service availability / uptime commitment present.'
        else:
            is_violation = True
            risk_level = 'MEDIUM'
            reasoning = 'No uptime guarantee; provider may suspend arbitrarily.'

    # Security responsibility
    elif 'security' in clause.lower() or 'protect' in policy_rule.lower() or 'security' in txt:
        if 'encryption' in txt or 'access control' in txt or 'safeguard' in txt or 'implement' in txt:
            is_violation = False
            risk_level = 'LOW'
            reasoning = 'Security obligations present.'
        else:
            is_violation = True
            risk_level = 'HIGH'
            reasoning = 'Provider disclaims security responsibilities.'

    # Refund policy
    elif 'refund' in clause.lower() or 'refund' in policy_rule.lower():
        if 'refund' in txt or 'compens' in txt or 'remedy' in txt:
            is_violation = False
            risk_level = 'LOW'
            reasoning = 'Refund or remedy terms present.'
        else:
            is_violation = True
            risk_level = 'MEDIUM'
            reasoning = 'No refund/remedy for outages or breaches.'

    # Governing law validity
    elif 'govern' in clause.lower() or 'governing' in policy_rule.lower() or 'law' in txt:
        if 'new york' in txt or 'governed by the laws of' in txt or 'state of' in txt:
            is_violation = False
            risk_level = 'LOW'
            reasoning = 'Recognized legal jurisdiction present.'
        else:
            is_violation = True
            risk_level = 'HIGH'
            reasoning = 'Governing law not a recognized jurisdiction or only internal policies.'

    # Dispute resolution fairness
    elif 'dispute' in clause.lower() or 'arbitration' in policy_rule.lower() or 'panel' in txt:
        if 'arbitration' in txt and ('binding' in txt or 'independent' in txt or 'judicial' in txt):
            is_violation = False
            risk_level = 'LOW'
            reasoning = 'Independent arbitration or judicial review allowed.'
        else:
            is_violation = True
            risk_level = 'HIGH'
            reasoning = 'Dispute resolution is unilateral or internal-only.'

    else:
        # Default: not matched - treat as low risk
        is_violation = False
        risk_level = 'LOW'
        reasoning = 'Clause not directly matched by deterministic checks (treated as low risk).'


    return RiskCheck(
        clause_name=clause_name,
        policy_rule=policy_rule,
        extracted_text=(relevant_text or '')[:1000],
        is_violation=is_violation,
        risk_level=risk_level,
        citation=citation,
        reasoning=reasoning
    )

def analyze_chunks_against_policy_all_sections(chunks: List[Dict[str, Any]], policy: List[Dict[str,Any]]) -> Dict[str,Any]:
    results = []  # list of RiskCheck dicts
    section_scores = []  # per-section aggregated info
    total_violation_weight = 0.0
    total_importance = 0.0

    # Compute total importance (denominator) as sum of importance of each policy
    for p in policy:
        total_importance += p.get('importance', 1.0) * 1.0  # base multiplier

    # For each chunk (section), evaluate every policy rule against that chunk
    for c in chunks:
        section_text = c.get('text','')
        section_id = c.get('id', None)
        section_result = {
            'id': section_id,
            'text': section_text[:300],
            'violations': [],
            'section_violation_weight': 0.0,
            'section_importance_total': 0.0
        }
        for p in policy:
            clause_name = p.get('clause_name')
            policy_rule = p.get('policy_rule')
            importance = p.get('importance',1.0)
            rc = local_rule_check(clause_name, policy_rule, section_text)
            # attach metadata
            rcd = rc.dict()
            rcd['section_id'] = section_id
            rcd['importance'] = importance
            results.append(rcd)
            section_result['section_importance_total'] += importance
            if rc.is_violation:
                w = RISK_WEIGHTS.get(rc.risk_level, 0.2) * importance
                section_result['section_violation_weight'] += w
                total_violation_weight += w
        section_scores.append(section_result)

    # document-level risk percentage
    max_possible = total_importance * max(RISK_WEIGHTS.values())
    risk_percentage = min(100.0, (total_violation_weight / max_possible) * 100.0 if max_possible > 0 else 0.0)

    # derive top risky sections and top risky rules
    sorted_sections = sorted(section_scores, key=lambda x: x['section_violation_weight'], reverse=True)
    top_sections = [{'id': s['id'], 'snippet': s['text'], 'score': round(s['section_violation_weight'],3)} for s in sorted_sections if s['section_violation_weight']>0]
    # aggregate by clause name
    clause_agg = {}
    for r in results:
        if r['is_violation']:
            clause_agg[r['clause_name']] = clause_agg.get(r['clause_name'], 0.0) + (RISK_WEIGHTS.get(r['risk_level'],0.2) * r.get('importance',1.0))

    top_clauses = sorted([{'clause_name': k, 'score': v} for k,v in clause_agg.items()], key=lambda x: x['score'], reverse=True)

    return {
        'results': results,
        'section_scores': section_scores,
        'document_risk_percentage': round(risk_percentage,2),
        'top_sections': top_sections,
        'top_clauses': top_clauses
    }
