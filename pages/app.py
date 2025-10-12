# VERSION 9.5: Integrated evidence-based SEL consultant persona and structured output
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

# This must be the first Streamlit command in your script
if not st.session_state.get("password_correct", False):
    st.switch_page("login.py")

# --- API CONFIGURATION ---
try:
    api_key = st.secrets["ANTHROPIC_API_KEY"]
    client = anthropic.Anthropic(api_key=api_key)
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
    "training_feedback": "", "check_in_questions": "", "strategy_response": ""
}
for key, default_value in SESSION_STATE_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default_value

# --- CONSTANTS & OTHER SETUP ---
GRADE_LEVELS = ["Kindergarten", "1st Grade", "2nd Grade", "3rd Grade", "4th Grade", "5th Grade", "6th Grade", "7th Grade", "8th Grade", "9th Grade", "10th Grade", "11th Grade", "12th Grade"]
SUBJECTS = ["Science", "History", "English Language Arts", "Mathematics", "Art", "Music"]
COMPETENCIES = {
    "Self-Awareness": ["Identifying Emotions", "Self-Perception", "Recognizing Strengths", "Self-Confidence", "Self-Efficacy"],
    "Self-Management": ["Impulse Control", "Stress Management", "Self-Discipline", "Self-Motivation", "Goal-Setting", "Organizational Skills"],
    "Social Awareness": ["Perspective-Taking", "Empathy", "Appreciating Diversity", "Respect for Others"],
    "Relationship Skills": ["Communication", "Social Engagement", "Building Relationships", "Teamwork", "Conflict Resolution"],
    "Responsible Decision-Making": ["Identifying Problems", "Analyzing Situations", "Solving Problems", "Evaluating", "Reflecting", "Ethical Responsibility"]
}
CASEL_COMPETENCIES = list(COMPETENCIES.keys())


# --- HELPER FUNCTIONS (No changes needed here) ---
def read_document(uploaded_file):
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

def create_pdf(markdown_text):
    html_text = markdown2.markdown(markdown_text, extras=["cuddled-lists", "tables"])
    html_encoded = html_text.encode('latin-1', 'replace').decode('latin-1')
    pdf = FPDF()
    pdf.add_font("DejaVu", "", "fonts/DejaVuSans.ttf", uni=True)
    pdf.set_font("DejaVu", size=12)
    pdf.add_page()
    pdf.cell(0, 0, "") 
    pdf.write_html(html_encoded)
    pdf_output = pdf.output(dest='S').encode('latin-1')
    pdf_file = io.BytesIO(pdf_output)
    pdf_file.seek(0)
    return pdf_file

def create_docx(text):
    doc = docx.Document()
    doc.add_heading('SEL Integration Plan', 0)
    for line in text.split('\n'):
        if line.startswith('### '): doc.add_heading(line.lstrip('### '), level=3)
        elif line.startswith('## '): doc.add_heading(line.lstrip('## '), level=2)
        elif line.startswith('# '): doc.add_heading(line.lstrip('# '), level=1)
        else: doc.add_paragraph(line)
    docx_file = io.BytesIO()
    doc.save(docx_file)
    docx_file.seek(0)
    return docx_file

# --- PROMPTS (UPDATED FOR NEW PERSONA) ---

# This is the primary system prompt defining the agent's persona and rules.
# It's now passed into the main prompt functions.
SYSTEM_PROMPT = """
You are an intelligent SEL consultant supporting K–12 educators. Your guidance must be practical, evidence-based, and grounded in research from sources like CASEL, ASCA, and peer-reviewed journals (e.g., "Social and Emotional Learning: Research, Practice, and Policy"). You balance scientific rigor with educational practicality.

Core Directives:
- All primary recommendations MUST follow this exact four-part Markdown format:
  **Overview:** Brief definition or contextual framing (1-2 sentences).
  **Evidence Summary:** What research demonstrates, including study types and key findings (2-4 sentences). You must explicitly reference the type of evidence (e.g., "A meta-analysis of over 200 school-based programs...", "Consistent with developmental research on executive function...", "Validated through randomized controlled trials...").
  **Implementation Example:** A concrete classroom or counseling application with 3-5 actionable steps.
  **Measurement/Outcome:** Observable indicators of success and how progress is tracked (2-3 measurable criteria).
- Link strategies to specific CASEL competencies.
- Maintain a professional, compassionate, data-driven tone. Avoid personal opinions, anecdotes, and overly emotional language.
- Prioritize meta-analyses and systematic reviews over single studies.
"""

