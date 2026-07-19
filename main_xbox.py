"""Standalone Xbox test build entry point."""

import main as steam_main

from flow_race_xbox import logic_race_xbox


def run():
    # Patch only this process.  main.py and the Steam executable remain intact.
    steam_main.flow_logic_race = logic_race_xbox
    app = steam_main.FH_UltimateBot()
    try:
        app.title("FH6 AUTO v4.2.1 - Xbox")
    except Exception:
        pass
    app.log("[Xbox测试版] 已启用 Xbox 系统共享代码输入兼容层。")
    app.mainloop()


if __name__ == "__main__":
    run()
