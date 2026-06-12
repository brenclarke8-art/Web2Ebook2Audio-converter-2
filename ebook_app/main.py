"""Legacy launcher compatibility shim.

Supports older commands like ``python -m ebook_app.main`` by forwarding
to the current application entrypoint in ``ebook_app.app.main``.
"""

from ebook_app.app.main import main


if __name__ == "__main__":
    main()