def get_analysis_prompt(lesson_plan_text, standard="", competency="", skill=""):
    focus_instruction = ""
    if competency and skill:
        focus_instruction = f"The user has requested a specific focus on the CASEL competency of **{competency}**, with an emphasis on the skill of **{skill}**. Your analysis and recommendations should prioritize this focus."
    
    standard_instruction = ""
    if standard and standard.strip():
        standard_instruction = f"Crucially, all suggestions must also align with this educational standard: '{standard.strip()}'."

    return f"""
    {SYSTEM_PROMPT}

    An educator has submitted the following lesson plan for analysis and SEL integration recommendations.

    **Teacher's Lesson Plan:**
    ---
    {lesson_plan_text}
    ---

    **Your Task:**
    1.  Thoroughly analyze the lesson plan to identify the strongest, most natural opportunity for SEL integration.
    2.  Provide ONE comprehensive recommendation for a single, high-impact SEL strategy that aligns with the lesson content.
    3.  Your entire response for this recommendation must strictly follow the mandatory four-part format defined in your core directives.

    {focus_instruction}
    {standard_instruction}
    """

def get_creation_prompt(grade_level, subject, topic, competency="", skill=""):
    # The lesson plan creation prompt is slightly different, focusing on building a plan.
    # It will be prefaced with a rationale that follows the new guidelines.
    focus_instruction = ""
    if competency and skill:
        focus_instruction = f"The lesson's primary SEL focus must be on **{competency}**, specifically developing the skill of **{skill}**."
    
    return f"""
    You are a master curriculum designer and instructional coach, an expert in pedagogy and Social-Emotional Learning, operating under the principles of the SEL Consultant persona.
    
    **Request Details:**
    - **Grade Level:** {grade_level}
    - **Subject:** {subject}
    - **Lesson Topic:** {topic}
    - **SEL Focus:** {focus_instruction if focus_instruction else "A balanced approach to all CASEL competencies."}

    **Your Task:**
    1.  First, write a brief "Pedagogical Rationale" section that explains the evidence behind the primary SEL activity you will include in the lesson. This rationale should be 2-3 sentences and explicitly state the evidence type (e.g., "The use of 'think-pair-share' is supported by cooperative learning research...").
    2.  Then, generate a complete lesson plan in clear Markdown format, structured with the detailed sections below. Ensure the instructional sequence follows an "I Do, We Do, You Do" model and that the objectives are written in terms of observable behaviors.

    ## Pedagogical Rationale
    (Your evidence-based rationale here)
    
    ---

    # Lesson Plan: {subject} - {topic}

    ## 🎯 **Learning Objectives**
    * *Content Objective:* (What will students know or be able to do related to the subject?)
    * *SEL Objective:* (What specific SEL skill will students practice, described as an observable behavior?)
    ## 🔑 **Key Vocabulary**
    * *Content Vocabulary:* (List 3-5 key terms for the academic subject.)
    * *SEL Vocabulary:* (List 2-3 key terms related to the SEL focus.)
    ## 📋 **Materials**
    (List all materials needed for the lesson.)
    ---
    ## **Lesson Sequence**
    ### 🎣 **Anticipatory Set / Hook**
    ### 🧑‍🏫 **Direct Instruction (I Do)**
    ### ✍️ **Guided Practice (We Do)**
    ### 💡 **Independent Practice (You Do)**
    ### ✅ **Assessment / Check for Understanding**
    ### 🏁 **Closing / Wrap-up**
    ---
    ## 🧠 **Detailed SEL Alignment**
    (Explain how the lesson activities align with specific CASEL competencies.)
    """

