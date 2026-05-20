import re
import math
import logging
import json
import os
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Fallback dataset in case JSON files are missing
FALLBACK_DATASET = [
    {"text": "Worked on requirement gathering, SQL reporting, and CRM implementation", "role": "Business Analyst", "skills": "SQL, CRM, Requirement Gathering", "domain": "CRM", "experience": "Mid"},
    {"text": "Developed REST APIs using Java and Spring Boot", "role": "Java Developer", "skills": "Java, Spring Boot, REST API", "domain": "Software Development", "experience": "Mid"},
    {"text": "Created dashboards using Power BI and Excel reports", "role": "Data Analyst", "skills": "Power BI, Excel", "domain": "Analytics", "experience": "Fresher"},
    {"text": "Handled insurance renewal calls and customer follow-ups in CRM", "role": "CRM Executive", "skills": "CRM, Customer Handling", "domain": "Insurance", "experience": "Fresher"},
    {"text": "Automated test cases using Selenium WebDriver", "role": "QA Automation Engineer", "skills": "Selenium, Automation Testing", "domain": "Testing", "experience": "Mid"},
    {"text": "Managed service reminder campaigns and customer appointments", "role": "Service CRM Executive", "skills": "CRM, Telecalling", "domain": "Automobile", "experience": "Fresher"},
    {"text": "Designed ETL pipelines using Python and SQL", "role": "Data Engineer", "skills": "Python, SQL, ETL", "domain": "Data Engineering", "experience": "Senior"},
    {"text": "Worked on machine learning models using Python and TensorFlow", "role": "ML Engineer", "skills": "Python, TensorFlow, ML", "domain": "AI/ML", "experience": "Mid"},
    {"text": "Managed cloud infrastructure on AWS", "role": "Cloud Engineer", "skills": "AWS, Linux", "domain": "Cloud", "experience": "Mid"},
    {"text": "Created UI screens using React and JavaScript", "role": "Frontend Developer", "skills": "React, JavaScript", "domain": "Web Development", "experience": "Fresher"},
    {"text": "Built APIs and microservices using Node.js", "role": "Backend Developer", "skills": "Node.js, API", "domain": "Software Development", "experience": "Mid"},
    {"text": "Conducted UAT testing and prepared BRD documents", "role": "Business Analyst", "skills": "UAT, BRD", "domain": "CRM", "experience": "Mid"},
    {"text": "Processed customer complaints and escalations in CRM", "role": "Customer Support Executive", "skills": "CRM, Communication", "domain": "Support", "experience": "Fresher"},
    {"text": "Worked on NLP text classification projects", "role": "NLP Engineer", "skills": "Python, NLP", "domain": "AI/ML", "experience": "Senior"},
    {"text": "Performed database optimization in MySQL", "role": "Database Administrator", "skills": "MySQL, SQL", "domain": "Database", "experience": "Mid"},
]

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
        self.trained_items: List[Dict[str, any]] = []
        
        # Load and train
        self.load_and_train()

    def clean_text(self, text: str) -> str:
        """Step 1: Text Cleaning"""
        if not text:
            return ""
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        return text

    def tokenize(self, text: str) -> List[str]:
        """Step 2: Tokenization"""
        cleaned = self.clean_text(text)
        words = cleaned.split()
        tokens = [w for w in words if w not in STOPWORDS and len(w) > 1]
        return tokens

    def load_and_train(self):
        """Step 3 & 4: Embedding/Vectorization & Model Training"""
        dataset = []
        
        # Paths to JSON files in the workspace
        # C:\Users\W2632\project\job_search\data set
        base_dir = os.path.dirname(os.path.abspath(__file__))
        dataset_json_path = os.path.join(base_dir, "data set", "job_dataset.json")
        data_json_path = os.path.join(base_dir, "data set", "data.json")

        # 1. Load job_dataset.json
        if os.path.exists(dataset_json_path):
            try:
                with open(dataset_json_path, "r", encoding="utf-8") as f:
                    job_dataset_data = json.load(f)
                    for item in job_dataset_data:
                        title = item.get("Title", "")
                        skills_list = item.get("Skills", [])
                        resp_list = item.get("Responsibilities", [])
                        kw_list = item.get("Keywords", [])
                        exp_level = item.get("ExperienceLevel", "Mid")
                        
                        text_rep = f"{title} {' '.join(skills_list)} {' '.join(resp_list)} {' '.join(kw_list)}"
                        dataset.append({
                            "text": text_rep,
                            "role": title,
                            "skills": ", ".join(skills_list),
                            "domain": title.split()[-1] if title else "Technology",
                            "experience": exp_level
                        })
                logger.info(f"Loaded {len(job_dataset_data)} items from job_dataset.json")
            except Exception as e:
                logger.error(f"Error loading job_dataset.json: {e}")

        # 2. Load data.json
        if os.path.exists(data_json_path):
            try:
                with open(data_json_path, "r", encoding="utf-8") as f:
                    data_json_data = json.load(f)
                    for item in data_json_data:
                        title = item.get("jobTitle", "")
                        skills = item.get("skills", "")
                        desc = item.get("description", "")
                        exp = item.get("experience", "Mid")
                        
                        text_rep = f"{title} {skills} {desc}"
                        dataset.append({
                            "text": text_rep,
                            "role": title,
                            "skills": skills,
                            "domain": "Technology",
                            "experience": exp
                        })
                logger.info(f"Loaded {len(data_json_data)} items from data.json")
            except Exception as e:
                logger.error(f"Error loading data.json: {e}")

        # Fallback if no items loaded from JSON files
        if not dataset:
            logger.info("No external datasets found, falling back to built-in sample dataset.")
            dataset = FALLBACK_DATASET

        self.trained_items = dataset
        
        # Tokenize all training items
        tokenized_docs = [self.tokenize(item["text"]) for item in dataset]
        
        # Build vocabulary
        all_words = set()
        for doc in tokenized_docs:
            all_words.update(doc)
        self.vocab = sorted(list(all_words))
        
        # Calculate document frequency for IDF
        num_docs = len(dataset)
        doc_counts = {word: 0 for word in self.vocab}
        for doc in tokenized_docs:
            seen_in_doc = set(doc)
            for word in seen_in_doc:
                if word in doc_counts:
                    doc_counts[word] += 1
                    
        # Compute IDF
        self.idf = {}
        for word, count in doc_counts.items():
            self.idf[word] = math.log((1 + num_docs) / (1 + count)) + 1.0

        # Vectorize all documents
        self.dataset_vectors = []
        for doc in tokenized_docs:
            vector = self._vectorize_doc(doc)
            self.dataset_vectors.append(vector)
            
        logger.info(f"NLP Model trained on {num_docs} items. Vocab size: {len(self.vocab)}")

    def _vectorize_doc(self, tokens: List[str]) -> Dict[str, float]:
        """Convert list of tokens into TF-IDF vector with L2 normalization"""
        tf = {}
        for token in tokens:
            if token in self.vocab:
                tf[token] = tf.get(token, 0) + 1
        
        vector = {}
        for token, count in tf.items():
            vector[token] = count * self.idf[token]
            
        # L2 Norm
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
        """Step 5: Prediction"""
        tokens = self.tokenize(text)
        if not tokens:
            return {
                "role": None,
                "skills": [],
                "domain": None,
                "experience": None,
                "confidence": 0.0
            }
            
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

# Global singleton model
nlp_model = NLPModel()
