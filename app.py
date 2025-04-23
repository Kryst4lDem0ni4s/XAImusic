import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image
import requests
from io import BytesIO
import sys
import os
from datetime import datetime, timedelta
import random
import time
import sqlite3
import hashlib
import secrets
import uuid
import json

# Set up constants
RECCOBEATS_BASE_URL = "https://api.reccobeats.com"
MUSICBRAINZ_BASE_URL = "https://musicbrainz.org/ws/2"
USER_AGENT = "MusicRecommendationApp/1.0.0 (contact@example.com)"

# -------------------------------
# DATABASE SETUP
# -------------------------------
def setup_database():
    """Create SQLite database for user data if it doesn't exist"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create playlists table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS playlists (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # Create playlist_tracks table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS playlist_tracks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        playlist_id TEXT NOT NULL,
        track_id TEXT NOT NULL,
        track_name TEXT,
        artists TEXT,
        album_art TEXT,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (playlist_id) REFERENCES playlists (id)
    )
    ''')
    
    # Create user_favorites table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        track_id TEXT NOT NULL,
        track_name TEXT,
        artists TEXT,
        album_art TEXT,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # Create playback_state table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS playback_state (
        user_id TEXT PRIMARY KEY,
        current_track TEXT,
        current_track_name TEXT,
        current_artists TEXT,
        current_album_art TEXT,
        position_ms INTEGER DEFAULT 0,
        is_playing BOOLEAN DEFAULT 0,
        repeat_mode TEXT DEFAULT 'off',
        shuffle BOOLEAN DEFAULT 0,
        volume INTEGER DEFAULT 100,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # Create queue table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        track_id TEXT NOT NULL,
        track_name TEXT,
        artists TEXT,
        album_art TEXT,
        position INTEGER NOT NULL,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # Create recently_played table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS recently_played (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        track_id TEXT NOT NULL,
        track_name TEXT,
        artists TEXT,
        album_art TEXT,
        played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # Create user_listening_data table for analytics
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_listening_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        track_id TEXT NOT NULL,
        action TEXT NOT NULL,
        hour INTEGER,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # Create users table with karma_points column
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        karma_points INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Check if karma_points column exists, add it if it doesn't
    cursor.execute("PRAGMA table_info(users)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'karma_points' not in columns:
        cursor.execute('ALTER TABLE users ADD COLUMN karma_points INTEGER DEFAULT 0')
    
    # Create karma_history table for tracking point changes
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS karma_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        action TEXT NOT NULL,
        points INTEGER NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    conn.commit()
    conn.close()

def add_karma_points(user_id, action, points):
    """Add karma points to a user and record in history"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    try:
        # Update user's karma points
        cursor.execute('UPDATE users SET karma_points = karma_points + ? WHERE id = ?', (points, user_id))
        
        # Record in karma history
        cursor.execute('''
        INSERT INTO karma_history (user_id, action, points)
        VALUES (?, ?, ?)
        ''', (user_id, action, points))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Error adding karma points: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_user_karma(user_id):
    """Get a user's karma points and history"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT karma_points FROM users WHERE id = ?', (user_id,))
        result = cursor.fetchone()
        karma = result[0] if result else 0
        
        # Get karma history
        cursor.execute('''
        SELECT action, points, timestamp FROM karma_history
        WHERE user_id = ?
        ORDER BY timestamp DESC LIMIT 10
        ''', (user_id,))
        
        history = [{'action': row[0], 'points': row[1], 'timestamp': row[2]} for row in cursor.fetchall()]
        
        return {'total': karma, 'history': history}
    except Exception as e:
        print(f"Error getting karma: {e}")
        return {'total': 0, 'history': []}
    finally:
        conn.close()


# -------------------------------
# USER MANAGEMENT FUNCTIONS
# -------------------------------
def register_user(username, email, password):
    """Register a new user"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    # Check if username or email already exists
    cursor.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email))
    if cursor.fetchone():
        conn.close()
        return False, "Username or email already exists"
    
    # Hash the password
    salt = secrets.token_hex(16)
    password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    
    # Generate a unique ID
    user_id = str(uuid.uuid4())
    
    # Store the user
    cursor.execute('''
    INSERT INTO users (id, username, email, password_hash)
    VALUES (?, ?, ?, ?)
    ''', (user_id, username, email, f"{salt}:{password_hash}"))
    
    conn.commit()
    conn.close()
    
    return True, user_id

def login_user(username_or_email, password):
    """Login a user"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    # Find user by username or email
    cursor.execute('SELECT id, password_hash, username FROM users WHERE username = ? OR email = ?', 
                   (username_or_email, username_or_email))
    user_data = cursor.fetchone()
    conn.close()
    
    if not user_data:
        return False, "User not found"
    
    user_id, stored_password, username = user_data
    salt, hash_value = stored_password.split(':')
    
    # Verify password
    computed_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    if computed_hash != hash_value:
        return False, "Invalid password"
    
    return True, {"user_id": user_id, "username": username}

def get_user_profile(user_id):
    """Get user profile information"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT username, email, created_at FROM users WHERE id = ?', (user_id,))
    user_data = cursor.fetchone()
    
    if not user_data:
        conn.close()
        return None
    
    username, email, created_at = user_data
    
    # Get user's playlists
    cursor.execute('SELECT id, name, description FROM playlists WHERE user_id = ?', (user_id,))
    playlists = cursor.fetchall()
    
    # Get user's favorite tracks
    cursor.execute('SELECT track_id, track_name, artists FROM user_favorites WHERE user_id = ?', (user_id,))
    favorites = [{"id": row[0], "name": row[1], "artist": row[2]} for row in cursor.fetchall()]
    
    # Get recently played tracks
    cursor.execute('''
    SELECT track_id, track_name, artists FROM recently_played 
    WHERE user_id = ? 
    ORDER BY played_at DESC LIMIT 20
    ''', (user_id,))
    recently_played = [{"id": row[0], "name": row[1], "artist": row[2]} for row in cursor.fetchall()]
    
    # Get listening data for analytics
    cursor.execute('''
    SELECT hour, COUNT(*) as count FROM user_listening_data 
    WHERE user_id = ? 
    GROUP BY hour
    ORDER BY hour
    ''', (user_id,))
    listening_hours = cursor.fetchall()
    
    # Format listening hours data for heatmap
    hours_data = []
    for hour in range(24):
        found = False
        for row in listening_hours:
            if row[0] == hour:
                hours_data.append({"hour": hour, "count": row[1]})
                found = True
                break
        if not found:
            hours_data.append({"hour": hour, "count": 0})
    
    conn.close()
    
    return {
        'user_id': user_id,
        'username': username,
        'email': email,
        'created_at': created_at,
        'playlists': playlists,
        'favorites': favorites,
        'recently_played': recently_played,
        'listening_hours': hours_data
    }

def sign_out_user(user_id):
    """Sign out a user by clearing session state"""
    return True

# -------------------------------
# PLAYLIST MANAGEMENT FUNCTIONS
# -------------------------------
def create_playlist(user_id, name, description=""):
    """Create a new playlist"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    playlist_id = str(uuid.uuid4())
    
    cursor.execute('''
    INSERT INTO playlists (id, user_id, name, description)
    VALUES (?, ?, ?, ?)
    ''', (playlist_id, user_id, name, description))
    
    conn.commit()
    conn.close()
    
    add_karma_points(user_id, 'create_playlist', 10)
    
    return playlist_id

def add_track_to_playlist(playlist_id, track_id, user_id, track_name=None, artists=None, album_art=None):
    """Add a track to a playlist"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    # Verify the user owns this playlist
    cursor.execute('SELECT user_id FROM playlists WHERE id = ?', (playlist_id,))
    playlist_owner = cursor.fetchone()
    
    if not playlist_owner or playlist_owner[0] != user_id:
        conn.close()
        return False, "You don't have permission to modify this playlist"
    
    # Check if track already exists in the playlist
    cursor.execute('SELECT id FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?', 
                   (playlist_id, track_id))
    if cursor.fetchone():
        conn.close()
        return False, "Track already exists in this playlist"
    
    # If track details aren't provided, try to fetch them from MusicBrainz
    if not track_name or not artists:
        track_details = get_track_details_from_musicbrainz(track_id)
        if track_details:
            track_name = track_details.get('title', 'Unknown Track')
            artists = track_details.get('artist', 'Unknown Artist')
            album_art = track_details.get('album_art', None)
    
    # Add the track
    cursor.execute('''
    INSERT INTO playlist_tracks (playlist_id, track_id, track_name, artists, album_art)
    VALUES (?, ?, ?, ?, ?)
    ''', (playlist_id, track_id, track_name, artists, album_art))
    
    conn.commit()
    conn.close()
    
    add_karma_points(user_id, 'playlist_add', 3)
    
    return True, "Track added to playlist"

def remove_track_from_playlist(playlist_id, track_id, user_id):
    """Remove a track from a playlist"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    # Verify the user owns this playlist
    cursor.execute('SELECT user_id FROM playlists WHERE id = ?', (playlist_id,))
    playlist_owner = cursor.fetchone()
    
    if not playlist_owner or playlist_owner[0] != user_id:
        conn.close()
        return False, "You don't have permission to modify this playlist"
    
    # Remove the track
    cursor.execute('''
    DELETE FROM playlist_tracks 
    WHERE playlist_id = ? AND track_id = ?
    ''', (playlist_id, track_id))
    
    conn.commit()
    conn.close()
    
    return True, "Track removed from playlist"

def get_playlist(playlist_id, user_id=None):
    """Get a playlist and its tracks"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    # Get playlist details
    cursor.execute('''
    SELECT p.id, p.name, p.description, p.user_id, u.username
    FROM playlists p
    JOIN users u ON p.user_id = u.id
    WHERE p.id = ?
    ''', (playlist_id,))
    
    playlist_data = cursor.fetchone()
    
    if not playlist_data:
        conn.close()
        return None
    
    playlist_id, name, description, owner_id, owner_username = playlist_data
    
    # Get tracks in the playlist
    cursor.execute('''
    SELECT track_id, track_name, artists, album_art, added_at
    FROM playlist_tracks
    WHERE playlist_id = ?
    ORDER BY added_at DESC
    ''', (playlist_id,))
    
    tracks = []
    for row in cursor.fetchall():
        tracks.append({
            'id': row[0],
            'name': row[1],
            'artist': row[2],
            'album_art': row[3],
            'added_at': row[4]
        })
    
    conn.close()
    
    # Format the playlist data
    playlist = {
        'id': playlist_id,
        'name': name,
        'description': description,
        'owner': {
            'id': owner_id,
            'username': owner_username
        },
        'tracks': tracks,
        'is_owner': user_id == owner_id if user_id else False
    }
    
    return playlist

