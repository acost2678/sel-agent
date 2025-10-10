import streamlit as st

# --- Page Setup and Login Check ---
st.set_page_config(page_title="Teacher Wellness", page_icon="👩‍⚕️", layout="wide")

# Verify the user is logged in and retrieve the client
if not st.session_state.get("password_correct", False):
    st.switch_page("login.py")
client = st.session_state.client

# --- Prompt Engineering Functions ---

def get_boundary_email_prompt(scenario):
    return f"""
    You are an expert communication coach specializing in helping educators set healthy boundaries. Your tone is supportive, firm, and highly professional.
    A teacher needs help drafting an email for the following scenario: "{scenario}"

    Your task is to draft a clear, polite, and firm email that the teacher can adapt. The email should:
    1.  Acknowledge the other person's perspective (if applicable).
    2.  Clearly state the boundary or position.
    3.  Be brief and professional, avoiding over-explaining or apologizing excessively.
    4.  End on a collaborative and positive note where possible.

    Draft the email now.
    """

def get_reframe_prompt(negative_thought):
    return f"""
    You are a compassionate wellness coach using principles from Cognitive Behavioral Therapy (CBT). A teacher is experiencing a negative thought and needs help reframing it.
    Their thought is: "{negative_thought}"

    Your task is to respond in two parts:
    1.  **Validation:** Start by validating their feeling in one brief, empathetic sentence. (e.g., "That sounds like a really tough and discouraging feeling.")
    2.  **Gentle Challenge/Reframing:** Ask 1-2 open-ended, Socratic-style questions to help them challenge the thought and find a more balanced perspective. Do not give advice. Guide them to their own conclusion. Examples of good questions include:
        - "Is there any evidence that contradicts that thought?"
        - "What is a more compassionate or balanced way of looking at this situation?"
        - "If a friend described this exact situation to you, what would you tell them?"
    """

def get_destress_prompt():
    return f"""
    You are a mindfulness coach. A teacher has clicked a button for a "Quick De-Stress" tip.
    Your task is to provide one single, simple, actionable exercise that can be completed in 1-3 minutes at a desk.
    Choose from one of the following categories:
    - A simple breathing exercise (e.g., box breathing, 4-7-8 breath).
    - A short mindfulness prompt (e.g., notice 3 things you can see, 2 you can hear).
    - A quick physical stretch (e.g., neck roll, shoulder shrug).
    - A positive affirmation.

    Provide only the name of the exercise as a heading and the simple, step-by-step instructions. Keep it brief and direct.
    """

# --- USER INTERFACE ---

st.title("👩‍⚕️ Teacher Wellness Toolkit")
st.markdown("Practical tools to support your well-being.")
st.markdown("---")

# Create tabs for each feature
tab1, tab2, tab3 = st.tabs(["Boundary Builder", "Reframe Your Thoughts", "Quick De-Stress"])

with tab1:
    st.header("✉️ The Boundary Builder")
    st.info("Draft professional emails to protect your time and energy.")

    boundary_scenarios = [
        "Responding to a parent who communicates outside of work hours",
        "Declining an extra, unpaid responsibility",
        "Requesting a mental health day from administration",
        "Setting expectations for email response times with parents"
    ]
    scenario = st.selectbox("Choose a scenario:", options=boundary_scenarios)

    if st.button("Draft Email"):
        with st.spinner("Drafting your professional response..."):
            try:
                prompt = get_boundary_email_prompt(scenario)
                message = client.messages.create(
                    model="claude-2.1", max_tokens=1024, messages=[{"role": "user", "content": prompt}]
                )
                st.text_area("Email Draft:", value=message.content[0].text, height=300)
            except Exception as e:
                st.error(f"Could not generate email: {e}")

with tab2:
    st.header("🧠 The Positive Reframing Tool")
    st.info("Use this CBT-based tool to challenge and reframe negative thoughts.")

    neg_thought = st.text_area("What's a stressful or negative thought on your mind?", placeholder="e.g., 'My lesson today was a complete failure and the students were bored.'")

    if st.button("Help Me Reframe This"):
        if neg_thought:
            with st.spinner("Finding a new perspective..."):
                try:
                    prompt = get_reframe_prompt(neg_thought)
                    message = client.messages.create(
                        model="claude-2.1", max_tokens=1024, messages=[{"role": "user", "content": prompt}]
                    )
                    st.success(message.content[0].text)
                except Exception as e:
                    st.error(f"Could not generate reframing: {e}")
        else:
            st.warning("Please enter a thought to reframe.")

with tab3:
    st.header("🧘 The Quick De-Stress Generator")
    st.info("Click the button for an immediate, simple action you can take to de-escalate stress.")

    if st.button("Give Me a 1-Minute De-Stress Tip"):
        with st.spinner("Finding a mindful moment..."):
            try:
                prompt = get_destress_prompt()
                message = client.messages.create(
                    model="claude-2.1", max_tokens=512, messages=[{"role": "user", "content": prompt}]
                )
                st.markdown(f"--- \n {message.content[0].text}")
            except Exception as e:
                st.error(f"Could not generate tip: {e}")

# --- Navigation Button ---
st.markdown("---")
if st.button("⬅️ Go back to Home"):
    st.switch_page("pages/home.py")
