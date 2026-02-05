#!/usr/bin/env python3
"""
Weather & Flight Tracking Dashboard for Raspberry Pi
Displays local weather conditions and nearby aircraft in real-time
"""

import requests
import time
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import matplotlib.patches as mpatches
from matplotlib.animation import FuncAnimation
import numpy as np
from typing import Dict, List, Optional
import warnings
import os
from dotenv import load_dotenv 
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

warnings.filterwarnings('ignore')

load_dotenv()

WEATHER_API = os.getenv("WEATHER_API")
CLIENT_ID = os.getenv("CLIENT_ID")
SECRET_ID= os.getenv("SECRET_ID")

# Configuration
CONFIG = {
    'location': {
        'lat': 55.6761,  # Copenhagen latitude
        'lon': 12.5683,  # Copenhagen longitude
        'name': 'Copenhagen'
    },
    'weather': {
        'api_key': WEATHER_API,  # Get free key from openweathermap.org
        'units': 'metric'
    },
    'aviation': {
        'radius': 200,  # km around your location
        'update_interval': 30,  # seconds
        # OpenSky OAuth2 credentials (optional but recommended)
        # Get these from: https://opensky-network.org/my-opensky/account
        'client_id': CLIENT_ID,  # Your OpenSky client_id
        'client_secret': SECRET_ID,  # Your OpenSky client_secret
    },
    'display': {
        'fullscreen': False,
        'refresh_rate': 5,  # seconds
        'layout': '2x2',  # Options: '2x2', 'widescreen', 'bigmap', 'vertical', '3column'
    }
}