def get_user_playlists(user_id):
    """Get all playlists for a user"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT id, name, description, created_at
    FROM playlists
    WHERE user_id = ?
    ORDER BY created_at DESC
    ''', (user_id,))
    
    playlists = []
    for row in cursor.fetchall():
        playlist_id, name, description, created_at = row
        
        # Get track count for each playlist
        cursor.execute('SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id = ?', (playlist_id,))
        track_count = cursor.fetchone()[0]
        
        playlists.append({
            'id': playlist_id,
            'name': name,
            'description': description,
            'created_at': created_at,
            'track_count': track_count
        })
    
    conn.close()
    return playlists

# -------------------------------
# TRACK MANAGEMENT FUNCTIONS
# -------------------------------
def toggle_favorite_track(user_id, track_id, favorite=True, track_name=None, artists=None, album_art=None):
    """Add or remove a track from user's favorites"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    if favorite:
        # Check if already favorited
        cursor.execute('SELECT id FROM user_favorites WHERE user_id = ? AND track_id = ?', (user_id, track_id))
        if cursor.fetchone():
            conn.close()
            return False, "Track already in favorites"
        
        # If track details aren't provided, try to fetch them from MusicBrainz
        if not track_name or not artists:
            track_details = get_track_details_from_musicbrainz(track_id)
            if track_details:
                track_name = track_details.get('title', 'Unknown Track')
                artists = track_details.get('artist', 'Unknown Artist')
                album_art = track_details.get('album_art', None)
        
        # Add to favorites
        cursor.execute('''
        INSERT INTO user_favorites (user_id, track_id, track_name, artists, album_art)
        VALUES (?, ?, ?, ?, ?)
        ''', (user_id, track_id, track_name, artists, album_art))
    else:
        # Remove from favorites
        cursor.execute('''
        DELETE FROM user_favorites
        WHERE user_id = ? AND track_id = ?
        ''', (user_id, track_id))
    
    conn.commit()
    conn.close()
    
    if favorite:
        # Add karma points for liking a track
        add_karma_points(user_id, 'like', 5)
    else:
        # Remove karma points for unliking a track
        add_karma_points(user_id, 'unlike', -2)
    
    return True, "Favorites updated successfully"

def get_user_favorites(user_id):
    """Get all favorite tracks for a user"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT track_id, track_name, artists, album_art, added_at
    FROM user_favorites
    WHERE user_id = ?
    ORDER BY added_at DESC
    ''', (user_id,))
    
    favorites = []
    for row in cursor.fetchall():
        favorites.append({
            'id': row[0],
            'name': row[1],
            'artist': row[2],
            'album_art': row[3],
            'added_at': row[4]
        })
    
    conn.close()
    
    return favorites

# -------------------------------
# PLAYBACK MANAGEMENT FUNCTIONS
# -------------------------------
def get_playback_state(user_id):
    """Get the current playback state for a user"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT current_track, current_track_name, current_artists, current_album_art, 
           position_ms, is_playing, repeat_mode, shuffle, volume
    FROM playback_state
    WHERE user_id = ?
    ''', (user_id,))
    
    state = cursor.fetchone()
    
    if not state:
        # Initialize playback state if it doesn't exist
        cursor.execute('''
        INSERT INTO playback_state (user_id)
        VALUES (?)
        ''', (user_id,))
        conn.commit()
        
        state = (None, None, None, None, 0, 0, 'off', 0, 100)
    
    # Get queue
    cursor.execute('''
    SELECT track_id, track_name, artists, album_art
    FROM queue
    WHERE user_id = ?
    ORDER BY position
    ''', (user_id,))
    
    queue = []
    for row in cursor.fetchall():
        queue.append({
            'id': row[0],
            'name': row[1],
            'artist': row[2],
            'album_art': row[3]
        })
    
    # Get recently played
    cursor.execute('''
    SELECT track_id, track_name, artists, album_art
    FROM recently_played
    WHERE user_id = ?
    ORDER BY played_at DESC
    LIMIT 50
    ''', (user_id,))
    
    recently_played = []
    for row in cursor.fetchall():
        recently_played.append({
            'id': row[0],
            'name': row[1],
            'artist': row[2],
            'album_art': row[3]
        })
    
    conn.close()
    
    return {
        'current_track': state[0],
        'current_track_name': state[1],
        'current_artists': state[2],
        'current_album_art': state[3],
        'position_ms': state[4],
        'is_playing': bool(state[5]),
        'repeat_mode': state[6],
        'shuffle': bool(state[7]),
        'volume': state[8],
        'queue': queue,
        'recently_played': recently_played
    }

def update_playback_state(user_id, **kwargs):
    """Update playback state for a user"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    # Build update query dynamically based on provided kwargs
    if kwargs:
        set_clause = ', '.join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values())
        values.append(user_id)
        
        cursor.execute(f'''
        UPDATE playback_state
        SET {set_clause}, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
        ''', values)
        
        conn.commit()
    
    conn.close()
    return True

def start_playback(user_id, track_id=None, track_name=None, artists=None, album_art=None):
    """Start or resume playback"""
    update_data = {'is_playing': True}
    
    if track_id:
        update_data['current_track'] = track_id
        update_data['position_ms'] = 0
        
        # If track details aren't provided, try to fetch them from MusicBrainz
        if not track_name or not artists:
            track_details = get_track_details_from_musicbrainz(track_id)
            if track_details:
                track_name = track_details.get('title', 'Unknown Track')
                artists = track_details.get('artist', 'Unknown Artist')
                album_art = track_details.get('album_art', None)
        
        update_data['current_track_name'] = track_name
        update_data['current_artists'] = artists
        update_data['current_album_art'] = album_art
        
        # Add to recently played
        conn = sqlite3.connect('music_app.db')
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO recently_played (user_id, track_id, track_name, artists, album_art)
        VALUES (?, ?, ?, ?, ?)
        ''', (user_id, track_id, track_name, artists, album_art))
        
        # Add to listening data for analytics
        current_hour = datetime.now().hour
        cursor.execute('''
        INSERT INTO user_listening_data (user_id, track_id, action, hour)
        VALUES (?, ?, ?, ?)
        ''', (user_id, track_id, 'play', current_hour))
        
        conn.commit()
        conn.close()
        
        add_karma_points(user_id, 'play', 1)
    
    return update_playback_state(user_id, **update_data)

def pause_playback(user_id):
    """Pause playback"""
    return update_playback_state(user_id, is_playing=False)

def skip_to_next(user_id):
    """Skip to next track in queue"""
    state = get_playback_state(user_id)
    
    if not state['queue']:
        return False, "No tracks in queue"
    
    # Get next track from queue
    next_track = state['queue'][0]
    
    # Remove from queue
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    DELETE FROM queue
    WHERE user_id = ? AND track_id = ?
    ''', (user_id, next_track['id']))
    
    # Reorder remaining queue items
    cursor.execute('''
    UPDATE queue
    SET position = position - 1
    WHERE user_id = ? AND position > 0
    ''', (user_id,))
    
    conn.commit()
    conn.close()
    
    # Start playing next track
    start_playback(
        user_id, 
        next_track['id'], 
        next_track['name'], 
        next_track['artist'], 
        next_track['album_art']
    )
    
    return True, "Skipped to next track"

def skip_to_previous(user_id):
    """Skip to previous track"""
    state = get_playback_state(user_id)
    
    if not state['recently_played']:
        return False, "No previous tracks"
    
    # Get previous track
    prev_track = state['recently_played'][0]
    
    # If current track exists, add it to the front of the queue
    if state['current_track']:
        conn = sqlite3.connect('music_app.db')
        cursor = conn.cursor()
        
        # Shift all queue positions
        cursor.execute('''
        UPDATE queue
        SET position = position + 1
        WHERE user_id = ?
        ''', (user_id,))
        
        # Add current track to front of queue
        cursor.execute('''
        INSERT INTO queue (user_id, track_id, track_name, artists, album_art, position)
        VALUES (?, ?, ?, ?, ?, 0)
        ''', (
            user_id, 
            state['current_track'], 
            state['current_track_name'], 
            state['current_artists'], 
            state['current_album_art']
        ))
        
        conn.commit()
        conn.close()
    
    # Start playing previous track
    start_playback(
        user_id, 
        prev_track['id'], 
        prev_track['name'], 
        prev_track['artist'], 
        prev_track['album_art']
    )
    
    return True, "Skipped to previous track"

def add_to_queue(user_id, track_id, track_name=None, artists=None, album_art=None):
    """Add a track to the playback queue"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    # Get the highest position
    cursor.execute('''
    SELECT MAX(position) FROM queue
    WHERE user_id = ?
    ''', (user_id,))
    
    max_position = cursor.fetchone()[0]
    if max_position is None:
        max_position = -1
    
    # If track details aren't provided, try to fetch them from MusicBrainz
    if not track_name or not artists:
        track_details = get_track_details_from_musicbrainz(track_id)
        if track_details:
            track_name = track_details.get('title', 'Unknown Track')
            artists = track_details.get('artist', 'Unknown Artist')
            album_art = track_details.get('album_art', None)
    
    # Add to queue
    cursor.execute('''
    INSERT INTO queue (user_id, track_id, track_name, artists, album_art, position)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, track_id, track_name, artists, album_art, max_position + 1))
    
    conn.commit()
    conn.close()
    
    return True, "Track added to queue"

