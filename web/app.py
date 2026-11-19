import streamlit as st
import pandas as pd
import plotly.express as px

countries = {"United States": "USA", "Brazil": "BRA", "Japan": "JPN", "Australia": "AUS"}

name = st.selectbox("Highlight a country", list(countries))

df = pd.DataFrame({"country": [countries[name]], "value": [1]})

fig = px.choropleth(df, locations="country", color="value",
                    hover_name=[name], projection="cylindrical stereographic")
fig.update_layout(coloraxis_showscale=False)

st.plotly_chart(fig)