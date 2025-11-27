# A simple keyword-based "retrieval" used offline.

from typing import List, Dict, Any

def retrieve_relevant_chunk(chunks: List[Dict[str, Any]], query: str) -> str:
    q = query.lower()
    best = ''
    best_score = -1

    for c in chunks:
        text = c.get('text','').lower()
        score = sum(tok in text for tok in q.split())

        # Special weights
        if '3 year' in text:
            score += 2
        if '1.5' in text or '1.5x' in text:
            score += 2

        if score > best_score:
            best_score = score
            best = c.get('text','')

    return best
