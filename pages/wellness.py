import streamlit as st

st.set_page_config(page_title="Teacher Wellness", page_icon="👩‍⚕️", layout="wide")

# Verify the user is logged in
if not st.session_state.get("password_correct", False):
    st.switch_page("login.py")

st.title("👩‍⚕️ Teacher Wellness Toolkit")
st.markdown("---")
st.info("This feature is coming soon!")

if st.button("⬅️ Go back to Home"):
    st.switch_page("pages/home.py")
