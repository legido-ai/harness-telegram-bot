import os
import tempfile
import uvicorn
from app.config import Settings
from app.health import HealthState, create_app
from app.store import Store

settings = Settings.from_env({
    "TELEGRAM_BOT_TOKEN": "1:x",
    "TELEGRAM_ALLOWED_USER_IDS": "1",
    "OPENCODE_SERVER_PASSWORD": "x",
    "DATA_DIR": tempfile.mkdtemp(),
})
store = Store(settings.db_path)
store.migrate()
state = HealthState(poller_alive=True)
state.note_update()
print("uid", os.getuid(), flush=True)
uvicorn.run(create_app(settings, store, state), host="127.0.0.1", port=8080, log_level="warning")
