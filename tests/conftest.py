def pytest_collection_modifyitems(items):
    # Tk and Qt do not share a process well on macOS: importing PySide6 while the Tk tests run
    # can crash them. So the Qt tests run last, and test_qt_app.py imports PySide6 only then.
    # Remove this once the Tkinter UI is gone.
    items.sort(key=lambda item: item.path.name == "test_qt_app.py")
