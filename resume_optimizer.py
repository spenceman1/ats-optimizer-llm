import re
from typing import Dict, List, Tuple
from collections import Counter

class ResumeOptimizer:
    def __init__(self):
        self.max_content_length = 4200  # More realistic estimate for one page
        self.max_bullets_per_role = 5  # Increased from 4
        self.min_bullets_per_role = 2
        
    def extract_job_keywords(self, job_description: str) -> List[str]:
        """Extract key skills and technologies from job description"""
        keywords = set()
        job_lower = job_description.lower()
        
        # Direct string matching for specific tools mentioned in the job requirements
        priority_tools = [
            'smartsheet', 'ms project', 'microsoft project', 'project',
            'atlassian', 'jira', 'confluence', 'bitbucket',
            'python', 'c++', 'javascript', 'java', 'c#',
            'agile', 'scrum', 'kanban',
            'project management', 'management',
            'git', 'github', 'gitlab',
            'software development', 'software', 'development', 'programming',
            'collaboration', 'cross-functional', 'team',
            'leadership', 'lead', 'manage',
            'communication', 'excel', 'office',
            'google workspace', 'google', 'slack', 'teams'
        ]
        
        # Check for each tool in the job description
        for tool in priority_tools:
            if tool in job_lower:
                keywords.add(tool)
        
        # Add the specific job requirements you mentioned
        job_specific_keywords = [
            'smartsheet', 'ms project', 'atlassian', 'python', 'c++', 'c',
            'project management', 'software', 'development', 'team'
        ]
        keywords.update(job_specific_keywords)
        
        # Remove any long phrases (keep only single words or short phrases)
        filtered_keywords = []
        for keyword in keywords:
            if len(keyword.split()) <= 3 and len(keyword) <= 25:  # Max 3 words, 25 chars
                filtered_keywords.append(keyword)
        
        return filtered_keywords
    
    def score_relevance(self, text: str, keywords: List[str]) -> float:
        """Score text relevance based on keyword matching"""
        if not text or not keywords:
            return 0.0
        
        text_lower = text.lower()
        matches = sum(1 for keyword in keywords if keyword.lower() in text_lower)
        score = matches / len(keywords)
        
        return score
    
    def enhance_achievements_from_source(self, experience: List[Dict], resume_text: str, linkedin_text: str) -> List[Dict]:
        """Extract additional achievements from source documents if roles have too few bullets"""
        if not resume_text and not linkedin_text:
            return experience
        
        enhanced_experience = []
        source_text = f"{resume_text} {linkedin_text}".lower()
        
        for exp in experience:
            enhanced_exp = exp.copy()
            achievements = exp.get('achievements', [])
            
            # If role has fewer than 3 bullets, try to extract more from source
            if len(achievements) < 3:
                role = exp.get('role', '').lower()
                company = exp.get('company', '').lower()
                
                # Look for additional bullet points in source text
                additional_bullets = []
                
                # Simple patterns to find achievement-like sentences
                sentences = re.split(r'[.!?]', source_text)
                for sentence in sentences:
                    sentence = sentence.strip()
                    if len(sentence) > 20 and len(sentence) < 150:  # Reasonable bullet length
                        # Check if sentence relates to this role/company
                        if (role and role in sentence) or (company and company in sentence):
                            # Check if it looks like an achievement
                            achievement_indicators = ['led', 'managed', 'created', 'developed', 'improved', 'increased', 'delivered', 'coordinated', 'built', 'designed']
                            if any(indicator in sentence for indicator in achievement_indicators):
                                # Clean up the sentence
                                clean_sentence = sentence.strip(' -•*')
                                if clean_sentence and clean_sentence not in achievements:
                                    additional_bullets.append(clean_sentence.capitalize())
                
                # Add up to 2 additional bullets
                for bullet in additional_bullets[:2]:
                    if len(achievements) < 5:  # Don't exceed 5 total
                        achievements.append(bullet)
                
                enhanced_exp['achievements'] = achievements
            
            enhanced_experience.append(enhanced_exp)
        
        return enhanced_experience
    
    def optimize_experience(self, experience: List[Dict], job_keywords: List[str]) -> List[Dict]:
        """Optimize professional experience for relevance and length"""
        if not experience:
            return experience
        
        optimized_experience = []
        
        for i, exp in enumerate(experience):
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
                    # Boost score for quantifiable achievements
                    if any(char.isdigit() for char in achievement):
                        score += 0.3
                    # Boost score for impact words
                    impact_words = ['led', 'managed', 'increased', 'decreased', 'improved', 'streamlined', 'optimized', 'delivered', 'launched', 'coordinated', 'built', 'created', 'developed', 'directed']
                    if any(word in achievement.lower() for word in impact_words):
                        score += 0.2
                    scored_achievements.append((achievement, score))
                
                # Sort by relevance and keep top achievements
                scored_achievements.sort(key=lambda x: x[1], reverse=True)
                
                # Be more generous with bullet allocation
                # Most recent roles (first 2) get more bullets
                if i < 2:  # Top 2 most recent roles
                    max_achievements = 5
                elif relevance_score > 0.3:  # Highly relevant roles
                    max_achievements = 4
                else:  # Other roles
                    max_achievements = 3
                
                # Always keep at least 2 bullets if available
                min_achievements = min(2, len(scored_achievements))
                num_to_keep = min(max_achievements, max(min_achievements, len(scored_achievements)))
                
                optimized_exp['achievements'] = [
                    achievement for achievement, _ in scored_achievements[:num_to_keep]
                ]
            
            optimized_experience.append(optimized_exp)
        
        return optimized_experience
    
    def optimize_skills(self, skills: List, job_keywords: List[str]) -> List[str]:
        """Filter skills to match job requirements and remove irrelevant ones"""
        if not skills:
            return []
        
        # Convert skills to strings
        skill_strings = [str(skill.get('skill', skill) if isinstance(skill, dict) else skill).strip() 
                        for skill in skills if skill]
        
        # Define high-priority skills for software/PM roles
        always_include = [
            'agile project management', 'jira', 'airtable', 'google workspace', 'microsoft office'
        ]
        
        # Define skills to completely remove for software development roles
        skills_to_remove = [
            'adobe creative cloud', 'unity', 'unreal engine', 'miro',
            'photoshop', 'illustrator', 'after effects'
        ]
        
        # Priority software and PM tools
        priority_skills = [
            'smartsheet', 'ms project', 'microsoft project', 'atlassian', 'jira', 'confluence',
            'python', 'c++', 'javascript', 'git', 'github', 'agile', 'scrum',
            'project management', 'google workspace', 'microsoft office', 'excel', 'airtable'
        ]
        
        filtered_skills = []
        
        for skill in skill_strings:
            skill_lower = skill.lower()
            
            # Skip empty skills
            if not skill_lower:
                continue
            
            # Remove creative tools completely
            if any(remove_skill in skill_lower for remove_skill in skills_to_remove):
                continue
            
            # Always include certain skills
            if any(include_skill in skill_lower for include_skill in always_include):
                filtered_skills.append(skill)
                continue
            
            # Include priority skills
            if any(priority_skill in skill_lower for priority_skill in priority_skills):
                filtered_skills.append(skill)
                continue
            
            # Include if it matches job keywords
            if any(keyword in skill_lower for keyword in job_keywords):
                filtered_skills.append(skill)
                continue
            
            # Include general office/collaboration tools
            office_collab = ['slack', 'teams', 'office', 'workspace', 'excel']
            if any(tool in skill_lower for tool in office_collab):
                filtered_skills.append(skill)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_skills = []
        for skill in filtered_skills:
            if skill.lower() not in seen:
                seen.add(skill.lower())
                unique_skills.append(skill)
        
        return unique_skills[:12]  # Limit to top 12 skills
    
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
    
    def optimize_resume(self, structured_result: Dict, job_description: str, resume_text: str = "", linkedin_text: str = "") -> Dict:
        """Main optimization function"""
        # Extract keywords from job description
        job_keywords = self.extract_job_keywords(job_description)
        
        # Create optimized copy
        optimized = structured_result.copy()
        
        # First, try to enhance achievements from source documents
        if resume_text or linkedin_text:
            optimized['experience'] = self.enhance_achievements_from_source(
                optimized.get('experience', []), resume_text, linkedin_text
            )
        
        # Then optimize each section
        optimized['experience'] = self.optimize_experience(
            optimized.get('experience', []), job_keywords
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
        
        # Check if we need length optimization (be less aggressive initially)
        estimated_length = self.estimate_content_length(optimized)
        
        # Only reduce if significantly over limit
        if estimated_length > self.max_content_length * 1.2:  # 20% buffer before reducing
            
            # Step 1: Remove volunteering if too long
            if optimized.get('volunteering'):
                optimized['volunteering'] = []
                estimated_length = self.estimate_content_length(optimized)
            
            # Step 2: If still too long, reduce projects to top 2
            if estimated_length > self.max_content_length and len(optimized.get('projects', [])) > 2:
                optimized['projects'] = optimized['projects'][:2]
                estimated_length = self.estimate_content_length(optimized)
            
            # Step 3: Only as last resort, reduce bullets per role
            if estimated_length > self.max_content_length:
                for exp in optimized.get('experience', []):
                    if len(exp.get('achievements', [])) > 3:
                        exp['achievements'] = exp['achievements'][:3]
                estimated_length = self.estimate_content_length(optimized)
            
            # Step 4: Final resort - limit to top 4 roles
            if estimated_length > self.max_content_length * 1.3:
                experiences = optimized.get('experience', [])
                if len(experiences) > 4:
                    optimized['experience'] = experiences[:4]
        
        return optimized