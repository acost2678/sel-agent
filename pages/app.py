# VERSION 11.0: Enhanced with Streaming, Memory, Rate Limiting, Usage Tracking & Caching
import streamlit as st
import anthropic
import os
import docx
from dotenv import load_dotenv
import io
import markdown2
from fpdf import FPDF
import json
from pptx import Presentation
from PyPDF2 import PdfReader
from datetime import datetime, timedelta
from collections import defaultdict
import time

# This must be the first Streamlit command in your script
if not st.session_state.get("password_correct", False):
    st.switch_page("login.py")

# --- API CONFIGURATION ---
try:
    api_key = st.secrets["ANTHROPIC_API_KEY"]
    client = anthropic.Anthropic(api_key=api_key)
    MODEL_NAME = "claude-sonnet-4-5-20250929"
except KeyError:
    st.error("🔴 ANTHROPIC_API_KEY not found. Please add it to your Streamlit Secrets.")
    st.stop()
except Exception as e:
    st.error(f"🔴 An error occurred during API configuration: {e}")
    st.stop()

# --- INITIAL SETUP ---
st.set_page_config(page_title="SEL Integration Agent", page_icon="🧠", layout="wide")

# --- Initialize Session State ---
SESSION_STATE_DEFAULTS = {
    "ai_response": "", "response_title": "", "student_materials": "",
    "differentiation_response": "", "parent_email": "", "scenario": "",
    "conversation_history": [], "training_module": "", "training_scenario": "",
    "training_feedback": "", "check_in_questions": "", "strategy_response": "",
    # New: Usage tracking
    "total_tokens_used": 0,
    "total_api_calls": 0,
    "session_start_time": datetime.now(),
    "api_call_times": [],
    "conversation_memory": [],
    # New: Streaming control
    "use_streaming": True,
    # New: Cost tracking
    "estimated_cost": 0.0
}
for key, default_value in SESSION_STATE_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default_value

# --- CONSTANTS & OTHER SETUP ---
GRADE_LEVELS = ["Kindergarten", "1st Grade", "2nd Grade", "3rd Grade", "4th Grade", "5th Grade", 
                "6th Grade", "7th Grade", "8th Grade", "9th Grade", "10th Grade", "11th Grade", "12th Grade"]
SUBJECTS = ["Science", "History", "English Language Arts", "Mathematics", "Art", "Music"]
COMPETENCIES = {
    "Self-Awareness": ["Identifying Emotions", "Self-Perception", "Recognizing Strengths", "Self-Confidence", "Self-Efficacy"],
    "Self-Management": ["Impulse Control", "Stress Management", "Self-Discipline", "Self-Motivation", "Goal-Setting", "Organizational Skills"],
    "Social Awareness": ["Perspective-Taking", "Empathy", "Appreciating Diversity", "Respect for Others"],
    "Relationship Skills": ["Communication", "Social Engagement", "Building Relationships", "Teamwork", "Conflict Resolution"],
    "Responsible Decision-Making": ["Identifying Problems", "Analyzing Situations", "Solving Problems", "Evaluating", "Reflecting", "Ethical Responsibility"]
}
CASEL_COMPETENCIES = list(COMPETENCIES.keys())

# API Cost Constants (per million tokens)
INPUT_COST_PER_MTK = 3.00  # $3 per million input tokens
OUTPUT_COST_PER_MTK = 15.00  # $15 per million output tokens
CACHE_WRITE_COST_PER_MTK = 3.75  # $3.75 per million tokens for cache writes
CACHE_READ_COST_PER_MTK = 0.30  # $0.30 per million tokens for cache reads

# Rate limiting constants
MAX_CALLS_PER_MINUTE = 50
MAX_CALLS_PER_HOUR = 1000

# --- RATE LIMITING ---
class RateLimiter:
    """Simple rate limiter to prevent API abuse"""
    
    @staticmethod
    def check_rate_limit():
        """Check if we're within rate limits"""
        current_time = datetime.now()
        
        # Clean old timestamps (older than 1 hour)
        st.session_state.api_call_times = [
            t for t in st.session_state.api_call_times 
            if current_time - t < timedelta(hours=1)
        ]
        
        # Check per-minute limit
        recent_calls = [
            t for t in st.session_state.api_call_times 
            if current_time - t < timedelta(minutes=1)
        ]
        if len(recent_calls) >= MAX_CALLS_PER_MINUTE:
            return False, f"Rate limit exceeded: Maximum {MAX_CALLS_PER_MINUTE} calls per minute"
        
        # Check per-hour limit
        if len(st.session_state.api_call_times) >= MAX_CALLS_PER_HOUR:
            return False, f"Rate limit exceeded: Maximum {MAX_CALLS_PER_HOUR} calls per hour"
        
        return True, "OK"
    
    @staticmethod
    def record_api_call():
        """Record an API call timestamp"""
        st.session_state.api_call_times.append(datetime.now())
        st.session_state.total_api_calls += 1

