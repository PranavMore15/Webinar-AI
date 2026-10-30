import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', '1') == '1'
    print(f"\n=======================================================")
    print(f" WebinarAI Development Server Starting")
    print(f" Mode: Stage 1 (Foundation & Responsive Dashboard)")
    print(f" Access URL: http://127.0.0.1:{port}")
    print(f"=======================================================\n")
    app.run(host='127.0.0.1', port=port, debug=debug)
