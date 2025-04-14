#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import dash
from dash import dcc, html, Input, Output, State
import plotly.express as px
import plotly.graph_objects as go
import geopandas as gpd
import pandas as pd
import json
import zipfile
import os

# Initialize app (Render-specific setup)
app = dash.Dash(__name__)
server = app.server  # Required for Render

# ---------------------------
# Load and Prepare Data
# ---------------------------
# Define paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# Unzip GeoJSON files
def unzip_geojsons(zip_path, extract_to='data'):
    """Unzip GeoJSON files from a zip archive"""
    if not os.path.exists(extract_to):
        os.makedirs(extract_to)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

# Unzip data if needed (comment out after first run if files persist)
if not os.path.exists(os.path.join(DATA_DIR, 'geoBoundaries-CAN-ADM1_simplified.geojson')):
    unzip_geojsons(os.path.join(BASE_DIR, 'data.zip'), DATA_DIR)

# Load province polygons
try:
    with open(os.path.join(DATA_DIR, 'geoBoundaries-CAN-ADM1_simplified.geojson')) as f:
        geojson_data = json.load(f)
    gdf = gpd.GeoDataFrame.from_features(geojson_data['features'])
except Exception as e:
    print(f"Error loading province data: {str(e)}")
    # Create empty fallback data
    geojson_data = {"type": "FeatureCollection", "features": []}
    gdf = gpd.GeoDataFrame()

gdf = gdf.rename(columns={"shapeName": "Province"})
gdf.set_crs(epsg=4326, inplace=True)


# Define notable places per province (as lists)
province_to_places = {
    "Alberta": ["Banff NP", "Jasper NP", "Calgary Tower", "Lake Louise", "West Edmonton Mall"],
    "British Columbia": ["Stanley Park", "Butchart Gardens", "Whistler", "Capilano Bridge", "Pacific Rim NP"],
    "Manitoba": ["The Forks", "Riding Mountain NP", "Assiniboine Zoo", "Museum for Human Rights", "FortWhyte Alive"],
    "New Brunswick": ["Bay of Fundy", "Hopewell Rocks", "Fundy NP", "Reversing Falls", "Kings Landing"],
    "Newfoundland and Labrador": ["Gros Morne NP", "Signal Hill", "L'Anse aux Meadows", "Cape Spear", "Bonavista"],
    "Nova Scotia": ["Peggy's Cove", "Cabot Trail", "Halifax Citadel", "Lunenburg", "Kejimkujik NP"],
    "Ontario": ["CN Tower", "Niagara Falls", "Algonquin Park", "Parliament Hill", "Royal Ontario Museum"],
    "Prince Edward Island": ["Green Gables", "Cavindish Beach", "Confederation Trail", "PEI NP", "Point Prim Lighthouse"],
    "Quebec": ["Old Quebec", "Mont-Tremblant", "Montmorency Falls", "Quebec City", "Sainte-Anne-de-Beaupré"],
    "Saskatchewan": ["Forestry Zoo", "Wanuskewin", "Prince Albert NP", "Wascana Centre", "RCMP Heritage Centre"],
    "Northwest Territories": ["Nahanni NP", "Great Slave Lake", "Virginia Falls", "Yellowknife", "Wood Buffalo NP"],
    "Nunavut": ["Auyuittuq NP", "Sylvia Grinnell Park", "Qaummaarviit Park", "Iqaluit", "Sirmilik NP"],
    "Yukon": ["Kluane NP", "Miles Canyon", "SS Klondike", "Whitehorse", "Tombstone Park"]
}

# For hover info, add a comma-separated string of notable places to gdf
gdf["Notable Places"] = gdf["Province"].map(lambda prov: ", ".join(province_to_places[prov]))

# Load points-of-interest geoJSON as a GeoDataFrame
#poi_geojson_path = "hotosm_can_points_of_interest_points_geojson.geojson"
#points_gdf = gpd.read_file(poi_geojson_path)
#points_gdf.set_crs(epsg=4326, inplace=True)
#points_gdf = points_gdf.to_crs(gdf.crs)

# Replace your GeoJSON loading code with this more robust version:
try:
    points_gdf = gpd.read_file(os.path.join(DATA_DIR, "hotosm_can_points_of_interest_points_geojson.geojson"))
