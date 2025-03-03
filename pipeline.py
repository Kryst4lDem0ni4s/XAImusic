import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
import seaborn as sns
import matplotlib.pyplot as plt

# -------------------------------
# MODULE 1: DATA INGESTION & STORAGE
# -------------------------------
def load_dummy_user_interactions(num_entries=100):
    """
    Simulate real-time ingestion of user interactions.
    Expected Data: DataFrame with columns:
      - user_id (int)
      - track_id (int)
      - artist_id (str)
      - action (str): one of ['play', 'skip', 'like', 'playlist_add']
      - timestamp (datetime)
    """
    actions = ['play', 'skip', 'like', 'playlist_add']
    data = []
    # Assume 10 dummy users and 50 tracks.
    user_ids = list(range(1, 11))
    track_ids = list(range(1, 51))
    # For simplicity, assign artists as "Artist_1" to "Artist_5"
    artist_ids = [f"Artist_{i}" for i in range(1, 6)]
    now = datetime.now()

    for _ in range(num_entries):
        user = random.choice(user_ids)
        track = random.choice(track_ids)
        # Assign an artist based on track id (cyclic assignment)
        artist = artist_ids[(track - 1) % len(artist_ids)]
        action = random.choice(actions)
        # Random timestamp within the last 24 hours
        ts = now - timedelta(seconds=random.randint(0, 86400))
        data.append({
            'user_id': user,
            'track_id': track,
            'artist_id': artist,
            'action': action,
            'timestamp': ts
        })
    return pd.DataFrame(data)

def load_dummy_track_metadata():
    """
    Simulate track metadata for 50 tracks.
    Expected Data: DataFrame with columns:
      - track_id (int)
      - title (str)
      - simulated_audio_features (dict): e.g., {'tempo': int, 'pitch': float}
      - artist_id (str)
    """
    data = []
    artist_ids = [f"Artist_{i}" for i in range(1, 6)]
    for track in range(1, 51):
        # Random audio features
        features = {
            'tempo': random.randint(80, 160),
            'pitch': round(random.uniform(0.5, 1.5), 2)
        }
        artist = artist_ids[(track - 1) % len(artist_ids)]
        data.append({
            'track_id': track,
            'title': f"Track {track}",
            'simulated_audio_features': features,
            'artist_id': artist
        })
    return pd.DataFrame(data)

