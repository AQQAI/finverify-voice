"""
Run many questions through the engine directly (no server needed) and see which
route each takes. Use it to check coverage and find gaps in facts.json.
  python eval_questions.py questions.txt   -> prints a table, writes eval_results.csv
"""
import csv, sys
import engine

def main(path):
    qs = [l.strip() for l in open(path, encoding="utf-8") if l.strip() and not l.startswith("#")]
    rows = []
    for q in qs:
        r = engine.answer(q, use_llm=False)
        facts = ",".join(f["id"] for f in r["facts"])
        rows.append({"question": q, "route": r["route"], "facts": facts, "ms": r["ms"], "answer": r["spoken"]})
        print(f"{r['route']:<13} {facts:<32} {q}")
    with open("eval_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    gaps = sum(r["route"] == "no_answer" for r in rows)
    print(f"\n{len(rows)} questions, {gaps} with no verified answer -> eval_results.csv")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "questions.txt")
