import os
import yaml


class ConfigError(Exception):
    """Custom exception for configuration errors.
    
    Purpose:
    - Provides a clear, domain-specific error type for configuration issues.
    - Lets you distinguish config problems from other exceptions (e.g., network errors).
    - Keeps your error handling clean: you can catch ConfigError explicitly.
    """
    pass


class ConfigLoader:
    def __init__(self):
        self.mode = os.getenv("BOT_MODE")
        if not self.mode:
            raise ConfigError("BOT_MODE not set (paper / sandbox / live)")

        if self.mode not in {"paper", "sandbox", "live"}:
            raise ConfigError(f"Invalid BOT_MODE: {self.mode}")

    def load(self):
        config = {}

        def load_yaml(path):
            try:
                with open(path, "r") as f:
                    return yaml.safe_load(f)
            except FileNotFoundError:
                raise ConfigError(f"Config file not found: {path}")

        # Load base + mode-specific config
        config.update(load_yaml("config/base.yaml"))
        config.update(load_yaml(f"config/{self.mode}.yaml"))

        # Inject mode explicitly
        config["mode"] = self.mode

        # Merge environment overrides
        if self.mode == "live":
            config["api_key"] = os.getenv("API_KEY")
            config["api_secret"] = os.getenv("API_SECRET")
        elif self.mode == "sandbox":
            config["api_key"] = os.getenv("API_KEY_SANDBOX")
            config["api_secret"] = os.getenv("API_SECRET_SANDBOX")

        self._validate(config)
        return config

    def _validate(self, config):
        # Ensure required sections exist
        required_sections = ["app", "risk", "strategy", "runtime"]
        for section in required_sections:
            if section not in config:
                raise ConfigError(f"Missing required section: {section}")

        # HARD FAIL RULES
        if config["mode"] == "live":
            if os.getenv("CONFIRM_LIVE") != "YES":
                raise ConfigError("Live trading requires CONFIRM_LIVE=YES")

            if not config.get("api_key") or not config.get("api_secret"):
                raise ConfigError("Missing API credentials for live mode")

        if config["mode"] == "sandbox":
            if not config.get("api_key") or not config.get("api_secret"):
                raise ConfigError("Missing API credentials for sandbox mode")

        if config["mode"] == "paper":
            # Paper mode must not have any API keys set
            if os.getenv("API_KEY") or os.getenv("API_SECRET") or \
               os.getenv("API_KEY_SANDBOX") or os.getenv("API_SECRET_SANDBOX"):
                raise ConfigError("API keys set while in paper mode")
