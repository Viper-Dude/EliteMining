"""
EliteMining API Uploader
Uploads mining session data and hotspot information to server API.
"""

import json
import re
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

import requests
import logging

from path_utils import get_app_data_dir

logger = logging.getLogger(__name__)


class APIUploader:
    """Handles uploading mining session data and hotspot info to API."""
    
    def __init__(self):
        """Initialize uploader with configuration."""
        self.timeout = 10  # seconds
        
        # Upload statistics
        self.sessions_uploaded = 0
        self.hotspots_uploaded = 0
        self.last_upload_time = None
        
        # Queue management
        self.queue_file = Path(get_app_data_dir()) / "failed_api_uploads.json"
        self.max_queue_size = 100
        self.upload_queue = []
        
        # Retry delays (seconds)
        self.retry_delays = [0, 30, 120, 300]  # immediate, 30s, 2min, 5min
        
        self._load_queue()
    
    def _get_config(self):
        """Get current config settings."""
        try:
            from config import load_api_upload_settings
            return load_api_upload_settings()
        except Exception as e:
            logger.error(f"Error loading API config: {e}")
            return {
                "enabled": False,
                "endpoint_url": "",
                "api_key": "",
                "cmdr_name": ""
            }
    
    @property
    def enabled(self):
        return self._get_config()["enabled"]
    
    @property
    def api_url(self):
        return self._get_config()["endpoint_url"].rstrip('/')
    
    @property
    def api_key(self):
        return self._get_config()["api_key"]
    
    @property
    def cmdr_name(self):
        return self._get_config()["cmdr_name"]
    
    def _load_queue(self):
        """Load failed uploads queue from disk."""
        try:
            if self.queue_file.exists():
                with open(self.queue_file, 'r', encoding='utf-8') as f:
                    self.upload_queue = json.load(f)
                logger.info(f"Loaded {len(self.upload_queue)} queued uploads")
        except Exception as e:
            logger.error(f"Error loading upload queue: {e}")
            self.upload_queue = []
    
    def _save_queue(self):
        """Save failed uploads queue to disk."""
        try:
            self.queue_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(self.upload_queue, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving upload queue: {e}")
    
    def parse_txt_report(self, filepath: str) -> Optional[Dict[str, Any]]:
        """Parse TXT session report and extract data."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            data = {}
            
            # Parse header section
            data['timestamp'] = self._extract_timestamp_from_filename(filepath)
            data['system'] = self._extract_field(content, r'System:\s*(.+)')
            data['body'] = self._extract_field(content, r'Body:\s*(.+)')
            data['ship'] = self._extract_field(content, r'Ship Type:\s*(.+)')
            data['session_type'] = "Laser Mining"  # Default, could be enhanced
            
            # Parse session stats
            duration_str = self._extract_field(content, r'Session Duration:\s*(\d+:\d+)')
            data['duration'] = duration_str if duration_str else "00:00"
            
            total_tons_str = self._extract_field(content, r'Total Cargo Refined:\s*([\d.]+)t')
            data['total_tons'] = float(total_tons_str) if total_tons_str else 0.0
            
            tph_str = self._extract_field(content, r'Mining Efficiency:\s*([\d.]+)\s*t/hr')
            data['tph'] = float(tph_str) if tph_str else 0.0
            
            # Parse mineral analysis section
            prospectors_str = self._extract_field(content, r'Prospector Limpets Used:\s*(\d+)')
            data['prospectors_used'] = int(prospectors_str) if prospectors_str else 0
            
            asteroids_str = self._extract_field(content, r'Asteroids Prospected:\s*(\d+)')
            data['asteroids_prospected'] = int(asteroids_str) if asteroids_str else 0
            
            materials_tracked_str = self._extract_field(content, r'Minerals Tracked:\s*(\d+)')
            data['materials_tracked'] = int(materials_tracked_str) if materials_tracked_str else 0
            
            total_finds_str = self._extract_field(content, r'Total Material Finds:\s*(\d+)')
            data['total_finds'] = int(total_finds_str) if total_finds_str else 0
            
            hit_rate_str = self._extract_field(content, r'Hit Rate:\s*([\d.]+)%')
            data['hit_rate_percent'] = float(hit_rate_str) if hit_rate_str else 0.0
            
            avg_quality_str = self._extract_field(content, r'Overall Quality:\s*([\d.]+)%')
            data['avg_quality_percent'] = float(avg_quality_str) if avg_quality_str else 0.0
            
            # Calculate asteroids with materials from hit rate
            if data['asteroids_prospected'] > 0 and data['hit_rate_percent'] > 0:
                data['asteroids_with_materials'] = int(
                    (data['hit_rate_percent'] / 100.0) * data['asteroids_prospected']
                )
            else:
                data['asteroids_with_materials'] = 0
            
            # Parse best material
            best_material_match = re.search(r'Best Performer:\s*(\w+)\s*\(([\d.]+)%', content)
            if best_material_match:
                data['best_material'] = f"{best_material_match.group(1)} ({best_material_match.group(2)}%)"
            else:
                data['best_material'] = None
            
            # Parse materials mined (from CARGO MATERIAL BREAKDOWN or REFINED MINERALS)
            data['materials_mined'] = self._parse_materials_section(content)
            
            # Parse mineral performance (prospecting data)
            data['mineral_performance'] = self._parse_mineral_performance(content)
            
            # Calculate total average yield from materials mined
            if data['materials_mined']:
                total_avg_yield = sum(m['avg_percentage'] for m in data['materials_mined'].values())
                data['total_average_yield'] = round(total_avg_yield, 1)
            else:
                data['total_average_yield'] = 0.0
            
            # Parse session comment
            comment = self._extract_comment(content)
            if comment:
                data['comment'] = comment
            
            return data
            
        except Exception as e:
            logger.error(f"Error parsing TXT report {filepath}: {e}")
            return None
    
    def _extract_timestamp_from_filename(self, filepath: str) -> str:
        """Extract timestamp from filename like Session_2025-01-15_14-30-00_..."""
        try:
            filename = Path(filepath).stem
            match = re.search(r'Session_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', filename)
            if match:
                timestamp_str = match.group(1)
                # Convert from 2025-01-15_14-30-00 to 2025-01-15T14:30:00
                date_part, time_part = timestamp_str.split('_')
                time_part = time_part.replace('-', ':')
                return f"{date_part}T{time_part}"
        except:
            pass
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    
    def _extract_field(self, content: str, pattern: str) -> Optional[str]:
        """Extract single field using regex."""
        match = re.search(pattern, content)
        return match.group(1).strip() if match else None
    
    def _parse_materials_section(self, content: str) -> Dict[str, Dict[str, float]]:
        """Parse materials mined from CARGO MATERIAL BREAKDOWN or REFINED MINERALS."""
        materials = {}
        
        # Try CARGO MATERIAL BREAKDOWN first (has more detail)
        cargo_section = re.search(r'=== CARGO MATERIAL BREAKDOWN ===(.*?)(?:===|$)', content, re.DOTALL)
        if cargo_section:
            section_text = cargo_section.group(1)
            # Match lines like: Platinum: 25.5t (280.1 t/hr)
            for match in re.finditer(r'(\w+):\s*([\d.]+)t\s*\(([\d.]+)\s*t/hr\)', section_text):
                material_name = match.group(1)
                tons = float(match.group(2))
                tph = float(match.group(3))
                
                # Get performance data for this material
                avg_pct, best_pct, find_count = self._find_material_performance(content, material_name)
                
                materials[material_name] = {
                    'tons': tons,
                    'tph': tph,
                    'avg_percentage': avg_pct,
                    'best_percentage': best_pct,
                    'find_count': find_count
                }
        else:
            # Fallback to REFINED MINERALS section
            refined_section = re.search(r'=== REFINED MINERALS ===(.*?)(?:===|$)', content, re.DOTALL)
            if refined_section:
                section_text = refined_section.group(1)
                for match in re.finditer(r'-\s*(\w+):\s*([\d.]+)t\s*\(([\d.]+)\s*t/hr\)', section_text):
                    material_name = match.group(1)
                    tons = float(match.group(2))
                    tph = float(match.group(3))
                    
                    avg_pct, best_pct, find_count = self._find_material_performance(content, material_name)
                    
                    materials[material_name] = {
                        'tons': tons,
                        'tph': tph,
                        'avg_percentage': avg_pct,
                        'best_percentage': best_pct,
                        'find_count': find_count
                    }
        
        return materials
    
    def _find_material_performance(self, content: str, material_name: str) -> Tuple[float, float, int]:
        """Find performance data for a specific material from MINERAL ANALYSIS section."""
        # Look for pattern like:
        # Platinum:
        #   • Average: 15.3%
        #   • Best: 32.8%
        #   • Finds: 15x
        pattern = rf'{material_name}:\s*•\s*Average:\s*([\d.]+)%\s*•\s*Best:\s*([\d.]+)%\s*•\s*Finds:\s*(\d+)x'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return float(match.group(1)), float(match.group(2)), int(match.group(3))
        return 0.0, 0.0, 0
    
    def _parse_mineral_performance(self, content: str) -> Dict[str, Dict[str, float]]:
        """Parse mineral performance (prospecting data) from MINERAL ANALYSIS."""
        performance = {}
        
        mineral_section = re.search(r'--- Mineral Performance ---(.*?)(?:Overall Quality|===|$)', content, re.DOTALL)
        if mineral_section:
            section_text = mineral_section.group(1)
            
            # Pattern to match material blocks
            material_blocks = re.finditer(r'(\w+):\s*•\s*Average:\s*([\d.]+)%\s*•\s*Best:\s*([\d.]+)%\s*•\s*Finds:\s*(\d+)x', section_text, re.DOTALL)
            
            for match in material_blocks:
                material_name = match.group(1)
                find_count = int(match.group(4))
                
                # Calculate prospected count and hit rate
                # We need asteroids_prospected from the session info
                asteroids_match = re.search(r'Asteroids Prospected:\s*(\d+)', content)
                if asteroids_match:
                    total_prospected = int(asteroids_match.group(1))
                    # Estimate: assume each material was prospected proportionally
                    # This is approximate since we don't have exact per-material prospecting data
                    hit_rate = (find_count / total_prospected * 100.0) if total_prospected > 0 else 0.0
                    
                    performance[material_name] = {
                        'prospected': total_prospected,  # This is total, not per-material
                        'hit_rate': round(hit_rate, 1)
                    }
        
        return performance
    
    def _extract_comment(self, content: str) -> Optional[str]:
        """Extract session comment if present."""
        comment_section = re.search(r'=== SESSION COMMENT ===(.*?)$', content, re.DOTALL)
        if comment_section:
            return comment_section.group(1).strip()
        return None
    
    def build_session_json(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build JSON payload for session upload."""
        json_data = {
            'cmdr_name': self.cmdr_name,
            'timestamp': parsed_data['timestamp'],
            'system': parsed_data['system'],
            'body': parsed_data['body'],
            'ship': parsed_data['ship'],
            'session_type': parsed_data['session_type'],
            'duration': parsed_data['duration'],
            'total_tons': parsed_data['total_tons'],
            'tph': parsed_data['tph'],
            'prospectors_used': parsed_data['prospectors_used'],
            'asteroids_prospected': parsed_data['asteroids_prospected'],
            'asteroids_with_materials': parsed_data['asteroids_with_materials'],
            'hit_rate_percent': parsed_data['hit_rate_percent'],
            'avg_quality_percent': parsed_data['avg_quality_percent'],
            'total_average_yield': parsed_data['total_average_yield'],
            'materials_tracked': parsed_data['materials_tracked'],
            'total_finds': parsed_data['total_finds'],
        }
        
        # Optional fields
        if parsed_data.get('best_material'):
            json_data['best_material'] = parsed_data['best_material']
        
        if parsed_data.get('comment'):
            json_data['comment'] = parsed_data['comment']
        
        # Materials mined
        if parsed_data.get('materials_mined'):
            json_data['materials_mined'] = parsed_data['materials_mined']
        
        # Mineral performance
        if parsed_data.get('mineral_performance'):
            json_data['mineral_performance'] = parsed_data['mineral_performance']
        
        # TODO: Add hotspot_info if session matches a tracked hotspot
        # This will be implemented when integrating with user_database
        
        return json_data
    
    def upload_session(self, session_data: Dict[str, Any], retry_count: int = 0) -> bool:
        """Upload single session to API with retry logic."""
        if not self.enabled:
            logger.debug("API upload disabled, skipping")
            return False
        
        if not self.api_key or not self.api_url:
            logger.warning("API key or URL not configured")
            return False
        
        try:
            endpoint = f"{self.api_url}/api/mining/session"
            headers = {
                'Content-Type': 'application/json',
                'X-API-Key': self.api_key
            }
            
            # Add retry delay if not first attempt
            if retry_count > 0 and retry_count <= len(self.retry_delays):
                delay = self.retry_delays[retry_count]
                if delay > 0:
                    logger.info(f"Retry attempt {retry_count}, waiting {delay}s...")
                    time.sleep(delay)
            
            logger.info(f"Uploading session to {endpoint}")
            response = requests.post(
                endpoint,
                json=session_data,
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                logger.info("Session uploaded successfully")
                self.sessions_uploaded += 1
                self.last_upload_time = datetime.now().isoformat()
                return True
            elif response.status_code == 401:
                logger.error("API authentication failed (invalid API key)")
                return False  # Don't retry auth failures
            elif response.status_code == 400:
                logger.error(f"Bad request: {response.text}")
                return False  # Don't retry bad data
            elif response.status_code == 429:
                logger.warning("Rate limited by server")
                if retry_count < len(self.retry_delays) - 1:
                    return self.upload_session(session_data, retry_count + 1)
            else:
                logger.error(f"Upload failed with status {response.status_code}: {response.text}")
                if retry_count < len(self.retry_delays) - 1:
                    return self.upload_session(session_data, retry_count + 1)
            
            # If we've exhausted retries, queue it
            if retry_count >= len(self.retry_delays) - 1:
                self._add_to_queue(session_data, 'session')
                
        except requests.exceptions.Timeout:
            logger.error(f"Upload timeout (retry {retry_count})")
            if retry_count < len(self.retry_delays) - 1:
                return self.upload_session(session_data, retry_count + 1)
            else:
                self._add_to_queue(session_data, 'session')
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
            if retry_count < len(self.retry_delays) - 1:
                return self.upload_session(session_data, retry_count + 1)
            else:
                self._add_to_queue(session_data, 'session')
        except Exception as e:
            logger.error(f"Unexpected error uploading session: {e}")
            self._add_to_queue(session_data, 'session')
        
        return False
    
    def upload_session_from_file(self, filepath: str) -> bool:
        """Parse TXT report and upload to API."""
        try:
            parsed_data = self.parse_txt_report(filepath)
            if not parsed_data:
                logger.error(f"Failed to parse report: {filepath}")
                return False
            
            session_json = self.build_session_json(parsed_data)
            return self.upload_session(session_json)
            
        except Exception as e:
            logger.error(f"Error uploading session from file {filepath}: {e}")
            return False
    
    def _add_to_queue(self, data: Dict[str, Any], data_type: str):
        """Add failed upload to queue."""
        if len(self.upload_queue) >= self.max_queue_size:
            logger.warning(f"Upload queue full ({self.max_queue_size}), removing oldest item")
            self.upload_queue.pop(0)
        
        queue_item = {
            'data': data,
            'type': data_type,
            'timestamp': datetime.now().isoformat(),
            'retry_count': 0
        }
        
        self.upload_queue.append(queue_item)
        self._save_queue()
        logger.info(f"Added {data_type} to upload queue (queue size: {len(self.upload_queue)})")
    
    def retry_queued_uploads(self):
        """Retry all queued uploads on app startup."""
        if not self.enabled or not self.upload_queue:
            return
        
        logger.info(f"Retrying {len(self.upload_queue)} queued uploads...")
        
        successful = []
        for item in self.upload_queue:
            data_type = item['type']
            data = item['data']
            
            if data_type == 'session':
                if self.upload_session(data):
                    successful.append(item)
            # TODO: Add hotspot upload retry
        
        # Remove successful uploads from queue
        for item in successful:
            self.upload_queue.remove(item)
        
        if successful:
            self._save_queue()
            logger.info(f"Successfully uploaded {len(successful)} queued items")
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test API connection and authentication."""
        if not self.api_url:
            return False, "API endpoint URL not configured"
        
        if not self.api_key:
            return False, "API key not configured"
        
        try:
            # Try to reach the base URL
            endpoint = f"{self.api_url}/api/mining/session"
            headers = {
                'X-API-Key': self.api_key
            }
            
            # Send a test GET request (or OPTIONS)
            response = requests.get(endpoint, headers=headers, timeout=5)
            
            if response.status_code == 401:
                return False, "Authentication failed (invalid API key)"
            elif response.status_code in [200, 404, 405]:  # 405 = Method Not Allowed (GET on POST endpoint)
                return True, "Connection successful"
            else:
                return False, f"Server returned status {response.status_code}"
                
        except requests.exceptions.Timeout:
            return False, "Connection timeout"
        except requests.exceptions.ConnectionError:
            return False, "Cannot reach server"
        except Exception as e:
            return False, f"Error: {str(e)}"
