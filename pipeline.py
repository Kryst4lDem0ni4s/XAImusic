import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
import seaborn as sns
import matplotlib.pyplot as plt
# import kagglehub
# # Download latest version
# path = kagglehub.dataset_download("maharshipandya/-spotify-tracks-dataset")
# print("Path to dataset files:", path)

# -------------------------------
# MODULE 1: DATA INGESTION & STORAGE
# -------------------------------
def load_spotify_track_metadata(filename="spotify_data.csv"):
    """
    Load track metadata from the Spotify dataset CSV file.
    Expected columns (for example):
      - track_id
      - track_name
      - artist
      - album_name
      - release_date
      - popularity
      - danceability
      - energy
      - key
      - loudness
      - mode
      - speechiness
      - acousticness
      - instrumentalness
      - liveness
      - valence
      - tempo
      - duration_ms
      - time_signature
    """
    try:
        df = pd.read_csv(filename)
        print(f"Loaded Spotify track metadata from {filename}")
        return df
    except Exception as e:
        print(f"Error loading Spotify dataset: {e}")
        return pd.DataFrame()

def simulate_user_interactions(num_entries=100, track_ids=None):
    """
    Simulate real-time ingestion of user interactions using Spotify track IDs.
    Expected Data: DataFrame with columns:
      - user_id (int)
      - track_id (int)
      - action (str): one of ['play', 'skip', 'like', 'playlist_add']
      - timestamp (datetime)
    """
    actions = ['play', 'skip', 'like', 'playlist_add']
    data = []
    user_ids = list(range(1, 11))  # simulate 10 users
    if track_ids is None:
        # If no track_ids are provided, use a default range
        track_ids = list(range(1, 101))
    now = datetime.now()

    for _ in range(num_entries):
        user = random.choice(user_ids)
        track = random.choice(track_ids)
        action = random.choice(actions)
        # Random timestamp within the last 24 hours
        ts = now - timedelta(seconds=random.randint(0, 86400))
        data.append({
            'user_id': user,
            'track_id': track,
            'action': action,
            'timestamp': ts
        })
    return pd.DataFrame(data)

def simulate_contextual_data(num_entries=100):
    """
    Simulate contextual metadata for each interaction.
    Expected Data: DataFrame with columns:
      - user_id (int)
      - timestamp (datetime)
      - mood (float): simulated mood score between 0 and 1
      - device (str): e.g., 'mobile' or 'desktop'
      - location (str): e.g., dummy city names
    """
    data = []
    devices = ['mobile', 'desktop']
    locations = ['CityA', 'CityB', 'CityC']
    now = datetime.now()

    for _ in range(num_entries):
        user = random.randint(1, 10)
        ts = now - timedelta(seconds=random.randint(0, 86400))
        data.append({
            'user_id': user,
            'timestamp': ts,
            'mood': round(random.uniform(0, 1), 2),
            'device': random.choice(devices),
            'location': random.choice(locations)
        })
    return pd.DataFrame(data)

def persist_time_series_data(df, filename="time_series_data.csv"):
    """
    Persist the interactions data to a CSV file for long-term analysis.
    """
    df.to_csv(filename, index=False)
    print(f"Persisted time-series data to {filename}")

def ingest_data(spotify_filename="spotify_data.csv", num_interactions=100):
    """
    Ingest data from the Spotify dataset and simulate user interactions and contextual data.
    """
    # Load Spotify track metadata
    track_metadata = load_spotify_track_metadata(spotify_filename)
    
    # Use track_ids from the dataset if available
    if not track_metadata.empty and 'track_id' in track_metadata.columns:
        track_ids = track_metadata['track_id'].tolist()
    else:
        track_ids = list(range(1, 101))
    
    # Simulate user interactions and contextual data
    interactions = simulate_user_interactions(num_entries=num_interactions, track_ids=track_ids)
    context = simulate_contextual_data(num_entries=num_interactions)
    
    # Persist interactions for later time-series analysis
    persist_time_series_data(interactions)
    
    return {
        'interactions': interactions,
        'tracks': track_metadata,
        'context': context
    }

