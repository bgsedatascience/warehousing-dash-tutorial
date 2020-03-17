import dash
import dash_html_components as html
import dash_core_components as dcc
import plotly.graph_objs as go
import records
import pandas as pd
from dash.dependencies import Input, Output
from datetime import datetime
from dateutil.relativedelta import relativedelta

timeseries_query = """
with t as (select country, dt, extract(year from dt) as year, extract(week from dt) as week, sales_amount from order_facts left join dates on date_id=id left join employees using (employee_number) order by dt) select sum(sales_amount)::numeric as sales_amount, min(dt) as dt, year, week, country from t group by week, year, country;
"""

top_products_query = """
SELECT product_name, SUM(sales_amount)::numeric AS sales_amount
FROM order_facts
LEFT JOIN products USING (product_code)
LEFT JOIN dates ON date_id=id
LEFT JOIN employees USING (employee_number)
WHERE dt > :start AND dt < :finish
GROUP BY product_code, product_name
ORDER BY sales_amount DESC
LIMIT :n;
"""

top_products_by_country_query = """
WITH t AS
     (WITH products_per_country AS
         (SELECT country, product_code, product_name, SUM(sales_amount) AS sales_amount
         FROM order_facts
         LEFT JOIN products USING (product_code)
         LEFT JOIN employees USING (employee_number)
         LEFT JOIN dates ON date_id=id
         WHERE dt > :start AND dt < :finish
         GROUP BY product_code, product_name, employees.country)
     SELECT country, product_name, sales_amount, ROW_NUMBER() OVER (PARTITION BY country ORDER BY sales_amount DESC)
     FROM products_per_country)
SELECT country, product_name, sales_amount::numeric
FROM t
WHERE row_number <= :n
"""


analytics = records.Database('postgres://postgres@0.0.0.0/analytics')
app = dash.Dash('dash-tutorial')

def get_data_timerange():
    query = 'select min(dt), max(dt) from order_facts left join dates on date_id=id'
    d = analytics.query(query).as_dict()[0]
    return d['min'], d['max']

def get_marks(start, end):
    result = []
    current = start
    while current <= end:
        result.append(current)
        current += relativedelta(months=3)
    return {int(m.timestamp()): m.strftime('%Y-%m') for m in result}

MIN_TIME, MAX_TIME = get_data_timerange()

app.layout = html.Div(className = 'layout', children = [
    html.H1(className = 'title', children = 'Classic Models Dashboard'),
    html.H4('My subtitle for my cool dashboard', className='subtitle'),
    dcc.Graph(id='timeline', figure={}),
    html.Div(className='timeline-controls', children = [
        dcc.Checklist(id = 'country-checkbox',
                      options = [ {'label': 'By Country', 'value': 'by_country'}]),
        dcc.RangeSlider(
            id='year-slider',
            min=MIN_TIME.timestamp(),
            max=MAX_TIME.timestamp(),
            value=[MIN_TIME.timestamp(), MAX_TIME.timestamp()],
            marks = get_marks(MIN_TIME, MAX_TIME)
        )
    ]),
    dcc.Graph(id='products', figure = {})
])


@app.callback(
    Output('timeline', 'figure'),
    [Input('country-checkbox', 'value'),
     Input('year-slider', 'value')]
)
def timeline(boxes, time_range):
    start, finish = [datetime.fromtimestamp(t) for t in time_range]
    dat = analytics.query(timeseries_query).as_dict()
    df = pd.DataFrame(dat)

    df = df[(df['dt'] > start) & (df['dt'] < finish)]

    if boxes and 'by_country' in boxes:
        data = [go.Scatter(x = d.dt,
                           y = d.sales_amount,
                           ids = d.index,
                           mode = 'markers',
                           name = country) for country, d in df.groupby('country')]

    else:
        df = df \
            .groupby(['week', 'year']) \
            .agg({ 'sales_amount': 'sum', 'dt': 'first'})

        data = [go.Scatter(x = df.dt,
                           y = df.sales_amount,
                           ids = df.index,
                           mode = 'markers')]

    return {
        'data': data,
        'layout': {
            'title': 'Sales Over Time'
        }
    }

@app.callback(
    Output('products', 'figure'),
    [Input('country-checkbox', 'value'),
     Input('year-slider', 'value')]
)
def products(boxes, time_range):
    start, finish = [datetime.fromtimestamp(t) for t in time_range]

    if boxes and 'by_country' in boxes:
        res = analytics.query(top_products_by_country_query, n = 3, start = start, finish = finish)
        df = pd.DataFrame(res.as_dict())
        data = [go.Bar(ids = d.index,
                       x = d.sales_amount,
                       y = d.country,
                       orientation='h',
                       name = product)
                for product,d in df.groupby('product_name')]

    else:
        res = analytics.query(top_products_query, n = 5, start = start, finish = finish)
        df = pd.DataFrame(res.as_dict())
        data = [go.Bar(ids = df.index,
                       x = df.sales_amount,
                       y = df.product_name,
                       orientation='h')]

    return {'data': data,
            'layout': {'title': 'Most Profitable Products',
                       'yaxis': {'automargin': True},
                       'barmode': 'stack' }}

app.run_server(debug=True)
