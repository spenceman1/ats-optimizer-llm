import re
from typing import Dict, List, Tuple
from collections import Counter

class ResumeOptimizer:
    def __init__(self):
        self.max_content_length = 4000  # Estimated chars for one page
        self.max_bullets_per_role = 4
        self.min_bullets_per_role = 2
        
    def extract_job_keywords(self, job_description: str) -> List[str]:
        """Extract key skills and technologies from job description"""
        # Common technical skills and tools
        tech_patterns = [
            r'\b(Python|Java|JavaScript|React|Node\.?js|SQL|AWS|Azure|Docker|Kubernetes)\b',
            r'\b(Agile|Scrum|Project Management|Leadership|Analytics|Machine Learning)\b',
            r'\b([A-Z][a-z]+(?: [A-Z][a-z]+)*)\b',  # Capitalized terms
        ]
        
        keywords = set()
        job_lower = job_description.lower()
        
        # Extract technical terms
        for pattern in tech_patterns:
            matches = re.findall(pattern, job_description, re.IGNORECASE)
            keywords.update([match.lower() for match in matches])
        
        # Extract common business terms
        business_terms = [
            'leadership', 'management', 'strategy', 'analytics', 'optimization',
            'collaboration', 'communication', 'problem solving', 'innovation',
            'process improvement', 'customer service', 'sales', 'marketing'
        ]
        
        for term in business_terms:
            if term in job_lower:
                keywords.add(term)
        
        return list(keywords)
    
    def score_relevance(self, text: str, keywords: List[str]) -> float:
        """Score text relevance based on keyword matching"""
        if not text or not keywords:
            return 0.0
        
        text_lower = text.lower()
        matches = sum(1 for keyword in keywords if keyword.lower() in text_lower)
        return matches / len(keywords)
    
    def optimize_experience(self, experience: List[Dict], job_keywords: List[str]) -> List[Dict]:
        """Optimize professional experience for relevance and length"""
        if not experience:
            return experience
        
        optimized_experience = []
        
        for exp in experience:
            # Score the role's overall relevance
            role_text = f"{exp.get('role', '')} {exp.get('company', '')} {' '.join(exp.get('achievements', []))}"
            relevance_score = self.score_relevance(role_text, job_keywords)
            
            # Keep all roles but optimize achievements
            optimized_exp = exp.copy()
            achievements = exp.get('achievements', [])
            
            if achievements:
                # Score each achievement
                scored_achievements = []
                for achievement in achievements:
                    score = self.score_relevance(achievement, job_keywords)
                    scored_achievements.append((achievement, score))
                
                # Sort by relevance and keep top achievements
                scored_achievements.sort(key=lambda x: x[1], reverse=True)
                
                # Keep 2-4 most relevant achievements per role
                num_to_keep = min(self.max_bullets_per_role, 
                                max(self.min_bullets_per_role, len(scored_achievements)))
                
                optimized_exp['achievements'] = [
                    achievement for achievement, _ in scored_achievements[:num_to_keep]
                ]
            
            optimized_experience.append(optimized_exp)
        
        # Sort experiences by relevance (most recent + most relevant first)
        # Keep chronological order but may remove least relevant roles if needed
        return optimized_experience
    
    def optimize_skills(self, skills: List, job_keywords: List[str]) -> List[str]:
        """Filter skills to match job requirements"""
        if not skills:
            return []
        
        # Convert skills to strings
        skill_strings = []
        for skill in skills:
            if isinstance(skill, dict):
                skill_strings.append(skill.get('skill', ''))
            else:
                skill_strings.append(str(skill))
        
        # Score each skill based on job relevance
        scored_skills = []
        for skill in skill_strings:
            if skill.strip():
                relevance = self.score_relevance(skill, job_keywords)
                # Also give priority to skills that appear in job description
                job_text_lower = ' '.join(job_keywords).lower()
                if skill.lower() in job_text_lower:
                    relevance += 0.5
                scored_skills.append((skill, relevance))
        
        # Sort by relevance and take top skills
        scored_skills.sort(key=lambda x: x[1], reverse=True)
        
        # Keep top 15-20 most relevant skills
        return [skill for skill, _ in scored_skills[:20]]
    
    def optimize_projects(self, projects: List[Dict], job_keywords: List[str], max_projects: int = 3) -> List[Dict]:
        """Keep most relevant projects"""
        if not projects:
            return projects
        
        scored_projects = []
        for project in projects:
            project_text = f"{project.get('project_title', '')} {project.get('role', '')} {' '.join(project.get('achievements', []))}"
            relevance = self.score_relevance(project_text, job_keywords)
            scored_projects.append((project, relevance))
        
        # Sort by relevance and keep top projects
        scored_projects.sort(key=lambda x: x[1], reverse=True)
        
        optimized_projects = []
        for project, _ in scored_projects[:max_projects]:
            # Optimize project achievements
            optimized_proj = project.copy()
            achievements = project.get('achievements', [])
            
            if achievements:
                scored_achievements = [
                    (achievement, self.score_relevance(achievement, job_keywords))
                    for achievement in achievements
                ]
                scored_achievements.sort(key=lambda x: x[1], reverse=True)
                
                # Keep top 2-3 achievements per project
                optimized_proj['achievements'] = [
                    achievement for achievement, _ in scored_achievements[:3]
                ]
            
            optimized_projects.append(optimized_proj)
        
        return optimized_projects
    
    def estimate_content_length(self, structured_result: Dict) -> int:
        """Estimate the character count of the resume content"""
        total_chars = 0
        
        # Count characters in each section
        sections = ['name', 'email', 'phone', 'summary']
        for section in sections:
            if structured_result.get(section):
                total_chars += len(str(structured_result[section]))
        
        # Count experience
        for exp in structured_result.get('experience', []):
            total_chars += len(exp.get('role', '') + exp.get('company', ''))
            total_chars += sum(len(achievement) for achievement in exp.get('achievements', []))
        
        # Count projects
        for proj in structured_result.get('projects', []):
            total_chars += len(proj.get('project_title', '') + proj.get('role', ''))
            total_chars += sum(len(achievement) for achievement in proj.get('achievements', []))
        
        # Count skills
        skills = structured_result.get('skills', [])
        total_chars += sum(len(str(skill)) for skill in skills)
        
        return total_chars
    
    def optimize_resume(self, structured_result: Dict, job_description: str) -> Dict:
        """Main optimization function"""
        # Extract keywords from job description
        job_keywords = self.extract_job_keywords(job_description)
        
        # Create optimized copy
        optimized = structured_result.copy()
        
        # Optimize each section
        optimized['experience'] = self.optimize_experience(
            structured_result.get('experience', []), job_keywords
        )
        
        optimized['skills'] = self.optimize_skills(
            structured_result.get('skills', []), job_keywords
        )
        
        optimized['projects'] = self.optimize_projects(
            structured_result.get('projects', []), job_keywords
        )
        
        # Optimize volunteering (keep only most relevant)
        if structured_result.get('volunteering'):
            optimized['volunteering'] = self.optimize_projects(
                structured_result.get('volunteering', []), job_keywords, max_projects=2
            )
        
        # Check if we need further length optimization
        estimated_length = self.estimate_content_length(optimized)
        
        if estimated_length > self.max_content_length:
            # Further reduce content
            # Remove volunteering if still too long
            if optimized.get('volunteering'):
                optimized['volunteering'] = []
            
            # Reduce projects to top 2
            if len(optimized.get('projects', [])) > 2:
                optimized['projects'] = optimized['projects'][:2]
            
            # Reduce bullets per experience role
            for exp in optimized.get('experience', []):
                if len(exp.get('achievements', [])) > 3:
                    exp['achievements'] = exp['achievements'][:3]
        
        return optimized
