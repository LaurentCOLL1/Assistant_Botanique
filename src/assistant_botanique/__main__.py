"""Points d'entrée GUI et notifications de fond."""
from __future__ import annotations

import argparse

from app_data import DATABASE_BY_ID
from storage import CollectionRepository

from assistant_botanique.services.notifications import NotificationService


def main() -> None:
    parser = argparse.ArgumentParser(prog="assistant-botanique")
    parser.add_argument("--notify", action="store_true", help="Afficher les contrôles de plantes arrivés à échéance")
    parser.add_argument("--install-notifications", metavar="HH:MM", help="Installer la tâche planifiée Windows")
    args = parser.parse_args()
    if args.notify:
        NotificationService().notify_due(CollectionRepository().database, DATABASE_BY_ID)
        return
    if args.install_notifications:
        NotificationService().install_windows_task(args.install_notifications)
        return
    from assistant_botanique.ui.app import run_gui

    run_gui()


if __name__ == "__main__":
    main()
