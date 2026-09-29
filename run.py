import os
import sys
import site
import uvicorn

# Ensure user site packages directory is included
user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.insert(0, user_site)


# Ensure current directory is in sys.path
project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

if __name__ == "__main__":
    from backend.config import settings
    print(f"================================================================")
    print(f"  AI AUDITOR ASSISTANT COPILOT - SERVER STARTING")
    print(f"  Access Dashboard at: http://{settings.HOST}:{settings.PORT}")
    print(f"  API Docs at:         http://{settings.HOST}:{settings.PORT}/docs")
    print(f"================================================================")

    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )

