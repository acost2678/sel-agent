import streamlit as st

st.set_page_config(
    page_title="SEL Agent Login",
    page_icon="🧠",
)

def check_password():
    """Returns `True` if the user had the correct password."""
    if "password" not in st.secrets:
        st.error("Password not set. Please add a password to your .streamlit/secrets.toml file.")
        return False
    
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state.get("password") == st.secrets["password"]:
            st.session_state["password_correct"] = True
            # Store user email for admin check
            st.session_state["user_email"] = st.session_state.get("email", "")
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    
    if st.session_state.get("password_correct", False):
        return True
    
    st.title("🧠 SEL Integration Agent")
    st.markdown("### Welcome! Please sign in to continue.")
    
    # Email input (for admin identification)
    st.text_input(
        "Email Address",
        key="email",
        placeholder="your.email@school.edu",
        help="Enter your email address"
    )
    
    # Password input
    st.text_input(
        "Enter Password to Access", 
        type="password", 
        on_change=password_entered, 
        key="password"
    )
    
    if "password_correct" in st.session_state and not st.session_state.password_correct:
        st.error("😕 Password incorrect. Please try again.")
    
    return False

if check_password():
    st.switch_page("pages/app.py")



