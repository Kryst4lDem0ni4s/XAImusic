import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image
import requests
from io import BytesIO
import sys
import os
from datetime import datetime
import random
import time
import sqlite3
import uuid

# Initialize database
def initialize_database():
    """Create SQLite database for user data if it doesn't exist"""
    db_path = 'music_recommendation_data.db'
    
    # Check if database exists
    db_exists = os.path.exists(db_path)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables if they don't exist
    if not db_exists:
        # Users table
        cursor.execute('''
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            karma_points INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # User interactions table
        cursor.execute('''
        CREATE TABLE interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            track_id TEXT NOT NULL,
            action TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        
        # User preferences table
        cursor.execute('''
        CREATE TABLE preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            preference_key TEXT NOT NULL,
            preference_value TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        
        conn.commit()
        print("Database initialized successfully")
    
    conn.close()

# Database functions
def get_or_create_user(username):
    """Get user from database or create if not exists"""
    conn = sqlite3.connect('music_recommendation_data.db')
    cursor = conn.cursor()
    
    # Check if user exists
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    
    if not user:
        # Create user with a unique ID
        user_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username)
        )
        conn.commit()
        
        # Get the newly created user
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
    
    conn.close()
    
    # Return user as a dictionary
    return {
        'user_id': user[0],
        'username': user[1],
        'karma_points': user[2],
        'created_at': user[3]
    }

def save_interaction(user_id, track_id, action):
    """Save user interaction to database"""
    conn = sqlite3.connect('music_recommendation_data.db')
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO interactions (user_id, track_id, action) VALUES (?, ?, ?)",
        (user_id, track_id, action)
    )
    
    conn.commit()
    conn.close()

def update_karma_points(user_id, points_to_add):
    """Update user's karma points"""
    conn = sqlite3.connect('music_recommendation_data.db')
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE users SET karma_points = karma_points + ? WHERE user_id = ?",
        (points_to_add, user_id)
    )
    
    conn.commit()
    conn.close()

def get_user_interactions(user_id, limit=50):
    """Get user's recent interactions"""
    conn = sqlite3.connect('music_recommendation_data.db')
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT track_id, action, timestamp FROM interactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
        (user_id, limit)
    )
    
    interactions = cursor.fetchall()
    conn.close()
    
    # Return interactions as a list of dictionaries
    return [
        {'track_id': i[0], 'action': i[1], 'timestamp': i[2]}
        for i in interactions
    ]

# Add the directory containing pipeline.py to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import functions from your backend pipeline
try:
    from pipeline import (ingest_data, preprocess_data, extract_audio_features, 
                         fuse_features, extract_latent_features, build_interaction_graph,
                         adaptive_recommendations, generate_explanations, compute_leaderboard)
except ImportError:
    st.error("Could not import functions from pipeline.py. Make sure the file exists and contains the required functions.")

# Initialize the database
initialize_database()

# Set page configuration
st.set_page_config(
    page_title="Music Recommendation System",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply custom CSS for dark theme similar to the React design
st.markdown("""
<style>
    .main {
        background-color: #121212;
        color: white;
    }
    .stApp {
        background-color: #121212;
    }
    .css-1d391kg {
        background-color: #1e1e1e;
    }
    .st-bq {
        background-color: #292929;
    }
    .st-cn {
        background-color: #1e1e1e;
    }
    .stButton>button {
        background-color: #1e1e1e;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 0.5rem 1rem;
    }
    .stButton>button:hover {
        background-color: #2e2e2e;
    }
    h1, h2, h3 {
        color: white;
    }
    .highlight {
        color: #00c9a7;
        font-weight: bold;
    }
    .genre-pill {
        display: inline-block;
        padding: 5px 10px;
        border-radius: 15px;
        margin: 2px;
        font-size: 12px;
    }
    .card {
        background-color: #1e1e1e;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state for persistent data
if 'karma_points' not in st.session_state:
    st.session_state.karma_points = 95
if 'is_playing' not in st.session_state:
    st.session_state.is_playing = False
if 'current_song' not in st.session_state:
    st.session_state.current_song = "No song playing"
if 'user_data' not in st.session_state:
    st.session_state.user_data = None
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None
if 'recommendations' not in st.session_state:
    st.session_state.recommendations = None
if 'interaction_graph' not in st.session_state:
    st.session_state.interaction_graph = None
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'page' not in st.session_state:
    st.session_state.page = "login"
if 'user' not in st.session_state:
    st.session_state.user = None
if 'user_id' not in st.session_state:
    st.session_state.user_id = None

# Function to create sample dataset if needed
def create_sample_dataset():
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    # Check if file already exists
    if os.path.exists('spotify_data.csv') or os.path.exists(os.path.join('data', 'spotify_data.csv')):
        return
    
    # Create a sample Spotify dataset with required columns
    sample_data = {
        'track_id': range(1, 101),
        'artists': [f'Artist {i%10}' for i in range(1, 101)],  # Note: using 'artists' instead of 'artist_name'
        'track_name': [f'Track {i}' for i in range(1, 101)],
        'album_name': [f'Album {i%20}' for i in range(1, 101)],
        'release_date': ['2023-01-01'] * 100,
        'popularity': np.random.randint(1, 100, 100),
        'danceability': np.random.random(100),
        'energy': np.random.random(100),
        'key': np.random.randint(0, 12, 100),
        'loudness': np.random.uniform(-20, 0, 100),
        'mode': np.random.randint(0, 2, 100),
        'speechiness': np.random.random(100),
        'acousticness': np.random.random(100),
        'instrumentalness': np.random.random(100),
        'liveness': np.random.random(100),
        'valence': np.random.random(100),
        'tempo': np.random.uniform(60, 200, 100),
        'track_genre': np.random.choice(['Pop', 'Rock', 'Hip-Hop', 'R&B', 'Indie'], 100)
    }
    
    df = pd.DataFrame(sample_data)
    df.to_csv('spotify_data.csv', index=False)
    st.success("Created sample Spotify dataset")

# Function to load data from the backend pipeline
def load_backend_data():
    with st.spinner("Loading data from backend..."):
        try:
            # Ensure sample dataset exists
            create_sample_dataset()
            
            # Use your pipeline functions to get real data
            raw_data = ingest_data(spotify_filename="spotify_data.csv", num_interactions=100)
            
            # Validate data structure
            if 'tracks' in raw_data and not raw_data['tracks'].empty:
                # Rename 'artists' column to 'artist_name' if it exists
                if 'artists' in raw_data['tracks'].columns and 'artist_name' not in raw_data['tracks'].columns:
                    raw_data['tracks']['artist_name'] = raw_data['tracks']['artists']
                    print("Renamed 'artists' column to 'artist_name'")
                
                # Check for required columns
                required_columns = ['track_id', 'artist_name', 'track_name']
                missing_columns = [col for col in required_columns if col not in raw_data['tracks'].columns]
                
                if missing_columns:
                    print(f"Missing columns in track data: {missing_columns}")
                    # Add missing columns with placeholder values
                    for col in missing_columns:
                        raw_data['tracks'][col] = f"Unknown {col.replace('_', ' ').title()}"
            
            processed_data = preprocess_data(raw_data)
            
            track_metadata = raw_data['tracks']
            audio_features = extract_audio_features(track_metadata)
            fused_features = fuse_features(audio_features, raw_data['context'])
            latent_features = extract_latent_features(fused_features)
            interaction_graph = build_interaction_graph(processed_data, fused_features, track_metadata)
            recommendations = adaptive_recommendations(interaction_graph, latent_features)
            
            # Store in session state
            st.session_state.user_data = raw_data
            st.session_state.processed_data = processed_data
            st.session_state.recommendations = recommendations
            st.session_state.interaction_graph = interaction_graph
            
            return True
        except Exception as e:
            st.error(f"Error loading backend data: {e}")
            # If real data fails, use simulated data
            return False

# Simulated data for fallback
def get_simulated_data():
    # Top artists data
    top_artists = [
        {
            "name": "Drake",
            "songs": ["God's Plan", "Hotline Bling"],
            "image": "https://i.scdn.co/image/ab6761610000e5eb7d05e78b5df0b1a3da19c7b3",
        },
        {
            "name": "Travis Scott",
            "songs": ["SICKO MODE", "Goosebumps"],
            "image": "https://i.scdn.co/image/ab6761610000e5ebd9b3c67c5e3e7ac96390f3ea",
        },
        {
            "name": "The Weeknd",
            "songs": ["Blinding Lights", "Starboy"],
            "image": "https://i.scdn.co/image/ab6761610000e5ebb15f0b43a62f0c68c61b36dd",
        },
        {
            "name": "Post Malone",
            "songs": ["Circles", "Sunflower"],
            "image": "https://i.scdn.co/image/ab6761610000e5eb0f35aa2c9b79a8f4dbf18b9d",
        },
        {
            "name": "Kanye West",
            "songs": ["Stronger", "Power"],
            "image": "https://i.scdn.co/image/ab6761610000e5eb4419817bfaf7c0637e15d7f2",
        },
    ]
    
    # Genre data
    genre_data = [
        {"name": "Hip-Hop", "value": 400},
        {"name": "Pop", "value": 300},
        {"name": "Indie", "value": 200},
        {"name": "R&B", "value": 150},
        {"name": "Trap", "value": 100},
    ]
    
    # User points data
    user_points = [
        {"category": "Liked Songs", "value": 50},
        {"category": "Added to Playlist", "value": 30},
        {"category": "Shared", "value": 10},
        {"category": "Donated", "value": 5},
    ]
    
    return {
        "top_artists": top_artists,
        "genre_data": genre_data,
        "user_points": user_points
    }

# Function to search for music using an API
def search_music_api(query, limit=5):
    # This is a placeholder - in a real app, you would use a real music API
    # Example with Deezer API:
    try:
        url = f"https://api.deezer.com/search?q={query}&limit={limit}"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json().get('data', [])
        return []
    except Exception as e:
        st.error(f"Error searching music: {e}")
        return []

# Function to toggle play/pause
def toggle_play():
    st.session_state.is_playing = not st.session_state.is_playing
    
# Function to add karma points
def add_karma(points):
    if 'user_id' in st.session_state:
        update_karma_points(st.session_state.user_id, points)
    st.session_state.karma_points += points
    st.success(f"Added {points} karma points!")

# Function to like a song
def like_song(track_id="unknown"):
    if 'user_id' in st.session_state:
        save_interaction(st.session_state.user_id, track_id, 'like')
    add_karma(5)
    st.balloons()

# Function to add to playlist
def add_to_playlist(track_id="unknown"):
    if 'user_id' in st.session_state:
        save_interaction(st.session_state.user_id, track_id, 'playlist_add')
    add_karma(3)
    st.success("Song added to playlist!")

# Login page function
def login_page():
    st.title("Login to Music Recommendation System")
    
    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")
    
    if st.button("Login"):
        # In a real app, you would verify against a database
        if username and password:
            # Get or create user in database
            user = get_or_create_user(username)
            
            # Store user info in session state
            st.session_state.user_id = user['user_id']
            st.session_state.user = username
            st.session_state.karma_points = user['karma_points']
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid username or password")
    
    if st.button("Register"):
        st.session_state.page = "register"
        st.rerun()

# Register page function
def register_page():
    st.title("Register for Music Recommendation System")
    
    username = st.text_input("Username", key="register_username")
    password = st.text_input("Password", type="password", key="register_password")
    confirm_password = st.text_input("Confirm Password", type="password", key="confirm_password")
    
    if st.button("Register"):
        if password != confirm_password:
            st.error("Passwords do not match")
        elif not username or not password:
            st.error("Username and password are required")
        else:
            # Create user in database
            user = get_or_create_user(username)
            
            # Store user info in session state
            st.session_state.user_id = user['user_id']
            st.session_state.user = username
            st.session_state.karma_points = user['karma_points']
            st.session_state.logged_in = True
            st.success("Registration successful!")
            st.rerun()
    
    if st.button("Back to Login"):
        st.session_state.page = "login"
        st.rerun()

# Main application
def main():
    # Check if user is logged in
    if not st.session_state.logged_in:
        if st.session_state.page == "login":
            login_page()
        elif st.session_state.page == "register":
            register_page()
        return
    
    # Define simulated data at the beginning for fallback
    simulated_data = get_simulated_data()
    
    # Header with search
    col1, col2 = st.columns([1, 2])
    with col1:
        st.title("Your Music Dashboard")
    with col2:
        search_col, button_col = st.columns([5, 1])
        with search_col:
            search_query = st.text_input("Search", placeholder="Search music...", label_visibility="collapsed")
        with button_col:
            if st.button("🔍"):
                if search_query:
                    st.session_state.search_results = search_music_api(search_query)
                    if not st.session_state.search_results:
                        st.info(f"No results found for '{search_query}'")
    
    # Display search results if any
    if 'search_results' in st.session_state and st.session_state.search_results:
        st.subheader("Search Results")
        for i, track in enumerate(st.session_state.search_results):
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f"{track.get('title', 'Unknown')} - {track.get('artist', {}).get('name', 'Unknown Artist')}")
            with col2:
                if st.button("Play", key=f"play_{i}"):
                    st.session_state.current_song = f"{track.get('title', 'Unknown')} - {track.get('artist', {}).get('name', 'Unknown Artist')}"
                    st.session_state.is_playing = True
                    track_id = track.get('id', 'unknown')
                    # If there's a preview URL, play it
                    if 'preview' in track and track['preview']:
                        st.audio(track['preview'])
                    # Save interaction
                    if 'user_id' in st.session_state:
                        save_interaction(st.session_state.user_id, track_id, 'play')
            with col3:
                if st.button("Add", key=f"add_{i}"):
                    track_id = track.get('id', 'unknown')
                    add_to_playlist(track_id)
        st.markdown("---")
    
    # Try to load real data from backend, fall back to simulated if it fails
    backend_loaded = load_backend_data()
    
    if not backend_loaded:
        # Use simulated data
        data = simulated_data  # Assign to a local variable
        top_artists = data["top_artists"]
        genre_data = data["genre_data"]
        user_points = data["user_points"]
    else:
        # Use real data from backend
        # Extract top artists from the interaction graph
        leaderboard = compute_leaderboard(st.session_state.interaction_graph)
        top_artists = []
        for artist_name, score in leaderboard[:5]:
            # Get random songs for this artist
            songs = [f"Song {i+1}" for i in range(2)]
            top_artists.append({
                "name": artist_name,
                "songs": songs,
                "image": "https://i.pravatar.cc/300?img=" + str(hash(artist_name) % 70)
            })
        
        # Extract genre data from processed data
        if 'track_genre' in st.session_state.processed_data.columns:
            genre_counts = st.session_state.processed_data['track_genre'].value_counts().head(5)
            genre_data = [{"name": genre, "value": count} for genre, count in genre_counts.items()]
        else:
            genre_data = simulated_data["genre_data"]  # Fallback
            
        # Extract user points from interaction data
        if 'action' in st.session_state.processed_data.columns:
            action_counts = st.session_state.processed_data['action'].value_counts()
            user_points = [
                {"category": "Liked Songs", "value": action_counts.get('like', 0)},
                {"category": "Added to Playlist", "value": action_counts.get('playlist_add', 0)},
                {"category": "Played", "value": action_counts.get('play', 0)},
                {"category": "Skipped", "value": action_counts.get('skip', 0)}
            ]
        else:
            user_points = simulated_data["user_points"]  # Fallback
    
    # Top Artists Section
    st.header("Top 5 Artists of the Week")
    
    # Display artists in a grid
    cols = st.columns(5)
    for i, artist in enumerate(top_artists):
        with cols[i]:
            st.markdown(f"""
            <div style="position: relative; height: 200px; border-radius: 10px; overflow: hidden; border: 1px solid #2e3a40;">
                <img src="{artist['image']}" style="width: 100%; height: 100%; object-fit: cover; opacity: 0.7;">
                <div style="position: absolute; bottom: 0; left: 0; right: 0; background: rgba(0,0,0,0.6); padding: 10px;">
                    <h3 style="color: #00c9a7; margin: 0; font-size: 18px;">{artist['name']}</h3>
                    <ul style="margin: 5px 0 0 0; padding-left: 15px; font-size: 12px;">
                        {' '.join([f'<li>{song}</li>' for song in artist['songs']])}
                    </ul>
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    # Genres Section
    st.header("Genres You've Explored")
    
    # Display genre pills
    colors = ["#00c9a7", "#ff6b6b", "#feca57", "#5f27cd", "#48dbfb"]
    genre_html = ""
    for i, genre in enumerate(genre_data):
        color = colors[i % len(colors)]
        genre_html += f'<span class="genre-pill" style="background-color: {color}; color: black;">{genre["name"]}</span>'
    
    st.markdown(f"<div>{genre_html}</div>", unsafe_allow_html=True)
    
    # Charts Section
    st.header("Analytics")
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Genre Distribution")
        # Create a pie chart using Plotly
        fig = px.pie(
            values=[genre["value"] for genre in genre_data],
            names=[genre["name"] for genre in genre_data],
            hole=0.4,
            color_discrete_sequence=colors
        )
        fig.update_layout(
            margin=dict(t=0, b=0, l=0, r=0),
            paper_bgcolor="#1e1e1e",
            plot_bgcolor="#1e1e1e",
            font=dict(color="white")
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("Your Point Activity")
        # Create a bar chart using Plotly
        fig = px.bar(
            x=[point["category"] for point in user_points],
            y=[point["value"] for point in user_points],
            color_discrete_sequence=["#48dbfb"]
        )
        fig.update_layout(
            xaxis_title=None,
            yaxis_title=None,
            margin=dict(t=0, b=0, l=0, r=0),
            paper_bgcolor="#1e1e1e",
            plot_bgcolor="#1e1e1e",
            font=dict(color="white")
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Music Player Section
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Music Player")
    
    # Current song display
    if st.session_state.is_playing:
        current_song = "Now Playing: " + st.session_state.current_song
    else:
        current_song = "Paused: " + st.session_state.current_song
    
    st.markdown(f"<h4 style='text-align: center;'>{current_song}</h4>", unsafe_allow_html=True)
    
    # Player controls
    cols = st.columns(7)
    with cols[0]:
        st.button("⏮️", key="prev")
    with cols[1]:
        if st.button("⏯️", key="play"):
            toggle_play()
    with cols[2]:
        st.button("⏭️", key="next")
    with cols[3]:
        if st.button("❤️", key="like"):
            like_song()
    with cols[4]:
        if st.button("➕", key="add"):
            add_to_playlist()
    with cols[5]:
        st.button("🎁", key="gift")
    with cols[6]:
        if st.button("🔄", key="refresh"):
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # User Profile Section
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("User Profile")
    
    col1, col2 = st.columns([1, 3])
    with col1:
        st.image("https://i.pravatar.cc/150", width=100)
    with col2:
        st.markdown(f"<h3>{st.session_state.user}</h3>", unsafe_allow_html=True)
        st.markdown(f"<p>Total Karma Points: <span class='highlight'>{st.session_state.karma_points}</span></p>", unsafe_allow_html=True)
        
        # Progress bar for next level
        next_level = (st.session_state.karma_points // 100 + 1) * 100
        progress = (st.session_state.karma_points % 100) / 100
        st.markdown(f"<p>Progress to Level {next_level // 100}:</p>", unsafe_allow_html=True)
        st.progress(progress)
        
        # Logout button
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.session_state.user_id = None
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # User Interaction History
    if 'user_id' in st.session_state and st.session_state.user_id:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Your Recent Activity")
        
        interactions = get_user_interactions(st.session_state.user_id)
        if interactions:
            for i, interaction in enumerate(interactions[:5]):
                st.markdown(f"""
                <p>{interaction['timestamp']}: {interaction['action'].capitalize()} - Track ID: {interaction['track_id']}</p>
                """, unsafe_allow_html=True)
        else:
            st.write("No recent activity found.")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Recommendations Section based on backend data
    if backend_loaded and st.session_state.recommendations:
        st.header("Personalized Recommendations")
        
        # Get explanations for recommendations
        explanations = generate_explanations(st.session_state.recommendations, st.session_state.interaction_graph)
        
        # Display recommendations
        for user_id, track_id in list(st.session_state.recommendations.items())[:3]:
            st.markdown(f"""
            <div class="card">
                <h4>Recommendation for User {user_id}</h4>
                <p>Track ID: {track_id}</p>
                <p><i>{explanations.get(user_id, "No explanation available")}</i></p>
            </div>
            """, unsafe_allow_html=True)
            
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("Play Now", key=f"play_rec_{user_id}"):
                    st.session_state.current_song = f"Track {track_id}"
                    st.session_state.is_playing = True
                    # Save interaction
                    if 'user_id' in st.session_state:
                        save_interaction(st.session_state.user_id, track_id, 'play')
            with col2:
                if st.button("Add to Playlist", key=f"add_rec_{user_id}"):
                    add_to_playlist(track_id)
    
    # Listening Heatmap (if data available)
    if backend_loaded and 'timestamp' in st.session_state.processed_data.columns:
        st.header("Your Listening Patterns")
        
        # Extract hour from timestamp
        st.session_state.processed_data['hour'] = pd.to_datetime(st.session_state.processed_data['timestamp']).dt.hour
        
        # Count plays by hour
        hour_counts = st.session_state.processed_data.groupby('hour').size().reset_index(name='count')
        
        # Create heatmap
        fig = px.density_heatmap(
            hour_counts, 
            x='hour', 
            y=['Plays'], 
            z='count',
            color_continuous_scale='YlGnBu'
        )
        fig.update_layout(
            title="Listening Activity by Hour",
            xaxis_title="Hour of Day",
            yaxis_title="",
            paper_bgcolor="#1e1e1e",
            plot_bgcolor="#1e1e1e",
            font=dict(color="white")
        )
        st.plotly_chart(fig, use_container_width=True)

if __name__ == "__main__":
    main()
