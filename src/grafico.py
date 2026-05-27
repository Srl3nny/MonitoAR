#!/usr/bin/env python3
import dash
from dash import dcc, callback
from dash import html, dash_table
from dash.dependencies import Input, Output
import plotly.express as px
import pandas as pd
import sqlite3
import time

databases = "/home/pi/projeto-monitoAR/dados_temp.db"

def load_data():
    conn = sqlite3.connect(databases)
    query = "SELECT * FROM dados_climaticos ORDER by data_hora DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

app = dash.Dash(__name__)

df = load_data()

app.layout = html.Div([
    html.Div(children="Dados de temperatura e Umidade"),
    dcc.DatePickerRange(
        id='date-picker-range',
        start_date=df['data_hora'].min(),
        end_date=df['data_hora'].max(),
        display_format='YYYY-MM-DD'
    ),
    dash_table.DataTable(data=df.to_dict('records'), page_size=10),
    dcc.RadioItems(options=['temperatura', 'umidade'], value='temperatura', id='controls-and-radio-item'),
    dcc.Graph(figure={}, id='controls-and-graph'),
    #dcc.Graph(id='grafico temp', figure=px.histogram(df,x='data_hora', y='temperatura', histfunc='avg' )),

])

@app.callback(
    Output('controls-and-graph', 'figure'),
    Input('controls-and-radio-item', 'value'),
    Input('date-picker-range', 'start_date'),
    Input('date-picker-range', 'end_date')
)

def update_graph(selected, start_date, end_date):
    filtered_df = df[(df['data_hora'] >= start_date) & (df['data_hora'] <= end_date)]
    fig = px.histogram(filtered_df, x='data_hora', y=selected, histfunc='avg')
    return fig

if __name__ == "__main__":
    app.run_server(host='0.0.0.0', debug=True, port=80)