def get_queue(user_id):
    """Get the user's playback queue"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT track_id, track_name, artists, album_art FROM queue
    WHERE user_id = ?
    ORDER BY position
    ''', (user_id,))
    
    queue = []
    for row in cursor.fetchall():
        queue.append({
            'id': row[0],
            'name': row[1],
            'artist': row[2],
            'album_art': row[3]
        })
    
    conn.close()
    
    return queue

def get_recently_played(user_id, limit=20):
    """Get recently played tracks"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT track_id, track_name, artists, album_art FROM recently_played
    WHERE user_id = ?
    ORDER BY played_at DESC
    LIMIT ?
    ''', (user_id, limit))
    
    tracks = []
    for row in cursor.fetchall():
        tracks.append({
            'id': row[0],
            'name': row[1],
            'artist': row[2],
            'album_art': row[3]
        })
    
    conn.close()
    
    return tracks

def set_volume(user_id, volume_percent):
    """Set playback volume"""
    if not 0 <= volume_percent <= 100:
        return False, "Volume must be between 0 and 100"
    
    update_playback_state(user_id, volume=volume_percent)
    return True, f"Volume set to {volume_percent}%"

def toggle_shuffle(user_id, shuffle_state):
    """Toggle shuffle mode"""
    update_playback_state(user_id, shuffle=shuffle_state)
    
    if shuffle_state:
        # Shuffle the queue
        conn = sqlite3.connect('music_app.db')
        cursor = conn.cursor()
        
        # Get current queue
        cursor.execute('''
        SELECT id FROM queue
        WHERE user_id = ?
        ORDER BY position
        ''', (user_id,))
        
        queue_ids = [row[0] for row in cursor.fetchall()]
        
        # Shuffle positions
        positions = list(range(len(queue_ids)))
        random.shuffle(positions)
        
        # Update positions
        for i, queue_id in enumerate(queue_ids):
            cursor.execute('''
            UPDATE queue
            SET position = ?
            WHERE id = ?
            ''', (positions[i], queue_id))
        
        conn.commit()
        conn.close()
    
    return True, f"Shuffle {'enabled' if shuffle_state else 'disabled'}"

def set_repeat_mode(user_id, mode):
    """Set repeat mode (off, track, context)"""
    if mode not in ["off", "track", "context"]:
        return False, "Invalid repeat mode"
    
    update_playback_state(user_id, repeat_mode=mode)
    return True, f"Repeat mode set to {mode}"

# -------------------------------
# API INTEGRATION FUNCTIONS
# -------------------------------
def get_track_recommendations(artists=None, track_name=None, limit=10):
    """Get track recommendations from ReccoBeats API"""
    url = f"{RECCOBEATS_BASE_URL}/v1/track/recommendation"
    
    params = {"limit": limit}
    
    if artists:
        params["artists"] = artists
    
    if track_name:
        params["track_name"] = track_name
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error getting recommendations: {e}")
        
        # Return simulated data if API fails
        return {
            "tracks": [
                {
                    "id": f"track_{i}",
                    "title": f"Recommended Track {i}",
                    "artist": f"Artist {i % 5}",
                    "album": f"Album {i % 10}",
                    "album_art": f"https://picsum.photos/seed/track{i}/300/300"
                } for i in range(1, limit + 1)
            ]
        }

def get_track_details_from_reccobeats(track_id):
    """Get details for a specific track from ReccoBeats API"""
    url = f"{RECCOBEATS_BASE_URL}/v1/track/{track_id}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error getting track details from ReccoBeats: {e}")
        return None

def get_track_details_from_musicbrainz(track_id):
    """Get track details from MusicBrainz API"""
    url = f"{MUSICBRAINZ_BASE_URL}/recording/{track_id}"
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json"
    }
    
    params = {
        "inc": "artists+releases",
        "fmt": "json"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Extract artist name
        artists = "Unknown Artist"
        if "artist-credit" in data and len(data["artist-credit"]) > 0:
            artists = data["artist-credit"][0]["name"]
        
        # Extract album art (using CoverArtArchive if available)
        album_art = None
        if "releases" in data and len(data["releases"]) > 0:
            release_id = data["releases"][0]["id"]
            album_art = f"https://coverartarchive.org/release/{release_id}/front-250"
        
        return {
            "id": track_id,
            "title": data.get("title", "Unknown Track"),
            "artist": artists,
            "album": data.get("releases", [{}])[0].get("title", "Unknown Album") if "releases" in data else "Unknown Album",
            "album_art": album_art or f"https://picsum.photos/seed/{track_id}/300/300"
        }
    except requests.exceptions.RequestException as e:
        print(f"Error getting track details from MusicBrainz: {e}")
        return None

def get_track_details(track_id):
    """Get track details with improved fallback mechanisms"""
    # Check if the ID looks like a Spotify ID (base62 string)
    is_spotify_id = len(track_id) == 22 and all(c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz" for c in track_id)
    
    # Try to get from our local cache first (database)
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    # Check in favorites, playlist_tracks, and recently_played tables
    for table in ['user_favorites', 'playlist_tracks', 'recently_played', 'queue']:
        cursor.execute(f'SELECT track_name, artists, album_art FROM {table} WHERE track_id = ? LIMIT 1', (track_id,))
        result = cursor.fetchone()
        if result and result[0]:  # If we found a match with actual data
            conn.close()
            return {
                "id": track_id,
                "title": result[0],
                "artist": result[1],
                "album_art": result[2] or f"https://picsum.photos/seed/{track_id}/300/300"
            }
    
    conn.close()
    
    # If it's a Spotify-like ID, try to get from Spotify dataset
    if is_spotify_id and hasattr(st.session_state, 'user_data') and st.session_state.user_data:
        tracks_df = st.session_state.user_data.get('tracks', pd.DataFrame())
        if not tracks_df.empty and 'track_id' in tracks_df.columns:
            track_data = tracks_df[tracks_df['track_id'] == track_id]
            if not track_data.empty:
                return {
                    "id": track_id,
                    "title": track_data.iloc[0].get('track_name', f"Track {track_id}"),
                    "artist": track_data.iloc[0].get('artists', f"Artist for {track_id}"),
                    "album": track_data.iloc[0].get('album_name', "Unknown Album"),
                    "album_art": f"https://picsum.photos/seed/{track_id}/300/300"
                }
    
    # If it looks like a MusicBrainz UUID (36 chars with hyphens)
    if len(track_id) == 36 and track_id.count('-') == 4:
        mb_details = get_track_details_from_musicbrainz(track_id)
        if mb_details:
            return mb_details
    # Try ReccoBeats
    details = get_track_details_from_reccobeats(track_id)
    if details:
        return details
    
    # Return simulated data as last resort
    return {
        "id": track_id,
        "title": f"Track {track_id[:8]}...",
        "artist": f"Artist",
        "album": "Unknown Album",
        "duration_ms": 180000,
        "album_art": f"https://picsum.photos/seed/{track_id}/300/300"
    }

def get_playback_url(track_id):
    """Get the streaming URL for a track"""
    # For demonstration purposes, we'll return a dummy URL
    # In a real application, you would integrate with a streaming service API
    return f"https://example.com/stream/{track_id}.mp3"

def search_tracks(query, limit=20, offset=0):
    """Search for tracks using ReccoBeats API, falling back to MusicBrainz"""
    # Try ReccoBeats first
    recco_results = search_tracks_reccobeats(query, limit, offset)
    if recco_results and 'tracks' in recco_results and recco_results['tracks']:
        return recco_results
    
    # Fall back to MusicBrainz
    mb_results = search_tracks_musicbrainz(query, limit, offset)
    if mb_results:
        return mb_results
    
    # Return simulated data if both APIs fail
    return {
        "tracks": [
            {
                "id": f"search_{i}",
                "title": f"{query} Result {i}",
                "artist": f"Artist {i % 5}",
                "album": f"Album {i % 10}",
                "album_art": f"https://picsum.photos/seed/search{i}/300/300"
            } for i in range(1, limit + 1)
        ]
    }

def search_tracks_reccobeats(query, limit=20, offset=0):
    """Search for tracks using ReccoBeats API"""
    url = f"{RECCOBEATS_BASE_URL}/v1/search"
    
    params = {
        "q": query,
        "type": "track",
        "limit": limit,
        "offset": offset
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error searching tracks with ReccoBeats: {e}")
        return None

def search_tracks_musicbrainz(query, limit=20, offset=0):
    """Search for tracks using MusicBrainz API"""
    url = f"{MUSICBRAINZ_BASE_URL}/recording"
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json"
    }
    
    params = {
        "query": query,
        "limit": limit,
        "offset": offset,
        "fmt": "json"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Convert MusicBrainz format to our standard format
        tracks = []
        for recording in data.get("recordings", []):
            artists = "Unknown Artist"
            if "artist-credit" in recording and len(recording["artist-credit"]) > 0:
                artists = recording["artist-credit"][0]["name"]
            
            album_name = "Unknown Album"
            album_art = None
            if "releases" in recording and len(recording["releases"]) > 0:
                album_name = recording["releases"][0]["title"]
                release_id = recording["releases"][0]["id"]
                album_art = f"https://coverartarchive.org/release/{release_id}/front-250"
            
            tracks.append({
                "id": recording["id"],
                "title": recording["title"],
                "artist": artists,
                "album": album_name,
                "album_art": album_art or f"https://picsum.photos/seed/{recording['id']}/300/300"
            })
        
        return {"tracks": tracks}
    except requests.exceptions.RequestException as e:
        print(f"Error searching tracks with MusicBrainz: {e}")
        return None

def search_musicbrainz(query, entity_type="recording", limit=25, offset=0):
    """Search the MusicBrainz database"""
    url = f"{MUSICBRAINZ_BASE_URL}/{entity_type}"
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json"
    }
    
    params = {
        "query": query,
        "limit": limit,
        "offset": offset,
        "fmt": "json"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error searching MusicBrainz: {e}")
        return None

def get_musicbrainz_recording(mbid):
    """Get recording details from MusicBrainz"""
    url = f"{MUSICBRAINZ_BASE_URL}/recording/{mbid}"
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json"
    }
    
    params = {
        "inc": "artists+releases+url-rels+isrcs",
        "fmt": "json"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error getting MusicBrainz recording: {e}")
        return None

def get_musicbrainz_artist(mbid):
    """Get artist details from MusicBrainz"""
    url = f"{MUSICBRAINZ_BASE_URL}/artist/{mbid}"
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json"
    }
    
    params = {
        "inc": "recordings+releases+release-groups+works+url-rels",
        "fmt": "json"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error getting MusicBrainz artist: {e}")
        return None

# -------------------------------
# MACHINE LEARNING INTEGRATION
# -------------------------------
def load_spotify_track_metadata(filename="spotify_data.csv"):
    """
    Load track metadata from the Spotify dataset CSV file.
    """
    try:
        # Check if file exists in current directory
        if os.path.exists(filename):
            df = pd.read_csv(filename)
        # Check if file exists in data directory
        elif os.path.exists(os.path.join('data', filename)):
            df = pd.read_csv(os.path.join('data', filename))
        else:
            print(f"File {filename} not found in current or data directory")
            return pd.DataFrame()
            
        print(f"Loaded Spotify track metadata from {filename}")
        return df
    except Exception as e:
        print(f"Error loading Spotify dataset: {e}")
        return pd.DataFrame()

def simulate_user_interactions(num_entries=100, track_ids=None):
    """
    Simulate real-time ingestion of user interactions using Spotify track IDs.
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

def preprocess_data(raw_data):
    """
    Clean and wrangle raw data.
    """
    interactions_df = raw_data['interactions'].dropna()
    context_df = raw_data['context'].dropna()
    tracks_df = raw_data['tracks'].dropna()
    
    # Rename 'artists' column to 'artists' if it exists
    if 'artists' in tracks_df.columns and 'artists' not in tracks_df.columns:
        tracks_df['artists'] = tracks_df['artists']
        print("Renamed 'artists' column to 'artists'")
    
    # Check for required columns
    required_columns = ['track_id', 'artists', 'track_name']
    missing_columns = [col for col in required_columns if col not in tracks_df.columns]
    
    if missing_columns:
        print(f"Missing columns in track data: {missing_columns}")
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
    
    # Compute session_id: start a new session if time difference > 5 minutes (300 sec)
    merged_df = merged_df.sort_values(['user_id', 'timestamp'])
    merged_df.reset_index(drop=True, inplace=True)
    merged_df['session_diff'] = merged_df.groupby('user_id')['timestamp'].diff().dt.total_seconds().fillna(0)
    merged_df['session_id'] = merged_df.groupby('user_id')['session_diff'].apply(lambda x: (x > 300).cumsum()).reset_index(drop=True)
    
    # Add track_genre if it exists in the dataset
    if 'track_genre' in tracks_df.columns:
        merged_df = pd.merge(merged_df, tracks_df[['track_id', 'track_genre']], on='track_id', how='left')
    elif 'genre' in tracks_df.columns:
        merged_df = pd.merge(merged_df, tracks_df[['track_id', 'genre']], on='track_id', how='left')
        merged_df.rename(columns={'genre': 'track_genre'}, inplace=True)
    
    return merged_df

def extract_audio_features(track_metadata):
    """
    Extract audio features from the Spotify dataset.
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
    """
    fused_features = {}
    avg_mood = context_df['mood'].mean() if not context_df.empty else 0.5
    for track_id, features in audio_features.items():
        fused = features.copy()
        fused['mood_factor'] = avg_mood
        fused_features[track_id] = fused
    return fused_features

def extract_latent_features(fused_features):
    """
    Simulate latent feature extraction (e.g., via a Variational Autoencoder).
    """
    latent_features = {}
    for track_id, features in fused_features.items():
        latent_features[track_id] = {k: v * 0.8 for k, v in features.items()}
    return latent_features

def build_interaction_graph(processed_df, fused_features, track_metadata):
    """
    Build a heterogeneous graph of users, tracks, and artists.
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
    """
    weighted_edges = []
    for (user, track, weight) in edges:
        adjusted_weight = weight * 1.2  # dummy adjustment factor
        weighted_edges.append((user, track, adjusted_weight))
    return weighted_edges

def adaptive_recommendations(graph, latent_features):
    """
    Simulate an RL-based recommendation system.
    """
    recommendations = {}
    track_ids = list(latent_features.keys())
    for user in graph['nodes']['users']:
        recommendations[user] = random.choice(track_ids) if track_ids else None
    return recommendations

def generate_explanations(recommendations, graph):
    """
    Generate more personalized explanations for recommendations.
    """
    explanations = {}
    
    # Define a variety of explanation templates
    templates = [
        "Based on your interest in {genre} music, we think you'll enjoy this {mood} track by {artist}.",
        "Since you've been listening to artists like {similar_artist}, we recommend this {genre} track from {artist}.",
        "This {mood} song by {artist} matches your listening patterns during {time_of_day}.",
        "Fans of {similar_artist} also enjoy this {genre} track by {artist}.",
        "This {genre} track by {artist} has similar audio characteristics to songs you frequently play."
    ]
    
    # Define some mood and genre mappings for variety
    moods = ["energetic", "relaxing", "upbeat", "mellow", "intense", "atmospheric"]
    genres = ["pop", "rock", "electronic", "hip-hop", "indie", "jazz", "classical"]
    times = ["morning", "afternoon", "evening", "late night"]
    
    for user, track in recommendations.items():
        if track:
            artist = graph['track_to_artist'].get(track, "Unknown Artist")
            
            # Get a random similar artist from the graph
            similar_artists = [a for a in graph['nodes']['artists'] if a != artist]
            similar_artist = random.choice(similar_artists) if similar_artists else "other artists you like"
            
            # Randomly select explanation elements
            mood = random.choice(moods)
            genre = random.choice(genres)
            time_of_day = random.choice(times)
            
            # Choose a template and format it
            template = random.choice(templates)
            explanation = template.format(
                artist=artist,
                genre=genre,
                mood=mood,
                similar_artist=similar_artist,
                time_of_day=time_of_day
            )
            
            explanations[user] = explanation
    
    return explanations


def compute_leaderboard(graph):
    """
    Compute a leaderboard based on aggregated weighted edges per artist.
    """
    artist_scores = {}
    for (user, track, weight) in graph['weighted_edges']:
        artist = graph['track_to_artist'].get(track, "Unknown Artist")
        artist_scores[artist] = artist_scores.get(artist, 0) + weight
    sorted_leaderboard = sorted(artist_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_leaderboard

# -------------------------------
# STREAMLIT UI
# -------------------------------
# Set page configuration
st.set_page_config(
    page_title="Music Recommendation System",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply custom CSS for dark theme
st.markdown("""
<style>
    .main {
        background-color: #121212;
        color: white;
    }
    .stApp {
        background-color: #121212;
    }
    .css-1d391kg, .css-1wrcr25 {
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
    .stTabs [data-baseweb="tab-list"] {
        background-color: #1e1e1e;
        border-radius: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        color: white;
    }
    .stTabs [aria-selected="true"] {
        background-color: #00c9a7;
        color: black;
    }
    .stAudio > div {
        background-color: #1e1e1e;
    }
    .stSelectbox > div > div {
        background-color: #1e1e1e;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'current_page' not in st.session_state:
    st.session_state.current_page = "login"
if 'current_track' not in st.session_state:
    st.session_state.current_track = None
if 'is_playing' not in st.session_state:
    st.session_state.is_playing = False
if 'ml_data_loaded' not in st.session_state:
    st.session_state.ml_data_loaded = False
if 'ml_recommendations' not in st.session_state:
    st.session_state.ml_recommendations = None
if 'ml_explanations' not in st.session_state:
    st.session_state.ml_explanations = None
if 'ml_interaction_graph' not in st.session_state:
    st.session_state.ml_interaction_graph = None
if 'user_data' not in st.session_state:
    st.session_state.user_data = None

# Initialize database
setup_database()

# Authentication pages
def login_page():
    st.title("Login to Music Recommendation System")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Login")
        username = st.text_input("Username or Email", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        
        if st.button("Login"):
            if username and password:
                success, result = login_user(username, password)
                if success:
                    st.session_state.user_id = result["user_id"]
                    st.session_state.username = result["username"]
                    st.session_state.current_page = "home"
                    st.rerun()
                else:
                    st.error(result)
            else:
                st.error("Please enter both username and password")
    
    with col2:
        st.subheader("Register")
        reg_username = st.text_input("Username", key="reg_username")
        reg_email = st.text_input("Email", key="reg_email")
        reg_password = st.text_input("Password", type="password", key="reg_password")
        reg_confirm = st.text_input("Confirm Password", type="password", key="reg_confirm")
        
        if st.button("Register"):
            if not reg_username or not reg_email or not reg_password:
                st.error("Please fill in all fields")
            elif reg_password != reg_confirm:
                st.error("Passwords do not match")
            else:
                success, result = register_user(reg_username, reg_email, reg_password)
                if success:
                    st.success("Registration successful! Please login.")
                else:
                    st.error(result)

# Main application pages
def sidebar_navigation():
    with st.sidebar:
        st.title("Navigation")
        
        if st.button("Home"):
            st.session_state.current_page = "home"
            st.rerun()
        
        if st.button("Search"):
            st.session_state.current_page = "search"
            st.rerun()
        
        if st.button("Library"):
            st.session_state.current_page = "library"
            st.rerun()
        
        if st.button("Profile"):
            st.session_state.current_page = "profile"
            st.rerun()
        
        if st.button("Analytics"):
            st.session_state.current_page = "analytics"
            st.rerun()
        
        st.markdown("---")
        
        if st.button("Logout"):
            sign_out_user(st.session_state.user_id)
            # Clear session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state.current_page = "login"
            st.rerun()

# Add these imports at the top of your file
import base64
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

# Replace the existing get_preview_url function with this enhanced version
def get_preview_url(track_id, track_name=None, artist=None):
    """
    Get a preview URL for a track using multiple fallback methods:
    1. Try to fetch from Jamendo (free music API)
    2. Try to find a YouTube video
    3. Fall back to SoundHelix samples
    
    Returns a tuple: (url, source_type, embed_html)
    where source_type is 'audio', 'youtube', or 'soundhelix'
    """
    # List of sample audio clips for fallback
    sample_clips = [
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-5.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-6.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-7.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-8.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-9.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-10.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-11.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-12.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-13.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-14.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-15.mp3",
    ]
    
    # Method 1: Try to fetch from Jamendo (free music API)
    if track_name and artist:
        try:
            search_query = f"{track_name} {artist}"
            jamendo_url = f"https://api.jamendo.com/v3.0/tracks/?client_id=56d30c95&format=json&limit=1&search={quote_plus(search_query)}"
            response = requests.get(jamendo_url)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('results') and len(data['results']) > 0:
                    audio_url = data['results'][0].get('audio')
                    if audio_url:
                        return (audio_url, 'audio', None)
        except Exception as e:
            print(f"Error fetching from Jamendo: {e}")
    
    # Method 2: Try to find a YouTube video
    if track_name and artist:
        try:
            search_query = f"{track_name} {artist} official audio"
            search_url = f"https://www.youtube.com/results?search_query={quote_plus(search_query)}"
            
            response = requests.get(search_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                # Look for video IDs in the page
                scripts = soup.find_all('script')
                for script in scripts:
                    if 'videoId' in script.text:
                        import re
                        video_ids = re.findall(r'"videoId":"([^"]+)"', script.text)
                        if video_ids:
                            video_id = video_ids[0]
                            embed_html = f"""
                            <iframe width="100%" height="80" 
                                src="https://www.youtube.com/embed/{video_id}?autoplay=1" 
                                frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                                allowfullscreen>
                            </iframe>
                            """
                            return (f"https://www.youtube.com/watch?v={video_id}", 'youtube', embed_html)
        except Exception as e:
            print(f"Error finding YouTube video: {e}")
    
    # Method 3: Fall back to SoundHelix samples
    sample_index = int(hashlib.md5(str(track_id).encode()).hexdigest(), 16) % len(sample_clips)
    return (sample_clips[sample_index], 'soundhelix', None)

# Update the music_player function to use the new get_preview_url function
def music_player():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Music Player")
    
    # Get playback state
    playback_state = get_playback_state(st.session_state.user_id)
    
    # Update session state
    st.session_state.current_track = playback_state['current_track']
    st.session_state.is_playing = playback_state['is_playing']
    
    if st.session_state.current_track:
        col1, col2 = st.columns([1, 3])
        
        with col1:
            if playback_state['current_album_art']:
                st.image(playback_state['current_album_art'], width=100)
            else:
                st.image(f"https://picsum.photos/seed/{st.session_state.current_track}/300/300", width=100)
        
        with col2:
            st.markdown(f"<h4>{playback_state['current_track_name'] or 'Unknown Track'}</h4>", unsafe_allow_html=True)
            st.write(f"Artist: {playback_state['current_artists'] or 'Unknown Artist'}")
        
        # Get a preview URL based on the track ID and metadata
        preview_url, source_type, embed_html = get_preview_url(
            st.session_state.current_track,
            playback_state['current_track_name'],
            playback_state['current_artists']
        )
        
        # Display appropriate player based on source type
        if source_type == 'youtube' and embed_html:
            st.components.v1.html(embed_html, height=80)
            st.caption("Playing from YouTube")
        else:
            # For audio files (both Jamendo and SoundHelix)
            st.audio(preview_url, format="audio/mp3")
            if source_type == 'soundhelix':
                st.caption("Playing sample audio (SoundHelix)")
            else:
                st.caption("Playing from Jamendo (Free Music)")
    else:
        st.markdown("<h4 style='text-align: center;'>No track selected</h4>", unsafe_allow_html=True)

    # Player controls
    cols = st.columns(6)  # Reduced from 7 columns (removed play/pause)
    with cols[0]:
        if st.button("⏮️", key="prev"):
            skip_to_previous(st.session_state.user_id)
            st.rerun()
    with cols[1]:
        if st.button("⏭️", key="next"):
            skip_to_next(st.session_state.user_id)
            st.rerun()
    with cols[2]:
        if st.button("❤️", key="like"):
            if st.session_state.current_track:
                track_details = get_track_details(st.session_state.current_track)
                toggle_favorite_track(
                    st.session_state.user_id, 
                    st.session_state.current_track, 
                    True,
                    track_details.get('title'),
                    track_details.get('artist'),
                    track_details.get('album_art')
                )
                st.success("Added to favorites")
    with cols[3]:
        if st.button("➕", key="add_to_playlist_btn"):
            if st.session_state.current_track:
                track_details = get_track_details(st.session_state.current_track)
                # Use a different session state variable
                st.session_state.show_playlist_modal = True
                st.session_state.modal_track_id = st.session_state.current_track
                st.session_state.modal_track_name = track_details.get('title')
                st.session_state.modal_track_artist = track_details.get('artist')
                st.session_state.modal_track_album_art = track_details.get('album_art')
                st.rerun()
    with cols[4]:
        if st.button("📋", key="add_to_queue"):
            if st.session_state.current_track:
                track_details = get_track_details(st.session_state.current_track)
                add_to_queue(
                    st.session_state.user_id, 
                    st.session_state.current_track,
                    track_details.get('title'),
                    track_details.get('artist'),
                    track_details.get('album_art')
                )
                st.success("Added to queue")
    with cols[5]:
        volume = st.slider("Volume", 0, 100, int(playback_state['volume']), key="volume_slider")
        if volume != playback_state['volume']:
            set_volume(st.session_state.user_id, volume)
            
            # Add JavaScript to actually control the volume of audio elements
            volume_js = f"""
            <script>
                const audioElements = document.getElementsByTagName('audio');
                for(let audio of audioElements) {{
                    audio.volume = {volume/100};
                }}
                
                // Also handle YouTube iframes if present
                const iframes = document.getElementsByTagName('iframe');
                for(let iframe of iframes) {{
                    if(iframe.src.includes('youtube')) {{
                        // Try to set YouTube volume via postMessage
                        iframe.contentWindow.postMessage(
                            JSON.stringify({{
                                'event': 'command',
                                'func': 'setVolume',
                                'args': [{volume}]
                            }}), '*'
                        );
                    }}
                }}
            </script>
            """
            st.components.v1.html(volume_js, height=0)
    
    st.markdown('</div>', unsafe_allow_html=True)

def load_ml_data_for_user(user_id):
    """Load ML data specifically for a user, combining pipeline data with user activity"""
    # First, load the general ML data
    raw_data = ingest_data(spotify_filename="spotify_data.csv", num_interactions=100)
    processed_data = preprocess_data(raw_data)
    
    # Extract audio features and other ML components
    track_metadata = raw_data['tracks']
    audio_features = extract_audio_features(track_metadata)
    fused_features = fuse_features(audio_features, raw_data['context'])
    latent_features = extract_latent_features(fused_features)
    
    # Now, get user-specific listening data
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT track_id, action, timestamp
    FROM user_listening_data
    WHERE user_id = ?
    ORDER BY timestamp DESC
    ''', (user_id,))
    
    user_interactions = cursor.fetchall()
    conn.close()
    
    # Convert to DataFrame format similar to the pipeline's
    if user_interactions:
        user_df = pd.DataFrame(user_interactions, columns=['track_id', 'action', 'timestamp'])
        
        # Merge with track metadata
        user_processed = pd.merge(user_df, track_metadata[['track_id', 'artists', 'track_name']], 
                                 on='track_id', how='left')
        
        # Combine with the general processed data, prioritizing user's data
        combined_df = pd.concat([user_processed, processed_data]).drop_duplicates(subset=['track_id', 'action'], keep='first')
    else:
        combined_df = processed_data
    
    # Build interaction graph with the combined data
    interaction_graph = build_interaction_graph(combined_df, fused_features, track_metadata)
    
    # Generate personalized recommendations
    recommendations = adaptive_recommendations(interaction_graph, latent_features)
    explanations = generate_explanations(recommendations, interaction_graph)
    
    return {
        'processed_data': combined_df,
        'interaction_graph': interaction_graph,
        'recommendations': recommendations,
        'explanations': explanations,
        'audio_features': audio_features,
        'track_metadata': track_metadata
    }

