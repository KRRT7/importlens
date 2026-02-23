from __future__ import annotations

import pytest

from importlens.parser import Import, flatten, parse

REALISTIC_SAMPLE = (
    "import time: self [us] | cumulative | imported package\n"
    "import time:       234 |        234 |   _io\n"
    "import time:       149 |        149 |   marshal\n"
    "import time:       579 |        579 |   posix\n"
    "import time:       832 |       1794 | _frozen_importlib_external\n"
    "import time:       214 |       2009 |   zipimport\n"
    "import time:       398 |       2407 | _frozen_importlib\n"
)


@pytest.fixture
def realistic_tree():
    return parse(REALISTIC_SAMPLE)


# --- parse: no results ---


@pytest.mark.parametrize(
    "text",
    [
        "",
        "\n\n\n",
        "some random text\nanother line\n",
    ],
    ids=["empty", "blank-lines", "no-import-lines"],
)
def test_parse_returns_empty(text):
    assert parse(text) == []


# --- parse: tree structure ---


def test_parse_single_top_level():
    text = "import time:       579 |        579 | posix"
    result = parse(text)
    assert len(result) == 1
    assert result[0].name == "posix"
    assert result[0].self_us == 579
    assert result[0].cumul_us == 579
    assert result[0].children == []


def test_parse_multiple_top_level():
    text = (
        "import time:       234 |        234 | _io\n"
        "import time:       149 |        149 | marshal\n"
        "import time:       579 |        579 | posix"
    )
    result = parse(text)
    assert len(result) == 3
    assert [i.name for i in result] == ["_io", "marshal", "posix"]


def test_parse_one_child():
    text = (
        "import time:       100 |        100 |   _heapq\n"
        "import time:       200 |        300 | heapq"
    )
    result = parse(text)
    assert len(result) == 1
    parent = result[0]
    assert parent.name == "heapq"
    assert parent.self_us == 200
    assert parent.cumul_us == 300
    assert len(parent.children) == 1
    assert parent.children[0].name == "_heapq"


def test_parse_multiple_children():
    text = (
        "import time:        50 |         50 |   child_a\n"
        "import time:        60 |         60 |   child_b\n"
        "import time:       200 |        310 | parent"
    )
    result = parse(text)
    assert len(result) == 1
    assert [c.name for c in result[0].children] == ["child_a", "child_b"]


def test_parse_deeply_nested():
    text = (
        "import time:        10 |         10 |       deep\n"
        "import time:        20 |         30 |     mid\n"
        "import time:        30 |         60 |   shallow\n"
        "import time:       100 |        160 | top"
    )
    result = parse(text)
    assert len(result) == 1
    top = result[0]
    assert top.name == "top"
    assert len(top.children) == 1
    shallow = top.children[0]
    assert shallow.name == "shallow"
    assert len(shallow.children) == 1
    mid = shallow.children[0]
    assert mid.name == "mid"
    assert len(mid.children) == 1
    assert mid.children[0].name == "deep"


def test_parse_sibling_subtrees():
    text = (
        "import time:        10 |         10 |   leaf_a\n"
        "import time:        20 |         30 | branch_a\n"
        "import time:        40 |         40 |   leaf_b\n"
        "import time:        50 |         90 | branch_b"
    )
    result = parse(text)
    assert len(result) == 2
    assert result[0].name == "branch_a"
    assert result[0].children[0].name == "leaf_a"
    assert result[1].name == "branch_b"
    assert result[1].children[0].name == "leaf_b"


def test_parse_dotted_module_names():
    text = (
        "import time:       718 |        718 |   encodings.aliases\n"
        "import time:      2067 |       3092 | encodings"
    )
    result = parse(text)
    assert len(result) == 1
    assert result[0].name == "encodings"
    assert result[0].children[0].name == "encodings.aliases"


# --- parse: line filtering ---


def test_parse_non_import_lines_ignored():
    text = (
        "Traceback (most recent call last):\n"
        "import time:       100 |        100 | os\n"
        "  File ...\n"
    )
    result = parse(text)
    assert len(result) == 1
    assert result[0].name == "os"


def test_parse_header_line_ignored():
    text = (
        "import time: self [us] | cumulative | imported package\n"
        "import time:       100 |        100 | os\n"
    )
    result = parse(text)
    assert len(result) == 1
    assert result[0].name == "os"


def test_parse_json_log_lines_ignored():
    text = (
        '{"@timestamp":"2026-02-21","level":"info","msg":"server started"}\n'
        "import time:       100 |        100 | os\n"
        '{"@timestamp":"2026-02-21","level":"info","msg":"ready"}\n'
    )
    result = parse(text)
    assert len(result) == 1
    assert result[0].name == "os"


# --- parse: negative values (CPython threading artifact) ---


def test_parse_negative_self_us():
    text = (
        "import time:   -197236 |     341007 |   html5lib._inputstream\n"
        "import time:       500 |     341507 | html5lib"
    )
    result = parse(text)
    assert len(result) == 1
    assert result[0].name == "html5lib"
    child = result[0].children[0]
    assert child.name == "html5lib._inputstream"
    assert child.self_us == -197236
    assert child.cumul_us == 341007


def test_parse_large_negative_self_us():
    text = "import time: -18670722 |      34380 | pikepdf._explicit_conv"
    result = parse(text)
    assert len(result) == 1
    assert result[0].self_us == -18670722
    assert result[0].cumul_us == 34380


# --- parse: realistic sample ---


def test_realistic_top_level_structure(realistic_tree):
    assert [i.name for i in realistic_tree] == [
        "_frozen_importlib_external",
        "_frozen_importlib",
    ]


def test_realistic_frozen_external_children(realistic_tree):
    ext = realistic_tree[0]
    assert ext.name == "_frozen_importlib_external"
    assert [c.name for c in ext.children] == ["_io", "marshal", "posix"]


def test_realistic_frozen_importlib_children(realistic_tree):
    lib = realistic_tree[1]
    assert lib.name == "_frozen_importlib"
    assert [c.name for c in lib.children] == ["zipimport"]


# --- flatten ---


def test_flatten_empty():
    assert flatten([]) == []


def test_flatten_single_node():
    node = Import(name="os", self_us=100, cumul_us=100)
    assert flatten([node]) == [("os", 100, 100, 0)]


def test_flatten_nested_depths():
    child = Import(name="_heapq", self_us=50, cumul_us=50)
    parent = Import(name="heapq", self_us=100, cumul_us=150, children=[child])
    result = flatten([parent])
    assert result == [
        ("heapq", 100, 150, 0),
        ("_heapq", 50, 50, 1),
    ]


def test_flatten_preorder_with_siblings():
    deep = Import(name="deep", self_us=10, cumul_us=10)
    mid = Import(name="mid", self_us=20, cumul_us=30, children=[deep])
    top = Import(name="top", self_us=30, cumul_us=60, children=[mid])
    sibling = Import(name="sibling", self_us=40, cumul_us=40)

    result = flatten([top, sibling])
    assert [r[0] for r in result] == ["top", "mid", "deep", "sibling"]
    assert [r[3] for r in result] == [0, 1, 2, 0]


def test_flatten_roundtrip_with_parse():
    text = (
        "import time:        10 |         10 |       deep\n"
        "import time:        20 |         30 |     mid\n"
        "import time:        30 |         60 |   shallow\n"
        "import time:       100 |        160 | top"
    )
    tree = parse(text)
    flat = flatten(tree)
    assert flat == [
        ("top", 100, 160, 0),
        ("shallow", 30, 60, 1),
        ("mid", 20, 30, 2),
        ("deep", 10, 10, 3),
    ]
