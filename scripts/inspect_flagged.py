import inspect
from routers.v2.admin.analytics.router import router

for route in router.routes:
    if hasattr(route, "path") and "flagged" in route.path:
        print(f"Route path: {route.path}")
        print(f"Route name: {route.name}")
        print(f"Endpoint source:")
        try:
            print(inspect.getsource(route.endpoint))
        except Exception as e:
            print(f"Could not get source: {e}")
