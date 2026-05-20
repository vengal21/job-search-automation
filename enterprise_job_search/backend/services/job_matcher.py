import logging
from typing import List, Dict, Any
from embeddings.chroma_client import vector_store
from services.ollama_client import OllamaClient
import json

logger = logging.getLogger(__name__)

MATCHING_SYSTEM_PROMPT = """
You are an expert AI Recruiter and ATS matching engine. 
Compare the resume summary and skills against the job description.
Identify missing key skills and generate a match score (0-100) and ATS score (0-100).
Provide recommendations for how the candidate can improve their resume for this job.
Output strictly valid JSON:
{
  "match_score": 85,
  "ats_score": 75,
  "missing_skills": ["List", "of", "skills"],
  "recommendations": ["Recommendation 1", "Recommendation 2"]
}
"""

class JobMatchingEngine:
    
    @staticmethod
    def match_jobs_semantic(resume_summary: str, resume_skills: List[str], top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Search for jobs in ChromaDB that semantically match the candidate's profile
        """
        query_text = f"Candidate Summary: {resume_summary}\nKey Skills: {', '.join(resume_skills)}"
        
        try:
            results = vector_store.search_jobs(query=query_text, n_results=top_k)
            
            # Format results
            matches = []
            if results and results.get("ids") and len(results["ids"]) > 0:
                for i in range(len(results["ids"][0])):
                    job_id = results["ids"][0][i]
                    metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                    distance = results["distances"][0][i] if results.get("distances") else 0.0
                    
                    # Convert distance to a rough similarity percentage (assuming cosine distance)
                    similarity = max(0, min(100, int((1.0 - distance) * 100)))
                    
                    matches.append({
                        "job_id": job_id,
                        "metadata": metadata,
                        "semantic_similarity": similarity
                    })
            return matches
        except Exception as e:
            logger.error(f"Semantic job search failed: {e}")
            return []

    @staticmethod
    def generate_detailed_match(resume_text: str, job_description: str) -> Dict[str, Any]:
        """
        Use Llama 3 to do a deep comparative analysis between a resume and a job description.
        Returns ATS score, Match score, missing skills, and recommendations.
        """
        prompt = f"RESUME:\n{resume_text}\n\nJOB DESCRIPTION:\n{job_description}"
        
        try:
            analysis = OllamaClient.generate_json(prompt=prompt, system=MATCHING_SYSTEM_PROMPT)
            return analysis
        except Exception as e:
            logger.error(f"Detailed LLM match failed: {e}")
            return {
                "match_score": 0,
                "ats_score": 0,
                "missing_skills": [],
                "recommendations": ["Analysis failed"]
            }
