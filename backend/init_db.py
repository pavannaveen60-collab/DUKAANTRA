
def initialize_database():
    raise RuntimeError(
        "Direct create_all schema initialization is disabled. "
        "Use `alembic -c alembic.ini upgrade head` from the backend directory."
    )


if __name__ == "__main__":
    try:
        initialize_database()
    except RuntimeError as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    initialize_database()