# -------------------------------
# MODULE 2: DATA PROCESSING & WRANGLING
# -------------------------------
def preprocess_data(raw_data):
    """
    Clean and wrangle raw data.
    Operations:
      - Remove missing values.
      - Merge interactions with contextual data (using user_id and nearest timestamp).
      - Merge with Spotify track metadata to add track details.
      - Compute session IDs (new session if time gap > 5 minutes).
    """
    interactions_df = raw_data['interactions'].dropna()
    context_df = raw_data['context'].dropna()
    tracks_df = raw_data['tracks'].dropna()
    
    tracks_df['artists']
    
    # Check if required columns exist in tracks_df
    required_columns = ['track_id', 'artists', 'track_name']
    missing_columns = [col for col in required_columns if col not in tracks_df.columns]
    
    if missing_columns:
        print(f"Warning: Missing columns in track data: {missing_columns}")
        # Add missing columns with placeholder values
        for col in missing_columns:
            tracks_df[col] = f"Unknown {col.replace('_', ' ').title()}"
    
    # Merge interactions with context using nearest timestamp (within 1 minute tolerance)
    merged_df = pd.merge_asof(
        interactions_df.sort_values('timestamp'),
        context_df.sort_values('timestamp'),
        on='timestamp',
        by='user_id',
        direction='nearest',
        tolerance=pd.Timedelta("1min")
    )
    
    # Merge with Spotify track metadata to obtain 'artists' and 'track_name'
    merged_df = pd.merge(merged_df, tracks_df[['track_id', 'artists', 'track_name']], on='track_id', how='left')
    
    # Debug: Show merged DataFrame structure
    print("Merged DataFrame after merging interactions and context:")
    print(merged_df.head())
    print("Columns in merged_df:", merged_df.columns.tolist())
    
    # Validate that 'artists' exists; if missing, fill with 'Unknown Artist'
    if 'artists' not in merged_df.columns:
        raise ValueError("'artists' column is missing after merging. Check the Spotify dataset.")
    elif merged_df['artists'].isna().any():
        print("Warning: Some tracks have missing artists. Filling with 'Unknown Artist'.")
        merged_df['artists'] = merged_df['artists'].fillna('Unknown Artist')
    
    # Compute session_id: start a new session if time difference > 5 minutes (300 sec)
    merged_df = merged_df.sort_values(['user_id', 'timestamp'])
    merged_df.reset_index(drop=True, inplace=True)
    merged_df['session_diff'] = merged_df.groupby('user_id')['timestamp'].diff().dt.total_seconds().fillna(0)
    merged_df['session_id'] = merged_df.groupby('user_id')['session_diff'].apply(lambda x: (x > 300).cumsum()).reset_index(drop=True)
    
    return merged_df

