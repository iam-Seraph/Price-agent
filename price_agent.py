"""Compatible CLI and import alias for the implementation in src/price_agent.py."""
import importlib
import sys

if __name__ == "__main__":
    from src.price_agent import main
    main()
else:
    sys.modules[__name__] = importlib.import_module("src.price_agent")
