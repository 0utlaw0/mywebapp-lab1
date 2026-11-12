"""Production entrypoint: gunicorn with command-line configuration."""
from gunicorn.app.base import BaseApplication

from mywebapp import create_app, parse_args


class Server(BaseApplication):
    def __init__(self, app, options):
        self.app = app
        self.options = options
        super().__init__()

    def load_config(self):
        for key, value in self.options.items():
            self.cfg.set(key, value)

    def load(self):
        return self.app


if __name__ == "__main__":
    cfg = parse_args()
    Server(
        create_app(cfg),
        {"bind": f"{cfg.host}:{cfg.port}", "workers": 2},
    ).run()