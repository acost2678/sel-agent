import streamlit as st
import anthropic
import os

st.set_page_config(page_title="Agent Home", page_icon="🏠", layout="wide")

# --- Initialize API Client and Store in Session State ---
# This block runs once after login and makes the client available to all pages.
if "client" not in st.session_state:
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
        st.session_state.client = anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        st.error(f"Could not initialize API client: {e}")
        st.stop()

# Verify the user is logged in
if not st.session_state.get("password_correct", False):
    st.switch_page("login.py")

st.title("Welcome to Your Teacher Support Agent")
st.markdown("Please choose a tool to get started.")

col1, col2 = st.columns(2)

with col1:
    with st.container(border=True):
        st.header("🧠 SEL Integration Agent")
        st.markdown("Your AI coach for integrating Social-Emotional Learning into your lessons. Analyze existing plans, create new ones, and generate student materials.")
        if st.button("Go to SEL Agent"):
            st.switch_page("pages/app.py")

with col2:
    with st.container(border=True):
        st.header("👩‍⚕️ Teacher Wellness")
        st.markdown("Tools and resources to support your mental health and well-being. Find mindfulness exercises, reframe challenges, and plan for self-care.")
        if st.button("Go to Wellness Tools"):
            st.switch_page("pages/wellness.py")
