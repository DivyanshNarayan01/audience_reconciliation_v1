#!/usr/bin/env python3
"""
Attendee Company Reconciliation

Matches event attendees to a master company list using deterministic rules
and optional LLM assistance for fuzzy matching.

Usage:
    python src/reconcile.py
"""

import os
import re
import pandas as pd
import yaml
from pathlib import Path
from dotenv import load_dotenv
from rapidfuzz import fuzz
import tldextract
import google.generativeai as genai

# Load environment variables
load_dotenv()

class CompanyReconciler:
    def __init__(self, config_path=".config"):
        """Initialize the reconciler with configuration."""
        self.config = self._load_config(config_path)
        self.data = {}
        self._setup_gemini()
        
    def _load_config(self, config_path):
        """Load configuration from YAML file."""
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def _setup_gemini(self):
        """Setup Gemini API if enabled."""
        self.gemini_enabled = False
        if self.config.get('llm', {}).get('provider') == 'gemini':
            api_key = os.getenv('GEMINI_API_KEY')
            if api_key:
                try:
                    genai.configure(api_key=api_key)
                    self.model = genai.GenerativeModel('gemini-1.5-flash')
                    self.gemini_enabled = True
                    print("Gemini API initialized successfully")
                except Exception as e:
                    print(f"Warning: Could not initialize Gemini API: {e}")
            else:
                print("Warning: GEMINI_API_KEY not found in environment variables")
    
    def _normalize_name(self, name):
        """Improved normalize company name by removing legal suffixes and special chars."""
        if not name:
            return ''
        
        name = str(name).lower()
        # Remove special characters except spaces and dots (for .com, .net, etc)
        name = re.sub(r'[^a-z0-9 .]', '', name)
        
        # Remove common legal suffixes but keep core identifiers like .com
        suffixes = r'\b(ltd|limited|plc|inc|llc|llp|pvt|private|co|company|corp|corporation|gmbh|sarl|sa|bv|oy|ab|as|sas|spa|ag|nv|bvba|oyj|pte|kft|aps|sro|sp zoo|holdings|group|international)\b'
        name = re.sub(suffixes, '', name)
        
        # Handle common company variations
        name = re.sub(r'\btech(nology|nologies)?\b', 'tech', name)
        name = re.sub(r'\bsystems?\b', 'systems', name)
        name = re.sub(r'\bsolutions?\b', 'solutions', name)
        
        # Normalize whitespace and dots
        name = re.sub(r'\.+', '.', name)  # Multiple dots to single dot
        name = re.sub(r'\s+', ' ', name.strip())
        name = re.sub(r'\s*\.\s*', '.', name)  # Spaces around dots
        
        return name.strip()
    
    def _extract_domain(self, email):
        """Extract domain from email address."""
        if not email or '@' not in email:
            return ''
        return email.split('@')[1].lower()
    
    def load_data(self):
        """Load all CSV data files."""
        data_dir = self.config['data_dir']
        files = self.config['files']
        
        # Load attendees
        self.data['attendees'] = pd.read_csv(f"{data_dir}/{files['attendees']}")
        self.data['attendees']['normalized_name'] = self.data['attendees']['attendee_company_name'].apply(self._normalize_name)
        self.data['attendees']['domain'] = self.data['attendees']['attendee_email_address'].apply(self._extract_domain)
        
        # Load master company list
        self.data['master'] = pd.read_csv(f"{data_dir}/{files['master']}")
        self.data['master']['normalized_company'] = self.data['master']['company_name'].apply(self._normalize_name)
        self.data['master']['normalized_parent'] = self.data['master']['parent_company_name'].apply(self._normalize_name)
        
        # Load historical reconciliation
        self.data['history'] = pd.read_csv(f"{data_dir}/{files['history']}")
        self.data['history']['normalized_company'] = self.data['history']['company_name'].apply(self._normalize_name)
        
        print(f"Loaded {len(self.data['attendees'])} attendees")
        print(f"Loaded {len(self.data['master'])} master companies")
        print(f"Loaded {len(self.data['history'])} historical records")
    
    def rule1_exact_company(self, attendee_row):
        """R1: Exact company name match (same country)."""
        attendee_name = attendee_row['normalized_name']
        attendee_country = attendee_row['attendee_country']
        
        # Find exact match in master list
        matches = self.data['master'][
            (self.data['master']['normalized_company'] == attendee_name) &
            (self.data['master']['company_country'] == attendee_country)
        ]
        
        if not matches.empty:
            match = matches.iloc[0]
            return {
                'company_name': match['company_name'],
                'parent_company_name': match['parent_company_name'],
                'company_country': match['company_country'],
                'match_confidence': 100,
                'logic_used': 'R1_exact_company_country'
            }
        return None
    
    def rule2_exact_parent(self, attendee_row):
        """R2: Exact parent company name match (same country)."""
        attendee_name = attendee_row['normalized_name']
        attendee_country = attendee_row['attendee_country']
        
        # Find exact match to parent company
        matches = self.data['master'][
            (self.data['master']['normalized_parent'] == attendee_name) &
            (self.data['master']['company_country'] == attendee_country)
        ]
        
        if not matches.empty:
            match = matches.iloc[0]
            return {
                'company_name': match['company_name'],
                'parent_company_name': match['parent_company_name'],
                'company_country': match['company_country'],
                'match_confidence': 95,
                'logic_used': 'R2_exact_parent_country'
            }
        return None
    
    def rule3_historical(self, attendee_row):
        """R3: Historical reconciliation lookup."""
        email = attendee_row['attendee_email_address']
        domain = attendee_row['domain']
        country = attendee_row['attendee_country']
        
        # R3a: Historical by email
        hist_matches = self.data['history'][
            (self.data['history']['attendee_email_address'] == email) &
            (self.data['history']['attendee_country'] == country)
        ]
        
        if not hist_matches.empty:
            hist_company = hist_matches.iloc[0]['company_name']
            # Find in master list
            master_matches = self.data['master'][
                (self.data['master']['company_name'] == hist_company) &
                (self.data['master']['company_country'] == country)
            ]
            
            if not master_matches.empty:
                match = master_matches.iloc[0]
                return {
                    'company_name': match['company_name'],
                    'parent_company_name': match['parent_company_name'],
                    'company_country': match['company_country'],
                    'match_confidence': 92,
                    'logic_used': 'R3a_hist_email_exact'
                }
        
        # R3b: Historical by domain (simplified - most recent)
        domain_matches = self.data['history'][
            self.data['history']['attendee_email_address'].str.contains(f'@{domain}') &
            (self.data['history']['attendee_country'] == country)
        ]
        
        if not domain_matches.empty:
            # Get most recent (last row for simplicity)
            hist_company = domain_matches.iloc[-1]['company_name']
            master_matches = self.data['master'][
                (self.data['master']['company_name'] == hist_company) &
                (self.data['master']['company_country'] == country)
            ]
            
            if not master_matches.empty:
                match = master_matches.iloc[0]
                return {
                    'company_name': match['company_name'],
                    'parent_company_name': match['parent_company_name'],
                    'company_country': match['company_country'],
                    'match_confidence': 90,
                    'logic_used': 'R3b_hist_domain_company'
                }
        
        return None
    
    def rule4_fuzzy_matching(self, attendee_row):
        """R4: Fuzzy matching within same country."""
        attendee_name = attendee_row['normalized_name']
        attendee_country = attendee_row['attendee_country']
        
        # Get companies in same country
        same_country = self.data['master'][
            self.data['master']['company_country'] == attendee_country
        ]
        
        best_match = None
        best_score = 0
        
        fuzzy_threshold = self.config['thresholds']['fuzzy_company']
        
        # Check company names
        for _, company in same_country.iterrows():
            score = fuzz.ratio(attendee_name, company['normalized_company'])
            if score >= fuzzy_threshold and score > best_score:
                confidence = min(score, self.config['confidence_caps']['r4_company'])
                best_match = {
                    'company_name': company['company_name'],
                    'parent_company_name': company['parent_company_name'],
                    'company_country': company['company_country'],
                    'match_confidence': confidence,
                    'logic_used': 'R4_fuzzy_company_validated'
                }
                best_score = score
        
        # Check parent names if no good company match
        if best_score < self.config['thresholds']['fuzzy_parent']:
            for _, company in same_country.iterrows():
                score = fuzz.ratio(attendee_name, company['normalized_parent'])
                if score >= self.config['thresholds']['fuzzy_parent'] and score > best_score:
                    confidence = min(score, self.config['confidence_caps']['r4_parent'])
                    best_match = {
                        'company_name': company['company_name'],
                        'parent_company_name': company['parent_company_name'],
                        'company_country': company['company_country'],
                        'match_confidence': confidence,
                        'logic_used': 'R4_fuzzy_parent_validated'
                    }
                    best_score = score
        
        return best_match
    
    def _get_gemini_suggestions(self, attendee_name, attendee_country, domain):
        """Get company name suggestions from Gemini with better context."""
        if not self.gemini_enabled:
            return []
        
        try:
            # Get ALL companies in same country for better context
            same_country_companies = self.data['master'][
                self.data['master']['company_country'] == attendee_country
            ]['company_name'].tolist()
            
            # Create better context with exact company names from our database
            company_context = ', '.join(same_country_companies[:15])  # Show more examples
            
            prompt = f"""
You are helping correct a misspelled company name to match our exact database.

Misspelled name: "{attendee_name}"
Country: "{attendee_country}"
Email domain: "{domain}"

Our database contains these EXACT company names for {attendee_country}:
{company_context}

Task: Suggest 5 possible corrections for "{attendee_name}" that might match our database entries above.
Focus on:
1. Simple typo corrections (missing/extra letters)
2. Common abbreviations or full names
3. Include exact suffixes like ".com Inc." if relevant
4. Consider the email domain "{domain}" as a hint

Return ONLY company names (no explanations), one per line:
"""
            
            # Generate with settings optimized for accuracy
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,  # Low temperature for consistent results
                    max_output_tokens=300
                )
            )
            suggestions = [line.strip() for line in response.text.split('\n') if line.strip()]
            return suggestions[:5]
            
        except Exception as e:
            print(f"Warning: Gemini API error: {e}")
            return []
    
    def rule4_gemini_assisted_matching(self, attendee_row):
        """R4: Gemini-assisted matching for complex cases."""
        attendee_name = attendee_row['attendee_company_name']  # Use original name for Gemini
        attendee_country = attendee_row['attendee_country']
        domain = attendee_row['domain']
        
        # First try Gemini if enabled
        if self.gemini_enabled:
            gemini_result = self._try_gemini_matching(attendee_row)
            if gemini_result:
                return gemini_result
        
        # Fall back to regular fuzzy matching
        fuzzy_result = self.rule4_fuzzy_matching(attendee_row)
        if fuzzy_result:
            return fuzzy_result
        
        return None
    
    def _try_gemini_matching(self, attendee_row):
        """Try Gemini matching first."""
        attendee_name = attendee_row['attendee_company_name']
        attendee_country = attendee_row['attendee_country']
        domain = attendee_row['domain']
        
        suggestions = self._get_gemini_suggestions(attendee_name, attendee_country, domain)
        if not suggestions:
            return None
        
        # Try to match suggestions against master list
        same_country = self.data['master'][
            self.data['master']['company_country'] == attendee_country
        ]
        
        best_match = None
        best_score = 0
        
        for suggestion in suggestions:
            normalized_suggestion = self._normalize_name(suggestion)
            
            # Check exact match first
            exact_matches = same_country[
                same_country['normalized_company'] == normalized_suggestion
            ]
            if not exact_matches.empty:
                match = exact_matches.iloc[0]
                return {
                    'company_name': match['company_name'],
                    'parent_company_name': match['parent_company_name'],
                    'company_country': match['company_country'],
                    'match_confidence': 94,  # High confidence for Gemini + exact match
                    'logic_used': 'R4_gemini_exact_match'
                }
            
            # Check fuzzy match against suggestion
            for _, company in same_country.iterrows():
                score = fuzz.ratio(normalized_suggestion, company['normalized_company'])
                if score >= 85 and score > best_score:  # Lower threshold for Gemini suggestions
                    confidence = min(score, 92)  # Cap confidence for Gemini fuzzy
                    best_match = {
                        'company_name': company['company_name'],
                        'parent_company_name': company['parent_company_name'],
                        'company_country': company['company_country'],
                        'match_confidence': confidence,
                        'logic_used': 'R4_gemini_fuzzy_match'
                    }
                    best_score = score
        
        return best_match
    
    def reconcile_attendee(self, attendee_row):
        """Apply all matching rules to a single attendee."""
        # Try rules in order
        for rule_func in [self.rule1_exact_company, self.rule2_exact_parent, 
                         self.rule3_historical, self.rule4_gemini_assisted_matching]:
            result = rule_func(attendee_row)
            if result:
                return result
        
        # No match found - get Gemini suggestions for transparency
        attendee_name = attendee_row['attendee_company_name']
        attendee_country = attendee_row['attendee_country']
        domain = attendee_row['domain']
        
        suggestions = self._get_gemini_suggestions(attendee_name, attendee_country, domain)
        suggestions_text = "; ".join(suggestions) if suggestions else "No suggestions"
        
        return {
            'company_name': None,
            'parent_company_name': None,
            'company_country': None,
            'match_confidence': 0,
            'logic_used': f'UNRESOLVED (Gemini suggestions: {suggestions_text})'
        }
    
    def reconcile_all(self):
        """Reconcile all attendees and return results."""
        results = []
        total = len(self.data['attendees'])
        
        for i, (_, attendee) in enumerate(self.data['attendees'].iterrows()):
            if i % 10 == 0:
                print(f"Processing {i+1}/{total} attendees...")
            
            match_result = self.reconcile_attendee(attendee)
            
            # Combine attendee info with match result
            result = {
                'attendee_email_address': attendee['attendee_email_address'],
                'attendee_company_name': attendee['attendee_company_name'],
                'attendee_country': attendee['attendee_country'],
                **match_result
            }
            results.append(result)
        
        return pd.DataFrame(results)
    
    def save_results(self, results_df):
        """Save results to output files."""
        output_dir = self.config['output_dir']
        os.makedirs(output_dir, exist_ok=True)
        
        output_files = self.config['output_files']
        
        # Save all results
        results_df.to_csv(f"{output_dir}/{output_files['final_results']}", index=False)
        print(f"Saved results to {output_dir}/{output_files['final_results']}")
        
        # Save unresolved cases
        unresolved = results_df[results_df['logic_used'] == 'UNRESOLVED']
        unresolved.to_csv(f"{output_dir}/{output_files['unresolved']}", index=False)
        print(f"Saved {len(unresolved)} unresolved cases to {output_dir}/{output_files['unresolved']}")
        
        # Create audit summary
        audit_summary = results_df.groupby(['logic_used', 'match_confidence']).size().reset_index(name='count')
        audit_summary.to_csv(f"{output_dir}/{output_files['audit_log']}", index=False)
        print(f"Saved audit log to {output_dir}/{output_files['audit_log']}")
        
        return results_df

def main():
    """Main execution function."""
    print("Starting Attendee-Company Reconciliation")
    
    # Initialize reconciler
    reconciler = CompanyReconciler()
    
    # Load data
    print("\nLoading data...")
    reconciler.load_data()
    
    # Run reconciliation
    print("\nRunning reconciliation...")
    results = reconciler.reconcile_all()
    
    # Display summary
    print(f"\nResults Summary:")
    summary = results['logic_used'].value_counts()
    for rule, count in summary.items():
        print(f"  {rule}: {count}")
    
    print(f"\nAverage confidence: {results[results['match_confidence'] > 0]['match_confidence'].mean():.1f}")
    
    # Save results
    print(f"\nSaving results...")
    reconciler.save_results(results)
    
    print("Reconciliation complete!")

if __name__ == "__main__":
    main()