def get_strategy_prompt(situation):
    # This prompt is for quick, in-the-moment help, so it uses a condensed version of the main format.
    return f"""
    {SYSTEM_PROMPT}

    A teacher needs an immediate, evidence-based strategy for the following classroom situation.

    **The Situation:** "{situation}"

    **Your Task:**
    Provide ONE quick, actionable strategy. Your response must follow this condensed format:
    - **Strategy:** (Name the strategy, e.g., "Mindful Minute")
    - **Evidence Rationale:** (1-2 sentences explaining the evidence base, e.g., "Grounded in mindfulness-based stress reduction (MBSR), which has been shown in multiple trials to improve emotional regulation...")
    - **Actionable Steps:** (2-3 immediate, simple steps for the teacher to take right now.)
    - **Expected Outcome:** (1 sentence describing the observable outcome, e.g., "Students should appear calmer and more focused.")
    """

# --- (Other prompt functions remain largely the same, as they build on the main responses) ---
def get_student_materials_prompt(lesson_plan_output):
    return f"""
    You are a practical instructional designer. Based on the provided lesson plan or SEL recommendation, create a set of student-facing materials in clear Markdown format. Ensure the materials are grade-level appropriate and align with evidence-based practices (e.g., open-ended questions for reflection).

    **Source Document:**
    ---
    {lesson_plan_output}
    ---

    **Your Task:**
    Generate the following materials:
    ### 🎟️ Exit Ticket
    (2-3 brief, reflective questions)
    ### 🗣️ Think-Pair-Share Prompts
    (2-3 engaging questions for partner discussion)
    ### ✍️ Journal Starters
    (2-3 thoughtful prompts for personal reflection)
    ### 📄 Practice Worksheet
    (1 simple, printable worksheet or graphic organizer related to the lesson's content and SEL skill.)
    """
def get_differentiation_prompt(lesson_plan_output):
    return f"You are an expert in instructional differentiation. Based on the lesson plan, provide evidence-based strategies to support diverse learners in Markdown format with headings: ###  scaffold Support (For Struggling Learners), ### ⬆️ Extension Activities (For Advanced Learners), ### 🌐 English Language Learner (ELL) Support.\n\nLesson Plan:\n---{lesson_plan_output}---"
def get_scenario_prompt(competency, skill, grade_level):
    return f"Generate a short, relatable, school-based scenario for a {grade_level} student. The scenario must require them to use the SEL competency of **{competency}**, focusing on the skill of **{skill}**. Present it in the second person ('You are...'), ending with a question. Make it a single paragraph."
def get_feedback_prompt(scenario, history):
    formatted_history = "\n".join([f"- {entry['role']}: {entry['content']}" for entry in history])
    return f"You are a supportive SEL coach using a Socratic approach. A student is working through this scenario:\n**Scenario:** {scenario}\n**Conversation History:**\n{formatted_history}\nYour task is to ask one reflective question to help the student think deeper. Do not give advice. Keep your response brief."
def get_training_prompt(competency):
    return f"""
    You are an expert SEL facilitator. Create a professional development module on **{competency}**, grounded in the CASEL framework and evidence-based practices.
    Structure your response in Markdown with these sections:
    ## 🧠 Understanding {competency}
    (Provide a core definition and its importance, citing CASEL.)
    ## 🛠️ Evidence-Based Classroom Moves
    For 2-3 key skills within this competency, provide a strategy in the following format:
    ### Skill: [Name of the Skill]
    * **The Move:** A practical strategy.
    * **Evidence Base:** A brief summary of the research that supports this move (e.g., "Based on Social Learning Theory...", "Supported by studies on cognitive flexibility...").
    * **Implementation Example:** A concrete step-by-step example.
    """
