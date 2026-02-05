#!/usr/bin/env python3
"""
Quick Test Script for Weather & Flight Dashboard
Tests API connections without full GUI
"""

import requests
from datetime import datetime
import os
from dotenv import load_dotenv 
# Test Configuration
load_dotenv()


WEATHER_API = os.getenv("WEATHER_API")
CLIENT_ID = os.getenv("CLIENT_ID")
SECRET_ID= os.getenv("SECRET_ID")
LAT= os.getenv("SECRET_ID")
SECRET_ID= os.getenv("SECRET_ID")

LAT = 55.6761  # Copenhagen
LON = 12.5683
WEATHER_API = WEATHER_API  # Replace with your key

def test_weather_api():
    """Test OpenWeather API connection"""
    if not WEATHER_API:
        raise RuntimeError("WEATHER_API key not found in environment")
    print("\n" + "="*50)
    print("Testing Weather API (OpenWeatherMap)")
    print("="*50)

    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            'lat': LAT,
            'lon': LON,
            'appid': WEATHER_API,
            'units': 'metric'
        }
        
        print(f"Requesting weather for: {LAT}, {LON}")
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Weather API working!")
            print(f"   Location: {data['name']}, {data['sys']['country']}")
            print(f"   Temperature: {data['main']['temp']}°C")
            print(f"   Conditions: {data['weather'][0]['description']}")
            print(f"   Wind: {data['wind']['speed']} m/s")
            return True
        else:
            print(f"❌ API Error: {response.status_code}")
            print(f"   Message: {response.json().get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def test_flight_api():
    """Test OpenSky Network API connection"""
    print("\n" + "="*50)
    print("Testing Flight API (OpenSky Network)")
    print("="*50)
    print("Note: This API is FREE and requires no authentication")
    
    try:
        # Calculate bounding box (100km radius)
        radius_km = 100
        lat_offset = radius_km / 111.0
        lon_offset = radius_km / 111.0
        
        url = "https://opensky-network.org/api/states/all"
        params = {
            'lamin': LAT - lat_offset,
            'lamax': LAT + lat_offset,
            'lomin': LON - lon_offset,
            'lomax': LON + lon_offset
        }
        
        print(f"Searching for aircraft within {radius_km}km of: {LAT}, {LON}")
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            
            if data and 'states' in data and data['states']:
                aircraft_count = len(data['states'])
                airborne_count = sum(1 for s in data['states'] if not s[8])  # not on ground
                
                print(f"✅ Flight API working!")
                print(f"   Total aircraft detected: {aircraft_count}")
                print(f"   Airborne aircraft: {airborne_count}")
                
                # Show first 3 aircraft
                print("\n   Sample aircraft:")
                count = 0
                for state in data['states']:
                    if not state[8] and state[7]:  # airborne and has altitude
                        callsign = state[1].strip() if state[1] else "N/A"
                        altitude_m = state[7]
                        altitude_ft = int(altitude_m * 3.28084) if altitude_m else 0
                        speed_ms = state[9]
                        speed_kts = int(speed_ms * 1.94384) if speed_ms else 0
                        
                        print(f"   • {callsign}: {altitude_ft:,} ft, {speed_kts} kts")
                        count += 1
                        if count >= 3:
                            break
                
                if airborne_count == 0:
                    print("   ℹ️  No airborne aircraft in range at this time")
                    
                return True
            else:
                print("✅ Flight API working!")
                print("   No aircraft detected in range")
                print("   (This is normal for some locations/times)")
                return True
                
        else:
            print(f"❌ API Error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def test_dependencies():
    """Test required Python packages"""
    print("\n" + "="*50)
    print("Testing Python Dependencies")
    print("="*50)
    
    required_packages = {
        'requests': 'requests',
        'matplotlib': 'matplotlib', 
        'numpy': 'numpy'
    }
    
    all_ok = True
    for package_name, import_name in required_packages.items():
        try:
            __import__(import_name)
            print(f"✅ {package_name} installed")
        except ImportError:
            print(f"❌ {package_name} NOT installed")
            print(f"   Install with: pip3 install {package_name}")
            all_ok = False
    
    return all_ok

def main():
    print("\n" + "="*60)
    print("  Weather & Flight Dashboard - Connection Test")
    print("="*60)
    print(f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test dependencies
    deps_ok = test_dependencies()
    
    # Test APIs
    weather_ok = test_weather_api()
    flight_ok = test_flight_api()
    
    # Summary
    print("\n" + "="*50)
    print("Test Summary")
    print("="*50)
    print(f"Dependencies: {'✅ OK' if deps_ok else '❌ FAILED'}")
    print(f"Weather API:  {'✅ OK' if weather_ok else '⚠️  SKIPPED/FAILED'}")
    print(f"Flight API:   {'✅ OK' if flight_ok else '❌ FAILED'}")
    
    if deps_ok and flight_ok:
        print("\n✅ Ready to run the dashboard!")
        print("   Run: python3 weather_flight_dashboard.py")
    else:
        print("\n⚠️  Please fix the issues above before running the dashboard")
    
    print("\nNotes:")
    print("• Weather API is optional but recommended")
    print("• Flight tracking works without any API key")
    print("• Both APIs require internet connection")
    print("="*50 + "\n")

if __name__ == '__main__':
    main()