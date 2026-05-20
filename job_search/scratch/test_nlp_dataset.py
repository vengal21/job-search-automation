import json
import time
import os
import re
import math
from typing import List, Dict

STOPWORDS = {
    "on", "and", "using", "in", "with", "for", "the", "a", "an", "of", "to", "at", 
    "by", "from", "up", "about", "into", "over", "after", "worked", "created", 
    "handled", "managed", "designed", "built", "conducted", "processed", "performed", "developed",
    "responsibilities", "skills", "keywords", "experience", "level"
}

class NLPModel:
    def __init__(self):
        self.vocab: List[str] = []
        self.idf: Dict[str, float] = {}
        self.dataset_vectors: List[Dict[str, float]] = []
        self.trained_items = []

    def clean_text(self, text: str) -> str:
        if not text:
            return ""
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        return text

    def tokenize(self, text: str) -> List[str]:
        cleaned = self.clean_text(text)
        words = cleaned.split()
        tokens = [w for w in words if w not in STOPWORDS and len(w) > 1]
        return tokens

    def train(self, filepath: str):
        t0 = time.time()
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            return
            
        with open(filepath, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            
        print(f"Loaded {len(raw_data)} items from {filepath}")
        
        # Format the items
        formatted_dataset = []
        for idx, item in enumerate(raw_data):
            title = item.get("Title", "")
            skills_list = item.get("Skills", [])
            resp_list = item.get("Responsibilities", [])
            kw_list = item.get("Keywords", [])
            exp_level = item.get("ExperienceLevel", "Mid")
            
            # Combine text representation
            text_rep = f"{title} {' '.join(skills_list)} {' '.join(resp_list)} {' '.join(kw_list)}"
            
            formatted_item = {
                "text": text_rep,
                "role": title,
                "skills": ", ".join(skills_list),
                "domain": title.split()[-1] if title else "Technology",
                "experience": exp_level
            }
            formatted_dataset.append(formatted_item)
            
        self.trained_items = formatted_dataset
        
        # Tokenize
        tokenized_docs = [self.tokenize(item["text"]) for item in formatted_dataset]
        
        # Vocabulary
        all_words = set()
        for doc in tokenized_docs:
            all_words.update(doc)
        self.vocab = sorted(list(all_words))
        
        # IDF
        num_docs = len(formatted_dataset)
        doc_counts = {word: 0 for word in self.vocab}
        for doc in tokenized_docs:
            seen_in_doc = set(doc)
            for word in seen_in_doc:
                if word in doc_counts:
                    doc_counts[word] += 1
                    
        self.idf = {}
        for word, count in doc_counts.items():
            self.idf[word] = math.log((1 + num_docs) / (1 + count)) + 1.0

        # Vectorize
        self.dataset_vectors = []
        for doc in tokenized_docs:
            vector = self._vectorize_doc(doc)
            self.dataset_vectors.append(vector)
            
        t1 = time.time()
        print(f"Trained on {num_docs} items in {t1 - t0:.3f} seconds. Vocab size: {len(self.vocab)}")

    def _vectorize_doc(self, tokens: List[str]) -> Dict[str, float]:
        tf = {}
        for token in tokens:
            if token in self.vocab:
                tf[token] = tf.get(token, 0) + 1
        vector = {}
        for token, count in tf.items():
            vector[token] = count * self.idf[token]
        sq_sum = sum(v ** 2 for v in vector.values())
        norm = math.sqrt(sq_sum)
        if norm > 0:
            for token in vector:
                vector[token] /= norm
        return vector

    def _cosine_similarity(self, v1: Dict[str, float], v2: Dict[str, float]) -> float:
        dot_product = 0.0
        for token, val in v1.items():
            if token in v2:
                dot_product += val * v2[token]
        return dot_product

    def predict(self, text: str) -> Dict[str, any]:
        tokens = self.tokenize(text)
        query_vector = self._vectorize_doc(tokens)
        
        best_sim = -1.0
        best_index = -1
        
        for idx, doc_vector in enumerate(self.dataset_vectors):
            sim = self._cosine_similarity(query_vector, doc_vector)
            if sim > best_sim:
                best_sim = sim
                best_index = idx
                
        if best_index != -1 and best_sim > 0.05:
            matched = self.trained_items[best_index]
            return {
                "role": matched["role"],
                "skills": [s.strip() for s in matched["skills"].split(",") if s.strip()],
                "domain": matched["domain"],
                "experience": matched["experience"],
                "confidence": best_sim
            }
        
        return {
            "role": None,
            "skills": [],
            "domain": None,
            "experience": None,
            "confidence": 0.0
        }

model = NLPModel()
model.train(r"C:\Users\W2632\project\job_search\data set\job_dataset.json")

test_queries = [
    "Experienced in C#, ASP.NET MVC, web app design, SQL Server",
    "Python scripting, TensorFlow model building, machine learning algorithms",
    "Automation testing with Selenium and test cases"
]

for q in test_queries:
    res = model.predict(q)
    print(f"Query: '{q}'\nPrediction: {res}\n")