def get_user_audio_features_analysis(user_id):
    """Get audio feature analysis specific to a user's listening patterns"""
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    try:
        # Get the user's most played tracks
        cursor.execute('''
        SELECT track_id, COUNT(*) as play_count
        FROM user_listening_data
        WHERE user_id = ? AND action = 'play'
        GROUP BY track_id
        ORDER BY play_count DESC
        LIMIT 50
        ''', (user_id,))
        
        user_tracks = cursor.fetchall()
        track_ids = [row[0] for row in user_tracks]
        
        # If we have ML data loaded
        if hasattr(st.session_state, 'user_data') and st.session_state.user_data:
            tracks_df = st.session_state.user_data.get('tracks', pd.DataFrame())
            
            if not tracks_df.empty:
                # Filter for user's tracks
                user_tracks_df = tracks_df[tracks_df['track_id'].isin(track_ids)]
                
                # Select audio features to analyze
                audio_features = ['danceability', 'energy', 'acousticness', 
                                 'instrumentalness', 'liveness', 'valence']
                
                # Check which features are available
                available_features = [f for f in audio_features if f in user_tracks_df.columns]
                
                if available_features:
                    # Calculate average features for user's tracks
                    user_avg_features = {}
                    for feature in available_features:
                        user_avg_features[feature] = user_tracks_df[feature].mean()
                    
                    # Calculate overall average for comparison
                    overall_avg_features = {}
                    for feature in available_features:
                        overall_avg_features[feature] = tracks_df[feature].mean()
                    
                    # Get feature distributions for user's tracks
                    feature_distributions = {}
                    for feature in available_features:
                        feature_distributions[feature] = user_tracks_df[feature].tolist()
                    
                    return {
                        'user_avg_features': user_avg_features,
                        'overall_avg_features': overall_avg_features,
                        'feature_distributions': feature_distributions,
                        'available_features': available_features
                    }
        
        # If we couldn't get data from ML pipeline
        return None
    except Exception as e:
        print(f"Error getting user audio features analysis: {e}")
        return None
    finally:
        conn.close()