def get_training_scenario_prompt(competency, training_module_text):
    return f"You are an expert SEL facilitator. Create a brief, challenging but common classroom scenario to help a teacher practice the competency of **{competency}**. End the scenario with an open-ended question. Generate ONLY the scenario and the question."
def get_training_feedback_prompt(competency, scenario, teacher_response):
    return f"You are a supportive SEL coach. The teacher is practicing **{competency}**. \n**Scenario:** {scenario}\n**Teacher's Response:** {teacher_response}\n**Your Task:** Provide constructive, encouraging feedback. Affirm a positive aspect and then ask one reflective question to deepen their practice."
def get_check_in_prompt(grade_level, tone):
    return f"You are an expert teacher grounded in developmental psychology. Generate 3-4 creative, age-appropriate morning check-in questions for a **{grade_level}** class with a **{tone}** tone. Format as a numbered list."
def get_parent_email_prompt(lesson_plan):
    return f"""
    You are a skilled educator. Based on the provided lesson plan, draft a professional, easy-to-understand email from a teacher to parents, following a 'strengths-based' communication model.
    **Lesson Plan:**\n---\n{lesson_plan}\n---
    **Email Structure:**
    1.  **Subject Line:** Clear and informative.
    2.  **What We're Learning:** Simply identify the main SEL skill.
    3.  **How We Practiced:** Briefly describe a classroom activity.
    4.  **Connection at Home:** Provide one simple, positive conversation starter for parents.
    """

def clear_generated_content():
    keys_to_clear = ["ai_response", "response_title", "student_materials", "differentiation_response", "parent_email"]
    for key in keys_to_clear:
        if key in st.session_state: st.session_state[key] = ""


# --- USER INTERFACE (No changes needed here) ---
st.title("🧠 SEL Integration Agent")
st.markdown("Your AI-powered instructional coach for Social-Emotional Learning.")

tab_list = [
    "Analyze Existing Lesson", "Create New Lesson", "🧑‍🎓 Student Scenarios", 
    "👩‍🏫 Teacher SEL Training", "☀️ Morning Check-in", "🆘 Strategy Finder"
]
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(tab_list)

with tab1:
    st.header("Analyze an Existing Lesson Plan")
    st.info("Upload or paste a lesson plan. The agent will provide one high-impact, evidence-based SEL integration strategy.")
    st.markdown("**Optional: Add a Specific SEL Focus**")
    col1a, col2a = st.columns(2)
    with col1a:
        analyze_competency = st.selectbox("Select a CASEL Competency", options=CASEL_COMPETENCIES, index=None, placeholder="Choose a competency...", key="analyze_comp")
    with col2a:
        if analyze_competency:
            analyze_skill = st.selectbox("Select a Focused Skill", options=COMPETENCIES[analyze_competency], index=None, placeholder="Choose a skill...", key="analyze_skill")
        else:
            analyze_skill = None
            st.selectbox("Select a Focused Skill", options=[], disabled=True, key="disabled_analyze_skill_fix")
    st.markdown("---")
    uploaded_file = st.file_uploader("Upload a .txt, .docx, .pptx, or .pdf file", type=["txt", "docx", "pptx", "pdf"])
    lesson_text_paste = st.text_area("Or paste the full text of your lesson plan here.", height=200)
    standard_input = st.text_area("(Optional) Paste educational standard(s) here.", placeholder="e.g., CCSS.ELA-LITERACY.RL.5.2", height=100)
    
    if st.button("🚀 Generate SEL Suggestions"):
        lesson_content = ""
        if uploaded_file: lesson_content = read_document(uploaded_file)
        elif lesson_text_paste: lesson_content = lesson_text_paste
        if lesson_content:
            with st.spinner("🤖 Analyzing lesson and synthesizing research..."):
                try:
                    clear_generated_content()
                    prompt = get_analysis_prompt(lesson_content, standard_input, analyze_competency, analyze_skill)
                   # --- Replace With This ---
                   message = client.messages.create(
    model="claude-3-5-sonnet-20240620",  # <--- Make sure there's a comma here
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}]
)
                st.session_state.ai_response = message.content[0].text
                st.session_state.response_title = "Evidence-Based SEL Recommendation"
                except Exception as e: st.error(f"Error during generation: {e}")
        else: st.warning("Please upload or paste a lesson plan to begin.")