# --- USAGE TRACKING ---
class UsageTracker:
    """Track API usage and costs"""
    
    @staticmethod
    def update_usage(input_tokens, output_tokens, cache_creation_tokens=0, cache_read_tokens=0):
        """Update token usage and cost estimates"""
        # Update token counts
        total_tokens = input_tokens + output_tokens
        st.session_state.total_tokens_used += total_tokens
        
        # Calculate costs
        input_cost = (input_tokens / 1_000_000) * INPUT_COST_PER_MTK
        output_cost = (output_tokens / 1_000_000) * OUTPUT_COST_PER_MTK
        cache_write_cost = (cache_creation_tokens / 1_000_000) * CACHE_WRITE_COST_PER_MTK
        cache_read_cost = (cache_read_tokens / 1_000_000) * CACHE_READ_COST_PER_MTK
        
        total_cost = input_cost + output_cost + cache_write_cost + cache_read_cost
        st.session_state.estimated_cost += total_cost
    
    @staticmethod
    def get_usage_summary():
        """Get a formatted usage summary"""
        session_duration = datetime.now() - st.session_state.session_start_time
        hours = session_duration.total_seconds() / 3600
        
        return {
            "total_calls": st.session_state.total_api_calls,
            "total_tokens": st.session_state.total_tokens_used,
            "estimated_cost": st.session_state.estimated_cost,
            "session_duration": session_duration,
            "calls_per_hour": st.session_state.total_api_calls / hours if hours > 0 else 0
        }

# --- CONVERSATION MEMORY ---
class ConversationMemory:
    """Manage conversation context and memory"""
    
    @staticmethod
    def add_to_memory(role, content, metadata=None):
        """Add a message to conversation memory"""
        memory_entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        st.session_state.conversation_memory.append(memory_entry)
        
        # Keep only last 20 exchanges to manage context window
        if len(st.session_state.conversation_memory) > 40:  # 20 exchanges = 40 messages
            st.session_state.conversation_memory = st.session_state.conversation_memory[-40:]
    
    @staticmethod
    def get_relevant_context(current_topic, max_messages=10):
        """Get relevant conversation history for context"""
        # For now, return most recent messages
        # Could be enhanced with semantic search in the future
        return st.session_state.conversation_memory[-max_messages:]
    
    @staticmethod
    def format_context_for_prompt():
        """Format memory as context string for prompts"""
        if not st.session_state.conversation_memory:
            return ""
        
        context_parts = ["Previous conversation context:"]
        for entry in st.session_state.conversation_memory[-10:]:  # Last 5 exchanges
            role = entry['role']
            content = entry['content'][:200]  # Truncate long content
            context_parts.append(f"{role}: {content}...")
        
        return "\n".join(context_parts)

# --- HELPER FUNCTIONS ---
def read_document(uploaded_file):
    """Read content from various document formats"""
    file_extension = os.path.splitext(uploaded_file.name)[1].lower()
    file_bytes = io.BytesIO(uploaded_file.read())
    text_content = ""
    try:
        if file_extension == ".docx":
            doc = docx.Document(file_bytes)
            text_content = "\n".join([para.text for para in doc.paragraphs])
        elif file_extension == ".pptx":
            prs = Presentation(file_bytes)
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        text_content += shape.text + "\n"
        elif file_extension == ".pdf":
            reader = PdfReader(file_bytes)
            for page in reader.pages:
                text_content += page.extract_text() + "\n"
        elif file_extension == ".txt":
            text_content = file_bytes.read().decode("utf-8")
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return None
    return text_content

def create_docx(text):
    """Create a Word document from markdown text"""
    doc = docx.Document()
    doc.add_heading('SEL Integration Plan', 0)
    for line in text.split('\n'):
        if line.startswith('### '): 
            doc.add_heading(line.lstrip('### '), level=3)
        elif line.startswith('## '): 
            doc.add_heading(line.lstrip('## '), level=2)
        elif line.startswith('# '): 
            doc.add_heading(line.lstrip('# '), level=1)
        else: 
            doc.add_paragraph(line)
    docx_file = io.BytesIO()
    doc.save(docx_file)
    docx_file.seek(0)
    return docx_file

