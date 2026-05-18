"""
AERIS - Maps & Navigation Engine
Integration for location, routing, and map UI.
"""
import logging
import requests
import webbrowser

logger = logging.getLogger(__name__)

class NavigationEngine:
    """Handles all navigation and map interactions"""

    def __init__(self):
        self.default_location = "New York, USA"

    def open_map(self, location=None):
        """Open a map UI centered on a specific location"""
        loc = location or self.default_location
        try:
            url = f"https://www.google.com/maps/search/{loc}"
            webbrowser.open(url)
            return {"success": True, "action": "open_map", "location": loc}
        except Exception as e:
            logger.error(f"Failed to open map: {e}")
            return {"success": False, "error": str(e)}

    def get_directions(self, origin, destination, mode="driving"):
        """Get directions between two points"""
        try:
            # Modes: driving, walking, bicycling, transit
            url = f"https://www.google.com/maps/dir/{origin}/{destination}/data=!4m2!4m1!3e0"
            if mode == "walking": url = url.replace("!3e0", "!3e2")
            elif mode == "transit": url = url.replace("!3e0", "!3e3")
            elif mode == "bicycling": url = url.replace("!3e0", "!3e1")
            
            webbrowser.open(url)
            return {
                "success": True, 
                "action": "directions", 
                "origin": origin,
                "destination": destination,
                "mode": mode
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def nearby_search(self, place_type, location=None):
        """Search for nearby places like restaurants, gas stations"""
        loc = location or self.default_location
        query = f"{place_type} near {loc}"
        try:
            url = f"https://www.google.com/maps/search/{query}"
            webbrowser.open(url)
            return {"success": True, "action": "nearby_search", "query": query}
        except Exception as e:
            return {"success": False, "error": str(e)}
