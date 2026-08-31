#!/usr/bin/env python3
import dash
from dash import dcc, callback
from dash import html, dash_table
from dash.dependencies import Input, Output
import plotly.express as px
import pandas as pd
import sqlite3
from datetime import timedelta

databases = "/home/pi/projeto-monitoAR/dados_temp.db"

def db_connect():
    return sqlite3.connect(databases, timeout=15)

def date_filter(start_date=None, end_date=None):
    where = []
    params = []

    if start_date:
        where.append("data_hora >= ?")
        params.append(str(pd.to_datetime(start_date).date()))

    if end_date:
        end_exclusive = pd.to_datetime(end_date) + timedelta(days=1)
        where.append("data_hora < ?")
        params.append(end_exclusive.strftime("%Y-%m-%d"))

    clause = ""
    if where:
        clause = " WHERE " + " AND ".join(where)

    return clause, params

def get_date_bounds():
    conn = db_connect()
    query = "SELECT min(data_hora) as min_data, max(data_hora) as max_data FROM dados_climaticos"
    bounds = pd.read_sql_query(query, conn)
    conn.close()

    min_data = pd.to_datetime(bounds.loc[0, 'min_data'])
    max_data = pd.to_datetime(bounds.loc[0, 'max_data'])
    return min_data, max_data

def load_graph_data(start_date=None, end_date=None):
    start = pd.to_datetime(start_date) if start_date else None
    end = pd.to_datetime(end_date) if end_date else None
    days = (end - start).days if start is not None and end is not None else 0
    clause, params = date_filter(start_date, end_date)

    if days > 31:
        bucket = "date(data_hora)"
        granularity = "dia"
    elif days > 2:
        bucket = "strftime('%Y-%m-%d %H:00:00', data_hora)"
        granularity = "hora"
    else:
        bucket = "data_hora"
        granularity = "leitura"

    query = f"""
        SELECT
            {bucket} AS data_hora,
            avg(temperatura) AS temperatura,
            avg(umidade) AS umidade,
            count(*) AS leituras
        FROM dados_climaticos
        {clause}
        GROUP BY {bucket}
        ORDER BY data_hora ASC
    """

    conn = db_connect()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if not df.empty:
        df['data_hora'] = pd.to_datetime(df['data_hora'])

    return df, granularity

def load_table_data(start_date=None, end_date=None):
    clause, params = date_filter(start_date, end_date)
    query = f"""
        SELECT id, data_hora, temperatura, umidade
        FROM dados_climaticos
        {clause}
        ORDER BY data_hora DESC
        LIMIT 100
    """

    conn = db_connect()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    return df

app = dash.Dash(__name__)

min_data, max_data = get_date_bounds()
default_start = (max_data - timedelta(days=1)).date()
default_end = max_data.date()

app.layout = html.Div([
    html.Div(children="Dados de temperatura e Umidade"),
    dcc.Interval(id='refresh-interval', interval=60 * 1000, n_intervals=0),
    dcc.DatePickerRange(
        id='date-picker-range',
        min_date_allowed=min_data.date(),
        max_date_allowed=(max_data + timedelta(days=365)).date(),
        start_date=default_start,
        end_date=default_end,
        display_format='YYYY-MM-DD'
    ),
    dash_table.DataTable(id='data-table', data=[], page_size=10),
    dcc.RadioItems(options=['temperatura', 'umidade'], value='temperatura', id='controls-and-radio-item'),
    dcc.Graph(figure={}, id='controls-and-graph'),
    html.Div(id='last-update'),
    #dcc.Graph(id='grafico temp', figure=px.histogram(df,x='data_hora', y='temperatura', histfunc='avg' )),

])

@app.callback(
    Output('controls-and-graph', 'figure'),
    Output('data-table', 'data'),
    Output('last-update', 'children'),
    Input('controls-and-radio-item', 'value'),
    Input('date-picker-range', 'start_date'),
    Input('date-picker-range', 'end_date'),
    Input('refresh-interval', 'n_intervals')
)

def update_graph(selected, start_date, end_date, n_intervals):
    df, granularity = load_graph_data(start_date, end_date)
    if df.empty:
        return {}, [], "Sem dados para o periodo selecionado"

    fig = px.line(df, x='data_hora', y=selected, markers=True)
    table_data = load_table_data(start_date, end_date).to_dict('records')
    latest = df['data_hora'].max().strftime("%Y-%m-%d %H:%M:%S")
    return fig, table_data, f"Ultima leitura no periodo: {latest}. Grafico agregado por {granularity}."

if __name__ == "__main__":
    app.run_server(host='0.0.0.0', debug=False, port=80, use_reloader=False)
