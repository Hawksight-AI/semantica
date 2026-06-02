# Decision Intelligence Datasets

This directory holds all external datasets used by the `benchmarks/decision_intelligence/` test suite. Place each downloaded dataset in the subdirectory indicated below. **Do not commit raw dataset files** — only the `README.md` lives here by default. Large binary fixtures route through git-lfs (see `benchmarks/fixtures/`).

---

## German Credit Dataset

**Tracks:** 1.1 (Precedent Search — MRR)  
**Metric:** MRR ≥ 0.70  
**License:** CC BY 4.0  
**Citation:** Hofmann, H. (1994). Statlog (German Credit Data). UCI Machine Learning Repository. https://doi.org/10.24432/C5NC77

**Source:** https://archive.ics.uci.edu/dataset/144/statlog+german+credit+data

**Download:**
```bash
mkdir -p benchmarks/datasets/decision_intelligence/german_credit
wget -O benchmarks/datasets/decision_intelligence/german_credit/german.data \
  https://archive.ics.uci.edu/ml/machine-learning-databases/statlog/german/german.data
wget -O benchmarks/datasets/decision_intelligence/german_credit/german.doc \
  https://archive.ics.uci.edu/ml/machine-learning-databases/statlog/german/german.doc
```

**Expected layout:**
```
benchmarks/datasets/decision_intelligence/german_credit/
  german.data         # 1,000 rows × 21 columns (space-separated)
  german.doc          # Attribute description
```

Each row is one loan applicant decision. The 21st column is the label (1 = good credit, 2 = bad credit). Ground-truth precedent pairs are constructed by pairing decisions with identical `credit_history` + `loan_purpose` + `employment` attributes.

---

## CUAD — Contract Understanding Atticus Dataset

**Tracks:** 1.1 (nDCG@10, graph lift), 1.4 / 31 (compliance accuracy)  
**Metrics:** nDCG@10 ≥ 0.65, graph lift ≥ 0.05, compliance accuracy ≥ 0.88, FNR ≤ 0.05  
**License:** CC BY 4.0  
**Citation:** Hendrycks, D. et al. (2021). CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review. arXiv:2103.06268.

**Source:** https://www.atticusprojectai.org/cuad  
**Direct download:** https://huggingface.co/datasets/theatticusproject/cuad

**Download:**
```bash
mkdir -p benchmarks/datasets/decision_intelligence/cuad
# Via Hugging Face CLI (recommended)
pip install datasets
python - <<'EOF'
from datasets import load_dataset
ds = load_dataset("theatticusproject/cuad", split="train")
import json, pathlib
pathlib.Path("benchmarks/datasets/decision_intelligence/cuad/cuad_train.json").write_text(
    json.dumps(ds.to_dict(), indent=2)
)
EOF
```

**Expected layout:**
```
benchmarks/datasets/decision_intelligence/cuad/
  cuad_train.json     # 510 contracts, 41 clause-type QA pairs per contract
```

Clause types used for compliance mapping: non-compete, indemnification, termination-for-convenience, limitation-of-liability, governing-law, change-of-control, assignment, and 34 others.

---

## LEDGAR — Legal Provisions Dataset

**Tracks:** 1.4 / 31 (clause-level F1)  
**Metric:** clause F1 ≥ 0.75  
**License:** Research use  
**Citation:** Tuggener, D. et al. (2020). LEDGAR: A Large-Scale Multi-Label Corpus for Text Classification of Legal Provisions. LREC 2020.

**Source:** https://metatext.io/datasets/ledgar  
**Alternative:** https://huggingface.co/datasets/lex_glue (includes LEDGAR split)

**Download:**
```bash
mkdir -p benchmarks/datasets/decision_intelligence/ledgar
python - <<'EOF'
from datasets import load_dataset
ds = load_dataset("lex_glue", "ledgar", split="train")
import json, pathlib
pathlib.Path("benchmarks/datasets/decision_intelligence/ledgar/ledgar_train.json").write_text(
    json.dumps(ds.to_dict(), indent=2)
)
EOF
```

**Expected layout:**
```
benchmarks/datasets/decision_intelligence/ledgar/
  ledgar_train.json   # 60,000 provisions, each labelled with multi-label compliance tags
```

60 000 SEC-filing legal provisions, labelled across 100 categories. Used for clause-level F1 evaluation in `test_clause_f1_ledgar`.

---

## TREC Clinical Trials 2022