def load_ml_data():
    """Load machine learning data and generate recommendations"""
    if not st.session_state.ml_data_loaded:
        with st.spinner("Loading recommendation engine..."):
            try:
                # Load data
                raw_data = ingest_data(spotify_filename="spotify_data.csv", num_interactions=100)
                processed_data = preprocess_data(raw_data)
                
                # Extract features
                track_metadata = raw_data['tracks']
                audio_features = extract_audio_features(track_metadata)
                fused_features = fuse_features(audio_features, raw_data['context'])
                latent_features = extract_latent_features(fused_features)
                
                # Build interaction graph and generate recommendations
                interaction_graph = build_interaction_graph(processed_data, fused_features, track_metadata)
                recommendations = adaptive_recommendations(interaction_graph, latent_features)
                explanations = generate_explanations(recommendations, interaction_graph)
                
                # Store in session state
                st.session_state.ml_data_loaded = True
                st.session_state.ml_recommendations = recommendations
                st.session_state.ml_explanations = explanations
                st.session_state.ml_interaction_graph = interaction_graph
                st.session_state.ml_processed_data = processed_data
                st.session_state.user_data = raw_data
            except Exception as e:
                st.error(f"Error loading ML data: {e}")
                # Initialize with empty values to prevent further errors
                st.session_state.ml_data_loaded = True
                st.session_state.ml_recommendations = {}
                st.session_state.ml_explanations = {}
                st.session_state.ml_interaction_graph = {'nodes': {'users': [], 'tracks': [], 'artists': []}, 'edges': [], 'weighted_edges': [], 'track_to_artist': {}}
                st.session_state.ml_processed_data = pd.DataFrame()
                st.session_state.user_data = {'tracks': pd.DataFrame(), 'interactions': pd.DataFrame(), 'context': pd.DataFrame()}

