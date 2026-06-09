from fastapi import FastAPI
from routers.v2.admin.analytics import router

for i, route in enumerate(router.routes):
    if hasattr(route, "path"):
        print(f"{i}: {route.path} - {route.name}")
