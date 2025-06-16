import firebase_admin
from firebase_admin import credentials, firestore
import os
import nltk
from nltk.translate.bleu_score import sentence_bleu
from rouge_score import rouge_scorer
from bs4 import BeautifulSoup
import requests

# Init Firebase
cred = credentials.Certificate("firebase_credentials.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Init NLP
nltk.download('punkt')
scorer = rouge_scorer.RougeScorer(['rouge1', 'rougeL'], use_stemmer=True)

# Evaluate
docs = db.collection("archived_pages").stream()

total = 0
bleu_scores, rouge1_scores, rougeL_scores = [], [], []

def clean_html(url):
    try:
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        # Remove scripts/styles
        for tag in soup(["script", "style", "header", "footer", "nav"]):
            tag.decompose()

        text = soup.get_text(separator=" ")
        text = " ".join(text.split())  # Clean spaces
        return text
    except Exception as e:
        print("Error loading snapshot:", e)
        return ""

for doc in docs:
    data = doc.to_dict()

    if data.get("snapshot_url") and data.get("ai_reconstruction"):
        reference_text = clean_html(data["snapshot_url"])
        ai_text = data["ai_reconstruction"]

        if len(reference_text) < 50 or len(ai_text) < 50:
            continue  # skip short or failed extractions

        total += 1

        ref_tokens = nltk.word_tokenize(reference_text)
        hyp_tokens = nltk.word_tokenize(ai_text)

        bleu = sentence_bleu([ref_tokens], hyp_tokens)
        rouge = scorer.score(reference_text, ai_text)

        bleu_scores.append(bleu)
        rouge1_scores.append(rouge["rouge1"].fmeasure)
        rougeL_scores.append(rouge["rougeL"].fmeasure)

# Report
if total == 0:
    print("No valid pairs found for evaluation.")
else:
    print(f"\nEvaluated {total} valid page reconstructions:")
    print(f"Average BLEU Score   : {sum(bleu_scores) / total:.4f}")
    print(f"Average ROUGE-1 F1   : {sum(rouge1_scores) / total:.4f}")
    print(f"Average ROUGE-L F1   : {sum(rougeL_scores) / total:.4f}")
