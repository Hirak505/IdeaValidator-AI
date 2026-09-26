import json
import os

def load_json(name):
    with open(f"validation_{name}.json", "r") as f:
        return json.load(f)

def summarize_iv(data):
    chief = data["chief_judge"]
    cons = data["consensus"]
    
    print(f"Overall: {chief['overall_score']}")
    print(f"Tech: {data['technical']['score']} | Biz: {data['business']['score']} | Inv: {data['innovation']['score']} | Pres: {data['presentation']['score']}")
    print(f"Chief Conf: {chief['confidence']} | Chief Evid: {chief['evidence_quality']}")
    print(f"Spread: {cons['spread']} | Most Aligned: {cons['most_aligned']} | Largest Disagreement: {cons['largest_disagreement']}")
    print(f"Differentiation Category: {chief['differentiation']['solution_category']}")
    print(f"Differentiation Unsupported: {chief['differentiation']['unsupported_claims']}")
    print("Major Weaknesses (Top 2):", chief['top_improvements'][:2])
    print("Roadmap Priorities:")
    for item in chief['prioritized_roadmap']:
        print(f"  - {item['priority']}: {item['title']} (Impact: {item['impact']}, Effort: {item['effort']})")
    print("---")

print("=== IdeaValidator Run 1 ===")
iv1 = load_json("iv_1")
summarize_iv(iv1)

print("=== IdeaValidator Run 2 ===")
iv2 = load_json("iv_2")
summarize_iv(iv2)

print("=== IdeaValidator Run 3 ===")
iv3 = load_json("iv_3")
summarize_iv(iv3)

print("=== Tech Strong / Biz Weak ===")
tb = load_json("tech_biz")
print(f"Tech Score: {tb['technical']['score']}")
print(f"Biz Score: {tb['business']['score']}")
print("Roadmap:")
for item in tb['chief_judge']['prioritized_roadmap']:
    print(f"  - {item['priority']}: {item['title']}")
print("---")

print("=== Incomplete Project ===")
inc = load_json("incomplete")
print(f"Scores -> Tech: {inc['technical']['score']}, Biz: {inc['business']['score']}, Inv: {inc['innovation']['score']}, Pres: {inc['presentation']['score']}, Overall: {inc['chief_judge']['overall_score']}")
print(f"Chief Conf: {inc['chief_judge']['confidence']} | Chief Evid: {inc['chief_judge']['evidence_quality']}")
print("Findings:")
for f in inc['technical']['key_findings'][:2]:
    print(f"  - Tech: {f['finding']} ({f['evidence_type']}) - Conf: {f['confidence']}")
for f in inc['business']['key_findings'][:2]:
    print(f"  - Biz: {f['finding']} ({f['evidence_type']}) - Conf: {f['confidence']}")
print("---")
