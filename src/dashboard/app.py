import streamlit as st

st.set_page_config(
    page_title="Nifty 100 Analytics",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("Nifty 100 Analytics Dashboard")
st.write("Welcome to the Nifty 100 Analytics Dashboard. Please select a page from the sidebar to begin.")

# Streamlit automatically builds sidebar navigation from the pages/ directory.
