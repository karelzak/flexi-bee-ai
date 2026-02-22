import streamlit.web.cli as stcli
import os, sys

def resolve_path(path):
    return os.path.abspath(os.path.join(os.getcwd(), path))

if __name__ == "__main__":
    # Point exclusively to the refactored version
    app_path = resolve_path("app_v2.py")
    
    if not os.path.exists(app_path):
        print(f"Error: {app_path} not found.")
        sys.exit(1)
        
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--global.developmentMode=false",
    ]
    sys.exit(stcli.main())