except Exception as e:
    print(f"Error loading GeoJSON: {str(e)}")
    # Fallback to empty DataFrame if needed
    points_gdf = gpd.GeoDataFrame()


# Precompute a DataFrame of only those POIs that match the notable places AND lie within the province boundary.
filtered_rows = []
for prov, places in province_to_places.items():
    # Use union_all() instead of unary_union
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
# Create a unique marker ID for each notable POI.
notable_df["marker_id"] = notable_df.apply(lambda row: f"{row['Province']}_{row['Place']}_{row.name}", axis=1)

# ---------------------------
# Initialize Dash App
# ---------------------------
app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1("Canada Provinces with Notable Places"),
    dcc.Dropdown(
        id='province-dropdown',
        options=[{'label': prov, 'value': prov} for prov in sorted(gdf['Province'].unique())],
        multi=True,
        placeholder="Select Provinces to highlight"
    ),
    # Store to hold the list of clicked markers
    dcc.Store(id='clicked-markers', data=[]),
    dcc.Graph(id='choropleth-map')
])

# ---------------------------
# Callback: Update Clicked Markers List
# ---------------------------
@app.callback(
    Output('clicked-markers', 'data'),
    Input('choropleth-map', 'clickData'),
    State('clicked-markers', 'data')
)
def update_clicked_markers(clickData, current_clicked):
    if clickData and 'points' in clickData:
        point = clickData['points'][0]
        # customdata contains our unique marker ID
        if 'customdata' in point:
            marker_id = point['customdata']
            # Add to list if not already present
            if marker_id not in current_clicked:
                return current_clicked + [marker_id]
    return current_clicked

# ---------------------------
# Callback: Update Map Based on Province Selection and Clicked Markers
# ---------------------------
@app.callback(
    Output('choropleth-map', 'figure'),
    Input('province-dropdown', 'value'),
    Input('clicked-markers', 'data')
)
def update_map(selected_provinces, clicked_markers):
    # If no province is selected, display all provinces in light gray.
    if not selected_provinces:
        fig = px.choropleth_mapbox(
            gdf,
            geojson=geojson_data,
            locations='Province',
            featureidkey="properties.shapeName",
            color_discrete_sequence=["lightgray"],
            hover_data=["Province", "Notable Places"],
            mapbox_style="carto-positron",
            zoom=2,
            center={"lat": 56.130, "lon": -106.347},
            opacity=0.5,
        )
        fig.update_layout(margin={"r":0, "t":0, "l":0, "b":0})
        return fig

    # Otherwise, filter to the selected provinces (displayed in blue).
    filtered_gdf = gdf[gdf["Province"].isin(selected_provinces)]
    filtered_geojson = {
        "type": "FeatureCollection",
        "features": [feat for feat in geojson_data['features']
                     if feat['properties']['shapeName'] in selected_provinces]
    }
    fig = px.choropleth_mapbox(
        filtered_gdf,
        geojson=filtered_geojson,
        locations='Province',
        featureidkey="properties.shapeName",
        color_discrete_sequence=["blue"],
        hover_data=["Province", "Notable Places"],
        mapbox_style="carto-positron",
        zoom=2,
        center={"lat": 56.130, "lon": -106.347},
        opacity=0.7,
    )

    # Filter our precomputed notable_df to only include markers in the selected provinces.
    marker_subset = notable_df[notable_df["Province"].isin(selected_provinces)]
    
    # Set marker color to green if its unique ID is in clicked_markers, else red
    marker_colors = ["green" if marker_id in clicked_markers else "red" 
                     for marker_id in marker_subset["marker_id"]]
    
    if not marker_subset.empty:
        fig.add_trace(go.Scattermapbox(
            lat=marker_subset["lat"],
            lon=marker_subset["lon"],
            mode='markers',
            marker=dict(size=10, color=marker_colors),
            text=marker_subset["Place"],
            customdata=marker_subset["marker_id"],
            hoverinfo='text'
        ))
    
    fig.update_layout(margin={"r":0, "t":0, "l":0, "b":0})
    return fig

    
if __name__ == '__main__':
    app.run_server(host='0.0.0.0', port=int(os.environ.get('PORT', 8050)), debug=False)