class WeatherAPI:
    """Handles weather data fetching"""
    
    def __init__(self, api_key: str, lat: float, lon: float):
        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.base_url = "https://api.openweathermap.org/data/2.5"
    
    def get_current_weather(self) -> Optional[Dict]:
        """Fetch current weather conditions"""
        try:
            url = f"{self.base_url}/weather"
            params = {
                'lat': self.lat,
                'lon': self.lon,
                'appid': self.api_key,
                'units': CONFIG['weather']['units']
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Weather API error: {e}")
            return None
    
    def get_forecast(self) -> Optional[Dict]:
        """Fetch weather forecast"""
        try:
            url = f"{self.base_url}/forecast"
            params = {
                'lat': self.lat,
                'lon': self.lon,
                'appid': self.api_key,
                'units': CONFIG['weather']['units']
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Forecast API error: {e}")
            return None

class OpenSkyAuth:
    """Handles OAuth2 authentication for OpenSky Network API"""
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
        self.access_token = None
        self.token_expiry = None
    
    def get_token(self) -> Optional[str]:
        """Get or refresh OAuth2 access token"""
        # Check if we have a valid token
        if self.access_token and self.token_expiry:
            if time.time() < self.token_expiry - 60:  # 60s buffer before expiry
                return self.access_token
        
        # Get new token
        try:
            data = {
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }
            
            response = requests.post(
                self.token_url,
                data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=10
            )
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data['access_token']
            # Tokens expire after 30 minutes (1800 seconds)
            self.token_expiry = time.time() + token_data.get('expires_in', 1800)
            
            print(f"✅ OAuth2 token obtained (expires in {token_data.get('expires_in', 1800)}s)")
            return self.access_token
            
        except Exception as e:
            print(f"❌ OAuth2 authentication failed: {e}")
            return None
    
    def get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for API requests"""
        token = self.get_token()
        if token:
            return {'Authorization': f'Bearer {token}'}
        return {}


class FlightTracker:
    """Handles flight tracking using OpenSky Network API (free, no key required)"""
    
    def __init__(self, lat: float, lon: float, radius: float, client_id: str = None, client_secret: str = None):
        self.lat = lat
        self.lon = lon
        self.radius = radius  # in km
        self.base_url = "https://opensky-network.org/api"
        
        # Setup OAuth2 authentication if credentials provided
        self.auth = None
        if client_id and client_secret:
            self.auth = OpenSkyAuth(client_id, client_secret)
            print("🔐 Using OAuth2 authentication for OpenSky API")
        else:
            print("ℹ️  Using anonymous OpenSky API access (limited to 400 credits/day)")
    
    def _calculate_bounds(self):
        """Calculate bounding box for aircraft search"""
        # Rough conversion: 1 degree latitude ≈ 111 km
        lat_offset = self.radius / 111.0
        lon_offset = self.radius / (111.0 * np.cos(np.radians(self.lat)))
        
        return {
            'lamin': self.lat - lat_offset,
            'lamax': self.lat + lat_offset,
            'lomin': self.lon - lon_offset,
            'lomax': self.lon + lon_offset
        }
    
    def get_nearby_aircraft(self) -> List[Dict]:
        """Fetch aircraft within radius using latest OpenSky API"""
        try:
            bounds = self._calculate_bounds()
            url = f"{self.base_url}/states/all"
            params = bounds
            
            # Get authentication headers if using OAuth2
            headers = {}
            if self.auth:
                headers = self.auth.get_auth_headers()
            
            response = requests.get(url, params=params, headers=headers, timeout=15)
            
            # Check rate limit headers (if available)
            if 'X-Rate-Limit-Remaining' in response.headers:
                remaining = response.headers.get('X-Rate-Limit-Remaining')
                print(f"  API credits remaining: {remaining}")
            
            if 'X-Rate-Limit-Retry-After-Seconds' in response.headers:
                retry_after = response.headers.get('X-Rate-Limit-Retry-After-Seconds')
                print(f"  Rate limited. Retry after: {retry_after}s")
            
            response.raise_for_status()
            data = response.json()
            
            if not data or 'states' not in data or not data['states']:
                return []
            
            aircraft_list = []
            for state in data['states']:
                # Parse OpenSky state vector according to latest API docs
                # Index mapping from API documentation:
                # 0: icao24, 1: callsign, 2: origin_country, 3: time_position,
                # 4: last_contact, 5: longitude, 6: latitude, 7: baro_altitude,
                # 8: on_ground, 9: velocity, 10: true_track, 11: vertical_rate,
                # 12: sensors, 13: geo_altitude, 14: squawk, 15: spi,
                # 16: position_source, 17: category
                
                aircraft = {
                    'icao24': state[0],
                    'callsign': state[1].strip() if state[1] else 'N/A',
                    'origin_country': state[2],
                    'time_position': state[3],
                    'last_contact': state[4],
                    'longitude': state[5],
                    'latitude': state[6],
                    'baro_altitude': state[7],  # meters (barometric)
                    'on_ground': state[8],
                    'velocity': state[9],  # m/s
                    'true_track': state[10],  # degrees (was 'heading')
                    'vertical_rate': state[11],  # m/s
                    'sensors': state[12] if len(state) > 12 else None,
                    'geo_altitude': state[13] if len(state) > 13 else None,
                    'squawk': state[14] if len(state) > 14 else None,
                    'spi': state[15] if len(state) > 15 else None,
                    'position_source': state[16] if len(state) > 16 else None,
                    'category': state[17] if len(state) > 17 else None,
                }
                
                # Filter out aircraft on ground
                if not aircraft['on_ground'] and aircraft['baro_altitude']:
                    # Use barometric altitude (more reliable)
                    altitude_m = aircraft['baro_altitude']
                    aircraft['altitude_ft'] = int(altitude_m * 3.28084)
                    
                    # Convert velocity to knots
                    aircraft['speed_kts'] = int(aircraft['velocity'] * 1.94384) if aircraft['velocity'] else 0
                    
                    # Use true_track (not heading which is magnetic)
                    aircraft['heading'] = aircraft['true_track']
                    
                    # Calculate distance
                    aircraft['distance'] = self._calculate_distance(
                        aircraft['latitude'], aircraft['longitude']
                    )
                    aircraft_list.append(aircraft)
            
            # Sort by distance
            aircraft_list.sort(key=lambda x: x['distance'])
            return aircraft_list[:15]  # Return top 15 closest
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                print(f"❌ Unauthorized (401). Check your OAuth2 credentials.")
            elif e.response.status_code == 429:
                print(f"⚠️  Rate limit exceeded (429). Wait before next request.")
                if 'X-Rate-Limit-Retry-After-Seconds' in e.response.headers:
                    retry = e.response.headers.get('X-Rate-Limit-Retry-After-Seconds')
                    print(f"   Retry after: {retry} seconds")
            else:
                print(f"HTTP error {e.response.status_code}: {e}")
            return []
        except Exception as e:
            print(f"Flight tracking error: {e}")
            return []
    
    def _calculate_distance(self, lat2: float, lon2: float) -> float:
        """Calculate distance in km using Haversine formula"""
        if lat2 is None or lon2 is None:
            return float('inf')
        
        R = 6371  # Earth radius in km
        lat1, lon1 = np.radians(self.lat), np.radians(self.lon)
        lat2, lon2 = np.radians(lat2), np.radians(lon2)
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
        
        return R * c
    
    @staticmethod
    def get_category_name(category: int) -> str:
        """Get human-readable aircraft category name"""
        categories = {
            0: "Unknown",
            1: "No Info",
            2: "Light",
            3: "Small",
            4: "Large",
            5: "High Vortex",
            6: "Heavy",
            7: "High Perf",
            8: "Helicopter",
            9: "Glider",
            10: "Balloon",
            11: "Parachute",
            12: "Ultralight",
            13: "Reserved",
            14: "Drone",
            15: "Space",
            16: "Emergency",
            17: "Service",
            18: "Obstacle",
            19: "Cluster",
            20: "Line"
        }
        return categories.get(category, "Unknown")

class WeatherFlightDashboard:
    """Main dashboard class"""
    
    def __init__(self):
        self.weather_api = WeatherAPI(
            CONFIG['weather']['api_key'],
            CONFIG['location']['lat'],
            CONFIG['location']['lon']
        )
        self.flight_tracker = FlightTracker(
            CONFIG['location']['lat'],
            CONFIG['location']['lon'],
            CONFIG['aviation']['radius'],
            CONFIG['aviation'].get('client_id'),
            CONFIG['aviation'].get('client_secret')
        )
        
        self.current_weather = None
        self.forecast = None
        self.aircraft = []
        
        # Setup matplotlib
        plt.style.use('dark_background')
        self.setup_layout()
        
    def setup_layout(self):
        """Create dashboard layout"""
        layout_mode = CONFIG['display']['layout']
        
        # Define layout configurations
        layouts = {
            '2x2': {
                'figsize': (14, 8),
                'description': 'Classic 2x2 Grid',
                'grid': (2, 2),
                'positions': {
                    'weather': (0, 0),
                    'map': (0, 1),
                    'forecast': (1, 0),
                    'flights': (1, 1)
                }
            },
            'widescreen': {
                'figsize': (16, 6),
                'description': 'Widescreen - All in one row',
                'grid': (1, 4),
                'positions': {
                    'weather': (0, 0),
                    'forecast': (0, 1),
                    'map': (0, 2),
                    'flights': (0, 3)
                }
            },
            'bigmap': {
                'figsize': (14, 8),
                'description': 'Big Map Focus',
                'grid': (3, 3),
                'positions': {
                    'map': ((0, 2), (0, 2)),  # rows 0-1, cols 0-1
                    'weather': (0, 2),
                    'forecast': (1, 2),
                    'flights': (2, slice(None))  # full width
                }
            },
            'vertical': {
                'figsize': (8, 14),
                'description': 'Vertical Stack',
                'grid': (4, 1),
                'positions': {
                    'weather': (0, 0),
                    'map': (1, 0),
                    'forecast': (2, 0),
                    'flights': (3, 0)
                }
            },
            '3column': {
                'figsize': (15, 8),
                'description': '3 Columns',
                'grid': (2, 3),
                'positions': {
                    'weather': (slice(None), 0),  # full height
                    'map': (0, 1),
                    'forecast': (1, 1),
                    'flights': (slice(None), 2)  # full height
                }
            }
        }
        
        # Get layout config or default to 2x2
        layout_config = layouts.get(layout_mode, layouts['2x2'])
        print(f"\nUsing layout: {layout_config['description']}")
        
        # Create figure with appropriate size
        self.fig = plt.figure(figsize=layout_config['figsize'])
        
        # Create grid
        gs = self.fig.add_gridspec(*layout_config['grid'], hspace=0.3, wspace=0.3)
        
        # Add subplots based on layout
        positions = layout_config['positions']
        
        if layout_mode == 'bigmap':
            # Special handling for bigmap layout
            self.ax_map = self.fig.add_subplot(gs[0:2, 0:2])
            self.ax_weather = self.fig.add_subplot(gs[0, 2])
            self.ax_forecast = self.fig.add_subplot(gs[1, 2])
            self.ax_flights = self.fig.add_subplot(gs[2, :])
        elif layout_mode == '3column':
            # Special handling for 3column layout
            self.ax_weather = self.fig.add_subplot(gs[:, 0])
            self.ax_map = self.fig.add_subplot(gs[0, 1])
            self.ax_forecast = self.fig.add_subplot(gs[1, 1])
            self.ax_flights = self.fig.add_subplot(gs[:, 2])
        else:
            # Standard grid layout
            self.ax_weather = self.fig.add_subplot(gs[positions['weather']])
            self.ax_map = self.fig.add_subplot(gs[positions['map']])
            self.ax_forecast = self.fig.add_subplot(gs[positions['forecast']])
            self.ax_flights = self.fig.add_subplot(gs[positions['flights']])
        
        if CONFIG['display']['fullscreen']:
            plt.get_current_fig_manager().full_screen_toggle()
    
    def fetch_data(self):
        """Fetch all data"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching data...")
        self.current_weather = self.weather_api.get_current_weather()
        self.forecast = self.weather_api.get_forecast()
        self.aircraft = self.flight_tracker.get_nearby_aircraft()
        print(f"  Found {len(self.aircraft)} aircraft")
    
    def draw_current_weather(self):
        """Draw current weather conditions"""
        self.ax_weather.clear()
        self.ax_weather.axis('off')
        
        if not self.current_weather:
            self.ax_weather.text(0.5, 0.5, 'Weather\nUnavailable', 
                                ha='center', va='center', fontsize=20, color='red')
            return
        
        # Extract data
        temp = self.current_weather['main']['temp']
        feels_like = self.current_weather['main']['feels_like']
        humidity = self.current_weather['main']['humidity']
        pressure = self.current_weather['main']['pressure']
        wind_speed = self.current_weather['wind']['speed']
        wind_dir = self.current_weather['wind'].get('deg', 0)
        description = self.current_weather['weather'][0]['description'].title()
        

        wind_speed_ms = self.current_weather['wind']['speed']
        wind_speed_kmh = wind_speed_ms * 3.6

        # Title
        self.ax_weather.text(0.5, 0.95, f"Weather - {CONFIG['location']['name']}", 
                            ha='center', va='top', fontsize=18, fontweight='bold')
        
        # Temperature (large)
        self.ax_weather.text(0.5, 0.7, f"{temp:.1f}°C", 
                            ha='center', va='center', fontsize=40, fontweight='bold',
                            color='#FFA500')
        
        # Feels like
        self.ax_weather.text(0.5, 0.6, f"Feels like {feels_like:.1f}°C", 
                            ha='center', va='center', fontsize=14, color='#AAAAAA')
        
        # Description
        self.ax_weather.text(0.5, 0.45, description, 
                            ha='center', va='center', fontsize=16, style='italic')
        

        self.ax_weather.text(0.15, 0.40, details[0], fontsize=11)
        self.ax_weather.text(0.55, 0.40, details[1], fontsize=11)
        self.ax_weather.text(0.35, 0.32, details[2], fontsize=11)
                
        # Details
        details_y = 0.30
        details = [
            f"💧 Humidity: {humidity}%",
            f"🌬️  Wind: {wind_speed_kmh:.0f} m/s @ {wind_dir}°",
            f"⏱️  Pressure: {pressure} hPa"
        ]
        
        for i, detail in enumerate(details):
            self.ax_weather.text(0.5, details_y - i*0.08, detail, 
                                ha='center', va='center', fontsize=12)
        
        # Timestamp
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.ax_weather.text(0.5, 0.02, f"Updated: {timestamp}", 
                            ha='center', va='bottom', fontsize=10, color='#666666')
    
    def draw_forecast(self):
        """Draw weather forecast"""
        self.ax_forecast.clear()
        
        if not self.forecast or 'list' not in self.forecast:
            self.ax_forecast.text(0.5, 0.5, 'Forecast\nUnavailable', 
                                 ha='center', va='center', fontsize=16, color='red')
            self.ax_forecast.axis('off')
            return
        
        # Extract next 8 forecast points (24 hours)
        forecasts = self.forecast['list'][:8]
        times = []
        temps = []
        
        for f in forecasts:
            dt = datetime.fromtimestamp(f['dt'])
            times.append(dt.strftime('%H:%M'))
            temps.append(f['main']['temp'])
        
        # Plot
        self.ax_forecast.plot(times, temps, 'o-', color='#FFA500', linewidth=2, markersize=8)
        self.ax_forecast.set_title('24-Hour Temperature Forecast', fontsize=14, fontweight='bold')
        self.ax_forecast.set_ylabel('Temperature (°C)', fontsize=11)
        self.ax_forecast.grid(True, alpha=0.3)
        self.ax_forecast.tick_params(axis='x', rotation=45, labelsize=9)
        
        # Add values on points
        for i, (t, temp) in enumerate(zip(times, temps)):
            self.ax_forecast.text(i, temp + 0.5, f'{temp:.1f}°', 
                                 ha='center', fontsize=9, color='white')
    
    def draw_flight_map(self):
        """Draw aircraft positions on map"""
        self.ax_map.clear()

        radar = inset_axes(
            self.ax_map,
            width="30%",
            height="30%",
            loc="lower left",
            borderpad=1
        )

        radar.set_facecolor("#111111")
        radar.set_xticks([])
        radar.set_yticks([])

        radar.set_xlim(
            CONFIG['location']['lon'] - radius_deg,
            CONFIG['location']['lon'] + radius_deg
        )
        radar.set_ylim(
            CONFIG['location']['lat'] - radius_deg,
            CONFIG['location']['lat'] + radius_deg
        )

        
        # Set map bounds
        radius_deg = CONFIG['aviation']['radius'] / 111.0
        self.ax_map.set_xlim(CONFIG['location']['lon'] - radius_deg, 
                             CONFIG['location']['lon'] + radius_deg)
        self.ax_map.set_ylim(CONFIG['location']['lat'] - radius_deg, 
                             CONFIG['location']['lat'] + radius_deg)
        
        # Draw your location
        self.ax_map.plot(CONFIG['location']['lon'], CONFIG['location']['lat'], 
                        'r*', markersize=20, label='Your Location', zorder=10)
        
        # Draw range circle
        circle = plt.Circle((CONFIG['location']['lon'], CONFIG['location']['lat']), 
                           radius_deg, fill=False, color='gray', linestyle='--', alpha=0.5)
        self.ax_map.add_patch(circle)
        
        # Draw aircraft
        if self.aircraft:
            for ac in self.aircraft:
                if ac['longitude'] and ac['latitude']:
                    # Plot aircraft
                    self.ax_map.plot(ac['longitude'], ac['latitude'], 
                                    marker=(3, 0, ac['heading'] if ac['heading'] else 0), 
                                    markersize=10, color='cyan', zorder=5)
                    
                    # Add callsign label
                    self.ax_map.text(ac['longitude'], ac['latitude'] + 0.05, 
                                    ac['callsign'], fontsize=8, ha='center', 
                                    color='white', alpha=0.8)
        
        self.ax_map.set_title(f'Aircraft within {CONFIG["aviation"]["radius"]} km', 
                             fontsize=14, fontweight='bold')
        self.ax_map.set_xlabel('Longitude', fontsize=10)
        self.ax_map.set_ylabel('Latitude', fontsize=10)
        self.ax_map.grid(True, alpha=0.3)
        self.ax_map.legend(loc='upper right', fontsize=9)
        
        # Add aircraft count
        self.ax_map.text(0.02, 0.98, f'Aircraft: {len(self.aircraft)}', 
                        transform=self.ax_map.transAxes, 
                        fontsize=12, fontweight='bold', 
                        verticalalignment='top', color='yellow')
    
    def draw_flight_list(self):
        """Draw list of nearby aircraft with enhanced info"""
        self.ax_flights.clear()
        self.ax_flights.axis('off')
        
        self.ax_flights.text(0.5, 0.98, 'Nearby Aircraft', 
                            ha='center', va='top', fontsize=14, fontweight='bold',
                            transform=self.ax_flights.transAxes)
        
        if not self.aircraft:
            self.ax_flights.text(0.5, 0.5, 'No aircraft detected\nin range', 
                                ha='center', va='center', fontsize=14, 
                                color='gray', style='italic')
            return
        
        # Table header
        header_y = 0.90
        self.ax_flights.text(0.05, header_y, 'Callsign', fontsize=10, fontweight='bold')
        self.ax_flights.text(0.25, header_y, 'Alt (ft)', fontsize=10, fontweight='bold')
        self.ax_flights.text(0.40, header_y, 'Speed', fontsize=10, fontweight='bold')
        self.ax_flights.text(0.55, header_y, 'Dist', fontsize=10, fontweight='bold')
        self.ax_flights.text(0.68, header_y, 'Type', fontsize=10, fontweight='bold')
        self.ax_flights.text(0.85, header_y, 'Sqwk', fontsize=10, fontweight='bold')
        
        # Draw line under header
        line_y = header_y - 0.03
        self.ax_flights.plot([0.05, 0.95], [line_y, line_y], 'w-', alpha=0.3, linewidth=1)
        
        # List aircraft (max 10)
        y_pos = line_y - 0.05
        row_height = 0.08
        
        for i, ac in enumerate(self.aircraft[:10]):
            # Alternate row colors
            if i % 2 == 0:
                rect = FancyBboxPatch((0.02, y_pos - 0.03), 0.96, row_height - 0.01,
                                     boxstyle="round,pad=0.005", 
                                     edgecolor='none', facecolor='white', alpha=0.05)
                self.ax_flights.add_patch(rect)
            
            # Callsign
            self.ax_flights.text(0.05, y_pos, ac['callsign'], fontsize=9)
            
            # Altitude
            alt_text = f"{ac['altitude_ft']:,}"
            # Color code by altitude
            if ac['altitude_ft'] > 30000:
                alt_color = '#00BFFF'  # High altitude - light blue
            elif ac['altitude_ft'] > 18000:
                alt_color = '#FFA500'  # Medium - orange
            else:
                alt_color = '#90EE90'  # Low - light green
            self.ax_flights.text(0.25, y_pos, alt_text, fontsize=9, color=alt_color)
            
            # Speed
            speed_text = f"{ac['speed_kts']} kt"
            self.ax_flights.text(0.40, y_pos, speed_text, fontsize=9, color='#00FF00')
            
            # Distance
            dist_text = f"{ac['distance']:.1f}km"
            self.ax_flights.text(0.55, y_pos, dist_text, fontsize=9, color='#00BFFF')
            
            # Aircraft category (if available)
            if ac.get('category'):
                cat_name = FlightTracker.get_category_name(ac['category'])
                self.ax_flights.text(0.68, y_pos, cat_name, fontsize=8, color='#FFFF00')
            
            # Squawk code (if available and interesting)
            if ac.get('squawk'):
                squawk = ac['squawk']
                # Highlight emergency squawks
                if squawk in ['7500', '7600', '7700']:
                    squawk_color = '#FF0000'  # Red for emergency
                    fontweight = 'bold'
                else:
                    squawk_color = '#AAAAAA'
                    fontweight = 'normal'
                self.ax_flights.text(0.85, y_pos, squawk, fontsize=8, 
                                    color=squawk_color, fontweight=fontweight)
            
            y_pos -= row_height
            
            if y_pos < 0.05:  # Don't go below bottom
                break
    
    def update(self, frame):
        """Update all panels"""
        # Fetch new data every N frames
        if frame % (CONFIG['display']['refresh_rate'] * 2) == 0:
            self.fetch_data()
        
        # Redraw all panels
        self.draw_current_weather()
        self.draw_forecast()
        self.draw_flight_map()
        self.draw_flight_list()
        
        return []
    
    def run(self):
        """Start the dashboard"""
        print("Starting Weather & Flight Tracking Dashboard...")
        print(f"Location: {CONFIG['location']['name']}")
        print(f"Flight tracking radius: {CONFIG['aviation']['radius']} km")
        print("\nPress Ctrl+C to stop\n")
        
        # Initial data fetch
        self.fetch_data()
        
        # Animate
        anim = FuncAnimation(self.fig, self.update, 
                           interval=CONFIG['display']['refresh_rate'] * 1000,
                           blit=False, cache_frame_data=False)
        
        plt.tight_layout()
        plt.show()

def main():
    """Main entry point"""
    # Check if API key is set
    if CONFIG['weather']['api_key'] == 'WEATHER_API':
        print("⚠️  WARNING: Please set your OpenWeather API key in the CONFIG")
        print("   Get a free key at: https://openweathermap.org/api")
        print("\n   You can still use flight tracking without weather data")
        response = input("\nContinue anyway? (y/n): ")
        if response.lower() != 'y':
            return
    
    try:
        dashboard = WeatherFlightDashboard()
        dashboard.run()
    except KeyboardInterrupt:
        print("\n\nShutting down dashboard...")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()