def call_claude_streaming(prompt, max_tokens=4096, temperature=1.0, use_cache=True):
    """
    Call Claude API with streaming and display response in real-time
    
    Args:
        prompt: The user prompt to send
        max_tokens: Maximum tokens for response
        temperature: Temperature for response generation (0-1)
        use_cache: Whether to use prompt caching
    
    Returns:
        str: The complete response text
    """
    # Check rate limit
    can_proceed, message = RateLimiter.check_rate_limit()
    if not can_proceed:
        st.error(f"⚠️ {message}. Please wait a moment.")
        return None
    
    try:
        # Prepare messages with optional caching
        system_content = [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"} if use_cache else None
            }
        ]
        
        # Create placeholder for streaming
        response_placeholder = st.empty()
        full_response = ""
        
        # Record API call
        RateLimiter.record_api_call()
        
        # Stream the response
        with client.messages.stream(
            model=MODEL_NAME,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_content,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            for text in stream.text_stream:
                full_response += text
                response_placeholder.markdown(full_response + "▌")
        
        # Final update without cursor
        response_placeholder.markdown(full_response)
        
        # Track usage
        usage = stream.get_final_message().usage
        UsageTracker.update_usage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_creation_tokens=getattr(usage, 'cache_creation_input_tokens', 0),
            cache_read_tokens=getattr(usage, 'cache_read_input_tokens', 0)
        )
        
        # Add to conversation memory
        ConversationMemory.add_to_memory("assistant", full_response)
        
        return full_response
        
    except anthropic.APIError as e:
        st.error(f"API Error: {e}")
        return None
    except Exception as e:
        st.error(f"Unexpected error: {e}")
        return None

