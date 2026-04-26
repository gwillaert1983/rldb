import json
import pytz
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["from_json"] = lambda s: json.loads(s) if s else {}


def _to_local(dt, fmt="%d/%m/%Y %H:%M"):
    if dt is None:
        return "—"
    tz = pytz.timezone("Europe/Brussels")
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(tz).strftime(fmt)


templates.env.filters["to_local"] = _to_local
