import os
import json
import socket
import subprocess
import psutil
from typing import Optional, Dict, Any
from pathlib import Path


class ServerConfigManager:
    """Robust server configuration manager with multiple detection methods"""
    
    def __init__(self, config_file: str = "server_config.json"):
        self.config_file = Path(config_file)
        self.config = self._load_config()
        self._detected_info = {}
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load config file: {e}")
        
        # Default configuration
        return {
            "server": {"host": "auto-detect", "port": "auto-detect", "protocol": "http"},
            "deployment": {"environment": "development", "base_url": None, "auto_detect_ip": True},
            "network": {"exclude_ips": ["127.0.0.1", "127.0.1.1", "172.17.0.1"]}
        }
    
    def get_server_ip(self) -> str:
        """Get server IP with multiple fallback methods"""
        # Priority 1: Environment variable
        env_ip = os.getenv("SERVER_IP")
        if env_ip:
            print(f"🔧 Using SERVER_IP from environment: {env_ip}")
            return env_ip
        
        # Priority 2: Configuration file override
        if self.config.get("deployment", {}).get("base_url"):
            # Extract IP from base_url if it's an IP-based URL
            base_url = self.config["deployment"]["base_url"]
            if "://" in base_url:
                host_part = base_url.split("://")[1].split(":")[0].split("/")[0]
                if self._is_ip_address(host_part):
                    print(f"🔧 Using IP from config base_url: {host_part}")
                    return host_part
        
        # Priority 3: Auto-detection
        if self.config.get("deployment", {}).get("auto_detect_ip", True):
            detected_ip = self._detect_best_ip()
            if detected_ip:
                print(f"🔍 Auto-detected IP: {detected_ip}")
                return detected_ip
        
        # Priority 4: Fallback
        fallback = self.config.get("deployment", {}).get("fallback_ip", "localhost")
        print(f"⚠️  Using fallback IP: {fallback}")
        return fallback
    
    def _detect_best_ip(self) -> Optional[str]:
        """Detect the best IP address using multiple methods"""
        exclude_ips = set(self.config.get("network", {}).get("exclude_ips", []))
        
        # Method 1: Network interfaces (most reliable)
        interface_ip = self._get_ip_from_interfaces(exclude_ips)
        if interface_ip:
            return interface_ip
        
        # Method 2: Socket connection method
        socket_ip = self._get_ip_from_socket()
        if socket_ip and socket_ip not in exclude_ips:
            return socket_ip
        
        # Method 3: psutil network interfaces
        psutil_ip = self._get_ip_from_psutil(exclude_ips)
        if psutil_ip:
            return psutil_ip
        
        return None
    
    def _get_ip_from_interfaces(self, exclude_ips: set) -> Optional[str]:
        """Get IP from network interfaces using ip command"""
        try:
            result = subprocess.run(['ip', 'addr', 'show'], capture_output=True, text=True)
            if result.returncode != 0:
                return None
            
            current_interface = None
            for line in result.stdout.split('\n'):
                line = line.strip()
                
                # Track current interface
                if line and not line.startswith(' '):
                    parts = line.split(':')
                    if len(parts) >= 2:
                        current_interface = parts[1].strip()
                
                # Look for inet addresses
                if 'inet ' in line and 'scope global' in line:
                    parts = line.split()
                    for part in parts:
                        if '/' in part and not part.startswith('inet'):
                            ip = part.split('/')[0]
                            if ip not in exclude_ips and self._is_valid_network_ip(ip):
                                print(f"🌐 Found IP {ip} on interface {current_interface}")
                                return ip
        except Exception as e:
            print(f"Interface detection failed: {e}")
        
        return None
    
    def _get_ip_from_socket(self) -> Optional[str]:
        """Get IP using socket connection method"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return None
    
    def _get_ip_from_psutil(self, exclude_ips: set) -> Optional[str]:
        """Get IP using psutil network interfaces"""
        try:
            interfaces = psutil.net_if_addrs()
            for interface_name, addresses in interfaces.items():
                if interface_name.startswith(('lo', 'docker')):
                    continue
                
                for addr in addresses:
                    if addr.family == socket.AF_INET:  # IPv4
                        ip = addr.address
                        if ip not in exclude_ips and self._is_valid_network_ip(ip):
                            print(f"🌐 Found IP {ip} on interface {interface_name} (psutil)")
                            return ip
        except Exception as e:
            print(f"psutil detection failed: {e}")
        
        return None
    
    def _is_ip_address(self, text: str) -> bool:
        """Check if text is a valid IP address"""
        try:
            socket.inet_aton(text)
            return True
        except socket.error:
            return False
    
    def _is_valid_network_ip(self, ip: str) -> bool:
        """Check if IP is a valid network IP (not loopback, not docker, etc.)"""
        if not self._is_ip_address(ip):
            return False
        
        # Exclude common non-routable IPs
        if ip.startswith(('127.', '169.254.')):
            return False
        
        # Include common private network ranges
        if (ip.startswith(('192.168.', '10.', '172.')) or 
            ip.startswith('172.') and 16 <= int(ip.split('.')[1]) <= 31):
            return True
        
        # Include other routable IPs
        return True
    
    def get_server_port(self) -> str:
        """Get server port"""
        # Priority 1: Environment variable
        env_port = os.getenv("SERVER_PORT")
        if env_port:
            print(f"🔧 Using SERVER_PORT from environment: {env_port}")
            return env_port
        
        # Priority 2: Configuration file
        config_port = self.config.get("server", {}).get("port")
        if config_port and config_port != "auto-detect":
            print(f"🔧 Using port from config: {config_port}")
            return str(config_port)
        
        # Priority 3: Extract from base_url
        base_url = self.config.get("deployment", {}).get("base_url")
        if base_url and ":" in base_url:
            try:
                # Extract port from URL like http://domain:8000
                url_parts = base_url.split("://")[1]
                if ":" in url_parts:
                    port = url_parts.split(":")[1].split("/")[0]
                    print(f"🔧 Using port from base_url: {port}")
                    return port
            except Exception:
                pass
        
        # Priority 4: Default
        default_port = "8000"
        print(f"🔧 Using default port: {default_port}")
        return default_port
    
    def get_server_protocol(self) -> str:
        """Get server protocol"""
        # Priority 1: Environment variable
        env_protocol = os.getenv("SERVER_PROTOCOL")
        if env_protocol:
            return env_protocol
        
        # Priority 2: Configuration file
        config_protocol = self.config.get("server", {}).get("protocol", "http")
        return config_protocol
    
    def get_base_url(self) -> str:
        """Get the complete base URL"""
        # Priority 1: Environment variable (complete override)
        env_base_url = os.getenv("BASE_URL")
        if env_base_url:
            print(f"🔧 Using BASE_URL from environment: {env_base_url}")
            return env_base_url
        
        # Priority 2: Configuration file base_url
        config_base_url = self.config.get("deployment", {}).get("base_url")
        if config_base_url:
            print(f"🔧 Using base_url from config: {config_base_url}")
            return config_base_url
        
        # Priority 3: Build from components
        protocol = self.get_server_protocol()
        ip = self.get_server_ip()
        port = self.get_server_port()
        
        base_url = f"{protocol}://{ip}:{port}"
        print(f"🔧 Built base_url from components: {base_url}")
        return base_url
    
    def save_detected_config(self):
        """Save the detected configuration for future use"""
        detected_config = {
            "last_detected": {
                "ip": self.get_server_ip(),
                "port": self.get_server_port(),
                "protocol": self.get_server_protocol(),
                "base_url": self.get_base_url()
            }
        }
        
        try:
            # Update existing config
            self.config.update(detected_config)
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            print(f"💾 Saved configuration to {self.config_file}")
        except Exception as e:
            print(f"Warning: Could not save config: {e}")


# Global instance
_config_manager = None

def get_config_manager() -> ServerConfigManager:
    """Get the global configuration manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ServerConfigManager()
    return _config_manager

def get_base_url() -> str:
    """Get the base URL for the server"""
    return get_config_manager().get_base_url()

def get_server_info() -> Dict[str, str]:
    """Get all server information"""
    manager = get_config_manager()
    return {
        "ip": manager.get_server_ip(),
        "port": manager.get_server_port(),
        "protocol": manager.get_server_protocol(),
        "base_url": manager.get_base_url()
    }
