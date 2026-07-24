#!/usr/bin/env python
import os
import sys


def main():
    default_settings = (
        "config.settings.test"
        if len(sys.argv) > 1 and sys.argv[1] == "test"
        else "config.settings.dev"
    )
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", default_settings)
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
