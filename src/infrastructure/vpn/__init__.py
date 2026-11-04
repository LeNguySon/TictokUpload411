"""
VPN Infrastructure Package for isolated per-profile WireGuard tunneling.
"""

from src.infrastructure.vpn.vpn_bridge import UserspaceVpnBridge
from src.infrastructure.vpn.wireguard_manager import WireGuardConfig, WireGuardManager

__all__ = ["WireGuardConfig", "WireGuardManager", "UserspaceVpnBridge"]
