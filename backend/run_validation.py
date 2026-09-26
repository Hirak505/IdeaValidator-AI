import asyncio
import json
import os
from judges import run_all_judges

# Read IdeaValidator-AI README.md
README_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "README.md")
with open(README_PATH, "r", encoding="utf-8") as f:
    IDEA_VALIDATOR_CONTEXT = f.read()

TECH_STRONG_BIZ_WEAK_CONTEXT = """
Project Name: UltraMatrix Compute API
Description: We built a highly optimized C++ matrix multiplication engine wrapped in a FastAPI service. 
It uses Redis for high-speed caching and Kubernetes for orchestrating multiple microservices. 
The backend implements a complex event sourcing pattern with Kafka for perfect audit logs.
Architecture: FastAPI, C++, Redis, Kubernetes, Kafka, PostgreSQL.
Business Model: We haven't figured out monetization yet. Maybe open source, maybe charge a subscription later. 
Target Users: Anyone who needs fast math.
Go-to-market: We will post it on HackerNews.
"""

INCOMPLETE_PROJECT_CONTEXT = """
Project Name: NextGen App
Description: A mobile app that will change the world using AI.
"""

async def run_evaluations():
    print("=== STARTING INTEGRATION VALIDATION ===")
    
    # 1. IdeaValidator-AI (Run 1)
    print("\n--- TEST CASE A: IDEA VALIDATOR (Run 1) ---")
    res_iv_1 = await run_all_judges(IDEA_VALIDATOR_CONTEXT)
    with open("validation_iv_1.json", "w") as f:
        json.dump(res_iv_1, f, indent=2)
        
    # 2. IdeaValidator-AI (Run 2)
    print("\n--- TEST CASE A: IDEA VALIDATOR (Run 2) ---")
    res_iv_2 = await run_all_judges(IDEA_VALIDATOR_CONTEXT)
    with open("validation_iv_2.json", "w") as f:
        json.dump(res_iv_2, f, indent=2)
        
    # 3. IdeaValidator-AI (Run 3)
    print("\n--- TEST CASE A: IDEA VALIDATOR (Run 3) ---")
    res_iv_3 = await run_all_judges(IDEA_VALIDATOR_CONTEXT)
    with open("validation_iv_3.json", "w") as f:
        json.dump(res_iv_3, f, indent=2)

    # 4. Tech Strong / Biz Weak
    print("\n--- TEST CASE B: TECH STRONG / BIZ WEAK ---")
    res_tech = await run_all_judges(TECH_STRONG_BIZ_WEAK_CONTEXT)
    with open("validation_tech_biz.json", "w") as f:
        json.dump(res_tech, f, indent=2)
        
    # 5. Incomplete Project
    print("\n--- TEST CASE C: INCOMPLETE PROJECT ---")
    res_inc = await run_all_judges(INCOMPLETE_PROJECT_CONTEXT)
    with open("validation_incomplete.json", "w") as f:
        json.dump(res_inc, f, indent=2)
        
    print("\n=== VALIDATION COMPLETE ===")

if __name__ == "__main__":
    asyncio.run(run_evaluations())