def get_musicbrainz_recommendations(limit=5):
    """
    Get music recommendations using MusicBrainz API
    
    This function retrieves popular or random recordings from MusicBrainz
    to serve as recommendations when no user history is available.
    
    Args:
        limit (int): Maximum number of recommendations to return
        
    Returns:
        list: A list of dictionaries containing track information
    """
    # Define popular genres to search for
    genres = ["rock", "pop", "electronic", "jazz", "hip-hop", "classical"]
    selected_genre = random.choice(genres)
    
    # Search for recordings in the selected genre
    url = f"{MUSICBRAINZ_BASE_URL}/recording"
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json"
    }
    
    params = {
        "query": f"tag:{selected_genre} AND primarytype:album",
        "limit": limit * 2,  # Request more to filter down to quality results
        "fmt": "json"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        recommendations = []
        for recording in data.get("recordings", [])[:limit]:
            # Extract artist name
            artists = "Unknown Artist"
            if "artist-credit" in recording and len(recording["artist-credit"]) > 0:
                artists = recording["artist-credit"][0]["name"]
            
            # Extract album art (using CoverArtArchive if available)
            album_art = None
            if "releases" in recording and len(recording["releases"]) > 0:
                release_id = recording["releases"][0]["id"]
                album_art = f"https://coverartarchive.org/release/{release_id}/front-250"
            
            recommendations.append({
                "id": recording["id"],
                "title": recording["title"],
                "artist": artists,
                "album": recording.get("releases", [{}])[0].get("title", "Unknown Album") if "releases" in recording else "Unknown Album",
                "album_art": album_art or f"https://picsum.photos/seed/{recording['id']}/300/300"
            })
        
        return recommendations
    except requests.exceptions.RequestException as e:
        print(f"Error getting MusicBrainz recommendations: {e}")
        
        # Return simulated data if API fails
        return [
            {
                "id": f"mb_rec_{i}",
                "title": f"Recommended Track {i}",
                "artist": f"Artist {i % 5}",
                "album": f"Album {i % 10}",
                "album_art": f"https://picsum.photos/seed/rec{i}/300/300"
            } for i in range(1, limit + 1)
        ]


def home_page():
    st.title("Your Music Dashboard")
    
    # Load ML data if not already loaded
    load_ml_data()
    
    # Get recommendations from MusicBrainz API
    mb_recommendations = get_musicbrainz_recommendations()
    
    # Get ML-based recommendations
    ml_recommendations = None
    if st.session_state.ml_recommendations:
        # Convert user_id to string for comparison
        user_id_str = str(st.session_state.user_id)
        # Find recommendations for this user or any user if not found
        for user, track in st.session_state.ml_recommendations.items():
            if str(user) == user_id_str:
                ml_recommendations = [(user, track)]
                break
        
        if not ml_recommendations:
            # Take first 3 recommendations if no match for current user
            ml_recommendations = list(st.session_state.ml_recommendations.items())[:3]
    
    # Display MusicBrainz recommendations
    if mb_recommendations:
        st.header("Recommended for You")
        
        # Display recommendations in a grid
        cols = st.columns(5)
        for i, track in enumerate(mb_recommendations[:5]):
            with cols[i % 5]:
                st.markdown(f"""
                <div style="position: relative; height: 200px; border-radius: 10px; overflow: hidden; border: 1px solid #2e3a40;">
                    <img src="{track.get('album_art', 'https://via.placeholder.com/300')}" style="width: 100%; height: 100%; object-fit: cover; opacity: 0.7;">
                    <div style="position: absolute; bottom: 0; left: 0; right: 0; background: rgba(0,0,0,0.6); padding: 10px;">
                        <h3 style="color: #00c9a7; margin: 0; font-size: 18px;">{track.get('title')}</h3>
                        <p style="margin: 5px 0 0 0; font-size: 12px;">{track.get('artist')}</p>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button("Play", key=f"play_rec_{i}"):
                    start_playback(
                        st.session_state.user_id, 
                        track.get('id'),
                        track.get('title'),
                        track.get('artist'),
                        track.get('album_art')
                    )
                    st.rerun()
    
    # Display ML-based recommendations
    if ml_recommendations:
        st.header("Personalized Recommendations")
        
        for i, (user_id, track_id) in enumerate(ml_recommendations):
            # Get track details
            track_details = get_track_details(track_id)
            
            # Get explanation
            explanation = st.session_state.ml_explanations.get(user_id, "Based on your listening patterns")
            
            st.markdown(f"""
            <div class="card">
                <div style="display: flex; align-items: center;">
                    <img src="{track_details.get('album_art', 'https://via.placeholder.com/300')}" style="width: 60px; height: 60px; object-fit: cover; margin-right: 15px; border-radius: 5px;">
                    <div>
                        <h3 style="margin: 0;">{track_details.get('title')}</h3>
                        <p style="margin: 5px 0;">{track_details.get('artist')}</p>
                        <p style="margin: 5px 0; font-style: italic; color: #aaa;">{explanation}</p>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                if st.button("Play Now", key=f"play_ml_{i}"):
                    start_playback(
                        st.session_state.user_id, 
                        track_id,
                        track_details.get('title'),
                        track_details.get('artist'),
                        track_details.get('album_art')
                    )
                    st.rerun()
            with col2:
                if st.button("Add to Queue", key=f"queue_ml_{i}"):
                    add_to_queue(
                        st.session_state.user_id, 
                        track_id,
                        track_details.get('title'),
                        track_details.get('artist'),
                        track_details.get('album_art')
                    )
                    st.success("Added to queue")
            with col3:
                if st.button("Add to Playlist", key=f"playlist_ml_{i}"):
                    st.session_state.add_to_playlist = True
                    st.session_state.add_track_id = track_id
                    st.session_state.add_track_name = track_details.get('title')
                    st.session_state.add_track_artist = track_details.get('artist')
                    st.session_state.add_track_album_art = track_details.get('album_art')
    
    # Display recently played
    recently_played = get_recently_played(st.session_state.user_id)
    if recently_played:
        st.header("Recently Played")
        
        for i, track in enumerate(recently_played[:5]):
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.markdown(f"""
                <div style="display: flex; align-items: center;">
                    <img src="{track.get('album_art', 'https://via.placeholder.com/300')}" style="width: 40px; height: 40px; object-fit: cover; margin-right: 10px; border-radius: 3px;">
                    <div>
                        <p style="margin: 0;"><b>{track.get('name', 'Unknown Track')}</b> - {track.get('artist', 'Unknown Artist')}</p>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                if st.button("Play", key=f"play_recent_{i}"):
                    start_playback(
                        st.session_state.user_id, 
                        track.get('id'),
                        track.get('name'),
                        track.get('artist'),
                        track.get('album_art')
                    )
                    st.rerun()
            with col3:
                if st.button("Add", key=f"add_recent_{i}"):
                    st.session_state.add_to_playlist = True
                    st.session_state.add_track_id = track.get('id')
                    st.session_state.add_track_name = track.get('name')
                    st.session_state.add_track_artist = track.get('artist')
                    st.session_state.add_track_album_art = track.get('album_art')
    
    # Display music player
    music_player()

def search_page():
    st.title("Search Music")
    
    search_query = st.text_input("Search for tracks, artists, or albums")
    
    if search_query:
        # Search using MusicBrainz API
        mb_results = search_tracks_musicbrainz(search_query)
        
        if mb_results and mb_results.get('tracks'):
            st.subheader("Tracks")
            
            for i, track in enumerate(mb_results['tracks']):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.markdown(f"""
                    <div style="display: flex; align-items: center;">
                        <img src="{track.get('album_art', 'https://via.placeholder.com/300')}" style="width: 40px; height: 40px; object-fit: cover; margin-right: 10px; border-radius: 3px;">
                        <div>
                            <p style="margin: 0;"><b>{track.get('title')}</b> - {track.get('artist')}</p>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    if st.button("Play", key=f"play_search_{i}"):
                        start_playback(
                            st.session_state.user_id, 
                            track.get('id'),
                            track.get('title'),
                            track.get('artist'),
                            track.get('album_art')
                        )
                        st.rerun()
                with col3:
                    if st.button("Add", key=f"add_search_{i}"):
                        st.session_state.add_to_playlist = True
                        st.session_state.add_track_id = track.get('id')
                        st.session_state.add_track_name = track.get('title')
                        st.session_state.add_track_artist = track.get('artist')
                        st.session_state.add_track_album_art = track.get('album_art')
        else:
            st.warning("No results found for your search query.")
    
    # If a MusicBrainz recording is selected, show details
    if 'mb_recording' in st.session_state:
        st.markdown("---")
        st.subheader("Track Details")
        
        recording = st.session_state.mb_recording
        artist_credit = recording.get('artist-credit', [{}])[0].get('name', 'Unknown Artist')
        
        st.markdown(f"""
        <div class="card">
            <h3>{recording.get('title')}</h3>
            <p>Artist: {artist_credit}</p>
            <p>Length: {int(recording.get('length', 0) / 1000)} seconds</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Show releases this recording appears on
        if 'releases' in recording:
            st.subheader("Appears On")
            
            for release in recording.get('releases', [])[:5]:
                st.markdown(f"""
                <div class="card">
                    <p>{release.get('title')} ({release.get('date', 'Unknown date')})</p>
                </div>
                """, unsafe_allow_html=True)
                
            # Add button to play this track
            if st.button("Play This Track"):
                track_id = recording.get('id')
                track_title = recording.get('title')
                album_art = None
                if 'releases' in recording and len(recording['releases']) > 0:
                    release_id = recording['releases'][0]['id']
                    album_art = f"https://coverartarchive.org/release/{release_id}/front-250"
                
                start_playback(
                    st.session_state.user_id, 
                    track_id,
                    track_title,
                    artist_credit,
                    album_art
                )
                st.rerun()
    
    # Display music player
    music_player()

def library_page():
    st.title("Your Library")
    
    tab1, tab2, tab3 = st.tabs(["Playlists", "Favorites", "Queue"])
    
    with tab1:
        st.subheader("Your Playlists")
        
        # Create new playlist
        with st.expander("Create New Playlist"):
            playlist_name = st.text_input("Playlist Name")
            playlist_desc = st.text_area("Description (optional)")
            
            # In library_page function
            if st.button("Create Playlist", key="create_playlist_btn"):
                if playlist_name:
                    playlist_id = create_playlist(st.session_state.user_id, playlist_name, playlist_desc)
                    st.success(f"Playlist '{playlist_name}' created successfully!")
                else:
                    st.error("Please enter a playlist name")

        
        # List user's playlists
        playlists = get_user_playlists(st.session_state.user_id)
        
        if playlists:
            for playlist in playlists:
                st.markdown(f"""
                <div class="card">
                    <h3>{playlist['name']}</h3>
                    <p>{playlist['description']}</p>
                    <p>{playlist['track_count']} tracks</p>
                </div>
                """, unsafe_allow_html=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("View", key=f"view_playlist_{playlist['id']}"):
                        st.session_state.current_playlist = playlist['id']
                        st.session_state.current_page = "playlist"
                        st.rerun()
                with col2:
                    if st.button("Play", key=f"play_playlist_{playlist['id']}"):
                        # Get playlist tracks and add to queue
                        playlist_data = get_playlist(playlist['id'], st.session_state.user_id)
                        if playlist_data and playlist_data['tracks']:
                            first_track = playlist_data['tracks'][0]
                            start_playback(
                                st.session_state.user_id, 
                                first_track['id'],
                                first_track['name'],
                                first_track['artist'],
                                first_track['album_art']
                            )
                            
                            # Add remaining tracks to queue
                            for track in playlist_data['tracks'][1:]:
                                add_to_queue(
                                    st.session_state.user_id, 
                                    track['id'],
                                    track['name'],
                                    track['artist'],
                                    track['album_art']
                                )
                            st.rerun()
        else:
            st.info("You haven't created any playlists yet")
    
    with tab2:
        st.subheader("Your Favorites")
        
        # Get user's favorite tracks
        favorites = get_user_favorites(st.session_state.user_id)
        
        if favorites:
            for i, track in enumerate(favorites):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.markdown(f"""
                    <div style="display: flex; align-items: center;">
                        <img src="{track.get('album_art', 'https://via.placeholder.com/300')}" style="width: 40px; height: 40px; object-fit: cover; margin-right: 10px; border-radius: 3px;">
                        <div>
                            <p style="margin: 0;"><b>{track.get('name', 'Unknown Track')}</b> - {track.get('artist', 'Unknown Artist')}</p>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    if st.button("Play", key=f"play_fav_{i}"):
                        start_playback(
                            st.session_state.user_id, 
                            track['id'],
                            track['name'],
                            track['artist'],
                            track['album_art']
                        )
                        st.rerun()
                with col3:
                    if st.button("Remove", key=f"remove_fav_{i}"):
                        toggle_favorite_track(st.session_state.user_id, track['id'], False)
                        st.rerun()
        else:
            st.info("You haven't added any favorites yet")
    
    with tab3:
        st.subheader("Your Queue")
        
        # Get user's queue
        queue = get_queue(st.session_state.user_id)
        
        if queue:
            for i, track in enumerate(queue):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"""
                    <div style="display: flex; align-items: center;">
                        <img src="{track.get('album_art', 'https://via.placeholder.com/300')}" style="width: 40px; height: 40px; object-fit: cover; margin-right: 10px; border-radius: 3px;">
                        <div>
                            <p style="margin: 0;">{i+1}. <b>{track.get('name', 'Unknown Track')}</b> - {track.get('artist', 'Unknown Artist')}</p>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    if st.button("Remove", key=f"remove_queue_{i}"):
                        # Remove from queue
                        conn = sqlite3.connect('music_app.db')
                        cursor = conn.cursor()
                        cursor.execute('''
                        DELETE FROM queue 
                        WHERE user_id = ? AND track_id = ? AND position = ?
                        ''', (st.session_state.user_id, track['id'], i))
                        
                        # Update positions for remaining tracks
                        cursor.execute('''
                        UPDATE queue
                        SET position = position - 1
                        WHERE user_id = ? AND position > ?
                        ''', (st.session_state.user_id, i))
                        
                        conn.commit()
                        conn.close()
                        st.rerun()
        else:
            st.info("Your queue is empty")
    
    # Display music player
    music_player()

def playlist_page():
    if 'current_playlist' not in st.session_state:
        st.session_state.current_page = "library"
        st.rerun()
    
    playlist_data = get_playlist(st.session_state.current_playlist, st.session_state.user_id)
    
    if not playlist_data:
        st.error("Playlist not found")
        st.session_state.current_page = "library"
        st.rerun()
    
    st.title(playlist_data['name'])
    st.write(playlist_data['description'])
    st.write(f"Created by: {playlist_data['owner']['username']}")
    
    # Play all button
    if st.button("Play All"):
        if playlist_data['tracks']:
            first_track = playlist_data['tracks'][0]
            start_playback(
                st.session_state.user_id, 
                first_track['id'],
                first_track['name'],
                first_track['artist'],
                first_track['album_art']
            )
            
            # Add remaining tracks to queue
            for track in playlist_data['tracks'][1:]:
                add_to_queue(
                    st.session_state.user_id, 
                    track['id'],
                    track['name'],
                    track['artist'],
                    track['album_art']
                )
            st.rerun()
    
    # List tracks
    st.subheader("Tracks")
    
    if playlist_data['tracks']:
        for i, track in enumerate(playlist_data['tracks']):
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.markdown(f"""
                <div style="display: flex; align-items: center;">
                    <img src="{track.get('album_art', 'https://via.placeholder.com/300')}" style="width: 40px; height: 40px; object-fit: cover; margin-right: 10px; border-radius: 3px;">
                    <div>
                        <p style="margin: 0;">{i+1}. <b>{track.get('name', 'Unknown Track')}</b> - {track.get('artist', 'Unknown Artist')}</p>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                if st.button("Play", key=f"play_pl_{i}"):
                    start_playback(
                        st.session_state.user_id, 
                        track['id'],
                        track['name'],
                        track['artist'],
                        track['album_art']
                    )
                    st.rerun()
            with col3:
                if playlist_data['is_owner']:
                    if st.button("Remove", key=f"remove_pl_{i}"):
                        success, message = remove_track_from_playlist(
                            st.session_state.current_playlist, 
                            track['id'], 
                            st.session_state.user_id
                        )
                        if success:
                            st.success("Track removed from playlist")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(message)
    else:
        st.info("This playlist is empty")
    
    # Add tracks to playlist section
    if playlist_data['is_owner']:
        st.subheader("Add Tracks")
        search_query = st.text_input("Search for tracks to add", key="playlist_search")
        
        if search_query:
            search_results = search_tracks_musicbrainz(search_query)
            
            if search_results and search_results.get('tracks'):
                for i, track in enumerate(search_results['tracks'][:5]):
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.markdown(f"""
                        <div style="display: flex; align-items: center;">
                            <img src="{track.get('album_art', 'https://via.placeholder.com/300')}" style="width: 40px; height: 40px; object-fit: cover; margin-right: 10px; border-radius: 3px;">
                            <div>
                                <p style="margin: 0;"><b>{track.get('title')}</b> - {track.get('artist')}</p>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    with col2:
                        if st.button("Add", key=f"add_to_pl_{i}"):
                            success, message = add_track_to_playlist(
                                st.session_state.current_playlist,
                                track.get('id'),
                                st.session_state.user_id,
                                track.get('title'),
                                track.get('artist'),
                                track.get('album_art')
                            )
                            if success:
                                st.success(message)
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error(message)
            else:
                st.info("No tracks found matching your search")
    
    # Back button
    if st.button("Back to Library"):
        st.session_state.current_page = "library"
        st.rerun()
    
    # Display music player
    music_player()
    
def profile_page():
    st.title("Your Profile")
    
    # Get user profile and karma
    profile = get_user_profile(st.session_state.user_id)
    karma = get_user_karma(st.session_state.user_id)
    
    if not profile:
        st.error("Could not load profile")
        return
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.image("https://i.pravatar.cc/150?u=" + profile['username'], width=150)
    
    with col2:
        st.markdown(f"<h2>{profile['username']}</h2>", unsafe_allow_html=True)
        st.write(f"Email: {profile['email']}")
        st.write(f"Member since: {profile['created_at']}")
        
        # Display karma points prominently
        st.markdown(f"""
        <div class="card" style="background-color: #2a2a2a; padding: 15px; border-radius: 10px; margin-top: 10px;">
            <h3 style="color: #00c9a7; margin: 0;">Karma Points: {karma['total']}</h3>
            <div style="background-color: #333; height: 10px; border-radius: 5px; margin-top: 10px; overflow: hidden;">
                <div style="background-color: #00c9a7; height: 100%; width: {min(karma['total']/1000*100, 100)}%;"></div>
            </div>
            <p style="margin-top: 5px; font-size: 12px;">Level {karma['total'] // 100 + 1} • {karma['total'] % 100}/100 to next level</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Display karma history
    st.subheader("Recent Karma Activity")
    
    if karma['history']:
        for item in karma['history']:
            action_emoji = "🎵" if item['action'] == 'play' else "❤️" if item['action'] == 'like' else "📋" if item['action'] == 'playlist_add' else "📝" if item['action'] == 'create_playlist' else "🔄"
            st.markdown(f"""
            <div style="display: flex; align-items: center; margin-bottom: 5px;">
                <div style="width: 30px; text-align: center; font-size: 20px;">{action_emoji}</div>
                <div style="flex-grow: 1; padding-left: 10px;">
                    <span>{item['action'].replace('_', ' ').title()}</span>
                    <span style="color: #aaa; font-size: 12px; margin-left: 10px;">{item['timestamp']}</span>
                </div>
                <div style="color: {'#00c9a7' if item['points'] > 0 else '#ff6b6b'}; font-weight: bold;">
                    {'+' if item['points'] > 0 else ''}{item['points']}
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No karma activity yet. Start interacting with music to earn points!")
    
    # User's listening stats
    st.subheader("Your Listening Stats")
    
    # Get user-specific audio feature analysis
    audio_analysis = get_user_audio_features_analysis(st.session_state.user_id)
    
    if audio_analysis and audio_analysis['available_features']:
        # Create comparison chart of user's preferences vs overall average
        features = audio_analysis['available_features']
        user_values = [audio_analysis['user_avg_features'][f] for f in features]
        overall_values = [audio_analysis['overall_avg_features'][f] for f in features]
        
        comparison_df = pd.DataFrame({
            'Feature': features,
            'Your Average': user_values,
            'Overall Average': overall_values
        })
        
        fig = px.bar(
            comparison_df, 
            x='Feature', 
            y=['Your Average', 'Overall Average'],
            barmode='group',
            title="Your Music Preferences vs Average",
            color_discrete_sequence=["#00c9a7", "#ff6b6b"]
        )
        fig.update_layout(
            paper_bgcolor="#1e1e1e",
            plot_bgcolor="#1e1e1e",
            font=dict(color="white")
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Add explanation of what this means
        st.markdown("""
        <div class="card">
            <h4>What This Means:</h4>
            <p>This chart shows how your music preferences compare to the average user. Higher values in features like:</p>
            <ul>
                <li><b>Danceability</b>: You prefer more danceable tracks</li>
                <li><b>Energy</b>: You prefer more energetic, intense music</li>
                <li><b>Acousticness</b>: You prefer more acoustic, less electronic sounds</li>
                <li><b>Valence</b>: You prefer more positive, happy music</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        
    load_ml_data()
    
    # Create listening activity chart
    if profile.get('listening_hours'):
        # Convert to DataFrame for plotting
        hours_df = pd.DataFrame(profile['listening_hours'])
        
        # Create a proper DataFrame with consistent dimensions
        fig = px.bar(
            hours_df,
            x='hour',
            y='count',
            title="Listening Activity by Hour",
            color_discrete_sequence=["#00c9a7"]
        )
        fig.update_layout(
            xaxis_title="Hour of Day",
            yaxis_title="Number of Plays",
            paper_bgcolor="#1e1e1e",
            plot_bgcolor="#1e1e1e",
            font=dict(color="white")
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Account settings
    st.header("Account Settings")
    
    with st.expander("Change Password"):
        current_password = st.text_input("Current Password", type="password", key="current_pwd")
        new_password = st.text_input("New Password", type="password", key="new_pwd")
        confirm_password = st.text_input("Confirm New Password", type="password", key="confirm_pwd")
        
        if st.button("Update Password"):
            if not current_password or not new_password or not confirm_password:
                st.error("Please fill in all fields")
            elif new_password != confirm_password:
                st.error("New passwords do not match")
            else:
                # Verify current password
                conn = sqlite3.connect('music_app.db')
                cursor = conn.cursor()
                
                cursor.execute('SELECT password_hash FROM users WHERE id = ?', (st.session_state.user_id,))
                stored_password = cursor.fetchone()[0]
                
                salt, hash_value = stored_password.split(':')
                computed_hash = hashlib.sha256((current_password + salt).encode()).hexdigest()
                
                if computed_hash != hash_value:
                    st.error("Current password is incorrect")
                else:
                    # Update password
                    new_salt = secrets.token_hex(16)
                    new_hash = hashlib.sha256((new_password + new_salt).encode()).hexdigest()
                    
                    cursor.execute(
                        'UPDATE users SET password_hash = ? WHERE id = ?',
                        (f"{new_salt}:{new_hash}", st.session_state.user_id)
                    )
                    
                    conn.commit()
                    st.success("Password updated successfully")
                
                conn.close()
    
    # Display music player
    music_player()

def profile_page():
    st.title("Your Profile")
    
    # Get user profile and karma
    profile = get_user_profile(st.session_state.user_id)
    karma = get_user_karma(st.session_state.user_id)
    
    if not profile:
        st.error("Could not load profile")
        return
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.image("https://i.pravatar.cc/150?u=" + profile['username'], width=150)
    
    with col2:
        st.markdown(f"<h2>{profile['username']}</h2>", unsafe_allow_html=True)
        st.write(f"Email: {profile['email']}")
        st.write(f"Member since: {profile['created_at']}")
        
        # Display karma points prominently
        st.markdown(f"""
        <div class="card" style="background-color: #2a2a2a; padding: 15px; border-radius: 10px; margin-top: 10px;">
            <h3 style="color: #00c9a7; margin: 0;">Karma Points: {karma['total']}</h3>
            <div style="background-color: #333; height: 10px; border-radius: 5px; margin-top: 10px; overflow: hidden;">
                <div style="background-color: #00c9a7; height: 100%; width: {min(karma['total']/1000*100, 100)}%;"></div>
            </div>
            <p style="margin-top: 5px; font-size: 12px;">Level {karma['total'] // 100 + 1} • {karma['total'] % 100}/100 to next level</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Display karma history
    st.subheader("Recent Karma Activity")
    
    if karma['history']:
        for item in karma['history']:
            action_emoji = "🎵" if item['action'] == 'play' else "❤️" if item['action'] == 'like' else "📋" if item['action'] == 'playlist_add' else "📝" if item['action'] == 'create_playlist' else "🔄"
            st.markdown(f"""
            <div style="display: flex; align-items: center; margin-bottom: 5px;">
                <div style="width: 30px; text-align: center; font-size: 20px;">{action_emoji}</div>
                <div style="flex-grow: 1; padding-left: 10px;">
                    <span>{item['action'].replace('_', ' ').title()}</span>
                    <span style="color: #aaa; font-size: 12px; margin-left: 10px;">{item['timestamp']}</span>
                </div>
                <div style="color: {'#00c9a7' if item['points'] > 0 else '#ff6b6b'}; font-weight: bold;">
                    {'+' if item['points'] > 0 else ''}{item['points']}
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No karma activity yet. Start interacting with music to earn points!")
    
    # User stats and activity
    st.header("Your Listening Stats")
    
    # Load ML data for analytics
    load_ml_data()
    
    # Create listening activity chart
    if profile.get('listening_hours'):
        # Convert to DataFrame for plotting
        hours_df = pd.DataFrame(profile['listening_hours'])
        
        # Create a proper DataFrame with consistent dimensions
        fig = px.bar(
            hours_df,
            x='hour',
            y='count',
            title="Listening Activity by Hour",
            color_discrete_sequence=["#00c9a7"]
        )
        fig.update_layout(
            xaxis_title="Hour of Day",
            yaxis_title="Number of Plays",
            paper_bgcolor="#1e1e1e",
            plot_bgcolor="#1e1e1e",
            font=dict(color="white")
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Account settings
    st.header("Account Settings")
    
    with st.expander("Change Password"):
        current_password = st.text_input("Current Password", type="password", key="current_pwd")
        new_password = st.text_input("New Password", type="password", key="new_pwd")
        confirm_password = st.text_input("Confirm New Password", type="password", key="confirm_pwd")
        
        if st.button("Update Password"):
            if not current_password or not new_password or not confirm_password:
                st.error("Please fill in all fields")
            elif new_password != confirm_password:
                st.error("New passwords do not match")
            else:
                # Verify current password
                conn = sqlite3.connect('music_app.db')
                cursor = conn.cursor()
                
                cursor.execute('SELECT password_hash FROM users WHERE id = ?', (st.session_state.user_id,))
                stored_password = cursor.fetchone()[0]
                
                salt, hash_value = stored_password.split(':')
                computed_hash = hashlib.sha256((current_password + salt).encode()).hexdigest()
                
                if computed_hash != hash_value:
                    st.error("Current password is incorrect")
                else:
                    # Update password
                    new_salt = secrets.token_hex(16)
                    new_hash = hashlib.sha256((new_password + new_salt).encode()).hexdigest()
                    
                    cursor.execute(
                        'UPDATE users SET password_hash = ? WHERE id = ?',
                        (f"{new_salt}:{new_hash}", st.session_state.user_id)
                    )
                    
                    conn.commit()
                    st.success("Password updated successfully")
                
                conn.close()
    
    # Display music player
    music_player()
    
def get_artist_engagement_data(user_id=None):
    """
    Get artist engagement data based on actual user activity
    If user_id is provided, get data for that user only
    Otherwise, get aggregate data for all users
    """
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    try:
        # Define the base query
        query = '''
        SELECT p.artists, COUNT(*) as play_count,
               SUM(CASE WHEN l.action = 'play' THEN 1 ELSE 0 END) as plays,
               SUM(CASE WHEN l.action = 'like' THEN 1 ELSE 0 END) as likes,
               SUM(CASE WHEN l.action = 'playlist_add' THEN 1 ELSE 0 END) as playlist_adds,
               SUM(CASE WHEN l.action = 'skip' THEN 1 ELSE 0 END) as skips
        FROM user_listening_data l
        JOIN recently_played p ON l.track_id = p.track_id
        '''
        
        # Add user filter if specified
        if user_id:
            query += ' WHERE l.user_id = ?'
            params = (user_id,)
        else:
            params = ()
            
        query += ' GROUP BY p.artists ORDER BY play_count DESC LIMIT 10'
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        # Calculate engagement score: plays + (likes * 1.5) + (playlist_adds * 1.2) - (skips * 0.5)
        engagement_data = []
        for row in results:
            artist = row[0]
            plays = row[2]
            likes = row[3]
            playlist_adds = row[4]
            skips = row[5]
            
            engagement_score = plays + (likes * 1.5) + (playlist_adds * 1.2) - (skips * 0.5)
            
            engagement_data.append({
                'artist': artist,
                'engagement_score': engagement_score,
                'plays': plays,
                'likes': likes,
                'playlist_adds': playlist_adds,
                'skips': skips
            })
        
        return engagement_data
    except Exception as e:
        print(f"Error getting artist engagement data: {e}")
        return []
    finally:
        conn.close()

def get_user_interaction_analysis(user_id=None):
    """
    Get user interaction analysis based on actual activity
    If user_id is provided, get data for that user only
    Otherwise, get aggregate data for all users
    """
    conn = sqlite3.connect('music_app.db')
    cursor = conn.cursor()
    
    try:
        # Get action counts
        if user_id:
            cursor.execute('''
            SELECT action, COUNT(*) as count
            FROM user_listening_data
            WHERE user_id = ?
            GROUP BY action
            ''', (user_id,))
        else:
            cursor.execute('''
            SELECT action, COUNT(*) as count
            FROM user_listening_data
            GROUP BY action
            ''')
        
        action_counts = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Get hourly activity
        if user_id:
            cursor.execute('''
            SELECT hour, COUNT(*) as count
            FROM user_listening_data
            WHERE user_id = ?
            GROUP BY hour
            ORDER BY hour
            ''', (user_id,))
        else:
            cursor.execute('''
            SELECT hour, COUNT(*) as count
            FROM user_listening_data
            GROUP BY hour
            ORDER BY hour
            ''')
        
        hourly_activity = []
        for hour in range(24):
            found = False
            for row in cursor.fetchall():
                if row[0] == hour:
                    hourly_activity.append({'hour': hour, 'count': row[1]})
                    found = True
                    break
            if not found:
                hourly_activity.append({'hour': hour, 'count': 0})
        
        return {
            'action_counts': action_counts,
            'hourly_activity': hourly_activity
        }
    except Exception as e:
        print(f"Error getting user interaction analysis: {e}")
        return {'action_counts': {}, 'hourly_activity': []}
    finally:
        conn.close()

def analytics_page():
    st.title("Music Analytics Dashboard")
    
    # Load ML data for analytics
    load_ml_data()
    
    if not st.session_state.ml_data_loaded:
        st.info("Loading recommendation engine data...")
        return
    
    # Artist Leaderboard with improved visualization
    st.header("Artist Leaderboard")
    
    if st.session_state.ml_interaction_graph:
        leaderboard = compute_leaderboard(st.session_state.ml_interaction_graph)
        
        # Create a more meaningful DataFrame for the leaderboard
        leaderboard_df = pd.DataFrame(leaderboard[:10], columns=['Artist', 'Engagement Score'])
        
        # Add engagement metrics explanation
        st.markdown("""
        <div class="card">
            <p>The <b>Engagement Score</b> is calculated based on multiple factors:</p>
            <ul>
                <li>Play count (1.0 points per play)</li>
                <li>Like actions (1.5 points per like)</li>
                <li>Playlist additions (1.2 points per add)</li>
                <li>Skip actions (-0.5 points per skip)</li>
            </ul>
            <p>Higher scores indicate stronger user engagement with the artist.</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Create a more visually appealing bar chart
        fig = px.bar(
            leaderboard_df,
            x='Artist',
            y='Engagement Score',
            title="Top Artists by User Engagement",
            color='Engagement Score',
            color_continuous_scale='Viridis',
            labels={'Engagement Score': 'User Engagement Score'}
        )
        fig.update_layout(
            xaxis_title="Artist",
            yaxis_title="Engagement Score",
            paper_bgcolor="#1e1e1e",
            plot_bgcolor="#1e1e1e",
            font=dict(color="white"),
            xaxis=dict(tickangle=-45)
        )
        st.plotly_chart(fig, use_container_width=True)

    # User Interaction Analysis
    st.header("User Interaction Analysis")
    
    if hasattr(st.session_state, 'ml_processed_data') and 'action' in st.session_state.ml_processed_data.columns:
        action_counts = st.session_state.ml_processed_data['action'].value_counts()
        
        fig = px.pie(
            values=action_counts.values,
            names=action_counts.index,
            title="User Interactions by Type",
            hole=0.4,
            color_discrete_sequence=["#00c9a7", "#ff6b6b", "#feca57", "#5f27cd"]
        )
        fig.update_layout(
            paper_bgcolor="#1e1e1e",
            plot_bgcolor="#1e1e1e",
            font=dict(color="white")
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Audio Features Analysis
    st.header("Audio Features Analysis")
    
    # Get track metadata with audio features
    if hasattr(st.session_state, 'user_data') and st.session_state.user_data and 'tracks' in st.session_state.user_data:
        track_metadata = st.session_state.user_data['tracks']
        
        # Select audio features to analyze
        audio_features = ['danceability', 'energy', 'acousticness', 'instrumentalness', 'valence']
        
        # Check if these features exist in the dataset
        available_features = [f for f in audio_features if f in track_metadata.columns]
        
        if available_features:
            # Create tabs for different visualizations
            feature_tabs = st.tabs(["Average Features", "Feature Distribution", "Feature Correlation"])
            
            with feature_tabs[0]:
                # Calculate average features
                feature_data = []
                for feature in available_features:
                    feature_data.append({
                        'Feature': feature.capitalize(),
                        'Average': track_metadata[feature].mean()
                    })
                
                feature_df = pd.DataFrame(feature_data)
                
                # Create bar chart
                fig = px.bar(
                    feature_df,
                    x='Feature',
                    y='Average',
                    title="Average Audio Features in Your Music",
                    color='Feature',
                    color_discrete_sequence=["#00c9a7", "#ff6b6b", "#feca57", "#5f27cd", "#48dbfb"]
                )
                fig.update_layout(
                    xaxis_title="Audio Feature",
                    yaxis_title="Average Value (0-1)",
                    paper_bgcolor="#1e1e1e",
                    plot_bgcolor="#1e1e1e",
                    font=dict(color="white")
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # Add explanation
                st.markdown("""
                <div class="card">
                    <h4>Understanding Audio Features:</h4>
                    <ul>
                        <li><b>Danceability</b>: How suitable a track is for dancing (0.0 = least danceable, 1.0 = most danceable)</li>
                        <li><b>Energy</b>: Perceptual measure of intensity and activity (0.0 = calm, 1.0 = energetic)</li>
                        <li><b>Acousticness</b>: Confidence measure of whether the track is acoustic (1.0 = high confidence)</li>
                        <li><b>Instrumentalness</b>: Predicts whether a track contains no vocals (1.0 = instrumental)</li>
                        <li><b>Valence</b>: Musical positiveness conveyed by a track (0.0 = negative, 1.0 = positive)</li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)
            
            with feature_tabs[1]:
                # Create distribution plots
                selected_feature = st.selectbox(
                    "Select feature to analyze:",
                    options=available_features,
                    format_func=lambda x: x.capitalize()
                )
                
                # Create histogram
                fig = px.histogram(
                    track_metadata, 
                    x=selected_feature,
                    nbins=20,
                    color_discrete_sequence=["#00c9a7"],
                    title=f"Distribution of {selected_feature.capitalize()} Values"
                )
                fig.update_layout(
                    xaxis_title=selected_feature.capitalize(),
                    yaxis_title="Number of Tracks",
                    paper_bgcolor="#1e1e1e",
                    plot_bgcolor="#1e1e1e",
                    font=dict(color="white")
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # Show statistics
                stats = track_metadata[selected_feature].describe()
                st.markdown(f"""
                <div class="card">
                    <h4>Statistics for {selected_feature.capitalize()}:</h4>
                    <p>Mean: {stats['mean']:.3f}</p>
                    <p>Median: {stats['50%']:.3f}</p>
                    <p>Standard Deviation: {stats['std']:.3f}</p>
                    <p>Min: {stats['min']:.3f}</p>
                    <p>Max: {stats['max']:.3f}</p>
                </div>
                """, unsafe_allow_html=True)
            
            with feature_tabs[2]:
                # Create correlation matrix for audio features
                corr_matrix = track_metadata[available_features].corr()
                
                # Create heatmap
                fig = px.imshow(
                    corr_matrix,
                    text_auto=True,
                    color_continuous_scale='Viridis',
                    title="Correlation Between Audio Features"
                )
                fig.update_layout(
                    paper_bgcolor="#1e1e1e",
                    plot_bgcolor="#1e1e1e",
                    font=dict(color="white")
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # Explain correlations
                st.markdown("""
                <div class="card">
                    <h4>Understanding Feature Correlations:</h4>
                    <p>This heatmap shows how different audio features relate to each other:</p>
                    <ul>
                        <li>Values close to 1 indicate strong positive correlation (features increase together)</li>
                        <li>Values close to -1 indicate strong negative correlation (one increases as the other decreases)</li>
                        <li>Values close to 0 indicate little to no correlation</li>
                    </ul>
                    <p>For example, energy and acousticness often have a negative correlation, as energetic tracks tend to be less acoustic.</p>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.warning("No audio features found in the dataset. Please load a dataset with audio features.")
    
    # Recommendation Insights
    st.header("Recommendation Insights")
    
    if st.session_state.ml_recommendations and st.session_state.ml_explanations:
        st.subheader("How Our Recommendations Work")
        
        st.markdown("""
        <div class="card">
            <p>Our recommendation system uses a combination of techniques:</p>
            <ul>
                <li>Collaborative filtering based on user interactions</li>
                <li>Content-based analysis of audio features</li>
                <li>Graph neural networks to model user-track relationships</li>
                <li>Reinforcement learning to adapt to your preferences over time</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        
        # Sample explanations
        st.subheader("Recommendation Explanations")
        
        for user_id, explanation in list(st.session_state.ml_explanations.items())[:3]:
            track_id = st.session_state.ml_recommendations.get(user_id)
            if track_id:
                track_details = get_track_details(track_id)
                
                st.markdown(f"""
                <div class="card">
                    <h4>{track_details.get('title')} by {track_details.get('artist')}</h4>
                    <p><i>{explanation}</i></p>
                </div>
                """, unsafe_allow_html=True)
    
    # Display music player
    music_player()

def add_to_playlist_modal():
    if 'show_playlist_modal' in st.session_state and st.session_state.show_playlist_modal:
        st.subheader("Add to Playlist")
        
        # Get user's playlists
        playlists = get_user_playlists(st.session_state.user_id)
        
        if playlists:
            playlist_id = st.selectbox("Select Playlist", 
                                      options=[p['id'] for p in playlists],
                                      format_func=lambda x: next((p['name'] for p in playlists if p['id'] == x), ""),
                                      key="playlist_select")
            
            if st.button("Add", key="confirm_add_to_playlist"):
                success, message = add_track_to_playlist(
                    playlist_id, 
                    st.session_state.modal_track_id, 
                    st.session_state.user_id,
                    st.session_state.modal_track_name,
                    st.session_state.modal_track_artist,
                    st.session_state.modal_track_album_art
                )
                if success:
                    st.success(message)
                else:
                    st.error(message)
                
                # Reset modal state
                st.session_state.show_playlist_modal = False
                for key in ['modal_track_id', 'modal_track_name', 'modal_track_artist', 'modal_track_album_art']:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
            
            if st.button("Cancel", key="cancel_add_to_playlist"):
                st.session_state.show_playlist_modal = False
                for key in ['modal_track_id', 'modal_track_name', 'modal_track_artist', 'modal_track_album_art']:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()

# Main app logic
def main():
    # Check if user is logged in
    if not st.session_state.user_id:
        login_page()
        return
    
    # Show sidebar navigation
    sidebar_navigation()
    
    # Check for add to playlist modal
    if 'show_playlist_modal' in st.session_state and st.session_state.show_playlist_modal:
        add_to_playlist_modal()
    
    # Show current page
    if st.session_state.current_page == "home":
        home_page()
    elif st.session_state.current_page == "search":
        search_page()
    elif st.session_state.current_page == "library":
        library_page()
    elif st.session_state.current_page == "playlist":
        playlist_page()
    elif st.session_state.current_page == "profile":
        profile_page()
    elif st.session_state.current_page == "analytics":
        analytics_page()
    else:
        st.session_state.current_page = "home"
        st.rerun()

if __name__ == "__main__":
    main()