# -------------------------------
# MODULE 3: VISUALIZATION FOR DATA ANALYTICS
# -------------------------------
def visualize_raw_analytics(processed_df):
    """
    Create visualizations for the raw analytics.
    Displays:
      - Heatmap: Number of plays by hour.
      - Leaderboard: Total interactions per artist.
    """
    # Validate required columns
    required_columns = ['timestamp', 'artists']
    missing_cols = [col for col in required_columns if col not in processed_df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns in processed data: {missing_cols}")
    
    # Extract hour from timestamp
    processed_df['hour'] = processed_df['timestamp'].dt.hour
    
    # Create heatmap data: count of plays per hour
    heatmap_data = processed_df.groupby('hour').size().reset_index(name='plays')
    
    plt.figure(figsize=(10, 6))
    sns.heatmap(heatmap_data[['plays']].T, annot=True, cmap="YlGnBu", cbar=False,
                yticklabels=['Plays'], xticklabels=heatmap_data['hour'])
    plt.title("User Plays by Hour")
    plt.xlabel("Hour of Day")
    plt.ylabel("")
    plt.show()
    
    # Leaderboard: Total interactions per artist
    leaderboard = processed_df.groupby('artists').size().reset_index(name='total_interactions')
    plt.figure(figsize=(10, 4))
    sns.barplot(x='artists', y='total_interactions', data=leaderboard)
    plt.title("Artist Leaderboard")
    plt.xlabel("Artist")
    plt.ylabel("Total Interactions")
    plt.xticks(rotation=45)
    plt.show()

# -------------------------------
# MODULE 4: MACHINE LEARNING PIPELINE COMPONENTS (Simulated)
# -------------------------------
def extract_audio_features(track_metadata):
    """
    Extract audio features from the Spotify dataset.
    Expected audio feature columns (for example):
      ['danceability', 'energy', 'key', 'loudness', 'mode',
       'speechiness', 'acousticness', 'instrumentalness',
       'liveness', 'valence', 'tempo']
    Returns:
      - audio_features: Dict mapping track_id to its audio feature dictionary.
    """
    feature_cols = ['danceability', 'energy', 'key', 'loudness', 'mode',
                    'speechiness', 'acousticness', 'instrumentalness',
                    'liveness', 'valence', 'tempo']
    audio_features = {}
    for _, row in track_metadata.iterrows():
        features = {col: row[col] for col in feature_cols if col in row}
        audio_features[row['track_id']] = features
    return audio_features

def fuse_features(audio_features, context_df):
    """
    Simulate fusion of audio features with contextual metadata.
    For simplicity, adds a dummy 'mood_factor' (average mood across interactions) to each track's features.
    """
    fused_features = {}
    avg_mood = context_df['mood'].mean() if not context_df.empty else 0.5
    for track_id, features in audio_features.items():
        fused = features.copy()
        fused['mood_factor'] = avg_mood
        fused_features[track_id] = fused
    return fused_features

def build_interaction_graph(processed_df, fused_features, track_metadata):
    """
    Build a heterogeneous graph of users, tracks, and artists.
    Returns:
      - graph: Dict containing nodes, edges, and track-to-artist mapping.
    """
    users = set(processed_df['user_id'].unique())
    tracks = set(processed_df['track_id'].unique())
    artists = set(processed_df['artists'].unique())
    
    # Build track-to-artist mapping from the Spotify track metadata
    track_to_artist = dict(zip(track_metadata['track_id'], track_metadata['artists']))
    
    # Build edges: (user_id, track_id, weight) based on interaction action
    edges = []
    for _, row in processed_df.iterrows():
        action = row['action']
        if action == 'play':
            weight = 1.0
        elif action == 'skip':
            weight = 0.5
        elif action == 'like':
            weight = 1.5
        elif action == 'playlist_add':
            weight = 1.2
        else:
            weight = 1.0
        edges.append((row['user_id'], row['track_id'], weight))
    
    # Simulate application of graph models (e.g., TGNN, GAT) by a dummy adjustment
    weighted_edges = apply_graph_models(edges)
    
    graph = {
        'nodes': {
            'users': users,
            'tracks': tracks,
            'artists': artists
        },
        'edges': edges,
        'weighted_edges': weighted_edges,
        'track_to_artist': track_to_artist
    }
    return graph

def apply_graph_models(edges):
    """
    Simulate graph model adjustments (e.g., TGNN and GAT).
    Returns:
      - weighted_edges: List of tuples (user_id, track_id, adjusted_weight).
    """
    weighted_edges = []
    for (user, track, weight) in edges:
        adjusted_weight = weight * 1.2  # dummy adjustment factor
        weighted_edges.append((user, track, adjusted_weight))
    return weighted_edges

def extract_latent_features(fused_features):
    """
    Simulate latent feature extraction (e.g., via a Variational Autoencoder).
    Returns:
      - latent_features: Dict mapping track_id to a latent feature vector (simulated).
    """
    latent_features = {}
    for track_id, features in fused_features.items():
        latent_features[track_id] = {k: v * 0.8 for k, v in features.items()}
    return latent_features

def adaptive_recommendations(graph, latent_features):
    """
    Simulate an RL-based recommendation system.
    Returns:
      - recommendations: Dict mapping each user_id to a recommended track_id.
    """
    recommendations = {}
    track_ids = list(latent_features.keys())
    for user in graph['nodes']['users']:
        recommendations[user] = track_ids[0] if track_ids else None
    return recommendations

def generate_explanations(recommendations, graph):
    """
    Simulate generating explanations (XAI) for each recommendation.
    Returns:
      - explanations: Dict mapping user_id to explanation strings.
    """
    explanations = {}
    for user, track in recommendations.items():
        explanations[user] = (
            f"User {user} is recommended track {track} due to high interaction weight and latent similarity."
        )
    return explanations

# -------------------------------
# MODULE 5: REAL-TIME DASHBOARD UPDATE & NLP INSIGHTS (Simulated)
# -------------------------------
def compute_leaderboard(graph):
    """
    Compute a leaderboard based on aggregated weighted edges per artist.
    Returns:
      - sorted_leaderboard: List of tuples (artists, total_score) sorted in descending order.
    """
    artist_scores = {}
    for (user, track, weight) in graph['weighted_edges']:
        artist = graph['track_to_artist'].get(track, "Unknown Artist")
        artist_scores[artist] = artist_scores.get(artist, 0) + weight
    sorted_leaderboard = sorted(artist_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_leaderboard

def generate_nlp_insights(graph, recommendations):
    """
    Simulate NLP/LLM-based summarization of key insights.
    Returns:
      - insights: A summary string.
    """
    num_users = len(graph['nodes']['users'])
    num_recs = len(recommendations)
    return f"Processed data for {num_users} users and generated {num_recs} recommendations."

def update_dashboard(recommendations, explanations, graph):
    """
    Simulate a real-time dashboard update.
    Prints the leaderboard, user recommendations, and key insights.
    """
    print("=== DASHBOARD UPDATE ===")
    print("Artist Leaderboard:")
    leaderboard = compute_leaderboard(graph)
    for artist, score in leaderboard:
        print(f"{artist}: {score:.2f}")
    
    print("\nUser Recommendations:")
    for user, track in recommendations.items():
        print(f"User {user}: Recommended Track {track} | Explanation: {explanations.get(user)}")
    
    key_insights = generate_nlp_insights(graph, recommendations)
    print("\nKey Insights Summary:")
    print(key_insights)
    print("========================\n")

# -------------------------------
# MODULE 6: MAIN PIPELINE ORCHESTRATION (PHASE 1)
# -------------------------------
def main():
    # Step 1: Data Ingestion & Basic Analytics
    raw_data = ingest_data(spotify_filename="spotify_data.csv", num_interactions=100)
    processed_data = preprocess_data(raw_data)
    print("Preprocessing complete. Displaying raw analytics visualizations...")
    visualize_raw_analytics(processed_data)
    
    # Step 2: ML Pipeline with Visualization at Each Stage (Simulated)
    track_metadata = raw_data['tracks']
    audio_features = extract_audio_features(track_metadata)
    fused_features = fuse_features(audio_features, raw_data['context'])
    latent_features = extract_latent_features(fused_features)
    interaction_graph = build_interaction_graph(processed_data, fused_features, track_metadata)
    recommendations = adaptive_recommendations(interaction_graph, latent_features)
    explanations = generate_explanations(recommendations, interaction_graph)
    
    # Step 3: Real-Time Dashboard Updates & NLP Insights (Simulated)
    update_dashboard(recommendations, explanations, interaction_graph)

# -------------------------------
# ENTRY POINT
# -------------------------------
if __name__ == "__main__":
    main()

