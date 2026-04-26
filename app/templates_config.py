import json

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["from_json"] = lambda s: json.loads(s) if s else {}