def call_claude(prompt, max_tokens=4096, temperature=1.0, use_cache=True, stream=None):
    """
    Unified function to call Claude API with proper error handling
    Supports both streaming and non-streaming modes
    
    Args:
        prompt: The user prompt to send
        max_tokens: Maximum tokens for response
        temperature: Temperature for response generation (0-1)
        use_cache: Whether to use prompt caching for the system prompt
        stream: If True, use streaming; if False, don't; if None, use session default
    
    Returns:
        str: The response text from Claude
    """
    # Determine if we should stream
    should_stream = stream if stream is not None else st.session_state.use_streaming
    
    if should_stream:
        return call_claude_streaming(prompt, max_tokens, temperature, use_cache)
    
    # Non-streaming mode
    # Check rate limit
    can_proceed, message = RateLimiter.check_rate_limit()
    if not can_proceed:
        st.error(f"⚠️ {message}. Please wait a moment.")
        return None
    
    try:
        # Prepare system message with optional caching
        system_content = [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"} if use_cache else None
            }
        ]
        
        # Record API call
        RateLimiter.record_api_call()
        
        # Make API call
        message = client.messages.create(
            model=MODEL_NAME,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_content,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = message.content[0].text
        
        # Track usage
        UsageTracker.update_usage(
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            cache_creation_tokens=getattr(message.usage, 'cache_creation_input_tokens', 0),
            cache_read_tokens=getattr(message.usage, 'cache_read_input_tokens', 0)
        )
        
        # Add to conversation memory
        ConversationMemory.add_to_memory("assistant", response_text)
        
        return response_text
        
    except anthropic.APIError as e:
        st.error(f"API Error: {e}")
        return None
    except Exception as e:
        st.error(f"Unexpected error: {e}")
        return None

# --- PROMPTS (OPTIMIZED FOR CLAUDE SONNET 4.5) ---
SYSTEM_PROMPT = """
You are an expert SEL (Social-Emotional Learning) consultant supporting K–12 educators. Your guidance is practical, evidence-based, and grounded in research from CASEL, ASCA, and peer-reviewed educational psychology journals.

Core Directives:
- All primary recommendations MUST follow this exact four-part Markdown format:
  **Overview:** Brief definition or contextual framing (1-2 sentences).
  **Evidence Summary:** What research demonstrates, including study types and key findings (2-4 sentences). Explicitly reference evidence types (e.g., "A meta-analysis of over 200 school-based programs...", "Consistent with developmental research...", "Validated through RCTs...").
  **Implementation Example:** A concrete classroom application with 3-5 actionable steps.
  **Measurement/Outcome:** Observable indicators of success and progress tracking methods (2-3 measurable criteria).
- Link strategies to specific CASEL competencies.
- Maintain a professional, compassionate, data-driven tone.
- Prioritize meta-analyses and systematic reviews over single studies.
"""

def get_analysis_prompt(lesson_plan_text, standard="", competency="", skill=""):
    focus_instruction = ""
    if competency and skill:
        focus_instruction = f"The user has requested specific focus on the CASEL competency of **{competency}**, emphasizing the skill of **{skill}**. Prioritize this focus in your analysis."
    
    standard_instruction = ""
    if standard and standard.strip():
        standard_instruction = f"All suggestions must align with this educational standard: '{standard.strip()}'."

    # Add conversation context if available
    context = ConversationMemory.format_context_for_prompt()
    context_section = f"\n\n{context}\n" if context else ""

    return f"""
{context_section}

An educator has submitted this lesson plan for SEL integration analysis:

**Lesson Plan:**
---
{lesson_plan_text}
---

**Task:**
1. Analyze the lesson to identify the strongest opportunity for SEL integration.
2. Provide ONE comprehensive, high-impact SEL strategy recommendation.
3. Follow the mandatory four-part format from the system prompt.

{focus_instruction}
{standard_instruction}
"""

def get_creation_prompt(grade_level, subject, topic, competency="", skill=""):
    focus_instruction = ""
    if competency and skill:
        focus_instruction = f"The lesson's primary SEL focus must be **{competency}**, specifically developing **{skill}**."
    
    context = ConversationMemory.format_context_for_prompt()
    context_section = f"\n\n{context}\n" if context else ""
    
    return f"""
{context_section}

Create a complete, SEL-integrated lesson plan with these specifications:
- **Grade Level:** {grade_level}
- **Subject:** {subject}
- **Topic:** {topic}
- **SEL Focus:** {focus_instruction if focus_instruction else "Balanced approach across CASEL competencies"}

**Requirements:**
1. Start with a "Pedagogical Rationale" (2-3 sentences) explaining the evidence behind your primary SEL activity.
2. Generate a complete lesson plan in Markdown with:
   - Learning Objectives (Content + SEL, observable behaviors)
   - Key Vocabulary (Content + SEL terms)
   - Materials list
   - Lesson Sequence (Hook → I Do → We Do → You Do → Assessment → Closing)
   - Detailed SEL Alignment section

Follow an "I Do, We Do, You Do" instructional model.
"""

def get_strategy_prompt(situation):
    context = ConversationMemory.format_context_for_prompt()
    context_section = f"\n\n{context}\n" if context else ""
    
    return f"""
{context_section}

A teacher needs an immediate, evidence-based strategy for this situation:

**Situation:** "{situation}"

**Task:**
Provide ONE quick, actionable strategy using this format:
- **Strategy Name:** (e.g., "Mindful Minute")
- **Evidence Rationale:** (1-2 sentences on research basis)
- **Actionable Steps:** (2-3 immediate steps)
- **Expected Outcome:** (1 sentence on observable results)
"""

def get_student_materials_prompt(lesson_plan_output):
    return f"""
You are an instructional designer. Based on this lesson plan, create student-facing materials in Markdown format:

**Lesson Plan:**
---
{lesson_plan_output}
---

**Generate:**
### 🎟️ Exit Ticket
(2-3 reflective questions)

### 🗣️ Think-Pair-Share Prompts
(2-3 discussion questions)

### ✍️ Journal Starters
(2-3 reflective prompts)

### 📄 Practice Worksheet
(Simple printable worksheet/graphic organizer)
"""

def get_differentiation_prompt(lesson_plan_output):
    return f"""
You are an expert in instructional differentiation. Based on this lesson, provide evidence-based strategies in Markdown:

**Lesson Plan:**
---
{lesson_plan_output}
---

**Structure:**
### 📉 Scaffold Support (Struggling Learners)
### ⬆️ Extension Activities (Advanced Learners)
### 🌐 ELL Support
"""

def get_scenario_prompt(competency, skill, grade_level):
    return f"""
Generate a brief, relatable school scenario for a {grade_level} student requiring use of the SEL competency **{competency}** (skill: **{skill}**).

Present in second person ('You are...'), ending with a question. Keep it to one paragraph.
"""

def get_feedback_prompt(scenario, history):
    formatted_history = "\n".join([f"- {entry['role']}: {entry['content']}" for entry in history])
    return f"""
You are a supportive SEL coach using a Socratic approach.

**Scenario:** {scenario}

**Conversation History:**
{formatted_history}

Ask ONE reflective question to deepen the student's thinking. Do not give advice. Keep it brief.
"""

def get_training_prompt(competency):
    return f"""
Create a professional development module on **{competency}** grounded in CASEL and evidence-based practices.

**Structure:**
## 🧠 Understanding {competency}
(Definition and importance, citing CASEL)

## 🛠️ Evidence-Based Classroom Strategies
For 2-3 key skills, provide:
### Skill: [Name]
* **The Strategy:** (Practical approach)
* **Evidence Base:** (Research summary)
* **Implementation Example:** (Step-by-step)
"""

def get_training_scenario_prompt(competency, training_module_text):
    return f"""
Create a brief, challenging classroom scenario to help a teacher practice **{competency}**.

End with an open-ended question. Generate ONLY the scenario and question.
"""

def get_training_feedback_prompt(competency, scenario, teacher_response):
    return f"""
You are a supportive SEL coach. The teacher is practicing **{competency}**.

**Scenario:** {scenario}
**Teacher's Response:** {teacher_response}

Provide constructive feedback: affirm a positive aspect, then ask one reflective question.
"""

def get_check_in_prompt(grade_level, tone):
    return f"""
Generate 3-4 creative, age-appropriate morning check-in questions for a **{grade_level}** class with a **{tone}** tone.

Format as a numbered list.
"""

def get_parent_email_prompt(lesson_plan):
    return f"""
Draft a professional, strengths-based email to parents based on this lesson plan:

**Lesson Plan:**
---
{lesson_plan}
---

**Structure:**
1. Subject Line (clear, informative)
2. What We're Learning (main SEL skill)
3. How We Practiced (brief activity description)
4. Connection at Home (simple conversation starter)
"""

def clear_generated_content():
    """Clear generated content from session state"""
    keys_to_clear = ["ai_response", "response_title", "student_materials", 
                     "differentiation_response", "parent_email"]
    for key in keys_to_clear:
        if key in st.session_state: 
            st.session_state[key] = ""

# --- ADMIN CHECK FUNCTION ---
def is_admin():
    """Check if current user is an admin"""
    try:
        # Get admin emails from secrets
        admin_emails = st.secrets.get("admin_emails", [])
        
        # If admin_emails is a string, convert to list
        if isinstance(admin_emails, str):
            admin_emails = [email.strip() for email in admin_emails.split(",")]
        
        # Get current user's email from session state (set during login)
        current_user = st.session_state.get("user_email", "")
        
        return current_user in admin_emails
    except:
        # If no admin_emails configured, default to showing all features
        return False

# --- SIDEBAR WITH SETTINGS AND USAGE ---
with st.sidebar:
    # Check if user is admin
    user_is_admin = is_admin()
    
    # Show different header based on role
    if user_is_admin:
        st.header("⚙️ Admin Dashboard")
        st.caption("👑 Administrator View")
    else:
        st.header("⚙️ Settings")
    
    st.markdown("---")
    
    # Streaming toggle (visible to all users)
    st.session_state.use_streaming = st.checkbox(
        "Enable Streaming Responses", 
        value=st.session_state.use_streaming,
        help="Show responses in real-time as they're generated"
    )
    
    # Conversation memory controls (visible to all users)
    st.markdown("---")
    st.subheader("🧠 Conversation Memory")
    memory_count = len(st.session_state.conversation_memory)
    if user_is_admin:
        st.metric("Messages in Memory", memory_count)
    else:
        st.caption(f"Messages stored: {memory_count}")
    
    if st.button("Clear Memory", help="Start fresh with a new conversation"):
        st.session_state.conversation_memory = []
        st.success("Memory cleared!")
        st.rerun()
    
    # Admin-only analytics section
    if user_is_admin:
        st.markdown("---")
        st.subheader("📊 Usage Analytics")
        st.caption("Admin-only information")
        
        usage = UsageTracker.get_usage_summary()
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("API Calls", usage['total_calls'])
            st.metric("Tokens Used", f"{usage['total_tokens']:,}")
        with col2:
            st.metric("Est. Cost", f"${usage['estimated_cost']:.4f}")
            st.metric("Calls/Hour", f"{usage['calls_per_hour']:.1f}")
        
        # Session duration
        duration = usage['session_duration']
        hours = int(duration.total_seconds() // 3600)
        minutes = int((duration.total_seconds() % 3600) // 60)
        st.info(f"⏱️ Session: {hours}h {minutes}m")
        
        st.markdown("---")
        
        # Rate limit info
        st.subheader("⚡ Rate Limits")
        st.caption("Admin-only monitoring")
        
        recent_calls = len([
            t for t in st.session_state.api_call_times 
            if datetime.now() - t < timedelta(minutes=1)
        ])
        st.progress(recent_calls / MAX_CALLS_PER_MINUTE)
        st.caption(f"{recent_calls}/{MAX_CALLS_PER_MINUTE} calls in last minute")
        
        st.progress(len(st.session_state.api_call_times) / MAX_CALLS_PER_HOUR)
        st.caption(f"{len(st.session_state.api_call_times)}/{MAX_CALLS_PER_HOUR} calls in last hour")
    else:
        # Simple message for regular users
        st.markdown("---")
        duration = datetime.now() - st.session_state.session_start_time
        minutes = int(duration.total_seconds() // 60)
        st.caption(f"⏱️ Session: {minutes} minutes")

# --- USER INTERFACE ---
st.title("🧠 SEL Integration Agent")
st.markdown("*Powered by Claude Sonnet 4.5 - Your AI instructional coach for Social-Emotional Learning*")

tab_list = [
    "Analyze Existing Lesson", "Create New Lesson", "🧑‍🎓 Student Scenarios", 
    "👩‍🏫 Teacher SEL Training", "☀️ Morning Check-in", "🆘 Strategy Finder"
]
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(tab_list)

with tab1:
    st.header("Analyze an Existing Lesson Plan")
    st.info("Upload or paste a lesson plan. Get one high-impact, evidence-based SEL integration strategy.")
    
    st.markdown("**Optional: Add a Specific SEL Focus**")
    col1a, col2a = st.columns(2)
    with col1a:
        analyze_competency = st.selectbox(
            "Select a CASEL Competency", 
            options=CASEL_COMPETENCIES, 
            index=None, 
            placeholder="Choose a competency...", 
            key="analyze_comp"
        )
    with col2a:
        if analyze_competency:
            analyze_skill = st.selectbox(
                "Select a Focused Skill", 
                options=COMPETENCIES[analyze_competency], 
                index=None, 
                placeholder="Choose a skill...", 
                key="analyze_skill"
            )
        else:
            analyze_skill = None
            st.selectbox("Select a Focused Skill", options=[], disabled=True, key="disabled_analyze_skill")
    
    st.markdown("---")
    uploaded_file = st.file_uploader(
        "Upload a .txt, .docx, .pptx, or .pdf file", 
        type=["txt", "docx", "pptx", "pdf"]
    )
    lesson_text_paste = st.text_area("Or paste the full text of your lesson plan here.", height=200)
    standard_input = st.text_area(
        "(Optional) Paste educational standard(s) here.", 
        placeholder="e.g., CCSS.ELA-LITERACY.RL.5.2", 
        height=100
    )
    
    if st.button("🚀 Generate SEL Suggestions"):
        lesson_content = ""
        if uploaded_file: 
            lesson_content = read_document(uploaded_file)
        elif lesson_text_paste: 
            lesson_content = lesson_text_paste
            
        if lesson_content:
            with st.spinner("🤖 Analyzing lesson with Claude Sonnet 4.5..."):
                clear_generated_content()
                
                # Add user query to memory
                ConversationMemory.add_to_memory(
                    "user", 
                    f"Analyze lesson plan (competency: {analyze_competency}, skill: {analyze_skill})",
                    {"type": "lesson_analysis"}
                )
                
                prompt = get_analysis_prompt(
                    lesson_content, 
                    standard_input, 
                    analyze_competency, 
                    analyze_skill
                )
                response = call_claude(prompt)
                if response:
                    st.session_state.ai_response = response
                    st.session_state.response_title = "Evidence-Based SEL Recommendation"
        else: 
            st.warning("Please upload or paste a lesson plan to begin.")

with tab2:
    st.header("Create a New, SEL-Integrated Lesson")
    st.info("Fill in the details to generate a new lesson plan from scratch.")
    
    st.markdown("**Optional: Add a Specific SEL Focus**")
    col1c, col2c = st.columns(2)
    with col1c:
        create_competency = st.selectbox(
            "Select a CASEL Competency", 
            options=CASEL_COMPETENCIES, 
            index=None, 
            placeholder="Choose a competency...", 
            key="create_comp"
        )
    with col2c:
        if create_competency:
            create_skill = st.selectbox(
                "Select a Focused Skill", 
                options=COMPETENCIES[create_competency], 
                index=None, 
                placeholder="Choose a skill...", 
                key="create_skill"
            )
        else:
            create_skill = None
            st.selectbox("Select a Focused Skill", options=[], disabled=True, key="disabled_create_skill")
    
    st.markdown("---")
    with st.form("create_form"):
        create_grade = st.selectbox("Grade Level", options=GRADE_LEVELS, index=0)
        create_subject = st.selectbox("Subject", options=SUBJECTS, index=0)
        create_topic = st.text_area(
            "Lesson Topic or Objective", 
            "The causes and effects of the American Revolution."
        )
        submitted = st.form_submit_button("✨ Create SEL Lesson Plan")
        
        if submitted:
            with st.spinner("🛠️ Building your lesson plan with Claude Sonnet 4.5..."):
                clear_generated_content()
                
                # Add user query to memory
                ConversationMemory.add_to_memory(
                    "user",
                    f"Create lesson: {create_topic} ({create_grade}, {create_subject})",
                    {"type": "lesson_creation"}
                )
                
                prompt = get_creation_prompt(
                    create_grade, 
                    create_subject, 
                    create_topic, 
                    create_competency, 
                    create_skill
                )
                response = call_claude(prompt)
                if response:
                    st.session_state.ai_response = response
                    st.session_state.response_title = "Your New SEL-Integrated Lesson Plan"

with tab3:
    st.header("Interactive SEL Scenarios")
    st.info("Select a competency and skill to generate a practice scenario.")
    
    col1b, col2b, col3b = st.columns(3)
    with col1b:
        scenario_competency = st.selectbox(
            "Select a CASEL Competency", 
            options=CASEL_COMPETENCIES, 
            index=3, 
            key="scenario_comp"
        )
    with col2b:
        scenario_skill = st.selectbox(
            "Select a Focused Skill", 
            options=COMPETENCIES[scenario_competency], 
            index=0, 
            key="scenario_skill"
        )
    with col3b:
        scenario_grade = st.selectbox(
            "Select a Grade Level", 
            options=GRADE_LEVELS, 
            key="scenario_grade"
        )
    
    if st.button("🎬 Generate New Scenario"):
        with st.spinner("Writing a scenario..."):
            prompt = get_scenario_prompt(scenario_competency, scenario_skill, scenario_grade)
            response = call_claude(prompt, max_tokens=1024, stream=False)
            if response:
                st.session_state.scenario = response
                st.session_state.conversation_history = []
    
    if st.session_state.scenario:
        st.markdown("---")
        st.markdown(f"**Scenario:** {st.session_state.scenario}")
        
        for entry in st.session_state.conversation_history:
            if entry['role'] == 'Student': 
                st.markdown(f"> **You:** {entry['content']}")
            else: 
                st.markdown(f"**Coach:** {entry['content']}")
        
        student_response = st.text_input("What would you do or say?", key="student_response_input")
        
        if st.button("💬 Submit Response"):
            if student_response:
                st.session_state.conversation_history.append({
                    "role": "Student", 
                    "content": student_response
                })
                
                with st.spinner("Coach is thinking..."):
                    feedback_prompt = get_feedback_prompt(
                        st.session_state.scenario, 
                        st.session_state.conversation_history
                    )
                    response = call_claude(feedback_prompt, max_tokens=1024, stream=False)
                    if response:
                        st.session_state.conversation_history.append({
                            "role": "Coach", 
                            "content": response
                        })
                        st.rerun()

with tab4:
    st.header("👩‍🏫 Teacher SEL Training")
    st.info("Select a competency to begin an in-depth training module.")
    
    training_competency = st.selectbox(
        "Select a CASEL Competency to learn about", 
        options=CASEL_COMPETENCIES, 
        index=None, 
        placeholder="Choose a competency...", 
        key="training_comp_select"
    )
    
    if st.button("🎓 Start Training Module"):
        if training_competency:
            with st.spinner("Preparing your training module..."):
                prompt = get_training_prompt(training_competency)
                response = call_claude(prompt)
                if response:
                    st.session_state.training_module = response
                    st.session_state.training_scenario = ""
                    st.session_state.training_feedback = ""
        else: 
            st.warning("Please select a competency to begin.")
    
    if st.session_state.training_module:
        st.markdown("---")
        st.markdown(st.session_state.training_module)
        st.markdown("---")
        
        st.subheader("🎬 Let's Try It Out")
        if st.button("Generate a Practice Scenario"):
            with st.spinner("Creating a classroom scenario..."):
                prompt = get_training_scenario_prompt(
                    training_competency, 
                    st.session_state.training_module
                )
                response = call_claude(prompt, max_tokens=1024, stream=False)
                if response:
                    st.session_state.training_scenario = response
                    st.session_state.training_feedback = ""
        
        if st.session_state.training_scenario:
            st.info(st.session_state.training_scenario)
            teacher_response = st.text_area(
                "How would you respond to this scenario?", 
                key="teacher_response_area"
            )
            
            if st.button("Get Feedback"):
                if teacher_response:
                    with st.spinner("Your coach is reviewing your response..."):
                        prompt = get_training_feedback_prompt(
                            training_competency, 
                            st.session_state.training_scenario, 
                            teacher_response
                        )
                        response = call_claude(prompt, max_tokens=1024, stream=False)
                        if response:
                            st.session_state.training_feedback = response
                else: 
                    st.warning("Please enter your response above.")
            
            if st.session_state.training_feedback:
                st.markdown("---")
                st.markdown("#### Coach's Feedback")
                st.success(st.session_state.training_feedback)

with tab5:
    st.header("☀️ SEL Morning Check-in")
    st.info("Generate creative questions for your morning meeting or class check-in.")
    
    col1d, col2d = st.columns(2)
    with col1d:
        check_in_grade = st.selectbox(
            "Select a Grade Level", 
            options=GRADE_LEVELS, 
            key="check_in_grade"
        )
    with col2d:
        check_in_tone = st.selectbox(
            "Select a Tone", 
            options=["Calm", "Energetic", "Reflective", "Fun", "Serious"], 
            key="check_in_tone"
        )
    
    if st.button("❓ Generate Questions"):
        with st.spinner("Coming up with some good questions..."):
            prompt = get_check_in_prompt(check_in_grade, check_in_tone)
            response = call_claude(prompt, max_tokens=1024, stream=False)
            if response:
                st.session_state.check_in_questions = response
    
    if st.session_state.check_in_questions:
        st.markdown("---")
        st.markdown(st.session_state.check_in_questions)

with tab6:
    st.header("🆘 On-Demand Strategy Finder")
    st.info("Describe a classroom situation to get immediate, actionable SEL strategies.")
    
    situation = st.text_area(
        "Describe the situation in your classroom:", 
        placeholder="e.g., 'Two students are arguing over a shared resource' or 'My class is very unfocused after lunch.'", 
        height=150
    )
    
    if st.button("💡 Find a Strategy"):
        if situation and situation.strip():
            with st.spinner("Finding effective strategies..."):
                prompt = get_strategy_prompt(situation)
                response = call_claude(prompt, max_tokens=2048)
                if response:
                    st.session_state.strategy_response = response
        else: 
            st.warning("Please describe the situation to get a strategy.")
    
    if st.session_state.strategy_response:
        st.markdown("---")
        st.markdown(st.session_state.strategy_response)

# --- DISPLAY OUTPUT AREA FOR TABS 1 AND 2 ---
if st.session_state.ai_response:
    st.markdown("---")
    st.header(st.session_state.response_title)
    st.markdown(st.session_state.ai_response)
    st.markdown("---")
    
    st.subheader("📧 Parent Communication")
    if st.button("Generate Parent Email"):
        with st.spinner("Drafting a parent email..."):
            email_prompt = get_parent_email_prompt(st.session_state.ai_response)
            response = call_claude(email_prompt, max_tokens=2048, stream=False)
            if response:
                st.session_state.parent_email = response
    
    if st.session_state.parent_email:
        st.text_area("Parent Email Draft", value=st.session_state.parent_email, height=300)
    
    st.markdown("---")
    st.subheader("👩‍🏫 Generate Student-Facing Materials")
    if st.button("Generate Materials"):
        with st.spinner("✍️ Creating student materials..."):
            materials_prompt = get_student_materials_prompt(st.session_state.ai_response)
            response = call_claude(materials_prompt, stream=False)
            if response:
                st.session_state.student_materials = response
    
    if st.session_state.student_materials:
        st.markdown(st.session_state.student_materials)
    
    st.markdown("---")
    st.subheader("🧠 Differentiate This Lesson")
    if st.button("Generate Differentiation Strategies"):
        with st.spinner("💡 Coming up with strategies for diverse learners..."):
            diff_prompt = get_differentiation_prompt(st.session_state.ai_response)
            response = call_claude(diff_prompt, stream=False)
            if response:
                st.session_state.differentiation_response = response
    
    if st.session_state.differentiation_response:
        st.markdown(st.session_state.differentiation_response)
    
    st.markdown("---")
    st.subheader("📥 Download Your Plan")
    full_download_text = st.session_state.ai_response
    if st.session_state.parent_email: 
        full_download_text += "\n\n---\n\n# Parent Communication Draft\n\n" + st.session_state.parent_email
    if st.session_state.student_materials: 
        full_download_text += "\n\n---\n\n# Student-Facing Materials\n\n" + st.session_state.student_materials
    if st.session_state.differentiation_response: 
        full_download_text += "\n\n---\n\n# Differentiation Strategies\n\n" + st.session_state.differentiation_response
    
    if full_download_text.strip():
        docx_file = create_docx(full_download_text)
        
        dl_col1, dl_col2 = st.columns(2)
        with dl_col1:
            st.download_button(
                label="Download as Text File (.txt)",
                data=full_download_text.encode('utf-8-sig'),
                file_name="sel_plan.txt",
                mime="text/plain"
            )
        with dl_col2:
            if docx_file:
                st.download_button(
                    label="Download as Word Doc (.docx)", 
                    data=docx_file, 
                    file_name="sel_plan.docx", 
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )

# Footer
st.markdown("---")
st.markdown("*💡 Powered by Claude Sonnet 4.5 from Anthropic*")
st.caption(f"Session started: {st.session_state.session_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