# ... (The rest of the UI code for other tabs remains exactly the same and is omitted for brevity) ...

with tab2:
    st.header("Create a New, SEL-Integrated Lesson")
    st.info("Fill in the details below to generate a new lesson plan from scratch.")
    st.markdown("**Optional: Add a Specific SEL Focus**")
    col1c, col2c = st.columns(2)
    with col1c:
        create_competency = st.selectbox("Select a CASEL Competency", options=CASEL_COMPETENCIES, index=None, placeholder="Choose a competency...", key="create_comp")
    with col2c:
        if create_competency:
            create_skill = st.selectbox("Select a Focused Skill", options=COMPETENCIES[create_competency], index=None, placeholder="Choose a skill...", key="create_skill")
        else:
            create_skill = None
            st.selectbox("Select a Focused Skill", options=[], disabled=True, key="disabled_create_skill")
    st.markdown("---")
    with st.form("create_form"):
        create_grade = st.selectbox("Grade Level", options=GRADE_LEVELS, index=0)
        create_subject = st.selectbox("Subject", options=SUBJECTS, index=0)
        create_topic = st.text_area("Lesson Topic or Objective", "The causes and effects of the American Revolution.")
        submitted = st.form_submit_button("✨ Create SEL Lesson Plan")
        if submitted:
            with st.spinner("🛠️ Building your new lesson plan..."):
                try:
                    clear_generated_content()
                    prompt = get_creation_prompt(create_grade, create_subject, create_topic, create_competency, create_skill)
                  # --- Replace With This ---
message = client.messages.create(
    model="claude-3-5-sonnet-20240620",  # <--- Make sure there's a comma here
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}]
)
                 st.session_state.ai_response = message.content[0].text
                 st.session_state.response_title = "Your New SEL-Integrated Lesson Plan"
                except Exception as e: st.error(f"An error occurred: {e}")
with tab3:
    st.header("Interactive SEL Scenarios")
    st.info("Select a competency and skill to generate a practice scenario for a student.")
    col1b, col2b, col3b = st.columns(3)
    with col1b:
        scenario_competency = st.selectbox("Select a CASEL Competency", options=CASEL_COMPETENCIES, index=3, key="scenario_comp")
    with col2b:
        scenario_skill = st.selectbox("Select a Focused Skill", options=COMPETENCIES[scenario_competency], index=0, key="scenario_skill")
    with col3b:
        scenario_grade = st.selectbox("Select a Grade Level", options=GRADE_LEVELS, key="scenario_grade")
    if st.button("🎬 Generate New Scenario"):
        with st.spinner("Writing a scenario..."):
            try:
                prompt = get_scenario_prompt(scenario_competency, scenario_skill, scenario_grade)
                # --- Replace With This ---
message = client.messages.create(
    model="claude-3-5-sonnet-20240620",  # <--- Make sure there's a comma here
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}]
)
                st.session_state.scenario = message.content[0].text
                st.session_state.conversation_history = []
            except Exception as e: st.error(f"Could not generate a scenario: {e}")
    if st.session_state.scenario:
        st.markdown("---")
        st.markdown(f"**Scenario:** {st.session_state.scenario}")
        for entry in st.session_state.conversation_history:
            if entry['role'] == 'Student': st.markdown(f"> **You:** {entry['content']}")
            else: st.markdown(f"**Coach:** {entry['content']}")
        student_response = st.text_input("What would you do or say?", key="student_response_input")
        if st.button("💬 Submit Response"):
            if student_response:
                st.session_state.conversation_history.append({"role": "Student", "content": student_response})
                with st.spinner("Coach is thinking..."):
                    try:
                        feedback_prompt = get_feedback_prompt(st.session_state.scenario, st.session_state.conversation_history)
                       # --- Replace With This ---
