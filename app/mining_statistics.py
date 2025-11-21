"""
Mining Statistics Module - Elite Mining Analytics
Handles material tracking, percentage yield calculations, and session analytics.
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

log = logging.getLogger(__name__)

@dataclass
class MaterialFind:
    """Represents a single material find from prospector analysis"""
    material_name: str
    percentage: float
    timestamp: datetime
    asteroid_id: Optional[str] = None  # For future tracking
    
@dataclass 
class MaterialStatistics:
    """Statistics for a single material type"""
    material_name: str
    finds: List[MaterialFind] = field(default_factory=list)
    
    def add_find(self, percentage: float, timestamp: Optional[datetime] = None) -> None:
        """Add a new material find"""
        if timestamp is None:
            timestamp = datetime.now()
        
        find = MaterialFind(
            material_name=self.material_name,
            percentage=percentage,
            timestamp=timestamp
        )
        self.finds.append(find)
        log.debug(f"Added {self.material_name} find: {percentage}%")
    
    def get_average_percentage(self) -> Optional[float]:
        """Calculate average percentage across all finds"""
        if not self.finds:
            return None
        
        total = sum(find.percentage for find in self.finds)
        return round(total / len(self.finds), 1)
    
    def get_best_percentage(self) -> Optional[float]:
        """Get the highest percentage found"""
        if not self.finds:
            return None
        
        return max(find.percentage for find in self.finds)
    
    def get_latest_percentage(self) -> Optional[float]:
        """Get the most recent percentage found"""
        if not self.finds:
            return None
        
        return self.finds[-1].percentage
    
    def get_find_count(self) -> int:
        """Get total number of finds for this material"""
        return len(self.finds)
    
    def get_quality_hits(self, min_percentage: float) -> int:
        """Get number of finds that meet or exceed the minimum percentage threshold"""
        return len([find for find in self.finds if find.percentage >= min_percentage])
    
    def reset(self) -> None:
        """Reset all statistics for new session"""
        self.finds.clear()

class SessionAnalytics:
    """Main analytics engine for tracking mining session statistics"""
    
    def __init__(self):
        self.material_stats: Dict[str, MaterialStatistics] = {}
        self.material_stats_all: Dict[str, MaterialStatistics] = {}  # Track ALL finds (regardless of threshold)
        self.session_active = False
        self.session_start_time: Optional[datetime] = None
        self.total_asteroids_prospected = 0
        self.asteroids_with_materials = 0
        
    def start_session(self) -> None:
        """Start a new mining session"""
        self.reset_session()
        self.session_active = True
        self.session_start_time = datetime.now()
        log.info("Mining session analytics started")
    
    def stop_session(self) -> None:
        """Stop the current mining session"""
        self.session_active = False
        log.info(f"Mining session stopped. Total asteroids: {self.total_asteroids_prospected}")
    
    def reset_session(self) -> None:
        """Reset all session statistics"""
        self.material_stats.clear()
        self.material_stats_all.clear()
        self.total_asteroids_prospected = 0
        self.asteroids_with_materials = 0
        self.session_start_time = None
        log.debug("Session statistics reset")
    
    def add_prospector_result(self, materials_found: Dict[str, float], selected_materials: List[str], min_pct_map: Dict[str, float] = None) -> None:
        """
        Add results from a prospector analysis
        
        Args:
            materials_found: Dict of {material_name: percentage}
            selected_materials: List of materials selected in announcements panel
            min_pct_map: Dict of {material_name: min_percentage_threshold}
        """
        if not self.session_active:
            return
        
        self.total_asteroids_prospected += 1
        timestamp = datetime.now()
        
        # Check if this asteroid has any valuable materials that meet thresholds
        has_valuable_materials = False
        
        # Track ALL materials found (for "Avg % All" column)
        for material_name, percentage in materials_found.items():
            material_selected = any(sel.lower() == material_name.lower() for sel in selected_materials)
            if material_selected:
                threshold_key = next((sel for sel in selected_materials if sel.lower() == material_name.lower()), material_name)
                
                # Track in material_stats_all (ALL finds regardless of threshold)
                if threshold_key not in self.material_stats_all:
                    self.material_stats_all[threshold_key] = MaterialStatistics(threshold_key)
                self.material_stats_all[threshold_key].add_find(percentage, timestamp)
        
        # Only track materials that are selected for announcements AND meet thresholds
        for material_name, percentage in materials_found.items():
            # Case-insensitive material matching
            material_selected = any(sel.lower() == material_name.lower() for sel in selected_materials)
            if material_selected:
                # Check if this material meets the announcement threshold
                meets_threshold = False
                # Find the correct case version for threshold lookup
                threshold_key = next((sel for sel in selected_materials if sel.lower() == material_name.lower()), material_name)
                if min_pct_map and threshold_key in min_pct_map:
                    min_threshold = min_pct_map[threshold_key]
                    # CORE ASTEROID FIX: Motherlode materials (0.0%) should be counted if enabled
                    # Regular surface materials need to meet the threshold percentage
                    if percentage == 0.0 or percentage >= min_threshold:
                        meets_threshold = True
                        has_valuable_materials = True
                else:
                    # If no threshold map provided, count any selected material
                    meets_threshold = True
                    has_valuable_materials = True
                
                # Only add to statistics if it meets the threshold
                if meets_threshold:
                    # Use the properly capitalized name from selected materials for display
                    display_name = threshold_key
                    
                    # Initialize material stats if first time seeing this material
                    if display_name not in self.material_stats:
                        self.material_stats[display_name] = MaterialStatistics(display_name)
                    
                    # Add the find (use 0.0 for motherlode materials)
                    self.material_stats[display_name].add_find(percentage, timestamp)
        
        # Track asteroids that had valuable materials meeting thresholds
        if has_valuable_materials:
            self.asteroids_with_materials += 1
        
        log.debug(f"Processed asteroid {self.total_asteroids_prospected}: {len(materials_found)} materials found")
    
    def add_prospector_event(self, event: Dict[str, any], selected_materials: List[str], min_pct_map: Dict[str, float] = None) -> None:
        """
        Add results from an Elite Dangerous ProspectedAsteroid event
        
        Args:
            event: Elite Dangerous journal event
            selected_materials: List of materials selected in announcements panel
        """
        if not self.session_active:
            return
        
        # Extract materials from Elite Dangerous event format
        materials_found = {}
        if 'Materials' in event:
            for material_data in event['Materials']:
                # Get material name (prefer localized name, but handle empty strings)
                localized_name = material_data.get('Name_Localised', '').strip()
                raw_name = material_data.get('Name', '').strip()
                material_name = localized_name if localized_name else raw_name
                percentage = material_data.get('Proportion', 0.0)
                
                if material_name and percentage > 0:
                    materials_found[material_name] = percentage
        
        # CORE ASTEROID FIX: Also check for motherlode material (core asteroids)
        # The motherlode material is stored separately and must be included in Mat Types count
        mother_localized = event.get('MotherlodeMaterial_Localised', '').strip()
        mother_raw = event.get('MotherlodeMaterial', '').strip()
        motherlode_material = mother_localized if mother_localized else mother_raw
        
        if motherlode_material:
            # For core asteroids, the motherlode material should be counted as a material type
            # Use 0.0 to distinguish motherlode (core) from surface materials
            # This ensures it's counted in "Mat Types" but shows as 0% in analytics
            if motherlode_material not in materials_found:
                materials_found[motherlode_material] = 0.0  # Mark as core material with 0% surface yield
        
        # Use the existing add_prospector_result method
        self.add_prospector_result(materials_found, selected_materials, min_pct_map)
    
    def get_tracked_materials(self) -> List[str]:
        """Get list of materials currently being tracked"""
        return list(self.material_stats.keys())
    
    def get_material_statistics(self, material_name: str) -> Optional[MaterialStatistics]:
        """Get statistics for a specific material"""
        return self.material_stats.get(material_name)
    
    def get_live_summary(self) -> Dict[str, Dict[str, any]]:
        """
        Get current session summary for live display
        
        Returns:
            Dict with material stats: {
                'material_name': {
                    'avg_percentage': float,
                    'best_percentage': float, 
                    'latest_percentage': float,
                    'find_count': int
                }
            }
        """
        summary = {}
        
        for material_name, stats in self.material_stats.items():
            if stats.get_find_count() > 0:
                summary[material_name] = {
                    'avg_percentage': stats.get_average_percentage(),
                    'best_percentage': stats.get_best_percentage(),
                    'latest_percentage': stats.get_latest_percentage(),
                    'find_count': stats.get_find_count()
                }
        
        return summary
    
    def get_quality_summary(self, min_pct_thresholds: Dict[str, float]) -> Dict[str, Dict[str, any]]:
        """
        Get session summary with quality hits based on minimum percentage thresholds
        
        Args:
            min_pct_thresholds: Dict of {material_name: min_percentage} from announcements panel
        
        Returns:
            Dict with material stats including quality hit counts: {
                'material_name': {
                    'avg_percentage': float,
                    'best_percentage': float, 
                    'latest_percentage': float,
                    'find_count': int,
                    'quality_hits': int  # Hits that meet min_percentage threshold
                }
            }
        """
        summary = {}
        
        for material_name, stats in self.material_stats.items():
            if stats.get_find_count() > 0:
                min_threshold = min_pct_thresholds.get(material_name, 0.0)
                quality_hits = stats.get_quality_hits(min_threshold)
                
                # CORE ASTEROID FIX: For motherlode materials (0.0%), count them as quality hits
                # since they represent actual motherlode finds from core asteroids
                if quality_hits == 0 and stats.get_find_count() > 0:
                    # Check if any finds are 0.0% (motherlode materials)
                    has_motherlode = any(find.percentage == 0.0 for find in stats.finds)
                    if has_motherlode:
                        quality_hits = stats.get_find_count()
                
                summary[material_name] = {
                    'avg_percentage': stats.get_average_percentage(),
                    'best_percentage': stats.get_best_percentage(),
                    'latest_percentage': stats.get_latest_percentage(),
                    'find_count': stats.get_find_count(),
                    'quality_hits': quality_hits
                }
        
        return summary
    
    def get_session_info(self) -> Dict[str, any]:
        """Get general session information"""
        return {
            'active': self.session_active,
            'start_time': self.session_start_time,
            'asteroids_prospected': self.total_asteroids_prospected,
            'asteroids_with_materials': self.asteroids_with_materials,
            'materials_tracked': len(self.material_stats),
            'total_finds': sum(stats.get_find_count() for stats in self.material_stats.values())
        }
    
    def get_total_asteroids(self) -> int:
        """Get total number of asteroids prospected"""
        return self.total_asteroids_prospected
    
    def calculate_statistics(self) -> Dict:
        """Calculate overall session statistics for detailed reports"""
        return {
            'total_asteroids': self.total_asteroids_prospected,
            'hit_rate': (self.asteroids_with_materials / max(1, self.total_asteroids_prospected)) * 100,
            'materials_found': len(self.material_stats),
            'session_duration': (datetime.now() - self.session_start_time).total_seconds() / 60 if self.session_start_time else 0
        }

# Helper functions for formatting and filtering

def filter_selected_materials(materials_found: Dict[str, float], announcement_settings: Dict[str, bool]) -> Dict[str, float]:
    """
    Filter materials to only include those selected in announcement settings
    
    Args:
        materials_found: All materials found by prospector
        announcement_settings: Dict of {material_name: is_selected}
    
    Returns:
        Filtered dict of only selected materials
    """
    return {
        material: percentage 
        for material, percentage in materials_found.items()
        if announcement_settings.get(material, False)
    }

def format_percentage(value: Optional[float]) -> str:
    """Format percentage value for display"""
    if value is None:
        return "—"
    return f"{value:.1f}%"

def format_find_count(count: int) -> str:
    """Format find count for display"""
    return f"{count}x"

# Example usage and testing functions

def test_statistics():
    """Test function to verify statistics calculations"""
    analytics = SessionAnalytics()
    analytics.start_session()
    
    # Simulate some prospector results
    selected_materials = ["Platinum", "Painite", "Osmium"]
    
    # Add some test data
    test_results = [
        {"Platinum": 34.2, "Painite": 28.5, "Gold": 15.2},  # Gold not selected
        {"Platinum": 28.7, "Osmium": 19.4},
        {"Platinum": 41.1, "Painite": 31.2, "Osmium": 22.8},
        {"Painite": 25.9, "Osmium": 17.6}
    ]
    
    for result in test_results:
        analytics.add_prospector_result(result, selected_materials)
    
    # Get summary
    summary = analytics.get_live_summary()
    session_info = analytics.get_session_info()
    
    print("=== Mining Statistics Test ===")
    print(f"Asteroids prospected: {session_info['asteroids_prospected']}")
    print(f"Materials tracked: {session_info['materials_tracked']}")
    print(f"Total finds: {session_info['total_finds']}")
    print()
    
    for material, stats in summary.items():
        print(f"{material}:")
        print(f"  Average: {format_percentage(stats['avg_percentage'])}")
        print(f"  Best: {format_percentage(stats['best_percentage'])}")
        print(f"  Latest: {format_percentage(stats['latest_percentage'])}")
        print(f"  Count: {format_find_count(stats['find_count'])}")
        print()

if __name__ == "__main__":
    # Run test when module is executed directly (not in PyInstaller)
    import sys
    if not getattr(sys, 'frozen', False):
        test_statistics()
