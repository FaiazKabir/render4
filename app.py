#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import os
import zipfile
import json

import dash
from dash import dcc, html, Input, Output, State
import plotly.express as px
import plotly.graph_objects as go
import geopandas as gpd
import pandas as pd

# ──────────────────────────────────────────────────────────────────────────────
# Initialize Dash & expose the Flask server for Render’s Gunicorn
# ──────────────────────────────────────────────────────────────────────────────
app = dash.Dash(__name__, suppress_callback_exceptions=True)
server = app.server   # <-- this is what Render’s Gunicorn will look for

# ──────────────────────────────────────────────────────────────────────────────
# Load & Prepare Data (exactly as you had it)
# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def unzip_geojsons(zip_path, extract_to=DATA_DIR):
    if not os.path.exists(extract_to):
        os.makedirs(extract_to)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

if not os.path.exists(os.path.join(DATA_DIR, 'geoBoundaries-CAN-ADM1_simplified.geojson')):
    unzip_geojsons(os.path.join(BASE_DIR, 'data.zip'))

# load provinces
with open(os.path.join(DATA_DIR, 'geoBoundaries-CAN-ADM1_simplified.geojson')) as f:
    geojson_data = json.load(f)
gdf = gpd.GeoDataFrame.from_features(geojson_data['features'])
gdf = gdf.rename(columns={"shapeName": "Province"})
gdf.set_crs(epsg=4326, inplace=True)

# your province_to_places dict…
province_to_places = { … }

gdf["Notable Places"] = gdf["Province"].map(lambda prov: ", ".join(province_to_places.get(prov, [])))

# load POIs
try:
    points_gdf = gpd.read_file(os.path.join(DATA_DIR, "hotosm_can_points_of_interest_points_geojson.geojson"))
    points_gdf.set_crs(epsg=4326, inplace=True)
except Exception:
    points_gdf = gpd.GeoDataFrame()

# build notable_df exactly as before…
filtered_rows = []
for prov, places in province_to_places.items():
    province_poly = gdf[gdf["Province"] == prov].geometry.union_all()
    for place in places:
        matches = points_gdf[points_gdf["name"].str.contains(place, case=False, na=False)]
        for _, row in matches.iterrows():
            if row.geometry.within(province_poly):
                filtered_rows.append({
                    "Province": prov,
                    "Place": place,
                    "lat": row.geometry.y,
                    "lon": row.geometry.x
                })

notable_df = pd.DataFrame(filtered_rows)
notable_df["marker_id"] = notable_df.apply(
    lambda row: f"{row['Province']}_{row['Place']}_{row.name}", axis=1
)

# ──────────────────────────────────────────────────────────────────────────────
# Layout & Callbacks (exactly as you had them)
# ──────────────────────────────────────────────────────────────────────────────
app.layout = html.Div([
    html.H1("Canada Provinces with Notable Places"),
    dcc.Dropdown(
        id='province-dropdown',
        options=[{'label': prov, 'value': prov} for prov in sorted(gdf['Province'].unique())],
        multi=True,
        placeholder="Select Provinces to highlight"
    ),
    dcc.Store(id='clicked-markers', data=[]),
    dcc.Graph(id='choropleth-map')
])

@app.callback(
    Output('clicked-markers', 'data'),
    Input('choropleth-map', 'clickData'),
    State('clicked-markers', 'data')
)
def update_clicked_markers(clickData, current_clicked):
    if clickData and 'points' in clickData:
        pt = clickData['points'][0]
        if 'customdata' in pt:
            mid = pt['customdata']
            if mid not in current_clicked:
                return current_clicked + [mid]
    return current_clicked

@app.callback(
    Output('choropleth-map', 'figure'),
    Input('province-dropdown', 'value'),
    Input('clicked-markers', 'data')
)
def update_map(selected_provinces, clicked_markers):
    # … your exact logic for drawing the map and markers …
    # (unchanged)
    return fig

# ──────────────────────────────────────────────────────────────────────────────
# Only run this when doing `python app.py` locally.
# On Render we’ll use Gunicorn and the `server` object instead.
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    app.run_server(host='0.0.0.0', port=port, debug=False)