def load_dummy_contextual_data(num_entries=100):
    """
    Simulate contextual metadata for each interaction.
    Expected Data: DataFrame with columns:
      - user_id (int)
      - timestamp (datetime) -- matching the interaction timestamp for simulation
      - mood (float): simulated mood score between 0 and 1
      - device (str): e.g., 'mobile' or 'desktop'
      - location (str): e.g., dummy city names
    """
    data = []
    devices = ['mobile', 'desktop']
    locations = ['CityA', 'CityB', 'CityC']
    now = datetime.now()
    # For each simulated interaction (assuming same number as interactions)
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
    Persist the raw interactions data to a CSV file for long-term analysis.
    """
    df.to_csv(filename, index=False)
    print(f"Persisted time-series data to {filename}")

def ingest_mock_data():
    """
    Ingest dummy data for interactions, track metadata, and contextual data.
    """
    user_interactions = load_dummy_user_interactions()
    track_metadata = load_dummy_track_metadata()
    contextual_data = load_dummy_contextual_data(len(user_interactions))
    
    # Persist interactions for time-series analysis (simulated)
    persist_time_series_data(user_interactions)
    
    return {
        'interactions': user_interactions,
        'tracks': track_metadata,
        'context': contextual_data
    }

# -------------------------------
# MODULE 2: DATA PROCESSING & WRANGLING
# -------------------------------
def preprocess_data(raw_data):
    """
    Clean and wrangle raw data.
    Operations:
      - Remove missing values.
      - Merge user interactions with contextual data and track metadata.
      - Compute additional metrics (e.g., session IDs based on timestamp differences).
    """
    interactions_df = raw_data['interactions'].dropna()
    context_df = raw_data['context'].dropna()
    tracks_df = raw_data['tracks'].dropna()
    
    # Merge interactions with context on user_id and nearest timestamp (for simulation, do a simple merge)
    merged_df = pd.merge_asof(
        interactions_df.sort_values('timestamp'),
        context_df.sort_values('timestamp'),
        on='timestamp',
        by='user_id',
        direction='nearest',
        tolerance=pd.Timedelta("1min")
    )
    
    # Merge with track metadata on track_id and include artist_id
    print("Track metadata columns:", tracks_df.columns.tolist())
    print("Track IDs in metadata:", tracks_df['track_id'].unique())
    print("Track IDs in interactions:", merged_df['track_id'].unique())
    
    merged_df = pd.merge(merged_df, tracks_df[['track_id', 'artist_id']], on='track_id', how='left')
    
    # Debug: Check the structure of merged_df after merging
    print("Merged DataFrame after merging interactions and context:")
    print(merged_df.head())
    print("Columns in merged_df:", merged_df.columns.tolist())
    print("Missing artist_id count:", merged_df['artist_id_x'].isna().sum())
    
    # Validate artist_id presence
    if 'artist_id_x' not in merged_df.columns:
        raise ValueError("'artist_id_x' column is missing after merging. Check track metadata.")
    elif merged_df['artist_id_x'].isna().any():
        print("Warning: Some tracks have missing artist_id. Filling with 'Unknown'")
        merged_df['artist_id_x'] = merged_df['artist_id_x'].fillna('Unknown')



    
    # Compute session_id: if time difference > 5 minutes (300 sec), new session (simple simulation)
    merged_df = merged_df.sort_values(['user_id', 'timestamp'])
    merged_df.reset_index(drop=True, inplace=True)
    merged_df['session_diff'] = merged_df.groupby('user_id')['timestamp'].diff().dt.total_seconds().fillna(0)
    merged_df['session_id'] = merged_df.groupby('user_id')['session_diff'].apply(
        lambda x: (x > 300).cumsum()
    ).reset_index(drop=True)

    
    return merged_df

# -------------------------------
# MODULE 3: VISUALIZATION FOR DATA ANALYTICS
# -------------------------------
def visualize_raw_analytics(processed_df):
    """
    Create visualizations for the raw analytics.
    Displays:
      - Heatmap: Number of plays by hour.
      - Leaderboard: Interactions by artist.
    """
    # Validate required columns
    required_columns = ['timestamp', 'artist_id_x']
    missing_cols = [col for col in required_columns if col not in processed_df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns in processed data: {missing_cols}")

    # Extract hour from timestamp
    if 'hour' in processed_df.columns:
        processed_df.drop(columns=['hour'], inplace=True)
    processed_df['hour'] = processed_df['timestamp'].dt.hour
    
    # Create heatmap data
    heatmap_data = processed_df.groupby('hour').size().reset_index(name='plays')
    
    plt.figure(figsize=(10, 6))
    sns.heatmap(heatmap_data[['plays']].T, annot=True, cmap="YlGnBu", cbar=False,
                yticklabels=['Plays'], xticklabels=heatmap_data['hour'])
    plt.title("User Plays by Hour")
    plt.xlabel("Hour of Day")
    plt.ylabel("")

    plt.show()
    
    # Leaderboard: Total interactions per artist
    leaderboard = processed_df.groupby('artist_id_x').size().reset_index(name='total_interactions')
    plt.figure(figsize=(8, 4))
    sns.barplot(x='artist_id_x', y='total_interactions', data=leaderboard)
    plt.title("Artist Leaderboard")
    plt.xlabel("Artist")
    plt.ylabel("Total Interactions")
    plt.show()

# -------------------------------
# MODULE 4: MACHINE LEARNING PIPELINE COMPONENTS (Simulated)
# -------------------------------
def extract_audio_features(track_metadata):
    """
    Simulate extraction of audio features from track metadata.
    Returns:
      - audio_features: Dict mapping track_id to its audio feature vector.
    """
    audio_features = {}
    for _, row in track_metadata.iterrows():
        audio_features[row['track_id']] = row.get('simulated_audio_features', {'tempo': 120, 'pitch': 1.0})
    return audio_features

def fuse_features(audio_features, context_df):
    """
    Simulate fusion of audio features with contextual metadata.
    Returns:
      - fused_features: Dict mapping track_id to fused feature vector.
    """
    fused_features = {}
    # Here, we simply add a dummy 'mood_factor' to each track's audio features.
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
      - graph: Dict with nodes, edges, and a track-to-artist mapping.
    """
    users = set(processed_df['user_id'].unique())
    tracks = set(processed_df['track_id'].unique())
    artists = set(processed_df['artist_id_x'].unique())
    
    # Build track-to-artist mapping from track metadata
    track_to_artist = dict(zip(track_metadata['track_id'], track_metadata['artist_id']))
    
    # Build edges: (user_id, track_id, weight)
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
    
    # Simulate application of TGNN and GAT (dummy adjustment)
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
    Simulate TGNN and GAT processing by adjusting the edge weights.
    Returns:
      - weighted_edges: List of tuples (user, track, adjusted_weight).
    """
    weighted_edges = []
    for (user, track, weight) in edges:
        adjusted_weight = weight * 1.2  # dummy adjustment
        weighted_edges.append((user, track, adjusted_weight))
    return weighted_edges

def extract_latent_features(fused_features):
    """
    Simulate latent feature extraction using a VAE.
    Returns:
      - latent_features: Dict mapping track_id to latent feature vector.
    """
    latent_features = {}
    for key, features in fused_features.items():
        latent_features[key] = {k: v * 0.8 for k, v in features.items()}
    return latent_features

def adaptive_recommendations(graph, latent_features):
    """
    Simulate an RL-based recommendation system.
    Returns:
      - recommendations: Dict mapping each user_id to a recommended track_id.
    """
    recommendations = {}
    track_ids = list(latent_features.keys())
    # For simplicity, assign the first track as the recommendation for all users.
    for user in graph['nodes']['users']:
        recommendations[user] = track_ids[0] if track_ids else None
    return recommendations

def generate_explanations(recommendations, graph):
    """
    Simulate generation of explanations (XAI) for each recommendation.
    Returns:
      - explanations: Dict mapping user_id to explanation strings.
    """
    explanations = {}
    for user, track in recommendations.items():
        explanations[user] = (
            f"User {user} is recommended track {track} "
            f"because it has high interaction weight and latent similarity."
        )
    return explanations

# -------------------------------
# MODULE 5: REAL-TIME DASHBOARD UPDATE & NLP INSIGHTS (Simulated)
# -------------------------------
def compute_leaderboard(graph):
    """
    Compute a leaderboard based on aggregated weighted edges per artist.
    Returns:
      - sorted_leaderboard: List of tuples (artist_id, total_score) sorted in descending order.
    """
    artist_scores = {}
    # Use the track_to_artist mapping in the graph
    for (user, track, weight) in graph['weighted_edges']:
        artist = graph['track_to_artist'].get(track, "Unknown Artist")
        artist_scores[artist] = artist_scores.get(artist, 0) + weight
    # Sort by score descending
    sorted_leaderboard = sorted(artist_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_leaderboard

def generate_nlp_insights(graph, recommendations):
    """
    Simulate NLP/LLM based summarization of key insights.
    Returns:
      - insights: String summarizing key data points.
    """
    num_users = len(graph['nodes']['users'])
    num_recs = len(recommendations)
    return f"Processed data for {num_users} users and generated {num_recs} recommendations."

def update_dashboard(recommendations, explanations, graph):
    """
    Simulate a real-time dashboard update.
    Prints the leaderboard, recommendations, and key insights.
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
    raw_data = ingest_mock_data()
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
    
    # (Optional) Additional intermediate visualizations can be added here.
    
    # Step 3: Real-Time Dashboard Updates & NLP Insights (Simulated)
    update_dashboard(recommendations, explanations, interaction_graph)

# -------------------------------
# ENTRY POINT
# -------------------------------
if __name__ == "__main__":
    main()
