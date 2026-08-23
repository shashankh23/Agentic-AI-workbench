import psutil
import socket

def get_network_snapshot() -> dict:
    """Returns current network IO counters and active connections for proof-of-sovereignty display."""
    io_counters = psutil.net_io_counters()
    
    connections = psutil.net_connections(kind='inet')
    external_connections = []
    local_connections = []
    
    for conn in connections:
        if conn.raddr:  # has a remote address
            remote_ip = conn.raddr.ip
            if remote_ip in ("127.0.0.1", "::1") or remote_ip.startswith("192.168.") or remote_ip.startswith("10."):
                local_connections.append(f"{remote_ip}:{conn.raddr.port}")
            else:
                external_connections.append(f"{remote_ip}:{conn.raddr.port}")
    
    return {
        "bytes_sent": io_counters.bytes_sent,
        "bytes_recv": io_counters.bytes_recv,
        "external_connections": external_connections,
        "local_connections": local_connections,
        "external_count": len(external_connections)
    }
