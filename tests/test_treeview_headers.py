from assistant_botanique.features.treeview_headers import (
    COLLECTION_COLUMNS,
    TODAY_COLUMNS,
    configure_collection_columns,
    configure_today_columns,
)


class FakeTree:
    def __init__(self, columns=()):
        self.columns = tuple(columns)
        self.headings = {}
        self.column_options = {}

    def __getitem__(self, key):
        if key != "columns":
            raise KeyError(key)
        return self.columns

    def configure(self, **kwargs):
        if "columns" in kwargs:
            self.columns = tuple(kwargs["columns"])

    def heading(self, key, **kwargs):
        self.headings[key] = kwargs

    def column(self, key, **kwargs):
        self.column_options[key] = kwargs


def test_today_headers_are_all_restored_after_columns_change():
    tree = FakeTree(("date", "plant", "care", "status", "details"))

    configure_today_columns(tree)

    assert tree.columns == tuple(spec.key for spec in TODAY_COLUMNS)
    assert tree.columns[:4] == ("date", "plant", "scientific", "care")
    assert {key: value["text"] for key, value in tree.headings.items()} == {
        spec.key: spec.label for spec in TODAY_COLUMNS
    }
    assert tree.headings["scientific"]["text"] == "Nom scientifique"
    assert all(tree.headings[spec.key]["text"] for spec in TODAY_COLUMNS)


def test_collection_headers_and_sort_commands_are_all_restored():
    calls = []
    tree = FakeTree(("nickname", "scientific", "family", "pot", "last", "next", "status"))

    configure_collection_columns(tree, lambda column, reverse: calls.append((column, reverse)))

    assert tree.columns == tuple(spec.key for spec in COLLECTION_COLUMNS)
    assert {key: value["text"] for key, value in tree.headings.items()} == {
        spec.key: spec.label for spec in COLLECTION_COLUMNS
    }
    tree.headings["scientific"]["command"]()
    assert calls == [("scientific", False)]