**Tracks:** 1.4 / 31 (eligibility classification)  
**Metric:** compliance accuracy ≥ 0.88  
**License:** Free for research  
**Citation:** TREC Clinical Trials Track 2022. https://trec.nist.gov/data/clinical2022.html

**Source:** https://trec.nist.gov/data/clinical2022.html

**Download:** Register at https://trec.nist.gov/data/clinical2022.html and request the data package. Place the unpacked files as:

**Expected layout:**
```
benchmarks/datasets/decision_intelligence/trec_ct_2022/
  topics2022.xml      # 75 patient topic descriptions
  qrels2022.txt       # Ground-truth eligibility labels (qrel format)
  clinical_trials/    # Trial XML files (optional for eligibility subset)
```

Used to test `PolicyEngine.check_decision_compliance()` on structured patient-eligibility decisions.

---

## ATOMIC 2020 (500-pair subset)

**Tracks:** 1.2 (causal recall, precision)  
**Metrics:** recall ≥ 0.80, precision ≥ 0.85  
**License:** CC BY 4.0  
**Citation:** Hwang, J.D. et al. (2021). COMET-ATOMIC 2020: On Symbolic and Neural Commonsense Knowledge Graphs. AAAI 2021.

**Source:** https://allenai.org/data/atomic-2020

**Download:**
```bash
mkdir -p benchmarks/datasets/decision_intelligence/atomic_subset
wget -O /tmp/atomic2020.zip \
  https://storage.googleapis.com/ai2-mosaic/public/atomic2020/atomic-2020-all-qa.zip
unzip /tmp/atomic2020.zip -d /tmp/atomic2020_full

# Extract 500 cause→effect pairs (xCause / xEffect relations only)
python - <<'EOF'
import csv, json, random, pathlib
random.seed(42)
pairs = []
for rel in ["xCause", "xEffect"]:
    with open(f"/tmp/atomic2020_full/train.tsv") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row.get("relation") == rel and row.get("tail") != "none":
                pairs.append({"cause": row["head"], "effect": row["tail"], "relation": rel})
random.shuffle(pairs)
chosen = pairs[:500]
pathlib.Path("benchmarks/datasets/decision_intelligence/atomic_subset/atomic_500.json").write_text(
    json.dumps(chosen, indent=2)
)
EOF
```

**Expected layout:**
```
benchmarks/datasets/decision_intelligence/atomic_subset/
  atomic_500.json     # 500 {"cause": ..., "effect": ..., "relation": ...} records
```

---

## e-CARE

**Tracks:** 1.2 (causal direction, explanation completeness)  
**License:** Research open  
**Citation:** Du, L. et al. (2022). e-CARE: a New Dataset for Exploring Explainable Causal Reasoning. ACL 2022. arXiv:2205.02593.

**Source:** https://github.com/Waste-Wood/e-CARE

**Download:**
```bash
mkdir -p benchmarks/datasets/decision_intelligence/ecare
git clone https://github.com/Waste-Wood/e-CARE /tmp/ecare_repo
cp /tmp/ecare_repo/data/train.jsonl benchmarks/datasets/decision_intelligence/ecare/train.jsonl
cp /tmp/ecare_repo/data/dev.jsonl   benchmarks/datasets/decision_intelligence/ecare/dev.jsonl
```

**Expected layout:**
```
benchmarks/datasets/decision_intelligence/ecare/
  train.jsonl         # 21,324 causal QA records with explanation annotations
  dev.jsonl           # dev split
```

Each record: `{"premise": ..., "ask-for": "cause"|"effect", "hypothesis1": ..., "hypothesis2": ..., "label": 0|1, "conceptual_explanation": ...}`

---

## CausalBench

**Tracks:** 1.2 (direction accuracy, intervention accuracy)  
**Metrics:** direction accuracy ≥ 0.72, intervention accuracy ≥ 0.60  
**Citation:** NeurIPS 2024 CausalBench. https://causalbench.org

**Source:** https://causalbench.org  (registration required for full benchmark)

**Download:** Follow instructions at https://causalbench.org/download. Place the relevant splits as:

**Expected layout:**
```
benchmarks/datasets/decision_intelligence/causalbench/
  direction_test.json      # cause→effect and effect→cause pairs
  intervention_test.json   # Counterfactual held-out pairs
  baselines.json           # 19 published LLM baseline scores (for reference)
```

Each `direction_test.json` record: `{"cause": ..., "effect": ..., "label": "cause_to_effect"|"effect_to_cause"}`  
Each `intervention_test.json` record: `{"premise": ..., "intervention": ..., "counterfactual": ..., "label": 0|1}`
