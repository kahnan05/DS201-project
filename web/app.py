import streamlit as st
import pandas as pd
import numpy as np

# 1. Text and Titles
st.title("My First Streamlit App")
st.write("Welcome! Adjust the slider below to update the chart.")

# 2. Interactive Widgets
number = st.slider("Select number of data points", min_value=10, max_value=100, value=50)
name = st.text_input("Enter your name", "Guest")

if st.button("Greet Me"):
    st.success(f"Hello, {name}!")

# 3. Data and Charts
data = pd.DataFrame(
    np.random.randn(number, 2),
    columns=["Series A", "Series B"]
)
st.line_chart(data)