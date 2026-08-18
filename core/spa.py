from pathlib import Path
from django.conf import settings
from django.http import FileResponse, Http404
DIST=Path(settings.BASE_DIR)/'frontend'/'dist'
def react_app(request,asset='index.html'):
    target=(DIST/asset).resolve()
    try: target.relative_to(DIST.resolve())
    except ValueError: raise Http404
    if not target.exists() or not target.is_file(): target=DIST/'index.html'
    if not target.exists(): raise Http404('React frontend has not been built yet. Run: cd frontend && npm install && npm run build')
    return FileResponse(open(target,'rb'))