message = client.messages.create(
    model="claude-3-5-sonnet-20240620",  # <--- Make sure there's a comma here
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}]
)
                        st.session_state.conversation_history.append({"role": "Coach", "content": message.content[0].text})
                        st.rerun()
                    except Exception as e: st.error(f"Could not get feedback: {e}")
with tab4:
    st.header("👩‍🏫 Teacher SEL Training")
    st.info("Select a competency to begin a professional, in-depth training module.")
    training_competency = st.selectbox("Select a CASEL Competency to learn about", options=CASEL_COMPETENCIES, index=None, placeholder="Choose a competency...", key="training_comp_select")
    if st.button("🎓 Start Training Module"):
        if training_competency:
            with st.spinner("Preparing your training module..."):
                try:
                    prompt = get_training_prompt(training_competency)
                   # --- Replace With This ---
message = client.messages.create(
    model="claude-3-5-sonnet-20240620",
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}]
)
                    st.session_state.training_module = message.content[0].text
                    st.session_state.training_scenario = ""
                    st.session_state.training_feedback = ""
                except Exception as e: st.error(f"Could not generate the training module: {e}")
        else: st.warning("Please select a competency to begin.")
    if st.session_state.training_module:
        st.markdown("---")
        st.markdown(st.session_state.training_module)
        st.markdown("---")
        st.subheader("🎬 Let's Try It Out")
        if st.button("Generate a Practice Scenario"):
            with st.spinner("Creating a classroom scenario..."):
                try:
                    prompt = get_training_scenario_prompt(training_competency, st.session_state.training_module)
                    # --- Replace With This ---
message = client.messages.create(
    model="claude-3-5-sonnet-20240620",  # <--- Make sure there's a comma here
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}]
)
                    st.session_state.training_scenario = message.content[0].text
                    st.session_state.training_feedback = ""
                except Exception as e: st.error(f"Could not generate the scenario: {e}")
        if st.session_state.training_scenario:
            st.info(st.session_state.training_scenario)
            teacher_response = st.text_area("How would you respond to this scenario?", key="teacher_response_area")
            if st.button("Get Feedback"):
                if teacher_response:
                    with st.spinner("Your coach is reviewing your response..."):
                        try:
                            prompt = get_training_feedback_prompt(training_competency, st.session_state.training_scenario, teacher_response)
                           # --- Replace With This ---
message = client.messages.create(
    model="claude-3-5-sonnet-20240620",  # <--- Make sure there's a comma here
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}]
)                      st.session_state.training_feedback = message.content[0].text
                        except Exception as e: st.error(f"Could not generate feedback: {e}")
                else: st.warning("Please enter your response above.")
            if st.session_state.training_feedback:
                st.markdown("---")
                st.markdown("#### Coach's Feedback")
                st.success(st.session_state.training_feedback)
with tab5:
    st.header("☀️ SEL Morning Check-in")
    st.info("Instantly generate creative questions for your morning meeting or class check-in.")
    col1d, col2d = st.columns(2)
    with col1d:
        check_in_grade = st.selectbox("Select a Grade Level", options=GRADE_LEVELS, key="check_in_grade")
    with col2d:
        check_in_tone = st.selectbox("Select a Tone", options=["Calm", "Energetic", "Reflective", "Fun", "Serious"], key="check_in_tone")
    if st.button("❓ Generate Questions"):
        with st.spinner("Coming up with some good questions..."):
            try:
                prompt = get_check_in_prompt(check_in_grade, check_in_tone)
                # --- Replace With This ---
