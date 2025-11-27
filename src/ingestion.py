from typing import List, Dict, Any

def chunk_file_with_unstructured(file_path: str) -> List[Dict[str, Any]]:
    print('➡ Step 1: Chunking file (Offline Mode)...')
    chunks = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print('Local processing error:', e)
        return []

    raw_sections = content.split('\n\n')
    for idx, section in enumerate(raw_sections):
        clean_text = section.strip()
        if clean_text:
            chunks.append({'id': idx, 'text': clean_text, 'type': 'NarrativeText'})

    print(f'   ✅ Offline Success: Created {len(chunks)} chunks from file.')
    return chunks
