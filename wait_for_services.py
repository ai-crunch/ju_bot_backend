#!/usr/bin/env python3
"""Wait for services to be ready before starting the application."""
import sys
import time
import socket
import urllib.request
import urllib.error

def wait_for_service(host: str, port: int, timeout: int = 60, check_http: bool = False) -> bool:
    """Wait for a service to be available on host:port."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # Check if port is open
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                # If HTTP check is requested, verify the service responds
                if check_http:
                    try:
                        url = f"http://{host}:{port}/healthz"
                        urllib.request.urlopen(url, timeout=2)
                        print(f"✓ {host}:{port} is ready and healthy")
                        return True
                    except (urllib.error.URLError, Exception):
                        # Port is open but service not ready yet
                        pass
                else:
                    print(f"✓ {host}:{port} is ready")
                    return True
        except Exception as e:
            pass
        print(f"Waiting for {host}:{port} to be ready...")
        time.sleep(1)
    print(f"✗ {host}:{port} did not become ready within {timeout} seconds")
    return False

if __name__ == "__main__":
    # Wait for Qdrant
    qdrant_host = sys.argv[1] if len(sys.argv) > 1 else "qdrant"
    qdrant_port = int(sys.argv[2]) if len(sys.argv) > 2 else 6333
    
    # Wait for MongoDB
    mongo_host = sys.argv[3] if len(sys.argv) > 3 else "mongodb"
    mongo_port = int(sys.argv[4]) if len(sys.argv) > 4 else 27017
    
    print("Waiting for services to be ready...")
    
    # Wait for Qdrant and check HTTP health endpoint
    if not wait_for_service(qdrant_host, qdrant_port, check_http=True):
        sys.exit(1)
    
    # Wait for MongoDB (just port check)
    if not wait_for_service(mongo_host, mongo_port):
        sys.exit(1)
    
    # Give services a moment to fully initialize
    print("Services are ready. Waiting 5 seconds for full initialization...")
    time.sleep(5)
    
    print("All services are ready!")
    sys.exit(0)
