import os
import json
import argparse
from src.ingestion import chunk_file_with_unstructured
from src.analysis import analyze_chunks_against_policy_all_sections
from src.policy_generator import generate_policy_from_chunks, save_policy_json

def display_report(report):
    print('\n' + '='*60)
    print(' LEGAL RISK ANALYSIS REPORT (ALL SECTIONS)')
    print('='*60 + '\n')
    print(f"Document Risk Percentage: {report['document_risk_percentage']}%\n")
    print('Top risky sections:')
    for s in report['top_sections'][:10]:
        print(f" - Section id {s['id']}: score {s['score']} - snippet: {s['snippet']}")
    print('\nTop risky clause types:')
    for c in report['top_clauses'][:10]:
        print(f" - {c['clause_name']}: score {c['score']}")
    print('\nDetailed per-section scores saved to output/report.json')

def main():
    parser = argparse.ArgumentParser(description="Legal Risk Analyzer with optional policy generator")
    parser.add_argument('--input', '-i', help='Input contract file', default='sample_contracts/sample_contract_long.txt')
    parser.add_argument('--generate-policies', '-g', action='store_true', help='Generate policies from the contract using AI agent (or fallback).')
    parser.add_argument('--append-policies', '-a', action='store_true', help='Append generated policies to policies.json (requires review recommended).')
    parser.add_argument('--use-model', action='store_true', help='Use external LLM for generation (you must implement call_model in policy_generator).')
    args = parser.parse_args()

    input_file = args.input
    if not os.path.exists(input_file):
        print(f"Input file not found: {input_file}. Falling back to sample_contracts/sample_contract.txt")
        input_file = 'sample_contracts/sample_contract.txt'

    chunks = chunk_file_with_unstructured(input_file)

    if args.generate_policies:
        print("➡ Generating policy rules from the contract (AI agent / fallback)...")
        policy_obj = generate_policy_from_chunks(chunks, source_doc=os.path.basename(input_file), use_model=args.use_model)
        save_path = f"generated_policy_{os.path.basename(input_file)}.json"
        save_policy_json(policy_obj, save_path)
        print(f"Generated policy saved to: {save_path}")
        print("IMPORTANT: Please review the generated rules before appending to `policies.json`")
        if args.append_policies:
            # append approved rules to policies.json (simple append - manual review recommended)
            try:
                with open('policies.json', 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except Exception:
                existing = []
            # Map generated rules into internal policy format
            for r in policy_obj.get('rules', []):
                mapped = {
                    "clause_name": r.get('clause_name'),
                    "policy_rule": r.get('policy_rule'),
                    "risk_level_if_violated": r.get('severity', 'MEDIUM'),
                    "importance": float(r.get('importance', 1.0))
                }
                existing.append(mapped)
            with open('policies.json', 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2)
            print("Appended generated rules to policies.json (please review).")
        return

    # Else run the analyzer using existing policies.json
    try:
        policy = json.load(open('policies.json','r', encoding='utf-8'))
    except Exception as e:
        print("ERROR: could not load policies.json:", e)
        return

    print("➡ Running analysis across all sections...")
    report = analyze_chunks_against_policy_all_sections(chunks, policy)
    os.makedirs('output', exist_ok=True)
    with open('output/report.json','w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    display_report(report)

if __name__ == '__main__':
    main()
