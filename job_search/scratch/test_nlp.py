import re
import math
from typing import List, Dict, Tuple

# Sample Dataset
DATASET = [
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
    "handled", "managed", "designed", "built", "conducted", "processed", "performed", "developed"
}

class NLPModel:
    def __init__(self):
        self.vocab: List[str] = []
        self.idf: Dict[str, float] = {}
        self.dataset_vectors: List[Dict[str, float]] = []

    def clean_text(self, text: str) -> str:
        """Step 1: Text Cleaning"""
        # Lowercase and remove punctuation
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        return text

    def tokenize(self, text: str) -> List[str]:
        """Step 2: Tokenization"""
        cleaned = self.clean_text(text)
        words = cleaned.split()
        # Remove stopwords and short tokens
        tokens = [w for w in words if w not in STOPWORDS and len(w) > 1]
        return tokens

    def train(self, dataset: List[Dict[str, str]]):
        """Step 3 & 4: Embedding/Vectorization & Model Training"""
        # Tokenize all training documents
        tokenized_docs = [self.tokenize(item["text"]) for item in dataset]
        
        # Build vocabulary
        all_words = set()
        for doc in tokenized_docs:
            all_words.update(doc)
        self.vocab = sorted(list(all_words))
        
        # Compute IDF
        num_docs = len(dataset)
        doc_counts = {word: 0 for word in self.vocab}
        for doc in tokenized_docs:
            seen_in_doc = set(doc)
            for word in seen_in_doc:
                if word in doc_counts:
                    doc_counts[word] += 1
                    
        self.idf = {}
        for word, count in doc_counts.items():
            # Smooth IDF
            self.idf[word] = math.log((1 + num_docs) / (1 + count)) + 1.0

        # Vectorize each training document
        self.dataset_vectors = []
        for doc in tokenized_docs:
            vector = self._vectorize_doc(doc)
            self.dataset_vectors.append(vector)

    def _vectorize_doc(self, tokens: List[str]) -> Dict[str, float]:
        """Vectorizes a list of tokens using TF-IDF representation"""
        # TF counts
        tf = {}
        for token in tokens:
            if token in self.vocab:
                tf[token] = tf.get(token, 0) + 1
        
        # TF-IDF
        vector = {}
        for token, count in tf.items():
            vector[token] = count * self.idf[token]
            
        # Normalize vector (L2 norm)
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
        query_vector = self._vectorize_doc(tokens)
        
        best_sim = -1.0
        best_index = -1
        
        # Find the most similar document in the dataset
        for idx, doc_vector in enumerate(self.dataset_vectors):
            sim = self._cosine_similarity(query_vector, doc_vector)
            if sim > best_sim:
                best_sim = sim
                best_index = idx
                
        if best_index != -1 and best_sim > 0.05:
            matched = DATASET[best_index]
            return {
                "role": matched["role"],
                "skills": [s.strip() for s in matched["skills"].split(",") if s.strip()],
                "domain": matched["domain"],
                "experience": matched["experience"],
                "confidence": best_sim
            }
        else:
            # Fallback if no similarity or empty text
            return {
                "role": "Software Developer",
                "skills": [],
                "domain": "Software Development",
                "experience": "Mid",
                "confidence": 0.0
            }

# Quick test
model = NLPModel()
model.train(DATASET)

test_queries = [
    "I developed a web app using React and JavaScript, worked on UI design",
    "SQL reporting and data analytics with Power BI dashboards",
    "ML model training with TensorFlow and Python code",
    "cloud migration to AWS and Linux server config"
]

for q in test_queries:
    res = model.predict(q)
    print(f"Query: '{q}'\nPrediction: {res}\n")