message = client.messages.create(
    model="claude-3-5-sonnet-20240620",
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}]
)
                st.session_state.check_in_questions = message.content[0].text
            except Exception as e: st.error(f"Could not generate questions: {e}")
    if st.session_state.check_in_questions:
        st.markdown("---")
        st.markdown(st.session_state.check_in_questions)
with tab6:
    st.header("🆘 On-Demand Strategy Finder")
    st.info("Describe a classroom situation to get immediate, actionable SEL strategies.")
    situation = st.text_area("Describe the situation in your classroom:", placeholder="e.g., 'Two students are arguing over a shared resource,' or 'My class is very unfocused after lunch.'", height=150)
    if st.button("💡 Find a Strategy"):
        if situation and situation.strip():
            with st.spinner("Finding effective strategies..."):
                try:
                    prompt = get_strategy_prompt(situation)
                    # --- Replace With This ---
message = client.messages.create(
    model="claude-3-5-sonnet-20240620",  # <--- Make sure there's a comma here
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}]
)
                    st.session_state.strategy_response = message.content[0].text
                except Exception as e: st.error(f"Could not find a strategy: {e}")
        else: st.warning("Please describe the situation to get a strategy.")
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
            try:
                email_prompt = get_parent_email_prompt(st.session_state.ai_response)
                # --- Replace With This ---
message = client.messages.create(
    model="claude-3-5-sonnet-20240620",  # <--- Make sure there's a comma here
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}]
)
                st.session_state.parent_email = message.content[0].text
            except Exception as e: st.error(f"An error occurred while generating the email: {e}")
    if st.session_state.parent_email:
        st.text_area("Parent Email Draft", value=st.session_state.parent_email, height=300)
    st.markdown("---")
    st.subheader("👩‍🏫 Generate Student-Facing Materials")
    if st.button("Generate Materials"):
        with st.spinner("✍️ Creating student materials..."):
            try:
                materials_prompt = get_student_materials_prompt(st.session_state.ai_response)
             message = client.messages.create(
    model="claude-3-5-sonnet-20240620",  # <--- Make sure there's a comma here
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}]
)
                st.session_state.student_materials = message.content[0].text
            except Exception as e: st.error(f"An error occurred while generating materials: {e}")
    if st.session_state.student_materials:
        st.markdown(st.session_state.student_materials)
    st.markdown("---")
    st.subheader("🧠 Differentiate This Lesson")
    if st.button("Generate Differentiation Strategies"):
        with st.spinner("💡 Coming up with strategies for diverse learners..."):
            try:
                diff_prompt = get_differentiation_prompt(st.session_state.ai_response)
            # --- Replace With This ---
message = client.messages.create(
    model="claude-3-5-sonnet-20240620",  # <--- Make sure there's a comma here
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}]
)
                st.session_state.differentiation_response = message.content[0].text
            except Exception as e: st.error(f"An error occurred while generating differentiation strategies: {e}")
    if st.session_state.differentiation_response:
        st.markdown(st.session_state.differentiation_response)
    st.markdown("---")
    st.subheader("📥 Download Your Plan")
    full_download_text = st.session_state.ai_response
    if st.session_state.parent_email: full_download_text += "\n\n---\n\n# Parent Communication Draft\n\n" + st.session_state.parent_email
    if st.session_state.student_materials: full_download_text += "\n\n---\n\n# Student-Facing Materials\n\n" + st.session_state.student_materials
    if st.session_state.differentiation_response: full_download_text += "\n\n---\n\n# Differentiation Strategies\n\n" + st.session_state.differentiation_response
    
    if full_download_text.strip():
        # Using plain text download as the primary, reliable option
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
                st.download_button(label="Download as Word Doc (.docx)", data=docx_file, file_name="sel_plan.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
