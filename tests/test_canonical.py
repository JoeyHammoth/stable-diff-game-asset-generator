from __future__ import annotations

import hashlib

import pytest

from sdga.canonical import (
    canonical_json,
    fold32,
    hash_file,
    hash_obj,
    sha256_tagged,
)


def test_canonical_json_sorts_keys_and_drops_whitespace():
    assert canonical_json({"b": 1, "a": [2, 3]}) == '{"a":[2,3],"b":1}'


def test_canonical_json_is_insertion_order_independent():
    left = {"x": 1, "y": {"p": 2, "q": 3}}
    right = {"y": {"q": 3, "p": 2}, "x": 1}
    assert canonical_json(left) == canonical_json(right)
    assert hash_obj(left) == hash_obj(right)


def test_hash_obj_is_a_tagged_sha256():
    digest = hash_obj({"a": 1})
    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 64


def test_sha256_tagged_matches_hashlib():
    assert sha256_tagged(b"abc") == "sha256:" + hashlib.sha256(b"abc").hexdigest()


def test_hash_file_hashes_content_not_name(tmp_path):
    first = tmp_path / "a.bin"
    second = tmp_path / "b.bin"
    first.write_bytes(b"hello")
    second.write_bytes(b"hello")
    assert hash_file(first) == hash_file(second) == sha256_tagged(b"hello")


def test_fold32_is_stable_and_input_dependent():
    assert fold32("a") == fold32("a")
    assert fold32("a") != fold32("b")
    assert 0 <= fold32("anything") < 2**32


def test_canonical_rejects_nan():
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_canonical_serialises_paths_portably(tmp_path):
    assert canonical_json({"p": tmp_path / "x.png"}).endswith('.png"}}')
    assert "\\" not in canonical_json({"p": tmp_path / "x.png"})
